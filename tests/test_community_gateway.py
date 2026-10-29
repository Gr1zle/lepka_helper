"""Настоящий API и две независимые базы клиентов: никакого общего SQLite-файла."""
import asyncio
from contextlib import contextmanager
from pathlib import Path
import os
import socket
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import flet as ft
import requests

import account_gateway as accounts
from api_client import ApiError
import community_gateway as community
import database as db
import project_service as projects
import project_sharing as sharing
from color_service import BASE_COLORS, calculateRecipe, getUserColorMixtures, saveColorMixture
from image_fixtures import photo
from test_startup import MemoryConnection, find, walk


class ServerFixture:
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            self.port = sock.getsockname()[1]
        self.url = f'http://127.0.0.1:{self.port}'
        self.log = tempfile.TemporaryFile(mode='w+')
        self.addCleanup(self.log.close)
        self.serverEnv = os.environ.copy()
        for name in ('LEPKA_MAIL_API_KEY', 'LEPKA_MAIL_FROM', 'LEPKA_API_URL'):
            self.serverEnv.pop(name, None)
        self.serverEnv.update(LEPKA_SERVER_DATA_DIR=str(self.root/'server'), LEPKA_DATA_DIR=str(self.root/'server'))
        self.startServer()
        self.addCleanup(self.stopServer)
        env = patch.dict(os.environ, {'LEPKA_API_URL': self.url, 'LEPKA_ALLOW_LOCAL_API': '1'})
        env.start()
        self.addCleanup(env.stop)

    def startServer(self):
        script = '''import os
from pathlib import Path
import database as db
from password_service import createPasswordHash
import uvicorn
from backend.main import app
folder=Path(os.environ['LEPKA_SERVER_DATA_DIR'])
folder.mkdir(parents=True,exist_ok=True)
db.DATABASE_PATH=folder/'accounts.db'
db.initializeDatabase()
if db.getUserByEmail('author@example.com') is None:
    passwordHash,salt=createPasswordHash('ServerPass123')
    db.createUser('author@example.com',passwordHash,salt,'Автор')
    db.createUser('reader@example.com',passwordHash,salt,'Читатель')
uvicorn.run(app,host='127.0.0.1',port=int(__import__('sys').argv[1]),access_log=False,log_level='warning')
'''
        self.process = subprocess.Popen([sys.executable, '-c', script, str(self.port)], env=self.serverEnv,
                                        stdout=self.log, stderr=self.log)
        for _ in range(150):
            if self.process.poll() is not None:
                self.log.seek(0)
                self.fail(self.log.read())
            try:
                if requests.get(self.url+'/health', timeout=.3).status_code == 200:
                    return
            except requests.RequestException:
                time.sleep(.03)
        self.fail('Тестовый сервер не запустился')

    def stopServer(self):
        if self.process.poll() is None:
            self.process.terminate()
        self.process.wait(timeout=10)

    @contextmanager
    def client(self, name, email):
        with patch.object(db, 'DATABASE_PATH', self.root/(name+'.db')):
            db.initializeDatabase()
            success, message, user = accounts.loginUser(email, 'ServerPass123')
            self.assertTrue(success, message)
            yield user, community.CommunityClient(user)

    def publish(self, client):
        success, message, postId = client.publishPost('Серверный котик', 'Моя первая работа на общем сервере',
            'Животные', 'котик, лепка', [photo()])
        self.assertTrue(success, message)
        return postId

    def publishWorkshop(self, user, client):
        project = projects.saveProject(user['userId'], 'Общий мастер-класс', 'Животные', '', 'PRIVATE')[2]
        step = projects.saveProjectStep(project, 'Слепить котика', user['userId'])[2]
        projects.saveProjectStepPhoto(project, step, user['userId'], photo())
        selected = [{**item, 'proportion': 50} for item in BASE_COLORS[:2]]
        mixture = saveColorMixture(user['userId'], 'Серый котик', '#808080', 100, calculateRecipe(selected, 100))
        sharing.addProjectMixture(project, user['userId'], mixture)
        attached = sharing.getProjectMixtures(project, user['userId'])[0]['projectMixtureId']
        success, message, postId = client.publishProject(project, 'Общий мастер-класс', 'Пошаговое описание для всех',
            'Животные', 'котик', step, [], [attached], {'level': 'Средний', 'timeMinutes': 45,
            'materials': ['Пластилин'], 'tools': ['Стек']})
        self.assertTrue(success, message)
        return project, postId


