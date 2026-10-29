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
        self.assertEqual(called, [])
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
