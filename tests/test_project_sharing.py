"""Публикация проекта и обмен рецептами: только временные базы и тестовые фото."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import flet as ft

import account_security
import color_service as colors
import database as db
import post_service as posts
import project_service as projects
import project_sharing as sharing
from image_fixtures import photo
from test_startup import MemoryConnection, find, walk
from ui_helpers import logoutPage


class SharingFixture:
    def setUp(self):
        mode = patch('account_gateway.getApiUrl', return_value='')
        mode.start()
        self.addCleanup(mode.stop)
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        path = patch.object(db, 'DATABASE_PATH', Path(self.folder.name) / 'sharing.db')
        path.start()
        self.addCleanup(path.stop)
        db.initializeDatabase()
        self.owner = db.createUser('owner@example.com', '', '', 'Автор')
        self.other = db.createUser('reader@example.com', '', '', 'Читатель')
        self.project = projects.saveProject(self.owner, 'Наш котик', 'Животные', '01.01.2020', 'Личные заметки SECRET')[2]
        self.step = self.addStep(self.project, self.owner, 'Слепить основу')
        self.result = self.addStep(self.project, self.owner, 'Готовый котик')
        selected = [{**item, 'proportion': 50} for item in colors.BASE_COLORS[:2]]
        self.recipe = colors.calculateRecipe(selected, 100)
        self.mixture = colors.saveColorMixture(self.owner, 'Серый котик', '#808080', 100, self.recipe)
        self.assertTrue(sharing.addProjectMixture(self.project, self.owner, self.mixture)[0])
        self.attached = sharing.getProjectMixtures(self.project, self.owner)[0]['projectMixtureId']

    def addStep(self, projectId, userId, description):
        stepId = projects.saveProjectStep(projectId, description, userId)[2]
        self.assertTrue(projects.saveProjectStepPhoto(projectId, stepId, userId, photo())[0])
        return stepId

    def publish(self, **changes):
        args = dict(projectId=self.project, userId=self.owner, titleText='Наш котик',
                    descriptionText='Котик по собственному рецепту', categoryName='Животные', tagsText='котик, лепка',
                    resultStepId=self.result, otherStepIds=[self.step], projectMixtureIds=[self.attached])
        args.update(changes)
        return sharing.publishProject(**args)


class SharingTests(SharingFixture, unittest.TestCase):
    def test_project_mixture_is_private_copy_and_survives_palette_deletion_and_restart(self):
        self.assertEqual(sharing.getProjectMixtures(self.project, self.other), [])
        self.assertFalse(sharing.addProjectMixture(self.project, self.other, self.mixture)[0])
        otherProject = projects.saveProject(self.other, 'Чужой котик', 'Животные', '', '')[2]
        self.assertFalse(sharing.addProjectMixture(otherProject, self.other, self.mixture)[0])
        self.assertFalse(sharing.removeProjectMixture(self.project, self.other, self.attached))
        self.assertFalse(sharing.removeProjectMixture(otherProject, self.owner, self.attached))
        self.assertTrue(colors.deleteColorMixture(self.owner, self.mixture))
        db.initializeDatabase()
        mixture = sharing.getProjectMixtures(self.project, self.owner)[0]
        self.assertEqual(mixture['recipeItems'], self.recipe)
        self.assertTrue(sharing.removeProjectMixture(self.project, self.owner, self.attached))
        self.assertEqual(sharing.getProjectMixtures(self.project, self.owner), [])

    def test_duplicate_corrupt_and_missing_mixtures_are_not_attached(self):
        self.assertFalse(sharing.addProjectMixture(self.project, self.owner, self.mixture)[0])
        bad = db.createColorMixture(self.owner, 'Сломанный рецепт', '#808080', 100, '{bad')
        for projectId, mixtureId in ((self.project, bad), (99999, self.mixture), (self.project, 99999)):
            self.assertFalse(sharing.addProjectMixture(projectId, self.owner, mixtureId)[0])
        self.assertEqual(len(sharing.getProjectMixtures(self.project, self.owner)), 1)

    def test_ten_mixtures_limit_and_failed_project_delete_preserve_attached_recipes(self):
        for index in range(9):
            mixtureId = colors.saveColorMixture(self.owner, f'Серый рецепт {index}', '#808080', 100, self.recipe)
            self.assertTrue(sharing.addProjectMixture(self.project, self.owner, mixtureId)[0])
        extra = colors.saveColorMixture(self.owner, 'Лишний серый', '#808080', 100, self.recipe)
        self.assertFalse(sharing.addProjectMixture(self.project, self.owner, extra)[0])
        before = sharing.getProjectMixtures(self.project, self.owner)
        with db.openDatabase() as connection:
            connection.execute("""CREATE TRIGGER reject_project BEFORE DELETE ON projects
                BEGIN SELECT RAISE(ABORT, 'test failure'); END""")
        with self.assertRaises(sqlite3.IntegrityError):
            projects.removeProject(self.project, self.owner)
        self.assertEqual(sharing.getProjectMixtures(self.project, self.owner), before)

    def test_broken_snapshot_is_not_exposed_or_copied_and_source_is_preserved(self):
        postId = self.publish()[2]
        for broken in ('{bad', '[]', '{}', '{"steps": null, "mixtures": []}',
                       '{"steps": [{"description": "Этап", "photoPosition": true}], "mixtures": []}'):
            with db.openDatabase() as connection:
                connection.execute('UPDATE posts SET projectDetailsJson = ? WHERE postId = ?', (broken, postId))
            self.assertIsNone(sharing.getPublishedProject(postId))
            self.assertFalse(sharing.copyPublishedMixture(postId, 0, self.other)[0])
            with db.openDatabase() as connection:
                self.assertEqual(connection.execute('SELECT projectDetailsJson FROM posts WHERE postId = ?', (postId,)).fetchone()[0], broken)
        self.assertEqual(colors.getUserColorMixtures(self.other), [])

    def test_publication_contains_only_selected_materials_and_result_is_first(self):
        privateStep = self.addStep(self.project, self.owner, 'Секретный этап')
        success, message, postId = self.publish(otherStepIds=[])
        self.assertTrue(success, message)
        details = sharing.getPublishedProject(postId)
        self.assertEqual(details['steps'], [{'description': 'Готовый котик', 'photoPosition': 0}])
        self.assertEqual(details['mixtures'][0]['recipeItems'], self.recipe)
        self.assertEqual(len(posts.getCommunityPosts()[0]['photoIds']), 1)
        with db.openDatabase() as connection:
            raw = connection.execute('SELECT projectDetailsJson FROM posts WHERE postId = ?', (postId,)).fetchone()[0]
        for secret in ('SECRET', '01.01.2020', 'Секретный этап', 'projectId', 'stepId', 'userId', 'deadline'):
            self.assertNotIn(secret, raw)
        self.assertIsNotNone(db.getProjectStepPhoto(self.project, privateStep, self.owner))
        self.assertEqual(posts.getUserPosts(self.owner)[0]['postId'], postId)

    def test_unselected_mixtures_are_not_published(self):
        postId = self.publish(projectMixtureIds=[])[2]
        self.assertEqual(sharing.getPublishedProject(postId)['mixtures'], [])
        self.assertFalse(sharing.copyPublishedMixture(postId, 0, self.other)[0])

    def test_foreign_project_steps_and_mixtures_cannot_be_published(self):
        otherProject = projects.saveProject(self.owner, 'Другой проект', 'Животные', '', '')[2]
        otherStep = self.addStep(otherProject, self.owner, 'Этап другого проекта')
        for changes in (dict(userId=self.other), dict(projectId=99999), dict(resultStepId=otherStep),
                        dict(otherStepIds=[otherStep]), dict(projectMixtureIds=[99999]),
                        dict(projectId=otherProject, resultStepId=otherStep, otherStepIds=[])):
            with self.subTest(changes=changes):
                self.assertFalse(self.publish(**changes)[0])
        self.assertEqual(posts.getCommunityPosts(), [])

    def test_missing_photo_invalid_ids_text_and_tags_do_not_create_partial_posts(self):
        blank = projects.saveProjectStep(self.project, 'Пока без фото', self.owner)[2]
        for changes in (dict(resultStepId=blank), dict(resultStepId=None), dict(resultStepId=True),
                        dict(otherStepIds=[self.result]), dict(otherStepIds=[self.step, self.step]),
                        dict(otherStepIds=None), dict(projectMixtureIds=[self.attached, self.attached]),
                        dict(descriptionText='мало'), dict(titleText='аб'), dict(categoryName='неизвестно'),
                        dict(tagsText='x'), dict(otherStepIds=[self.step]*10)):
            with self.subTest(changes=changes):
                self.assertFalse(self.publish(**changes)[0])
        with db.openDatabase() as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM posts').fetchone()[0], 0)
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM postPhotos').fetchone()[0], 0)

    def test_ten_photos_are_allowed_but_eleven_are_not(self):
        stages = [self.step, *[self.addStep(self.project, self.owner, f'Фото этапа {index}') for index in range(9)]]
        self.assertFalse(self.publish(otherStepIds=stages)[0])
        success, message, postId = self.publish(otherStepIds=stages[:9])
        self.assertTrue(success, message)
        self.assertEqual(len(db.getPostPhotoIds(postId)), 10)

    def test_failure_writing_photo_rolls_back_post_photos_and_snapshot(self):
        with db.openDatabase() as connection:
            connection.execute("""CREATE TRIGGER reject_photo BEFORE INSERT ON postPhotos WHEN NEW.position = 1
                BEGIN SELECT RAISE(ABORT, 'test failure'); END""")
        with self.assertRaises(sqlite3.IntegrityError):
            self.publish()
        with db.openDatabase() as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM posts').fetchone()[0], 0)
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM postPhotos').fetchone()[0], 0)
        self.assertEqual(len(sharing.getProjectMixtures(self.project, self.owner)), 1)

    def test_edit_and_delete_source_preserves_publication_and_copied_recipe(self):
        postId = self.publish()[2]
        details = sharing.getPublishedProject(postId)
        photoIds = db.getPostPhotoIds(postId)
        photoBytes = [db.getPostPhoto(photoId) for photoId in photoIds]
        projects.editProjectStep(self.project, self.result, self.owner, 'Изменённый результат')
        colors.deleteColorMixture(self.owner, self.mixture)
        self.assertTrue(projects.removeProject(self.project, self.owner))
        db.initializeDatabase()
        self.assertEqual(sharing.getPublishedProject(postId), details)
        self.assertEqual([db.getPostPhoto(photoId) for photoId in photoIds], photoBytes)
        success, message, mixtureId = sharing.copyPublishedMixture(postId, 0, self.other)
        self.assertTrue(success, message)
        self.assertTrue(posts.removePost(postId, self.owner))
        self.assertIsNone(sharing.getPublishedProject(postId))
        self.assertEqual(colors.getUserColorMixtures(self.other)[0]['mixtureId'], mixtureId)
        self.assertEqual(colors.getUserColorMixtures(self.other)[0]['recipeItems'], self.recipe)
        self.assertFalse(sharing.copyPublishedMixture(postId, 0, self.other)[0])

    def test_copy_is_private_validated_and_concurrent_clicks_do_not_duplicate(self):
        postId = self.publish()[2]
        for index in (-1, 10, True, '0'):
            self.assertFalse(sharing.copyPublishedMixture(postId, index, self.other)[0])
        self.assertFalse(sharing.copyPublishedMixture(99999, 0, self.other)[0])
        with ThreadPoolExecutor(max_workers=4) as executor:
            results = list(executor.map(lambda _: sharing.copyPublishedMixture(postId, 0, self.other), range(8)))
        self.assertTrue(all(result[0] for result in results))
        self.assertEqual(len({result[2] for result in results}), 1)
        self.assertEqual(len(colors.getUserColorMixtures(self.other)), 1)
        self.assertEqual(len(colors.getUserColorMixtures(self.owner)), 1)
        with db.openDatabase() as connection:
            broken = json.loads(connection.execute('SELECT projectDetailsJson FROM posts WHERE postId = ?', (postId,)).fetchone()[0])
            broken['mixtures'][0]['recipeItems'][0]['grams'] = 999
            connection.execute('UPDATE posts SET projectDetailsJson = ? WHERE postId = ?', (json.dumps(broken), postId))
        self.assertIsNone(sharing.getPublishedProject(postId))
        self.assertFalse(sharing.copyPublishedMixture(postId, 0, self.other)[0])

    def test_blocked_user_cannot_attach_publish_remove_or_copy(self):
        postId = self.publish()[2]
        with db.openDatabase() as connection:
            connection.execute('UPDATE users SET isBlocked = 1 WHERE userId IN (?, ?)', (self.owner, self.other))
        self.assertFalse(sharing.addProjectMixture(self.project, self.owner, self.mixture)[0])
        self.assertFalse(sharing.removeProjectMixture(self.project, self.owner, self.attached))
        self.assertFalse(self.publish()[0])
        self.assertFalse(sharing.copyPublishedMixture(postId, 0, self.other)[0])

    def test_account_deletion_removes_private_mixtures_and_public_snapshot(self):
        postId = self.publish()[2]
        posts.savePostComment(postId, self.other, 'Чужой комментарий')
        self.assertTrue(db.deleteUserDataById(self.owner))
        self.assertIsNone(sharing.getPublishedProject(postId))
        self.assertFalse(sharing.copyPublishedMixture(postId, 0, self.other)[0])
        self.assertEqual(len(posts.getPostComments(postId)), 1)
        with db.openDatabase() as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM projectMixtures').fetchone()[0], 0)
            self.assertEqual(connection.execute('SELECT projectDetailsJson FROM posts WHERE postId = ?', (postId,)).fetchone()[0], '')
            self.assertEqual(connection.execute('PRAGMA foreign_key_check').fetchall(), [])

    def test_old_text_and_photo_posts_survive_migration_without_project_details(self):
        postId = posts.savePost(self.owner, 'Старая работа', 'Подробное описание работы', 'Другое', '', [photo()])[2]
        with db.openDatabase() as connection:
            connection.execute('ALTER TABLE posts DROP COLUMN projectDetailsJson')
        db.initializeDatabase()
        self.assertIsNone(sharing.getPublishedProject(postId))
        self.assertEqual(len(posts.getCommunityPosts()[0]['photoIds']), 1)


class SharingUiTests(SharingFixture, unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        with db.openDatabase() as connection:
            self.user = account_security.createSession(connection, db.getUserByEmail('owner@example.com'))
            self.reader = account_security.createSession(connection, db.getUserByEmail('reader@example.com'))
        self.page = ft.Page(MemoryConnection(), 'sharing', asyncio.get_running_loop())
        self.page.theme_mode = ft.ThemeMode.LIGHT
        self.page.session.set('currentUser', self.user)
        self.page.go = lambda route: setattr(self.page, 'route', route)

    def mount(self, control):
        view = ft.View('/sharing', controls=[control])
        self.page.views[:] = [view]
        self.page.update()
        return view

    def dialog(self):
        return next(item for item in reversed(self.page.overlay) if isinstance(item, ft.AlertDialog) and item.open)

    async def test_project_form_publishes_only_checked_photos_and_recipes_then_reader_can_copy(self):
        from views.home_view import createProjectsTab, createColorsTab
        from views.community_tab import createHomeTab
        view = self.mount(createProjectsTab(self.page, self.user))
        find(view, ft.ElevatedButton, text='Опубликовать в сообщество').on_click(None)
        dialog = self.dialog()
        self.assertFalse(find(dialog, ft.TextField, label='Описание для сообщества').value)
        find(dialog, ft.TextField, label='Описание для сообщества').value = 'Открытое описание котика'
        for label in ('Серый котик', 'Слепить основу'):
            checkbox = find(dialog, ft.Checkbox, label=label)
            checkbox.value = True
            checkbox.on_change(SimpleNamespace(control=checkbox))
        find(dialog, ft.ElevatedButton, text='Опубликовать проект').on_click(None)
        self.assertFalse(dialog.open)
        postId = posts.getCommunityPosts()[0]['postId']
        self.assertEqual(len(sharing.getPublishedProject(postId)['steps']), 2)
        self.page.session.set('currentUser', self.reader)
        view = self.mount(createHomeTab(self.page, self.reader, self.reader['nickname']))
        find(view, ft.OutlinedButton, text='Сохранить рецепт в мою палитру').on_click(None)
        self.assertEqual(colors.getUserColorMixtures(self.other)[0]['recipeItems'], self.recipe)
        view = self.mount(createColorsTab(self.page, self.reader))
        find(view, ft.IconButton, tooltip='Открыть рецепт').on_click(None)
        self.assertEqual(find(view, ft.TextField, label='Название смеси').value, 'Серый котик')
        self.assertEqual(find(view, ft.TextField, label='Общий вес смеси (граммы)').value, '100.0')

    async def test_attach_and_remove_mixture_through_controls(self):
        from views.home_view import createProjectsTab
        sharing.removeProjectMixture(self.project, self.owner, self.attached)
        view = self.mount(createProjectsTab(self.page, self.user))
        find(view, ft.OutlinedButton, text='Добавить смесь из палитры').on_click(None)
        dialog = self.dialog()
        find(dialog, ft.Dropdown, label='Смесь из моей палитры').value = str(self.mixture)
        find(dialog, ft.ElevatedButton, text='Добавить смесь').on_click(None)
        self.assertEqual(len(sharing.getProjectMixtures(self.project, self.owner)), 1)
        find(view, ft.TextButton, text='Убрать смесь из проекта').on_click(None)
        self.assertEqual(sharing.getProjectMixtures(self.project, self.owner), [])

    async def test_search_finds_published_work_by_title_tag_author_and_filters_category(self):
        from views.home_view import createSearchTab
        postId = self.publish()[2]
        view = self.mount(createSearchTab(self.page, self.user))
        field = find(view, ft.TextField, label='Поиск уроков и работ')
        for query in ('Наш котик', 'лепка', 'Автор'):
            field.value = query
            field.on_change(None)
            self.assertTrue(any(isinstance(control, ft.Text) and control.value == 'Наш котик' for control in walk(view)))
        category = find(view, ft.Dropdown, label='Категория')
        category.value = 'Еда'
        category.on_change(None)
        self.assertFalse(any(isinstance(control, ft.Text) and control.value == 'Наш котик' for control in walk(view)))
        self.assertIsNotNone(sharing.getPublishedProject(postId))

    async def test_guest_can_read_but_cannot_copy_and_stale_handlers_cannot_publish(self):
        from views.home_view import createProjectsTab
        from views.community_tab import createHomeTab
        postId = self.publish()[2]
        guest = self.mount(createHomeTab(self.page, None, 'Гость'))
        self.assertTrue(find(guest, ft.OutlinedButton, text='Сохранить рецепт в мою палитру').disabled)
        view = self.mount(createProjectsTab(self.page, self.user))
        find(view, ft.ElevatedButton, text='Опубликовать в сообщество').on_click(None)
        dialog = self.dialog()
        find(dialog, ft.TextField, label='Описание для сообщества').value = 'Ещё одна работа с котиком'
        callback = find(dialog, ft.ElevatedButton, text='Опубликовать проект').on_click
        logoutPage(self.page)
        callback(None)
        self.assertEqual(len(posts.getCommunityPosts()), 1)
        self.assertEqual(posts.getCommunityPosts()[0]['postId'], postId)


if __name__ == '__main__':
    unittest.main()