class CommunityGatewayTests(ServerFixture, unittest.TestCase):
    def test_two_independent_clients_share_server_posts_and_owner_ids_do_not_collide(self):
        with self.client('author', 'author@example.com') as (author, first):
            postId = self.publish(first)
            self.assertEqual(first.getPosts()[0]['postId'], postId)
            self.assertEqual(db.getAllPosts(), [])  # На клиенте запись публикации не создаётся.
        with self.client('reader', 'reader@example.com') as (reader, second):
            item = second.getPosts()[0]
            self.assertEqual(item['userId'], reader['userId'])  # Чужой серверный ID совпал с локальным!
            self.assertFalse(community.ownsItem(item, reader))
            self.assertEqual(second.getPosts(mine=True), [])
            self.assertTrue(second.getPhoto(item['photoIds'][0]).startswith(b'\xff\xd8'))
            self.assertEqual(second.toggleLike(postId), (True, 1))
            self.assertTrue(second.saveComment(postId, 'Спасибо за работу')[0])
            with self.assertRaises(ApiError) as error:
                second.deletePost(postId)
            self.assertEqual(error.exception.statusCode, 404)
        with self.client('author', 'author@example.com') as (_, first):
            self.assertEqual(first.getPosts(mine=True)[0]['likesCount'], 1)
            self.assertFalse(first.getComments(postId)[0]['isOwn'])
            self.assertIsNone(first.getPhoto(999999))
            self.assertEqual(first.getComments(999999), [])

    def test_private_project_publication_sends_only_snapshot_and_keeps_source(self):
        with self.client('author', 'author@example.com') as (author, first):
            projectId, postId = self.publishWorkshop(author, first)
            self.assertIsNotNone(db.getProjectById(projectId, author['userId']))
            self.assertEqual(db.getAllPosts(), [])
        with self.client('reader', 'reader@example.com') as (reader, second):
            workshop = second.getWorkshop(postId)
            self.assertEqual(workshop['level'], 'Средний')
            self.assertNotIn('PRIVATE', str(workshop))
            self.assertEqual(db.getProjectsByUserId(reader['userId']), [])
            self.assertTrue(second.copyRecipe(postId, 0)[0])
            self.assertTrue(second.copyRecipe(postId, 0)[0])
            self.assertEqual(len(getUserColorMixtures(reader['userId'])), 1)
            self.assertTrue(second.copyProject(postId)[0])
            copied = db.getProjectsByUserId(reader['userId'])[0]
            self.assertEqual(len(projects.getProjectSteps(copied['projectId'], reader['userId'])), 1)
            self.assertEqual(projects.getProjectSteps(copied['projectId'], reader['userId'])[0]['hasPhoto'], False)
            self.assertEqual(len(sharing.getProjectMixtures(copied['projectId'], reader['userId'])), 1)

    def test_progress_follows_server_account_across_two_client_databases_and_restart(self):
        with self.client('author', 'author@example.com') as (author, first):
            _, postId = self.publishWorkshop(author, first)
        with self.client('reader1', 'reader@example.com') as (_, second):
            state = second.saveState(postId, {'lastStep': 0, 'completedSteps': [0], 'checkedMaterials': [1]})
            self.assertTrue(state['isCompleted'])
        self.stopServer()
        self.startServer()
        with self.client('reader2', 'reader@example.com') as (_, third):
            self.assertEqual(third.getState(postId)['checkedMaterials'], [1])
            self.assertTrue(third.getState(postId)['isCompleted'])
            self.assertEqual(db.getAllPosts(), [])

    def test_lost_publish_response_and_retry_create_one_server_work(self):
        with self.client('author', 'author@example.com') as (_, first):
            realRequest = community.apiRequest
            lost = [True]
            def send(*args, **kwargs):
                response = realRequest(*args, **kwargs)
                if args[0] == 'POST' and args[1] == '/community/posts' and lost[0]:
                    lost[0] = False
                    raise ApiError('Ответ потерян')
                return response
            with patch('community_gateway.apiRequest', side_effect=send):
                with self.assertRaises(ApiError):
                    self.publish(first)
                postId = self.publish(first)
            self.assertEqual([item['postId'] for item in first.getPosts()], [postId])
            self.assertEqual(db.getAllPosts(), [])

    def test_server_failure_does_not_publish_or_read_local_feed_as_fallback(self):
        with self.client('author', 'author@example.com') as (author, first):
            import post_service
            post_service.savePost(author['userId'], 'Старая местная работа', 'Старое описание работы', 'Другое', '', [photo()])
            self.stopServer()
            with self.assertRaises(ApiError):
                first.getPosts()
            with self.assertRaises(ApiError):
                self.publish(first)
            self.assertEqual(len(db.getAllPosts()), 1)

    def test_foreign_local_owner_cannot_use_cached_remote_session(self):
        with self.client('author', 'author@example.com') as (author, _):
            foreign = db.createUser('local@example.com', '', '', 'Локальный')
            client = community.CommunityClient({**author, 'userId': foreign})
            with self.assertRaises(ApiError) as error:
                self.publish(client)
            self.assertEqual(error.exception.statusCode, 401)

    def test_existing_local_post_can_be_exported_once_without_erasing_source(self):
        with self.client('author', 'author@example.com') as (author, first):
            import post_service
            localId = post_service.savePost(author['userId'], 'Местный котик', 'Работа из предыдущей версии', 'Животные', '', [photo()])[2]
            self.assertEqual(first.getPosts(), [])
            self.assertEqual(first.getLocalPosts()[0]['postId'], localId)
            success, message, serverId = first.exportLocalPost(localId)
            self.assertTrue(success, message)
            freshClient = community.CommunityClient(author)
            self.assertEqual(freshClient.exportLocalPost(localId)[2], serverId)
            self.assertEqual(len(freshClient.getPosts()), 1)
            self.assertEqual(len(db.getAllPosts()), 1)
            self.assertEqual(db.getAllPosts()[0]['titleText'], 'Местный котик')
            foreign = db.createUser('foreign@example.com', '', '', 'Чужой')
            foreignPost = post_service.savePost(foreign, 'Чужая работа', 'Работа другого пользователя', 'Другое', '', [photo()])[2]
            self.assertFalse(first.exportLocalPost(foreignPost)[0])

    def test_export_retry_key_survives_lost_response_and_new_client_object(self):
        with self.client('author', 'author@example.com') as (author, first):
            import post_service
            localId = post_service.savePost(author['userId'], 'Местная работа', 'Работа для проверки отправки', 'Животные', '', [photo()])[2]
            realRequest = community.apiRequest
            def lost(*args, **kwargs):
                realRequest(*args, **kwargs)
                raise ApiError('Ответ потерян')
            with patch('community_gateway.apiRequest', side_effect=lost), self.assertRaises(ApiError):
                first.exportLocalPost(localId)
            freshClient = community.CommunityClient(author)
            self.assertTrue(freshClient.exportLocalPost(localId)[0])
            self.assertEqual(len(freshClient.getPosts()), 1)
            self.assertEqual(len(db.getAllPosts()), 1)


