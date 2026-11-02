"""Клиент подключается к настоящему серверу в отдельном процессе и отдельной базе."""
import asyncio
from pathlib import Path
import os
import socket
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch, Mock

import flet as ft
import requests

import account_gateway as gateway
import api_client
import auth_service
import database
from password_service import createPasswordHash
from test_startup import MemoryConnection, find
from views.auth_view import createAuthView
from views.home_view import createHomeView
from ui_helpers import getCurrentUser, logoutPage, authenticatedAction


class GatewayTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        self.url = f'http://127.0.0.1:{port}'
        runEnv = os.environ.copy()
        for name in ('LEPKA_MAIL_API_KEY', 'LEPKA_MAIL_FROM', 'LEPKA_API_URL'):
            runEnv.pop(name, None)
        runEnv.update(LEPKA_SERVER_DATA_DIR=str(self.root / 'server'), LEPKA_DATA_DIR=str(self.root / 'server'))
        self.log = tempfile.TemporaryFile(mode='w+')
        self.addCleanup(self.log.close)
        script = """
import os
from pathlib import Path
import database
from password_service import createPasswordHash
import uvicorn
from backend.main import app
folder = Path(os.environ['LEPKA_SERVER_DATA_DIR'])
folder.mkdir(parents=True, exist_ok=True)
database.DATABASE_PATH = folder / 'accounts.db'
database.initializeDatabase()
passwordHash, salt = createPasswordHash('ServerPass123')
database.createUser('server@example.com', passwordHash, salt, 'server_user')
database.createUser('second@example.com', passwordHash, salt, 'second_user')
uvicorn.run(app, host='127.0.0.1', port=int(__import__('sys').argv[1]), access_log=False, log_level='warning')
"""
        self.process = subprocess.Popen([sys.executable, '-c', script, str(port)], env=runEnv,
                                        stdout=self.log, stderr=self.log)
        self.addCleanup(self.stopServer)
        for _ in range(150):
            if self.process.poll() is not None:
                self.log.seek(0)
                self.fail(self.log.read())
            try:
                if requests.get(self.url + '/health', timeout=0.3).status_code == 200:
                    break
            except requests.RequestException:
                time.sleep(0.03)
        else:
            self.fail('Сервер не запустился')
        envPatch = patch.dict(os.environ, {'LEPKA_API_URL': self.url, 'LEPKA_ALLOW_LOCAL_API': '1'})
        envPatch.start()
        self.addCleanup(envPatch.stop)
        dbPatch = patch.object(database, 'DATABASE_PATH', self.root / 'client.db')
        dbPatch.start()
        self.addCleanup(dbPatch.stop)
        database.initializeDatabase()
        passwordHash, salt = createPasswordHash('LocalPass123')
        self.localId = database.createUser('local@example.com', passwordHash, salt, 'local_user')
        self.page = ft.Page(MemoryConnection(), 'gateway-test', asyncio.get_event_loop())
        self.page.theme_mode = ft.ThemeMode.LIGHT
        self.page.update()

    def stopServer(self):
        if self.process.poll() is None:
            self.process.terminate()
        self.process.wait(timeout=10)

    def login(self):
        success, message, user = gateway.loginUser('server@example.com', 'ServerPass123')
        self.assertTrue(success, message)
        self.page.session.set('currentUser', user)
        return user

    async def test_remote_custom_role_and_admin_delete_use_server_ids(self):
        from scripts.manage_admin import grantAdmin
        from moderation_gateway import ModerationClient
        grantAdmin(self.root/'server'/'accounts.db','server@example.com')
        user=self.login();admin=ModerationClient(user)
        other=gateway.loginUser('second@example.com','ServerPass123')[2]
        admin.saveRole('helper','Помощник',['reports.manage'],'Роль для проверки серверных полномочий',True)
        admin.changeUser(other['serverUserId'],'Назначение роли на сервере',role='helper')
        other=gateway.loginUser('second@example.com','ServerPass123')[2]
        helper=ModerationClient(other)
        self.assertEqual(helper.access()['permissions'],['reports.manage'])
        self.assertEqual(helper.reports(),[])
        from api_client import ApiError
        with self.assertRaises(ApiError):helper.users()
        with self.assertRaises(ApiError):helper.changeUser(other['serverUserId'],'Попытка повысить собственные права',role='admin')
        with self.assertRaises(ApiError):admin.deleteRole('../users/'+str(other['serverUserId']),'Проверка недопустимого кода роли')
        self.assertEqual(helper.access()['roleName'],'helper')
        self.assertTrue(admin.deleteUser(other['serverUserId'],'Удаление учебного серверного аккаунта'))
        with self.assertRaises(ApiError):helper.access()
        with database.openDatabase() as c:
            self.assertEqual(c.execute('SELECT email,roleName FROM users WHERE userId=?',(self.localId,)).fetchone()['email'],'local@example.com')
            self.assertEqual(c.execute('SELECT COUNT(*) FROM customRoles').fetchone()[0],0)

    async def test_remote_contest_publication_replies_and_notice_center_keep_ids_on_server(self):
        from scripts.manage_admin import grantAdmin
        from challenge_gateway import ChallengeClient
        from community_gateway import CommunityClient
        from image_fixtures import photo
        import challenge_service
        grantAdmin(self.root/'server'/'accounts.db','server@example.com')
        user=self.login();contest=ChallengeClient(user);community=CommunityClient(user)
        self.assertNotEqual(user['userId'],user['serverUserId'])
        cid=contest.create('Серверный конкурс','Правила серверного конкурса',challenge_service.today(),resultMode='votes')
        success,message,pid=community.publishPost('Конкурсный кот','Описание готового кота','Животные','кот',[photo()],challengeId=cid)
        self.assertTrue(success,message)
        self.assertEqual(contest.detail(cid)['myPostId'],pid)
        reader=gateway.loginUser('second@example.com','ServerPass123')[2]
        other=CommunityClient(reader)
        self.assertTrue(other.toggleLike(pid)[0])
        parent=other.saveComment(pid,'Какой материал вы использовали?')[2]
        community.saveComment(pid,'Для котика использована мягкая глина',parent)
        events=contest.notices()
        self.assertEqual({r['kind'] for r in events},{'like','comment'})
        self.assertEqual(ChallengeClient(reader).notices()[0]['kind'],'reply')
        self.assertEqual(contest.noticeSummary()['unread'],2)
        self.assertEqual(contest.readAllNotices(),2)
        self.assertEqual(contest.notices(unread=True),[])
        self.assertEqual(community.getPostsPage(query='КОНКУРСНЫЙ')['items'][0]['postId'],pid)
        detail=contest.detail(cid)
        self.assertTrue(community.getThumbnail(detail['entries'][0]['photoId']))
        with database.openDatabase() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM challengeEntries').fetchone()[0],0)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM activityNotices').fetchone()[0],0)
            self.assertEqual(c.execute('SELECT roleName FROM users WHERE userId=?',(self.localId,)).fetchone()[0],'user')
        import post_service as posts
        localPost=posts.savePost(user['userId'],'Местная работа','Локальная публикация до подключения API','Животные','кот',[photo()])[2]
        with database.openDatabase() as c:c.execute('UPDATE posts SET tagsText=? WHERE postId=?',(f'кот, #challenge-{cid}',localPost))
        success,message,exported=community.exportLocalPost(localPost)
        self.assertTrue(success,message)
        self.assertNotIn('#challenge-',community.getPost(exported)['tagsText'])
        self.assertIn('#challenge-',posts.getUserPosts(user['userId'])[0]['tagsText'])
        self.assertEqual(contest.detail(cid)['myPostId'],pid)


    async def test_login_keeps_server_and_local_ids_separate_and_preserves_old_data(self):
        project = database.createProject(self.localId, 'Локальный проект', 'Животные', '', '')
        user = self.login()
        self.assertEqual(user['serverUserId'], self.localId)  # Совпадающие ID в двух базах.
        self.assertNotEqual(user['userId'], self.localId)
        self.assertEqual(database.getProjectsByUserId(user['userId']), [])
        self.assertEqual(database.getProjectsByUserId(self.localId)[0]['projectId'], project)
        secondLogin = gateway.loginUser('server@example.com', 'ServerPass123')[2]
        self.assertEqual(secondLogin['userId'], user['userId'])
        self.assertEqual(gateway.getSessionUser(user['sessionToken'])['userId'], user['userId'])
        with database.openDatabase() as connection:
            cache = connection.execute('SELECT * FROM users WHERE userId = ?', (user['userId'],)).fetchone()
            self.assertEqual(cache['passwordHash'], '!remote-account!')
            self.assertNotEqual(cache['email'], 'server@example.com')
            self.assertEqual(connection.execute('PRAGMA foreign_key_check').fetchall(), [])

    async def test_flet_login_profile_settings_and_logout_use_server(self):
        view = createAuthView(self.page)
        self.page.views[:] = [view]
        self.page.update()
        find(view, ft.TextField, label='Email').value = 'server@example.com'
        find(view, ft.TextField, label='Пароль').value = 'ServerPass123'
        find(view, ft.ElevatedButton, text='Войти').on_click(None)
        self.assertEqual(self.page.route, '/home')
        user = self.page.session.get('currentUser')
        self.assertIsNotNone(user)
        home = createHomeView(self.page)
        self.page.views[:] = [home]
        self.page.update()
        nav = find(home, ft.NavigationBar)
        nav.selected_index = 4
        nav.on_change(SimpleNamespace(control=nav))
        find(home, ft.TextField, label='Никнейм').value = 'updated_server'
        find(home, ft.ElevatedButton, text='Сохранить профиль').on_click(None)
        profile = gateway.getUserProfile(user['userId'], user['sessionToken'])
        self.assertEqual(profile['nickname'], 'updated_server')
        self.assertTrue(gateway.saveUserSettings(user['userId'], 'dark', 'ru', False, user['sessionToken'])[0])
        self.assertFalse(gateway.getUserProfile(user['userId'], user['sessionToken'])['notificationsEnabled'])
        logoutPage(self.page)
        self.assertIsNone(self.page.session.get('currentUser'))
        self.assertIsNone(gateway.getSessionUser(user['sessionToken']))

    async def test_remote_admin_uses_server_target_ids_and_never_promotes_local_cache(self):
        from scripts.manage_admin import grantAdmin
        from moderation_gateway import ModerationClient
        grantAdmin(self.root/'server'/'accounts.db','server@example.com')
        user=self.login();self.assertEqual(user['roleName'],'admin')
        client=ModerationClient(user)
        target=next(row for row in client.users('second@example.com'))
        self.assertEqual(target['userId'],user['userId'])  # Совпали чужой server ID и свой local ID.
        self.assertNotEqual(target['userId'],user['serverUserId'])
        self.assertTrue(client.changeUser(target['userId'],'Проверка серверной блокировки',blocked=True))
        self.assertFalse(gateway.loginUser('second@example.com','ServerPass123')[0])
        self.assertIsNotNone(gateway.getSessionUser(user['sessionToken']))
        with database.openDatabase() as c:
            local=c.execute('SELECT roleName,isBlocked FROM users WHERE userId=?',(user['userId'],)).fetchone()
            self.assertEqual(tuple(local),('user',0))
            self.assertEqual(c.execute('SELECT COUNT(*) FROM adminAudit').fetchone()[0],0)
        self.assertEqual(client.audit()[0]['action'],'user.block')

    async def test_local_reminders_use_remote_profile_setting_and_cached_owner(self):
        from datetime import date
        from project_planner import syncProjectReminders
        from views.project_planner import createDeadlineSummary
        user=self.login()
        deadline=date.today().strftime('%d.%m.%Y')
        database.createProject(self.localId,'Чужой локальный проект','Другое',deadline,'')
        database.createProject(user['userId'],'Личный проект с API','Другое',deadline,'')
        self.assertTrue(gateway.saveUserSettings(user['userId'],'light','ru',False,user['sessionToken'])[0])
        card=createDeadlineSummary(self.page,user)
        self.assertIsNotNone(find(card,ft.Text,value='Напоминания отключены в профиле'))
        with database.openDatabase() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM projectReminders').fetchone()[0],0)
        self.assertTrue(gateway.saveUserSettings(user['userId'],'light','ru',True,user['sessionToken'])[0])
        card=createDeadlineSummary(self.page,user)
        self.assertIsNotNone(find(card,ft.Text,value='Непрочитанных напоминаний: 1'))
        reminders=syncProjectReminders(user['userId'])
        self.assertEqual([row['projectName'] for row in reminders],['Личный проект с API'])

    async def test_avatar_is_saved_on_server_and_rendered_in_flet_profile(self):
        from pathlib import Path
        from image_fixtures import photo
        from views.profile_tab import createProfileTab
        user = self.login()
        view = ft.View('/profile', controls=[createProfileTab(self.page, user['nickname'], user['email'])])
        self.page.views[:] = [view]
        self.page.update()
        source = photo()
        path = self.root / source['name']
        path.write_bytes(source['data'])
        find(view, ft.OutlinedButton, text='Выбрать аватар').on_click(None)
        picker = next(c for c in self.page.overlay if isinstance(c, ft.FilePicker))
        picker.on_result(SimpleNamespace(files=[SimpleNamespace(name=path.name, path=str(path), size=path.stat().st_size, id=1)],control=picker))
        value = gateway.getUserProfile(user['userId'], user['sessionToken'])['avatarImage']
        self.assertTrue(value)
        self.assertEqual(find(view, ft.CircleAvatar).content.src_base64, value)
        # Серверный аватар не записывается к случайному совпавшему локальному ID.
        self.assertIsNone(database.getUserProfileById(user['userId'])['avatarImage'])
        find(view, ft.ElevatedButton, text='Сохранить профиль').on_click(None)
        self.assertEqual(gateway.getUserProfile(user['userId'], user['sessionToken'])['avatarImage'], value)
        find(view, ft.OutlinedButton, text='Убрать аватар').on_click(None)
        self.assertEqual(gateway.getUserProfile(user['userId'], user['sessionToken'])['avatarImage'], '')

    async def test_private_color_screen_remains_usable_with_verified_offline_session(self):
        from views.home_view import createColorsTab
        from color_service import getUserColorMixtures
        user=self.login();self.stopServer()
        offline=getCurrentUser(self.page);self.assertTrue(offline['offline'])
        view=ft.View('/colors',controls=[createColorsTab(self.page,offline)])
        self.page.views[:]=[view];self.page.update()
        from test_startup import walk
        for name in ('Белый','Чёрный'):
            gesture=next(c for c in walk(view) if isinstance(c,ft.GestureDetector) and any(isinstance(t,ft.Text) and t.value==name for t in walk(c)))
            gesture.on_tap(None)
        find(view,ft.ElevatedButton,text='Сохранить смесь').on_click(None)
        self.assertEqual(len(getUserColorMixtures(user['userId'])),1)
        self.assertEqual(getUserColorMixtures(self.localId),[])

    async def test_server_unavailable_never_falls_back_to_local_password(self):
        self.assertTrue(auth_service.loginUser('local@example.com', 'LocalPass123')[0])
        self.assertFalse(gateway.loginUser('local@example.com', 'LocalPass123')[0])
        user = self.login()
        self.stopServer()
        self.assertFalse(gateway.loginUser('local@example.com', 'LocalPass123')[0])
        called = []
        @authenticatedAction(self.page, user)
        def write():
            called.append(True)
        write()
        self.assertEqual(called, [True])
        self.assertTrue(self.page.session.get('currentUser')['offline'])
        self.assertEqual(self.page.session.get('currentUser')['sessionToken'], user['sessionToken'])
        self.assertIsNotNone(database.getUserByEmail('local@example.com'))

    async def test_explicit_logout_clears_local_session_when_server_is_unavailable(self):
        self.login()
        self.stopServer()
        logoutPage(self.page)
        self.assertIsNone(self.page.session.get('currentUser'))
        self.assertEqual(self.page.route, '/auth')
        with database.openDatabase() as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM remoteSessionBindings').fetchone()[0], 0)

    async def test_revoked_server_session_clears_flet_session(self):
        user = self.login()
        self.assertTrue(gateway.changeUserPassword(user['userId'], 'ServerPass123', 'Changed123', 'Changed123', user['sessionToken'])[0])
        called = []
        @authenticatedAction(self.page, user)
        def write():
            called.append(True)
        write()
        self.assertEqual(called, [])
        self.assertIsNone(self.page.session.get('currentUser'))
        self.assertEqual(self.page.route, '/auth')

    async def test_client_does_not_send_mail_even_when_a_key_is_present(self):
        with patch.dict(os.environ, {'LEPKA_MAIL_API_KEY': 'unused-test-placeholder'}):
            with patch('mail_service.sendAccountCode', side_effect=AssertionError('Локальная отправка запрещена')) as send:
                success, message = gateway.requestPasswordRecovery('server@example.com')
                # На отдельном сервере намеренно нет ключа; клиент не должен использовать свой.
                self.assertFalse(success)
                self.assertIn('не настроена', message)
                send.assert_not_called()
        with database.openDatabase() as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM accountCodes').fetchone()[0], 0)

    async def test_server_account_deletion_only_removes_bound_local_data(self):
        oldProject = database.createProject(self.localId, 'Старый проект', 'Животные', '', '')
        user = self.login()
        database.createProject(user['userId'], 'Новый проект', 'Животные', '', '')
        self.assertTrue(gateway.deleteUserAccount(user['userId'], 'ServerPass123', user['sessionToken'])[0])
        self.assertEqual(database.getProjectsByUserId(self.localId)[0]['projectId'], oldProject)
        self.assertEqual(database.getProjectsByUserId(user['userId']), [])
        self.assertIsNone(gateway.getSessionUser(user['sessionToken']))
        with database.openDatabase() as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM remoteAccounts').fetchone()[0], 0)
            self.assertEqual(connection.execute('PRAGMA foreign_key_check').fetchall(), [])

    async def test_cannot_use_local_id_of_another_account_with_valid_token(self):
        user = self.login()
        with self.assertRaises(api_client.ApiError):
            gateway.getUserProfile(self.localId, user['sessionToken'])
        with self.assertRaises(api_client.ApiError):
            gateway.saveUserSettings(self.localId, 'dark', 'ru', False, user['sessionToken'])
        profile = gateway.getUserProfile(user['userId'], user['sessionToken'])
        self.assertEqual(profile['themeMode'], 'light')


    async def test_remote_final_photo_project_keeps_structured_steps_and_copies_to_another_account(self):
        from image_fixtures import photo
        from community_gateway import CommunityClient
        from project_service import saveProject,saveStep,saveFinalPhoto,saveProjectStepPhoto,getProjectSteps
        user=self.login();client=CommunityClient(user)
        pid=saveProject(user['userId'],'Новый котик','Животные','','Приватные заметки')[2]
        sid=saveStep(pid,user['userId'],'Слепить основу','Сформировать овал')[2]
        saveFinalPhoto(pid,user['userId'],photo());saveProjectStepPhoto(pid,sid,user['userId'],photo())
        ok,message,postId=client.publishProject(pid,'Новый котик','Подробная общая работа','Животные','кот',None,[sid],[])
        self.assertTrue(ok,message)
        workshop=client.getWorkshop(postId)
        self.assertEqual(workshop['steps'][0]['title'],'Слепить основу')
        self.assertNotIn('Приватные',workshop['description'])
        other=gateway.loginUser('second@example.com','ServerPass123')[2]
        ok,message,copied=CommunityClient(other).copyProject(postId);self.assertTrue(ok,message)
        self.assertEqual(getProjectSteps(copied,other['userId'])[0]['details'],'Сформировать овал')
        with patch.object(client,'request',side_effect=api_client.ApiError('Старая версия',404)):
            result=client.publishProject(pid,'Новый котик','Подробная общая работа','Животные','кот',None,[sid],[])
        self.assertFalse(result[0]);self.assertIn('Обновите',result[1])

    async def test_two_separate_client_databases_share_only_server_community(self):
        from community_gateway import CommunityClient
        from challenge_gateway import ChallengeClient
        from image_fixtures import photo
        from project_service import saveProject,getUserProjects
        alice=self.login();a=CommunityClient(alice)
        gateway.saveUserSettings(alice['userId'],'light','en',True,alice['sessionToken'])
        personal=saveProject(alice['userId'],'Личный проект Alice','Животные','','Не публиковать')[2]
        ok,text,pid=a.publishPost('Общий котик','Работа для двух независимых клиентов','Животные','кот',[photo()])
        self.assertTrue(ok,text)
        with patch.object(database,'DATABASE_PATH',self.root/'second-device.db'):
            database.initializeDatabase()
            bob=gateway.loginUser('second@example.com','ServerPass123')[2];b=CommunityClient(bob)
            self.assertEqual(getUserProjects(bob['userId']),[])
            self.assertEqual(b.getPost(pid)['titleText'],'Общий котик')
            self.assertTrue(b.toggleLike(pid)[0])
            comment=b.saveComment(pid,'Видно со второго устройства')[2]
            self.assertIsNotNone(comment)
            self.assertEqual(gateway.getUserProfile(bob['userId'],bob['sessionToken'])['languageCode'],'ru')
            with database.openDatabase() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM posts').fetchone()[0],0)
        self.assertEqual(getUserProjects(alice['userId'])[0]['projectId'],personal)
        self.assertEqual(a.getPost(pid)['likesCount'],1)
        self.assertEqual(a.getComments(pid)[0]['commentText'],'Видно со второго устройства')
        self.assertTrue(a.saveComment(pid,'Ответ автора',comment)[0])
        self.assertEqual({n['kind'] for n in ChallengeClient(alice).notices()},{'like','comment'})
        with patch.object(database,'DATABASE_PATH',self.root/'second-device.db'):
            self.assertEqual(ChallengeClient(bob).notices()[0]['kind'],'reply')
            self.assertEqual(gateway.getSessionUser(bob['sessionToken'])['userId'],bob['userId'])
        self.assertEqual(gateway.getUserProfile(alice['userId'],alice['sessionToken'])['languageCode'],'en')


