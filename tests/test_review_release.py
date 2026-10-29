"""Контрольная поставка: запуск, повтор загрузки, удаление и сохранность данных."""
import asyncio
import hashlib
import json
import os
import sqlite3
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from zipfile import ZipFile

import flet as ft

import api_client
from api_client import ApiError
import app_state
import auth_service
import database as db
import profile_service
import project_service as projects
from scripts.create_server_demo import createServerDemo
from scripts import prepare_review as delivery
from test_startup import MemoryConnection, find, walk
from ui_helpers import logoutPage


class ReviewModeTests(unittest.TestCase):
    def test_duplicate_user_error_closes_connection_and_does_not_lock_windows_database(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(db, 'DATABASE_PATH', Path(folder)/'test.db'):
            db.initializeDatabase()
            db.createUser('existing@example.com', 'hash', 'salt', 'existing')
            connection = db.getConnection()
            try:
                with patch.object(db, 'getConnection', return_value=connection), self.assertRaises(sqlite3.IntegrityError):
                    db.createUser('existing@example.com', 'hash', 'salt', 'another')
                with self.assertRaises(sqlite3.ProgrammingError):
                    connection.execute('SELECT 1')
            finally:
                connection.close()

    def test_explicit_local_mode_ignores_api_without_reading_or_rewriting_config(self):
        with patch.dict(os.environ, {'LEPKA_FORCE_LOCAL': '1', 'LEPKA_API_URL': 'https://example.invalid'}), \
                patch('api_client.Path.read_text') as read:
            self.assertEqual(api_client.getApiUrl(), '')
            read.assert_not_called()
        with patch.dict(os.environ, {'LEPKA_FORCE_LOCAL': '0', 'LEPKA_API_URL': 'https://example.invalid'}):
            self.assertEqual(api_client.getApiUrl(), 'https://example.invalid')

    def test_server_demo_creates_confirmed_standard_user_and_preserves_local_db(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder)/'accounts.db'
            previous = db.DATABASE_PATH
            with patch.object(db, 'DATABASE_PATH', target):
                db.initializeDatabase()
            with patch('mail_service.requests.post') as mail:
                user = createServerDemo(folder)
                self.assertEqual(createServerDemo(folder)['userId'], user['userId'])
                mail.assert_not_called()
            self.assertEqual(db.DATABASE_PATH, previous)
            with patch.object(db, 'DATABASE_PATH', target):
                record = db.getUserByEmail('test@email.com')
                self.assertEqual(record['roleName'], 'user')
                self.assertEqual(record['emailVerified'], 1)
                self.assertNotEqual(record['passwordHash'], 'Test123456')
                self.assertTrue(auth_service.loginUser('test@email.com', 'Test123456')[0])

    def test_server_demo_does_not_reset_changed_password_or_confirm_existing_registration(self):
        for verified in (False, True):
            with tempfile.TemporaryDirectory() as folder:
                target = Path(folder)/'accounts.db'
                with patch.object(db, 'DATABASE_PATH', target):
                    db.initializeDatabase()
                    db.createUser('test@email.com', 'old hash', 'old salt', 'existing', emailVerified=verified)
                with self.assertRaises(ValueError):
                    createServerDemo(folder)
                with patch.object(db, 'DATABASE_PATH', target):
                    record = db.getUserByEmail('test@email.com')
                    self.assertEqual(record['passwordHash'], 'old hash')
                    self.assertEqual(record['emailVerified'], int(verified))

    def test_server_demo_does_not_create_database_at_wrong_path_or_take_another_nickname(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                createServerDemo(folder)
            self.assertEqual(list(Path(folder).iterdir()), [])
            with patch.object(db, 'DATABASE_PATH', Path(folder)/'accounts.db'):
                db.initializeDatabase()
                other = db.createUser('other@example.com', 'hash', 'salt', 'test_user')
            with self.assertRaises(ValueError):
                createServerDemo(folder)
            with patch.object(db, 'DATABASE_PATH', Path(folder)/'accounts.db'):
                self.assertEqual(db.getUserByEmail('other@example.com')['userId'], other)
                self.assertIsNone(db.getUserByEmail('test@email.com'))


class DeliveryTests(unittest.TestCase):
    def test_zip_excludes_personal_files_resets_api_and_verifies_file_hashes(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)/'source'
            root.mkdir()
            for name in delivery.getReviewFiles():
                path = root/name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'safe source')
            (root/'assets/client_config.json').write_text('{"apiBaseUrl":"https://private.example"}')
            for name in ('private.db', '.env', 'password.key', 'private.py', 'docs/private.md', 'assets/secret.txt'):
                (root/name).write_bytes(b'PRIVATE_SENTINEL')
            output = Path(folder)/'review.zip'
            with patch.object(delivery, 'ROOT', root), patch.dict(os.environ, {'LEPKA_MAIL_API_KEY': 'PRIVATE_SENTINEL'}):
                delivery.prepareReview(output)
            with ZipFile(output) as archive:
                prefix = 'lepka-helper-' + delivery.APP_VERSION + '/'
                names = archive.namelist()
                self.assertFalse(any(name.endswith(('.db','.key','.env','private.py')) for name in names))
                for name in names:
                    self.assertNotIn(b'PRIVATE_SENTINEL', archive.read(name))
                self.assertEqual(json.loads(archive.read(prefix+'assets/client_config.json')), {'apiBaseUrl': ''})
                manifest = json.loads(archive.read(prefix+'REVIEW_MANIFEST.json'))
                for name, expected in manifest['files'].items():
                    self.assertEqual(hashlib.sha256(archive.read(prefix+name)).hexdigest(), expected)
                before = output.read_bytes()
                with patch.object(delivery, 'ROOT', root), self.assertRaises(FileExistsError):
                    delivery.prepareReview(output)
                self.assertEqual(output.read_bytes(), before)


class ReviewUiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        for target in ('account_gateway.getApiUrl', 'views.auth_view.getApiUrl', 'views.profile_tab.getApiUrl', 'main.getApiUrl'):
            mode = patch(target, return_value='')
            mode.start()
            self.addCleanup(mode.stop)
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        path = patch.object(db, 'DATABASE_PATH', Path(self.folder.name)/'test.db')
        path.start()
        self.addCleanup(path.stop)
        state = patch.object(app_state, 'STATE_FILE', Path(self.folder.name)/'state.json')
        state.start()
        self.addCleanup(state.stop)
        db.initializeDatabase()
        auth_service.ensureDemoUser()
        self.user = auth_service.loginUser('test@email.com', 'Test123456')[2]
        self.page = ft.Page(MemoryConnection(), 'review', asyncio.get_running_loop())
        self.page.theme_mode = ft.ThemeMode.LIGHT
        self.page.session.set('currentUser', self.user)
        self.page.go = lambda route: setattr(self.page, 'route', route)

    def mount(self, control):
        view = control if isinstance(control, ft.View) else ft.View('/test', controls=[control])
        self.page.views[:] = [view]
        self.page.update()
        return view

    def dialog(self):
        return next(item for item in reversed(self.page.overlay) if isinstance(item, ft.AlertDialog) and item.open)

    async def test_failed_tab_shows_retry_in_selected_tab_and_recovers(self):
        from views.home_view import createHomeView
        with patch('views.home_view.createSearchTab', side_effect=[ApiError('Сервер недоступен'), ft.Text('Поиск восстановлен')]):
            view = self.mount(createHomeView(self.page))
            nav = find(view, ft.NavigationBar)
            nav.selected_index = 1
            nav.on_change(SimpleNamespace(control=nav))
            self.assertTrue(any(isinstance(item, ft.Text) and item.value == 'Не удалось открыть раздел' for item in walk(view)))
            self.assertFalse(any(isinstance(item, ft.Text) and item.value.startswith('Привет,') for item in walk(view)))
            find(view, ft.ElevatedButton, text='Повторить загрузку').on_click(None)
            self.assertTrue(any(isinstance(item, ft.Text) and item.value == 'Поиск восстановлен' for item in walk(view)))
            self.assertEqual(nav.selected_index, 1)
            self.assertIsNotNone(self.page.session.get('currentUser'))

    async def test_initial_feed_error_keeps_navigation_and_retry_rechecks_session(self):
        from views.home_view import createHomeView
        with patch('views.home_view.createHomeTab', side_effect=ApiError('Сервер недоступен')):
            view = self.mount(createHomeView(self.page))
        self.assertEqual(len(find(view, ft.NavigationBar).destinations), 5)
        button = find(view, ft.ElevatedButton, text='Повторить загрузку')
        logoutPage(self.page)
        button.on_click(None)
        self.assertEqual(self.page.route, '/auth')
        self.assertIsNone(self.page.session.get('currentUser'))

    async def test_project_removal_can_be_cancelled_and_stale_confirmation_cannot_delete(self):
        from views.home_view import createProjectsTab
        project = projects.saveProject(self.user['userId'], 'Проверка удаления', 'Другое', '', '')[2]
        view = self.mount(createProjectsTab(self.page, self.user))
        button = find(view, ft.IconButton, icon=ft.Icons.DELETE)
        button.on_click(None)
        self.assertIsNotNone(db.getProjectById(project, self.user['userId']))
        find(self.dialog(), ft.TextButton, text='Отмена').on_click(None)
        self.assertIsNotNone(db.getProjectById(project, self.user['userId']))
        button.on_click(None)
        confirm = find(self.dialog(), ft.ElevatedButton, text='Подтвердить удаление').on_click
        logoutPage(self.page)
        confirm(None)
        self.assertIsNotNone(db.getProjectById(project, self.user['userId']))

    async def test_theme_save_preserves_hidden_language_notification_preferences(self):
        from views.profile_tab import createProfileTab
        profile_service.saveUserSettings(self.user['userId'], 'light', 'en', False)
        view = self.mount(createProfileTab(self.page, self.user['nickname'], self.user['email']))
        self.assertFalse(any(isinstance(item, ft.Dropdown) and item.label == 'Язык приложения' for item in walk(view)))
        find(view, ft.Dropdown, label='Тема приложения').value = 'dark'
        find(view, ft.ElevatedButton, text='Сохранить настройки').on_click(None)
        profile = profile_service.getUserProfile(self.user['userId'])
        self.assertEqual(profile['themeMode'], 'dark')
        self.assertEqual(profile['languageCode'], 'en')
        self.assertFalse(profile['notificationsEnabled'])

    async def test_material_and_favorite_checkboxes_echo_changes_and_save(self):
        from views.home_view import createSearchTab
        from views.profile_tab import createProfileTab
        from lesson_service import getUserLessonState
        view = self.mount(createSearchTab(self.page, self.user))
        find(view, ft.TextButton, text='Открыть').on_click(None)
        checkbox = next(item for item in walk(view) if isinstance(item, ft.Checkbox) and item.label != 'Шаг выполнен')
        checkbox.value = True
        with patch.object(self.page, 'update', wraps=self.page.update) as updated:
            checkbox.on_change(SimpleNamespace(control=checkbox))
            updated.assert_called()
        self.assertEqual(getUserLessonState(self.user['userId'], 1)['checkedMaterials'], [0])
        view = self.mount(createProfileTab(self.page, self.user['nickname'], self.user['email']))
        favorite = find(view, ft.Checkbox, label='Белый')
        favorite.value = True
        favorite.on_change(SimpleNamespace(control=favorite))
        find(view, ft.ElevatedButton, text='Сохранить профиль').on_click(None)
        self.assertEqual(profile_service.getUserProfile(self.user['userId'])['favoriteColors'], ['Белый'])

    async def test_auth_has_no_nonworking_buttons_and_policy_does_not_accept_itself(self):
        from views.auth_view import createAuthView
        view = self.mount(createAuthView(self.page))
        self.assertFalse(any(isinstance(item, ft.OutlinedButton) and item.text == 'Войти через Google' for item in walk(view)))
        self.assertFalse(any(isinstance(item, ft.Switch) for item in walk(view)))
        tabs = find(view, ft.Tabs)
        tabs.selected_index = 1
        tabs.on_change(SimpleNamespace(control=tabs))
        find(view, ft.TextButton, text='Условия использования и данные').on_click(None)
        self.assertFalse(find(view, ft.Checkbox).value)
        find(self.dialog(), ft.TextButton, text='Понятно').on_click(None)
        self.assertFalse(find(view, ft.Checkbox).value)


if __name__ == '__main__':
    unittest.main()