class CommunityRemoteUiTests(ServerFixture, unittest.IsolatedAsyncioTestCase):
    async def test_flet_publish_saves_photo_on_server_and_not_in_local_posts(self):
        with self.client('author', 'author@example.com') as (author, first):
            from views.community_tab import createHomeTab
            page = ft.Page(MemoryConnection(), 'remote-publish', asyncio.get_running_loop())
            page.theme_mode = ft.ThemeMode.LIGHT
            page.session.set('currentUser', author)
            page.go = lambda route: setattr(page, 'route', route)
            view = ft.View('/home', controls=[createHomeTab(page, author, author['nickname'])])
            page.views[:] = [view]
            page.update()
            find(view, ft.TextField, label='Название работы').value = 'Новая серверная работа'
            find(view, ft.TextField, label='Описание').value = 'Проверка формы публикации через API'
            path = self.root/'Тест.png'
            path.write_bytes(photo()['data'])
            find(view, ft.OutlinedButton, text='Добавить фото').on_click(None)
            picker = next(item for item in page.overlay if isinstance(item, ft.FilePicker))
            picker.on_result(SimpleNamespace(files=[SimpleNamespace(name=path.name,path=str(path),size=path.stat().st_size,id=1)]))
            find(view, ft.ElevatedButton, text='Опубликовать').on_click(None)
            self.assertEqual(len(first.getPosts(mine=True)), 1)
            self.assertEqual(db.getAllPosts(), [])
            import post_service
            from views.profile_tab import createProfileTab
            post_service.savePost(author['userId'], 'Прежняя местная работа', 'Работа из предыдущей версии приложения', 'Другое', '', [photo()])
            profile = ft.View('/profile', controls=[createProfileTab(page, author['nickname'], author['email'])])
            page.views[:] = [profile]
            page.update()
            find(profile, ft.OutlinedButton, text='Публикации на этом устройстве').on_click(None)
            dialog = next(item for item in reversed(page.overlay) if isinstance(item, ft.AlertDialog))
            find(dialog, ft.OutlinedButton, text='Отправить эту работу на сервер').on_click(None)
            self.assertEqual(len(first.getPosts(mine=True)), 2)
            self.assertEqual(len(db.getAllPosts()), 1)

    async def test_real_flet_remote_workshop_progress_comments_and_ownership(self):
        with self.client('author', 'author@example.com') as (author, first):
            _, postId = self.publishWorkshop(author, first)
        with self.client('reader', 'reader@example.com') as (reader, second):
            from views.community_tab import createHomeTab
            self.page = ft.Page(MemoryConnection(), 'remote-community', asyncio.get_running_loop())
            self.page.theme_mode = ft.ThemeMode.LIGHT
            self.page.session.set('currentUser', reader)
            self.page.go = lambda route: setattr(self.page, 'route', route)
            view = ft.View('/home', controls=[createHomeTab(self.page, reader, reader['nickname'])])
            self.page.views[:] = [view]
            self.page.update()
            self.assertFalse(any(isinstance(control, ft.TextButton) and control.text == 'Удалить' for control in walk(view)))
            find(view, ft.TextField, label='Комментарий').value = 'Классный мастер-класс'
            find(view, ft.ElevatedButton, text='Отправить комментарий').on_click(None)
            self.assertEqual(len(second.getComments(postId)), 1)
            find(view, ft.OutlinedButton, text='Открыть мастер-класс').on_click(None)
            workshop = self.page.views[-1]
            checkbox = find(workshop, ft.Checkbox, label='Стек')
            checkbox.value = True
            checkbox.on_change(SimpleNamespace(control=checkbox))
            self.assertEqual(second.getState(postId)['checkedMaterials'], [1])
            self.assertEqual(db.getAllPosts(), [])


if __name__ == '__main__':
    unittest.main()