class TransportTests(unittest.TestCase):
    def test_https_is_required_except_explicit_local_test(self):
        for url in ('http://api.example.com', 'https://user:password@example.com', 'https://api.example.com?key=bad'):
            with patch.dict(os.environ, {'LEPKA_API_URL': url, 'LEPKA_ALLOW_LOCAL_API': '1'}):
                with self.assertRaises(api_client.ApiError):
                    api_client.getApiUrl()
        with patch.dict(os.environ, {'LEPKA_API_URL': 'http://127.0.0.1:8000', 'LEPKA_ALLOW_LOCAL_API': ''}):
            with self.assertRaises(api_client.ApiError):
                api_client.getApiUrl()

    def test_401_is_recognized_even_when_proxy_response_is_not_json(self):
        response = Mock(status_code=401)
        response.json.side_effect = ValueError('not json')
        with patch.dict(os.environ, {'LEPKA_API_URL': 'https://api.example.com'}):
            with patch('api_client.requests.request', return_value=response):
                with self.assertRaises(api_client.ApiError) as context:
                    api_client.apiRequest('GET', '/auth/me', sessionToken='test-session')
                self.assertEqual(context.exception.statusCode, 401)

    def test_transport_uses_bearer_and_keeps_tls_and_redirect_checks(self):
        response = Mock(status_code=200)
        response.json.return_value = {'data': {'userId': 1}}
        with patch.dict(os.environ, {'LEPKA_API_URL': 'https://api.example.com'}):
            with patch('api_client.requests.request', return_value=response) as request:
                api_client.apiRequest('GET', '/auth/me', sessionToken='test-session')
                self.assertEqual(request.call_args.kwargs['headers'], {'Authorization': 'Bearer test-session'})
                self.assertFalse(request.call_args.kwargs['allow_redirects'])
                self.assertNotIn('verify', request.call_args.kwargs)
                self.assertNotIn('LEPKA_MAIL_API_KEY', str(request.call_args))


if __name__ == '__main__':
    unittest.main()
