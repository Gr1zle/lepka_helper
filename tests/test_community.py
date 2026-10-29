"""Публикации: отдельные временные базы, фотографии и реальный HTTP-маршрут."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import flet as ft
from fastapi.testclient import TestClient
from PIL import Image

import auth_service
from account_security import logoutUser
import database as db
import post_service as posts
from photo_service import MAX_PHOTO_BYTES, preparePhoto
from photo_upload import createPhotoUpload, takePhotoUpload, cancelPhotoUpload
from web_app import createWebApp
from test_startup import MemoryConnection, find, walk
from ui_helpers import logoutPage


def imageBytes(format='PNG', size=(40, 30)):
    buffer = BytesIO()
    with Image.new('RGB', size, '#FF6B6B') as image:
        image.save(buffer, format=format)
    return buffer.getvalue()


def photo():
    return {'name': 'Котик.png', 'data': imageBytes()}


class CommunityTests(unittest.TestCase):
    def setUp(self):
        modePatch = patch('account_gateway.getApiUrl', return_value='')
        modePatch.start()
        self.addCleanup(modePatch.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.pathPatch = patch.object(db, 'DATABASE_PATH', Path(self.temp.name) / 'test.db')
        self.pathPatch.start()
        self.addCleanup(self.pathPatch.stop)
        db.initializeDatabase()
        auth_service.ensureDemoUser()
        self.user = auth_service.loginUser('test@email.com', 'Test123456')[2]
        self.owner = self.user['userId']
        self.other = db.createUser('other@example.com', '', '', 'Другой')

    def publish(self, **changes):
        args = dict(userId=self.owner, titleText='Мой котик', descriptionText='Котик из пластилина',
                    categoryName='Животные', tagsText='котик, лепка', photoFiles=[photo()])
        args.update(changes)
        return posts.savePost(**args)

    def test_create_read_photos_and_owner_gallery(self):
        success, _, postId = self.publish(photoFiles=[photo()] * 10)
        self.assertTrue(success)
        item = posts.getCommunityPosts()[0]
        self.assertEqual(item['postId'], postId)
        self.assertEqual(len(item['photoIds']), 10)
        self.assertEqual(posts.getUserPosts(self.owner)[0]['nickname'], self.user['nickname'])
        self.assertEqual(posts.getUserPosts(self.other), [])
        with Image.open(BytesIO(db.getPostPhoto(item['photoIds'][0]))) as image:
            self.assertEqual(image.format, 'JPEG')
            self.assertEqual(image.size, (40, 30))
        db.initializeDatabase()
        self.assertEqual(len(posts.getCommunityPosts()[0]['photoIds']), 10)

    def test_photos_required_and_counts_limited(self):
        for photos in (None, [], [photo()] * 11, [None], [{'name': 'bad.png', 'data': b'bad'}]):
            with self.subTest(count=len(photos) if photos is not None else None):
                self.assertFalse(self.publish(photoFiles=photos)[0])
        self.assertEqual(posts.getCommunityPosts(), [])

    def test_category_tags_and_text_validation_do_not_truncate(self):
        cases = [dict(categoryName='Своя категория'), dict(tagsText='x'), dict(tagsText='a' * 31),
                 dict(tagsText=', '.join(f'тег{i}' for i in range(11))), dict(titleText='ab'),
                 dict(titleText='a' * 101), dict(descriptionText='short'), dict(descriptionText='a' * 2001)]
        for change in cases:
            with self.subTest(change=change):
                self.assertFalse(self.publish(**change)[0])
        self.assertEqual(posts.getCommunityPosts(), [])
        self.assertTrue(self.publish(tagsText='')[0])

    def test_blocked_and_unknown_user_cannot_publish(self):
        with db.openDatabase() as connection:
            connection.execute('UPDATE users SET isBlocked = 1 WHERE userId = ?', (self.owner,))
        self.assertFalse(self.publish()[0])
        self.assertFalse(self.publish(userId=999999)[0])

    def test_failure_saving_second_photo_rolls_back_whole_post(self):
        with db.openDatabase() as connection:
            connection.execute("""CREATE TRIGGER failPhoto BEFORE INSERT ON postPhotos WHEN NEW.position = 1
                BEGIN SELECT RAISE(ABORT, 'test failure'); END""")
        import sqlite3
        with self.assertRaises(sqlite3.IntegrityError):
            self.publish(photoFiles=[photo(), photo()])
        with db.openDatabase() as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM posts').fetchone()[0], 0)
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM postPhotos').fetchone()[0], 0)

    def test_delete_checks_owner_and_removes_photos_likes_comments(self):
        postId = self.publish()[2]
        photoId = posts.getCommunityPosts()[0]['photoIds'][0]
        posts.togglePostLike(postId, self.other)
        posts.savePostComment(postId, self.other, 'Красивый котик')
        self.assertFalse(posts.removePost(postId, self.other))
        self.assertIsNotNone(db.getPostPhoto(photoId))
        self.assertTrue(posts.removePost(postId, self.owner))
        self.assertIsNone(db.getPostPhoto(photoId))
        self.assertEqual(posts.getPostComments(postId), [])
        self.assertEqual(posts.togglePostLike(postId, self.other), (False, None))
        with db.openDatabase() as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM postLikes').fetchone()[0], 0)

    def test_account_deletion_erases_photos_but_preserves_others_comments(self):
        postId = self.publish()[2]
        photoId = posts.getCommunityPosts()[0]['photoIds'][0]
        posts.savePostComment(postId, self.other, 'Чужой комментарий')
        self.assertTrue(auth_service.deleteUserAccount(self.owner, 'Test123456')[0])
        self.assertIsNone(db.getPostPhoto(photoId))
        self.assertEqual(len(posts.getPostComments(postId)), 1)
        self.assertTrue(posts.getCommunityPosts()[0]['isDeleted'])
        self.assertFalse(posts.savePostComment(postId, self.other, 'Новый комментарий')[0])

    def test_legacy_text_post_survives_initialization(self):
        postId = db.createPost(self.owner, 'Старая работа', 'Описание старой работы', 'Животные', '')
        db.initializeDatabase()
        self.assertEqual(posts.getCommunityPosts()[0]['postId'], postId)
        self.assertEqual(posts.getCommunityPosts()[0]['photoIds'], [])

    def test_likes_toggle_and_remain_consistent_under_concurrency(self):
        postId = self.publish()[2]
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda _: posts.togglePostLike(postId, self.other), range(10)))
        self.assertEqual(posts.getCommunityPosts()[0]['likesCount'], 0)
        self.assertEqual(posts.togglePostLike(postId, self.other), (True, 1))
        self.assertEqual(posts.togglePostLike(postId, self.owner), (True, 2))
        self.assertEqual(posts.togglePostLike(postId, self.other), (False, 1))
        with db.openDatabase() as connection:
            connection.execute('UPDATE users SET isBlocked = 1 WHERE userId = ?', (self.other,))
        self.assertEqual(posts.togglePostLike(postId, self.other), (False, None))

    def test_comment_validation_rate_limit_and_deletion_do_not_bypass_limit(self):
        postId = self.publish()[2]
        for value in ('abc', '     ', '😀😀😀😀😀', '!!!!!', 'a' * 1001, None):
            self.assertFalse(posts.savePostComment(postId, self.other, value)[0])
        ids = [posts.savePostComment(postId, self.other, 'Красивый котик')[2] for _ in range(5)]
        self.assertTrue(all(ids))
        self.assertFalse(posts.savePostComment(postId, self.other, 'Шестой комментарий')[0])
        self.assertTrue(posts.removePostComment(ids[0], self.other))
        self.assertFalse(posts.savePostComment(postId, self.other, 'Обход через удаление')[0])
        self.assertTrue(posts.savePostComment(postId, self.owner, 'Другой пользователь')[0])
        with db.openDatabase() as connection:
            connection.execute("UPDATE commentEvents SET createdAt = datetime('now', '-61 seconds')")
        self.assertTrue(posts.savePostComment(postId, self.other, 'После минутного окна')[0])

    def test_comment_editing_and_deletion_require_owner_and_time_window(self):
        postId = self.publish()[2]
        commentId = posts.savePostComment(postId, self.other, 'Первый комментарий')[2]
        self.assertFalse(posts.editPostComment(commentId, self.owner, 'Подмена автора')[0])
        self.assertFalse(posts.removePostComment(commentId, self.owner))
        self.assertTrue(posts.editPostComment(commentId, self.other, 'Исправленный комментарий')[0])
        with db.openDatabase() as connection:
            connection.execute("UPDATE postComments SET createdAt = datetime('now', '-31 minutes')")
        self.assertFalse(posts.editPostComment(commentId, self.other, 'Слишком поздно')[0])
        self.assertEqual(posts.getPostComments(postId)[0]['commentText'], 'Исправленный комментарий')
        self.assertTrue(posts.removePostComment(commentId, self.other))

    def test_upload_http_is_one_use_validates_photo_and_owner(self):
        ticket = createPhotoUpload(self.user, 'Котик.png')
        with TestClient(createWebApp()) as client:
            self.assertEqual(client.put('/photo-uploads/' + ticket, content=imageBytes()).status_code, 200)
            self.assertEqual(client.put('/photo-uploads/' + ticket, content=imageBytes()).status_code, 404)
        with self.assertRaises(ValueError):
            takePhotoUpload(ticket, self.other)
        result = takePhotoUpload(ticket, self.owner)
        self.assertEqual(result['name'], 'Котик.jpg')
        with self.assertRaises(ValueError):
            takePhotoUpload(ticket, self.owner)

    def test_bad_expired_cancelled_and_stale_session_uploads(self):
        with TestClient(createWebApp()) as client:
            ticket = createPhotoUpload(self.user, 'bad.png')
            self.assertEqual(client.put('/photo-uploads/' + ticket, content=b'not an image').status_code, 400)
            ticket = createPhotoUpload(self.user, 'large.png')
            self.assertEqual(client.put('/photo-uploads/' + ticket, content=b'x' * (MAX_PHOTO_BYTES + 1)).status_code, 413)
            ticket = createPhotoUpload(self.user, 'old.png')
            with patch('photo_upload.time.monotonic', return_value=float('inf')):
                self.assertEqual(client.put('/photo-uploads/' + ticket, content=imageBytes()).status_code, 404)
            ticket = createPhotoUpload(self.user, 'cancel.png')
            cancelPhotoUpload(ticket, self.owner)
            self.assertEqual(client.put('/photo-uploads/' + ticket, content=imageBytes()).status_code, 404)
            ticket = createPhotoUpload(self.user, 'logout.png')
            logoutUser(self.user['sessionToken'])
            self.assertEqual(client.put('/photo-uploads/' + ticket, content=imageBytes()).status_code, 401)

    def test_public_photo_http_hides_deleted_images(self):
        postId = self.publish()[2]
        photoId = posts.getCommunityPosts()[0]['photoIds'][0]
        with TestClient(createWebApp()) as client:
            response = client.get(f'/post-photos/{photoId}')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers['content-type'], 'image/jpeg')
            self.assertEqual(response.headers['cache-control'], 'no-store')
            self.assertEqual(client.get('/post-photos/999999').status_code, 404)
            posts.removePost(postId, self.owner)
            self.assertEqual(client.get(f'/post-photos/{photoId}').status_code, 404)


class PhotoTests(unittest.TestCase):
    def test_formats_rotation_resize_and_metadata_removal(self):
        for format, extension in [('PNG', 'png'), ('JPEG', 'jpg'), ('WEBP', 'webp')]:
            result = preparePhoto('Фото.' + extension, imageBytes(format, (2000, 1000)))
            with Image.open(BytesIO(result['data'])) as image:
                self.assertEqual(image.size, (1600, 800))
                self.assertEqual(image.getexif(), {})
        buffer = BytesIO()
        with Image.new('RGB', (40, 30)) as image:
            exif = Image.Exif()
            exif[274] = 6
            exif[315] = 'Private name'
            image.save(buffer, 'JPEG', exif=exif)
        with Image.open(BytesIO(preparePhoto('rotated.jpg', buffer.getvalue())['data'])) as image:
            self.assertEqual(image.size, (30, 40))
            self.assertFalse(image.getexif())

    def test_invalid_formats_sizes_and_truncated_images(self):
        for name, content in [('bad.gif', imageBytes('GIF')), ('fake.jpg', imageBytes()),
                              ('bad.png', b'bad'), ('empty.png', b''),
                              ('large.png', b'x' * (MAX_PHOTO_BYTES + 1)),
                              ('cut.png', imageBytes()[:30])]:
            with self.subTest(name=name), self.assertRaises(ValueError):
                preparePhoto(name, content)
        with self.assertRaises(ValueError):
            preparePhoto('large.png', imageBytes(size=(5000, 4001)))


class CommunityUiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        for target in ('account_gateway.getApiUrl', 'views.profile_tab.getApiUrl'):
            modePatch = patch(target, return_value='')
            modePatch.start()
            self.addCleanup(modePatch.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        patcher = patch.object(db, 'DATABASE_PATH', Path(self.temp.name) / 'ui.db')
        patcher.start()
        self.addCleanup(patcher.stop)
        db.initializeDatabase()
        auth_service.ensureDemoUser()
        self.user = auth_service.loginUser('test@email.com', 'Test123456')[2]
        self.page = ft.Page(MemoryConnection(), 'community', loop=asyncio.get_running_loop())
        self.page.session.set('currentUser', self.user)
        self.page.go = lambda route: setattr(self.page, 'route', route)
        self.page.theme_mode = ft.ThemeMode.LIGHT

    def mount(self, factory=None):
        from views.community_tab import createHomeTab
        content = factory() if factory else createHomeTab(self.page, self.user, self.user['nickname'])
        view = ft.View('/test', controls=[content])
        self.page.views[:] = [view]
        self.page.update()
        return view

    def fillForm(self, view):
        find(view, ft.TextField, label='Название работы').value = 'Мой котик'
        find(view, ft.TextField, label='Описание').value = 'Котик из пластилина'

    def pickNative(self, view):
        path = Path(self.temp.name) / 'Котик.png'
        path.write_bytes(imageBytes())
        find(view, ft.OutlinedButton, text='Добавить фото').on_click(None)
        picker = next(c for c in self.page.overlay if isinstance(c, ft.FilePicker))
        picker.on_result(SimpleNamespace(files=[SimpleNamespace(name=path.name, path=str(path), size=path.stat().st_size, id=1)]))
        return picker

    async def test_native_selection_publish_preview_and_delete_confirmation(self):
        view = self.mount()
        self.fillForm(view)
        find(view, ft.ElevatedButton, text='Опубликовать').on_click(None)
        self.assertEqual(posts.getCommunityPosts(), [])
        self.pickNative(view)
        find(view, ft.ElevatedButton, text='Опубликовать').on_click(None)
        self.assertEqual(len(posts.getCommunityPosts()), 1)
        self.assertTrue(any(isinstance(c, ft.Image) and c.src_base64 for c in walk(view)))
        find(view, ft.TextButton, text='Удалить').on_click(None)
        self.assertEqual(len(posts.getCommunityPosts()), 1)
        dialog = next(c for c in self.page.overlay if isinstance(c, ft.AlertDialog) and c.open)
        find(dialog, ft.ElevatedButton, text='Удалить работу').on_click(None)
        self.assertEqual(posts.getCommunityPosts(), [])

    async def test_browser_picker_upload_route_and_pending_publish(self):
        # Даже если браузер подменил свой флаг isWeb, пути сервера читать нельзя.
        self.page._set_attr('web', 'false')
        self.page.data = {'isWebServer': True}
        view = self.mount()
        self.fillForm(view)
        find(view, ft.OutlinedButton, text='Добавить фото').on_click(None)
        picker = next(c for c in self.page.overlay if isinstance(c, ft.FilePicker))
        with patch.object(picker, 'upload') as upload:
            picker.on_result(SimpleNamespace(files=[SimpleNamespace(name='cat.png', size=len(imageBytes()), id=5)]))
            target = upload.call_args.args[0][0]
        self.assertEqual(target.id, 5)
        publish = find(view, ft.ElevatedButton, text='Опубликовать')
        self.assertTrue(publish.disabled)
        publish.on_click(None)
        self.assertEqual(posts.getCommunityPosts(), [])
        with TestClient(createWebApp()) as client:
            self.assertEqual(client.put(target.upload_url, content=imageBytes()).status_code, 200)
        picker.on_upload(SimpleNamespace(file_name='cat.png', progress=1, error=None))
        self.assertFalse(publish.disabled)
        publish.on_click(None)
        self.assertEqual(len(posts.getCommunityPosts()[0]['photoIds']), 1)
        self.assertTrue(any(isinstance(c, ft.Image) and '/post-photos/' in (c.src or '') for c in walk(view)))

    async def test_stale_publish_and_comment_handlers_cannot_mutate_after_logout(self):
        view = self.mount()
        self.fillForm(view)
        self.pickNative(view)
        publish = find(view, ft.ElevatedButton, text='Опубликовать')
        publish.on_click(None)
        postId = posts.getCommunityPosts()[0]['postId']
        find(view, ft.TextField, label='Комментарий').value = 'После выхода'
        comment = find(view, ft.ElevatedButton, text='Отправить комментарий')
        self.fillForm(view)
        self.pickNative(view)
        logoutPage(self.page)
        publish.on_click(None)
        comment.on_click(None)
        self.assertEqual(len(posts.getCommunityPosts()), 1)
        self.assertEqual(posts.getPostComments(postId), [])

    async def test_profile_gallery_and_other_authors_actions(self):
        from views.profile_tab import createProfileTab
        from views.community_tab import createPostCard
        postId = posts.savePost(self.user['userId'], 'Котик', 'Описание котика', 'Животные', '', [photo()])[2]
        profile = self.mount(lambda: createProfileTab(self.page, self.user['nickname'], self.user['email']))
        find(profile, ft.OutlinedButton, text='Мои работы').on_click(None)
        dialog = next(c for c in self.page.overlay if isinstance(c, ft.AlertDialog) and c.open)
        self.assertTrue(any(isinstance(c, ft.Text) and c.value == 'Котик' for c in walk(dialog)))
        stat = next(c for c in walk(profile) if isinstance(c, ft.Column) and len(c.controls) == 2
                    and isinstance(c.controls[-1], ft.Text) and c.controls[-1].value == 'Работ')
        self.assertEqual(stat.controls[0].value, '1')
        find(dialog, ft.TextButton, text='Удалить').on_click(None)
        confirmation = next(c for c in self.page.overlay if isinstance(c, ft.AlertDialog) and c.open
                            and c.title.value == 'Удалить публикацию?')
        find(confirmation, ft.ElevatedButton, text='Удалить работу').on_click(None)
        self.assertEqual(stat.controls[0].value, '0')
        posts.savePost(self.user['userId'], 'Котик', 'Описание котика', 'Животные', '', [photo()])
        other = dict(self.user, userId=999999)
        view = self.mount(lambda: createPostCard(self.page, posts.getCommunityPosts()[0], other, lambda: None))
        self.assertFalse(any(isinstance(c, ft.TextButton) and c.text == 'Удалить' for c in walk(view)))
        guest = self.mount(lambda: createPostCard(self.page, posts.getCommunityPosts()[0], None, lambda: None))
        self.assertFalse(any(isinstance(c, ft.TextField) for c in walk(guest)))
        self.assertTrue(db.getPostPhoto(posts.getCommunityPosts()[0]['photoIds'][0]))

    async def test_comment_ui_add_edit_delete(self):
        view = self.mount()
        self.fillForm(view)
        self.pickNative(view)
        find(view, ft.ElevatedButton, text='Опубликовать').on_click(None)
        find(view, ft.TextField, label='Комментарий').value = 'Мой комментарий'
        find(view, ft.ElevatedButton, text='Отправить комментарий').on_click(None)
        find(view, ft.IconButton, tooltip='Изменить комментарий (до 30 минут)').on_click(None)
        dialog = next(c for c in self.page.overlay if isinstance(c, ft.AlertDialog) and c.open)
        find(dialog, ft.TextField, label='Текст комментария').value = 'Изменённый комментарий'
        find(dialog, ft.ElevatedButton, text='Сохранить комментарий').on_click(None)
        postId = posts.getCommunityPosts()[0]['postId']
        self.assertEqual(posts.getPostComments(postId)[0]['commentText'], 'Изменённый комментарий')
        find(view, ft.IconButton, tooltip='Удалить свой комментарий').on_click(None)
        self.assertEqual(posts.getPostComments(postId), [])
