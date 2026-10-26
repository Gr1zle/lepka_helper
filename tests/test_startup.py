"""Регрессии запуска. Flet настоящий, только транспорт Flutter заменён на память."""
import asyncio
import hashlib
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import flet as ft
from flet.core.connection import Connection

import app_state
import database
ORIGINAL_DATABASE_PATH = database.DATABASE_PATH
from auth_service import ensureDemoUser, loginUser, registerUser, changePasswordByEmail
from profile_service import changeUserPassword
from password_service import checkPassword
from main import main
from views.auth_view import createAuthView
from views.home_view import createHomeView, createProjectsTab
import project_service as projects
from views.onboarding_view import createOnboardingView
from views.splash_view import createSplashView


class MemoryConnection(Connection):
    def __init__(self):
        super().__init__()
        self.next_id = 0
        self.page_url = 'http://127.0.0.1:8550'

    def send_commands(self, session_id, commands):
        results = []
        for command in commands:
            if command.name == 'add':
                ids = []
                for _ in command.commands:
                    self.next_id += 1
                    ids.append(str(self.next_id))
                results.append(' '.join(ids))
        return SimpleNamespace(results=results)


def walk(control):
    yield control
    for child in control._get_children():
        yield from walk(child)


def find(root, cls, **attrs):
    return next(c for c in walk(root) if isinstance(c, cls)
                and all(getattr(c, k, None) == v for k, v in attrs.items()))


class StartupTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        folder = Path(self.temp.name)
        self.db_patch = patch.object(database, 'DATABASE_PATH', folder/'test.db')
        self.state_patch = patch.object(app_state, 'STATE_FILE', folder/'state.json')
        self.db_patch.start()
        self.state_patch.start()
        database.initializeDatabase()
        self.user = ensureDemoUser()
        self.page = ft.Page(MemoryConnection(), 'test', asyncio.get_event_loop())
        self.page.theme_mode = ft.ThemeMode.LIGHT
        self.page.session.set('currentUser', self.user)
        self.page.update()

    def tearDown(self):
        self.db_patch.stop()
        self.state_patch.stop()
        self.temp.cleanup()

    def mount(self, view):
        self.page.views.clear()
        self.page.views.append(view)
        self.page.update()
        return view

    async def test_all_tabs_serialize_in_both_themes(self):
        for theme in (ft.ThemeMode.LIGHT, ft.ThemeMode.DARK):
            self.page.theme_mode = theme
            view = self.mount(createHomeView(self.page))
            nav = find(view, ft.NavigationBar)
            self.assertEqual(len(nav.destinations), 5)
            for index in range(5):
                nav.selected_index = index
                nav.on_change(SimpleNamespace(control=nav))
                self.page.update()

    async def test_project_form_rejects_bad_deadline_and_accepts_empty(self):
        view = self.mount(ft.View('/projects', controls=[createProjectsTab(self.page, self.user)]))
        find(view, ft.TextField, label='Название проекта').value = 'Тестовый котик'
        deadline = find(view, ft.TextField, label='Дедлайн')
        deadline.value = 'НЕ ДАТА'
        save = find(view, ft.ElevatedButton, text='Сохранить проект')
        save.on_click(None)
        self.assertEqual(projects.getUserProjects(self.user['userId']), [])
        snacks = [c for c in self.page.overlay if isinstance(c, ft.SnackBar)]
        self.assertIn('ДД.ММ.ГГГГ', snacks[-1].content.value)
        self.assertEqual(deadline.value, 'НЕ ДАТА')
        deadline.value = ''
        save.on_click(None)
        self.assertEqual(len(projects.getUserProjects(self.user['userId'])), 1)
        self.assertTrue(any(isinstance(c, ft.Text) and 'Без дедлайна' in (c.value or '')
                            for c in walk(view)))

    async def test_project_step_and_delete_handlers(self):
        userId = self.user['userId']
        projectId = projects.saveProject(userId, 'Котик', 'Животные', '', '')[2]
        view = self.mount(ft.View('/projects', controls=[createProjectsTab(self.page, self.user)]))
        find(view, ft.TextField, label='Новый этап').value = 'Слепить основу'
        find(view, ft.IconButton, icon=ft.Icons.ADD_CIRCLE).on_click(None)
        self.assertEqual(len(projects.getProjectSteps(projectId, userId)), 1)
        checkbox = find(view, ft.Checkbox)
        checkbox.value = True
        checkbox.on_change(SimpleNamespace(control=checkbox))
        self.assertEqual(projects.getUserProjects(userId)[0]['progressPercent'], 100)
        find(view, ft.IconButton, icon=ft.Icons.DELETE_OUTLINE).on_click(None)
        self.assertEqual(projects.getProjectSteps(projectId, userId), [])
        # Удаление проекта проверяем с этапом, а не только с пустой карточкой.
        find(view, ft.TextField, label='Новый этап').value = 'Слепить уши'
        find(view, ft.IconButton, icon=ft.Icons.ADD_CIRCLE).on_click(None)
        find(view, ft.IconButton, icon=ft.Icons.DELETE).on_click(None)
        self.assertEqual(projects.getUserProjects(userId), [])
        connection = database.getConnection()
        try:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM projectSteps').fetchone()[0], 0)
        finally:
            connection.close()

    async def test_onboarding_saves_completion(self):
        view = self.mount(createOnboardingView(self.page))
        button = next(c for c in walk(view) if isinstance(c, ft.ElevatedButton))
        for _ in range(4):
            button.on_click(None)
        self.assertTrue(app_state.getAppState('isOnboardingCompleted'))
        self.assertEqual(self.page.route, '/auth')

    async def test_auth_errors_are_mounted_snackbars(self):
        view = self.mount(createAuthView(self.page))
        find(view, ft.TextField, label='Пароль').value = 'wrong'
        find(view, ft.ElevatedButton, text='Войти').on_click(None)
        snacks = [c for c in self.page.overlay if isinstance(c, ft.SnackBar)]
        self.assertTrue(snacks[-1].open)
        self.assertIn('Неверный', snacks[-1].content.value)

    async def test_login_reaches_home_route(self):
        view = self.mount(createAuthView(self.page))
        find(view, ft.ElevatedButton, text='Войти').on_click(None)
        self.assertEqual(self.page.route, '/home')
        self.assertEqual(self.page.session.get('currentUser')['userId'], self.user['userId'])

    async def test_recovery_dialog_opens_and_closes(self):
        view = self.mount(createAuthView(self.page))
        find(view, ft.TextButton, text='Забыли пароль?').on_click(None)
        dialog = next(c for c in self.page.overlay if isinstance(c, ft.AlertDialog))
        self.assertTrue(dialog.open)
        find(dialog, ft.TextButton, text='Отмена').on_click(None)
        self.assertFalse(dialog.open)

    async def test_recovery_requires_issued_code(self):
        view = self.mount(createAuthView(self.page))
        find(view, ft.TextButton, text='Забыли пароль?').on_click(None)
        dialog = next(c for c in self.page.overlay if isinstance(c, ft.AlertDialog))
        find(dialog, ft.TextField, label='Новый пароль').value = 'NewPass123'
        find(dialog, ft.TextField, label='Повторите новый пароль').value = 'NewPass123'
        find(dialog, ft.ElevatedButton, text='Сменить пароль').on_click(None)
        self.assertTrue(loginUser('test@email.com', 'Test123456')[0])
        self.assertFalse(loginUser('test@email.com', 'NewPass123')[0])

    async def test_account_delete_confirmation_can_cancel(self):
        view = self.mount(createHomeView(self.page))
        nav = find(view, ft.NavigationBar)
        nav.selected_index = 4
        nav.on_change(SimpleNamespace(control=nav))
        field = next(c for c in walk(view) if isinstance(c, ft.TextField) and c.password and 'удал' in (c.label or '').lower())
        field.value = 'Test123456'
        find(view, ft.ElevatedButton, text='Удалить аккаунт').on_click(None)
        dialog = next(c for c in self.page.overlay if isinstance(c, ft.AlertDialog))
        self.assertTrue(dialog.open)
        find(dialog, ft.TextButton, text='Отмена').on_click(None)
        self.assertFalse(dialog.open)
        self.assertTrue(loginUser('test@email.com', 'Test123456')[0])

    async def test_splash_constructs_with_real_flet(self):
        with patch.object(self.page, 'run_task') as run_task:
            view = self.mount(createSplashView(self.page))
            self.assertEqual(view.route, '/')
            run_task.assert_called_once()

    async def test_application_routes_from_start_to_login_and_home(self):
        async def wait_for_route(route):
            for _ in range(100):
                if self.page.views and self.page.views[-1].route == route:
                    return
                await asyncio.sleep(0.01)
            self.fail(f'Экран не загрузился: {route}')

        main(self.page)
        await wait_for_route('/')
        self.page.go('/auth')
        await wait_for_route('/auth')
        find(self.page.views[-1], ft.ElevatedButton, text='Войти').on_click(None)
        await wait_for_route('/home')
        self.assertEqual(len(find(self.page.views[-1], ft.NavigationBar).destinations), 5)

    async def test_registration_password_change_login_and_recovery(self):
        success, _, user = registerUser('student@example.com', 'Student123', 'Student123', 'student', True)
        self.assertTrue(success)
        self.assertTrue(loginUser('student@example.com', 'Student123')[0])
        self.assertTrue(changeUserPassword(user['userId'], 'Student123', 'NewPass123', 'NewPass123')[0])
        self.assertFalse(loginUser('student@example.com', 'Student123')[0])
        self.assertTrue(loginUser('student@example.com', 'NewPass123')[0])
        self.assertTrue(changePasswordByEmail('student@example.com', 'ResetPass123', 'ResetPass123')[0])
        self.assertTrue(loginUser('student@example.com', 'ResetPass123')[0])
        self.assertFalse(loginUser('student@example.com', 'NewPass123')[0])

    async def test_legacy_password_formats_still_work(self):
        salt = 'legacy-salt'
        password = 'Legacy123'
        hashes = [hashlib.sha256(f'{password}{salt}'.encode()).hexdigest(),
                  hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000).hex()]
        for stored in hashes:
            self.assertTrue(checkPassword(password, stored, salt))
            self.assertFalse(checkPassword('wrong', stored, salt))

    async def test_database_does_not_follow_working_directory(self):
        self.assertTrue(ORIGINAL_DATABASE_PATH.is_absolute())
        previous = Path.cwd()
        try:
            os.chdir(self.temp.name)
            database.initializeDatabase()
            self.assertTrue(loginUser('test@email.com', 'Test123456')[0])
        finally:
            os.chdir(previous)


if __name__ == '__main__':
    unittest.main()
