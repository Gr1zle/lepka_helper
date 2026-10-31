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
from auth_service import (ensureDemoUser, loginUser, registerUser, changePasswordByEmail,
                          requestRegistrationCode, requestPasswordRecovery)
from account_security import confirmRegistration, getSessionUser
from ui_helpers import logoutPage
from profile_service import changeUserPassword
from password_service import checkPassword
from main import main
from views.auth_view import createAuthView
from views.home_view import createHomeView, createProjectsTab
import project_service as projects
from image_fixtures import photo
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
        for target in ('account_gateway.getApiUrl', 'main.getApiUrl', 'device_session.getApiUrl',
                       'views.auth_view.getApiUrl', 'views.profile_tab.getApiUrl'):
            modePatch = patch(target, return_value='')
            modePatch.start()
            self.addCleanup(modePatch.stop)
        self.temp = tempfile.TemporaryDirectory()
        folder = Path(self.temp.name)
        devicePatch = patch('device_session.SESSION_FILE', folder/'device_session.json')
        devicePatch.start()
        self.addCleanup(devicePatch.stop)
        self.db_patch = patch.object(database, 'DATABASE_PATH', folder/'test.db')
        self.state_patch = patch.object(app_state, 'STATE_FILE', folder/'state.json')
        self.db_patch.start()
        self.state_patch.start()
        database.initializeDatabase()
        ensureDemoUser()
        self.user = loginUser("test@email.com", "Test123456")[2]
        self.connection = MemoryConnection()
        self.page = ft.Page(self.connection, 'test', asyncio.get_event_loop())
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

    async def test_model_view_rotates_zooms_lights_and_saves_favorite(self):
        import flet.canvas as cv
        from views.model_view import createModelView
        from model_service import favoriteModelIds
        view=self.mount(createModelView(self.page,'cat'))
        canvas=find(view,cv.Canvas)
        def snapshot():return [(s.elements[0].x,s.elements[0].y,s.paint.color) for s in canvas.shapes]
        before=snapshot()
        find(view,ft.TextButton,text='Слева').on_click(None)
        self.assertNotEqual(snapshot(),before)
        before=snapshot()
        find(view,ft.TextButton,text='Увеличить').on_click(None)
        self.assertNotEqual(snapshot(),before)
        light=next(c for c in walk(view) if isinstance(c,ft.Slider) and c.min==-180)
        colors=[s.paint.color for s in canvas.shapes]
        light.value=120;light.on_change(None)
        self.assertNotEqual([s.paint.color for s in canvas.shapes],colors)
        count=len(canvas.shapes)
        edges=find(view,ft.Checkbox,label='Показать рёбра')
        edges.value=True;edges.on_change(None)
        self.assertEqual(len(canvas.shapes),count*2)
        find(view,ft.TextButton,text='Модель в избранное').on_click(None)
        self.assertEqual(favoriteModelIds(self.user['userId']),{'cat'})

    async def test_planner_calendar_filter_and_read_state_survive_reopening(self):
        from datetime import date
        from project_service import saveProject
        from project_planner import syncProjectReminders
        from views.project_planner import createProjectPlanner
        saveProject(self.user['userId'],'Сегодня лепим котика','Животные',date.today().strftime('%d.%m.%Y'),'')
        view=self.mount(createProjectPlanner(self.page))
        self.assertIsNotNone(find(view,ft.Text,value='Сегодня лепим котика'))
        find(view,ft.TextButton,text='Прочитать все напоминания').on_click(None)
        self.assertTrue(all(r['isRead'] for r in syncProjectReminders(self.user['userId'])))
        view=self.mount(createProjectPlanner(self.page))
        self.assertIsNotNone(find(view,ft.Text,value='Напоминания · непрочитано: 0'))
        filters=find(view,ft.Dropdown,label='Показать проекты')
        filters.value='Без срока';filters.on_change(None)
        self.assertIsNotNone(find(view,ft.Text,value='На выбранный период проектов нет.'))

    async def test_planner_project_link_filters_own_project_and_can_show_all_again(self):
        from project_service import saveProject
        from views.project_planner import createProjectPlanner
        from views.home_view import createProjectsTab
        first=saveProject(self.user['userId'],'Первый проект','Другое','','')[2]
        saveProject(self.user['userId'],'Второй проект','Другое','','')
        view=self.mount(createProjectPlanner(self.page))
        filters=find(view,ft.Dropdown,label='Показать проекты');filters.value='Все активные';filters.on_change(None)
        find(view,ft.TextButton,text='К проекту').on_click(None)
        self.assertEqual(self.page.session.get('plannerProject')['projectId'],first)
        view=self.mount(ft.View('/home',controls=[createProjectsTab(self.page,self.user)]))
        names=[c.value for c in walk(view) if isinstance(c,ft.Text)]
        self.assertIn('Первый проект',names);self.assertNotIn('Второй проект',names)
        find(view,ft.TextButton,text='Показать все проекты').on_click(None)
        self.assertIn('Второй проект',[c.value for c in walk(view) if isinstance(c,ft.Text)])

    async def test_revoked_planner_handlers_cannot_read_notices_or_open_projects(self):
        from datetime import date
        from project_service import saveProject
        from project_planner import syncProjectReminders
        from views.project_planner import createProjectPlanner
        from account_security import logoutUser
        saveProject(self.user['userId'],'Важный проект','Другое',date.today().strftime('%d.%m.%Y'),'')
        view=self.mount(createProjectPlanner(self.page))
        read=find(view,ft.TextButton,text='Прочитать все напоминания').on_click
        opening=find(view,ft.TextButton,text='К проекту').on_click
        logoutUser(self.user['sessionToken'])
        read(None);opening(None)
        self.assertIsNone(self.page.session.get('plannerProject'))
        self.assertTrue(all(not r['isRead'] for r in syncProjectReminders(self.user['userId'])))

    async def test_lesson_media_changes_with_step_and_can_be_enlarged(self):
        from views.home_view import createSearchTab
        view=self.mount(ft.View('/search',controls=[createSearchTab(self.page,self.user)]))
        find(view,ft.TextButton,text='Открыть').on_click(None)
        self.assertTrue(find(view,ft.Image).src.endswith('lesson_1_1.png'))
        find(view,ft.ElevatedButton,text='Следующий').on_click(None)
        self.assertTrue(find(view,ft.Image).src.endswith('lesson_1_2.png'))
        find(view,ft.TextButton,text='Увеличить схему').on_click(None)
        dialog=next(c for c in self.page.overlay if isinstance(c,ft.AlertDialog) and c.open)
        self.assertIsNotNone(find(dialog,ft.InteractiveViewer))

    async def test_model_route_back_preserves_lesson_draft_without_saving_it(self):
        from lesson_library import getLessonNote
        async def waitRoute(route):
            for _ in range(200):
                if self.page.views and self.page.views[-1].route==route:return
                await asyncio.sleep(.01)
            self.fail('Route not ready: '+route)
        main(self.page)
        # Дождаться первого события /: иначе оно может догнать /home и заменить
        # уже переключённую вкладку поиска вторым экземпляром домашнего экрана.
        await waitRoute('/')
        self.page.go('/home');await waitRoute('/home')
        nav=find(self.page.views[-1],ft.NavigationBar)
        nav.selected_index=1;nav.on_change(SimpleNamespace(control=nav))
        find(self.page.views[-1],ft.TextButton,text='Открыть').on_click(None)
        note=find(self.page.views[-1],ft.TextField,label='Личная заметка к уроку')
        note.value='Черновик при осмотре модели';note.on_change(SimpleNamespace(control=note))
        find(self.page.views[-1],ft.TextButton,text='3D этой фигурки').on_click(None)
        await waitRoute('/models/cat')
        self.page.views[-1].appbar.leading.on_click(None)
        await waitRoute('/home')
        self.assertEqual(find(self.page.views[-1],ft.TextField,label='Личная заметка к уроку').value,'Черновик при осмотре модели')
        self.assertEqual(getLessonNote(self.user['userId'],1),'')

    async def test_lesson_favorite_note_draft_and_share_are_preserved(self):
        from views.home_view import createSearchTab
        from lesson_library import favoriteLessonIds,getLessonNote
        view = self.mount(ft.View('/search',controls=[createSearchTab(self.page,self.user)]))
        find(view,ft.TextButton,text='Открыть').on_click(None)
        find(view,ft.TextButton,text='В избранное').on_click(None)
        self.assertEqual(favoriteLessonIds(self.user['userId']),{1})
        field = find(view,ft.TextField,label='Личная заметка к уроку')
        field.value = 'Тонкие ушки; PRIVATE_NOTE'
        field.on_change(SimpleNamespace(control=field))
        find(view,ft.ElevatedButton,text='Следующий').on_click(None)
        field.value=''
        field.on_change(SimpleNamespace(control=field))
        self.assertEqual(find(view,ft.TextField,label='Личная заметка к уроку').value,'Тонкие ушки; PRIVATE_NOTE')
        self.assertEqual(getLessonNote(self.user['userId'],1),'')
        find(view,ft.ElevatedButton,text='Сохранить заметку').on_click(None)
        self.assertEqual(getLessonNote(self.user['userId'],1),'Тонкие ушки; PRIVATE_NOTE')
        with patch.object(self.page,'set_clipboard') as clipboard:
            find(view,ft.TextButton,text='Скопировать урок').on_click(None)
            self.assertIn('Милый котик',clipboard.call_args.args[0])
            self.assertNotIn('PRIVATE_NOTE',clipboard.call_args.args[0])
        find(view,ft.TextButton,text='← Назад к поиску').on_click(None)
        find(view,ft.TextButton,text='Открыть').on_click(None)
        self.assertEqual(find(view,ft.TextField,label='Личная заметка к уроку').value,'Тонкие ушки; PRIVATE_NOTE')

    async def test_back_to_search_rebuilds_controls_and_ignores_late_search_event(self):
        view=self.mount(createHomeView(self.page))
        nav=find(view,ft.NavigationBar)
        nav.selected_index=1
        nav.on_change(SimpleNamespace(control=nav))
        field=find(view,ft.TextField,label='Поиск уроков и работ')
        field.value='кот'
        find(view,ft.ElevatedButton,text='Найти').on_click(None)
        find(view,ft.TextButton,text='Открыть').on_click(None)
        field.value=''
        field.on_change(SimpleNamespace(control=field))
        find(view,ft.TextButton,text='← Назад к поиску').on_click(None)
        restored=find(view,ft.TextField,label='Поиск уроков и работ')
        self.assertIsNot(restored,field)
        self.assertEqual(restored.value,'кот')
        self.assertIsNotNone(find(view,ft.ElevatedButton,text='Найти'))

    async def test_search_history_is_submitted_only_and_query_survives_tab_recreation(self):
        from views.home_view import createSearchTab
        from lesson_library import recentSearches
        view = self.mount(ft.View('/search',controls=[createSearchTab(self.page,self.user)]))
        field = find(view,ft.TextField,label='Поиск уроков и работ')
        field.value='кот'
        field.on_change(SimpleNamespace(control=field))
        self.assertEqual(recentSearches(self.user['userId']),[])
        find(view,ft.ElevatedButton,text='Найти').on_click(None)
        self.assertEqual(recentSearches(self.user['userId']),['кот'])
        view = self.mount(ft.View('/search',controls=[createSearchTab(self.page,self.user)]))
        self.assertEqual(find(view,ft.TextField,label='Поиск уроков и работ').value,'кот')
        find(view,ft.TextButton,text='Сбросить фильтры').on_click(None)
        self.assertEqual(find(view,ft.TextField,label='Поиск уроков и работ').value,'')

    async def test_profile_favorite_navigation_restores_lesson_and_search_tab(self):
        from lesson_library import saveLessonFavorite
        saveLessonFavorite(self.user['userId'],1,True)
        view = self.mount(createHomeView(self.page))
        nav=find(view,ft.NavigationBar)
        nav.selected_index=4
        nav.on_change(SimpleNamespace(control=nav))
        find(view,ft.TextButton,text='Избранные уроки').on_click(None)
        dialog=next(c for c in self.page.overlay if isinstance(c,ft.AlertDialog) and c.open)
        find(dialog,ft.TextButton,text='Милый котик из пластилина').on_click(None)
        self.assertEqual(find(view,ft.NavigationBar).selected_index,1)
        self.assertIsNotNone(find(view,ft.TextField,label='Личная заметка к уроку'))
        find(view,ft.TextButton,text='← Назад к поиску').on_click(None)
        self.assertTrue(any(isinstance(c,ft.TextButton) and c.text=='Открыть' for c in walk(view)))

    async def test_revoked_lesson_handlers_cannot_write_note_favorite_or_history(self):
        from account_security import logoutUser
        from lesson_library import getLessonNote,favoriteLessonIds,recentSearches
        from views.home_view import createSearchTab
        view=self.mount(ft.View('/search',controls=[createSearchTab(self.page,self.user)]))
        field=find(view,ft.TextField,label='Поиск уроков и работ')
        field.value='дракон'
        search=find(view,ft.ElevatedButton,text='Найти')
        find(view,ft.TextButton,text='Открыть').on_click(None)
        note=find(view,ft.TextField,label='Личная заметка к уроку')
        note.value='Не должна сохраниться'
        save=find(view,ft.ElevatedButton,text='Сохранить заметку')
        favorite=find(view,ft.TextButton,text='В избранное')
        logoutUser(self.user['sessionToken'])
        save.on_click(None)
        favorite.on_click(None)
        search.on_click(None)
        self.assertEqual(getLessonNote(self.user['userId'],1),'')
        self.assertEqual(favoriteLessonIds(self.user['userId']),set())
        self.assertEqual(recentSearches(self.user['userId']),[])

    async def test_search_keeps_builtin_lessons_when_community_fails_and_offline_skips_api(self):
        from views.home_view import createSearchTab
        from api_client import ApiError
        with patch('views.home_view.CommunityClient') as client:
            client.return_value.getPosts.side_effect=ApiError('Сеть недоступна')
            view=self.mount(ft.View('/search',controls=[createSearchTab(self.page,self.user)]))
            self.assertIsNotNone(find(view,ft.TextButton,text='Открыть'))
            offline=find(view,ft.Checkbox,label='Только встроенные уроки и модели (офлайн)')
            offline.value=True
            client.return_value.getPosts.reset_mock()
            offline.on_change(None)
            client.return_value.getPosts.assert_not_called()
            self.assertEqual(len([c for c in walk(view) if isinstance(c,ft.TextButton) and c.text=='Открыть']),6)

    async def test_calculator_and_timer_controls_work(self):
        from views.home_view import createColorsTab
        view = self.mount(ft.View('/colors', controls=[createColorsTab(self.page, self.user)]))
        find(view, ft.TextButton, text='Количество пластилина').on_click(None)
        dialog = next(c for c in self.page.overlay if isinstance(c, ft.AlertDialog) and c.open)
        find(dialog, ft.TextField, label='Объём, см³').value = '100'
        find(dialog, ft.ElevatedButton, text='Рассчитать массу').on_click(None)
        self.assertTrue(any(isinstance(c, ft.Text) and '176.00' in (c.value or '') for c in walk(dialog)))
        find(dialog, ft.TextButton, text='Закрыть').on_click(None)
        with patch.object(self.page, 'run_task'):
            find(view, ft.TextButton, text='Таймер').on_click(None)
        dialog = next(c for c in self.page.overlay if isinstance(c, ft.AlertDialog) and c.open)
        find(dialog, ft.TextField, label='Длительность, минуты').value = '1'
        find(dialog, ft.ElevatedButton, text='Старт / продолжить').on_click(None)
        self.assertTrue(self.page.session.get('clayTimer').running)
        find(dialog, ft.TextButton, text='Пауза').on_click(None)
        self.assertFalse(self.page.session.get('clayTimer').running)
        find(dialog, ft.TextButton, text='Сброс').on_click(None)
        self.assertEqual(self.page.session.get('clayTimer').seconds(),60)

    async def test_json_import_previews_and_creates_copy_only_after_confirmation(self):
        from project_archive import exportProject
        projectId = projects.saveProject(self.user['userId'],'Перенос','Животные','','Заметки')[2]
        path = Path(self.temp.name)/'project.json'
        path.write_bytes(exportProject(projectId,self.user['userId']))
        view = self.mount(ft.View('/projects', controls=[createProjectsTab(self.page,self.user)]))
        find(view, ft.ElevatedButton, text='Импорт JSON').on_click(None)
        picker = next(c for c in self.page.overlay if isinstance(c,ft.FilePicker))
        picker.on_result(SimpleNamespace(control=picker,files=[SimpleNamespace(name='project.json',size=path.stat().st_size,path=str(path))]))
        self.assertEqual(len(projects.getUserProjects(self.user['userId'])),1)
        dialog = next(c for c in self.page.overlay if isinstance(c,ft.AlertDialog) and c.open)
        find(dialog,ft.ElevatedButton,text='Импортировать проект').on_click(None)
        self.assertEqual(len(projects.getUserProjects(self.user['userId'])),2)
        find(dialog,ft.ElevatedButton,text='Импортировать проект').on_click(None)
        self.assertEqual(len(projects.getUserProjects(self.user['userId'])),2)

    async def test_android_json_backup_can_be_saved_and_restored_inside_app(self):
        from project_backups import listBackups
        self.page._set_attr('platform','android')
        projects.saveProject(self.user['userId'],'Копия','Животные','','Заметки')
        with patch('project_backups.DATA_DIRECTORY',Path(self.temp.name)):
            view = self.mount(ft.View('/projects',controls=[createProjectsTab(self.page,self.user)]))
            find(view,ft.TextButton,text='Экспорт JSON').on_click(None)
            names = listBackups(self.user['userId'])
            self.assertEqual(len(names),1)
            find(view,ft.TextButton,text='Копии в приложении').on_click(None)
            dialog = next(c for c in self.page.overlay if isinstance(c,ft.AlertDialog) and c.open)
            find(dialog,ft.TextButton,text=names[0]).on_click(None)
            preview = next(c for c in self.page.overlay if isinstance(c,ft.AlertDialog) and c.open)
            find(preview,ft.ElevatedButton,text='Импортировать проект').on_click(None)
            self.assertEqual(len(projects.getUserProjects(self.user['userId'])),2)

    async def test_project_step_order_can_be_cancelled_or_saved_after_drag(self):
        projectId = projects.saveProject(self.user['userId'], 'Порядок', 'Животные', '', '')[2]
        ids = [projects.saveProjectStep(projectId, name, self.user['userId'])[2] for name in ('Основа', 'Детали', 'Сборка')]
        view = self.mount(ft.View('/projects', controls=[createProjectsTab(self.page, self.user)]))
        find(view, ft.TextButton, text='Порядок этапов').on_click(None)
        dialog = next(c for c in self.page.overlay if isinstance(c, ft.AlertDialog) and c.open)
        find(dialog, ft.IconButton, tooltip='Этап ниже').on_click(None)
        self.assertEqual([s['stepId'] for s in projects.getProjectSteps(projectId, self.user['userId'])], ids)
        find(dialog, ft.TextButton, text='Отмена').on_click(None)
        self.assertEqual([s['stepId'] for s in projects.getProjectSteps(projectId, self.user['userId'])], ids)
        find(view, ft.TextButton, text='Порядок этапов').on_click(None)
        dialog = next(c for c in self.page.overlay if isinstance(c, ft.AlertDialog) and c.open)
        find(dialog, ft.ReorderableListView).on_reorder(SimpleNamespace(old_index=2, new_index=0))
        find(dialog, ft.ElevatedButton, text='Сохранить порядок').on_click(None)
        self.assertEqual([s['stepId'] for s in projects.getProjectSteps(projectId, self.user['userId'])], [ids[2], ids[0], ids[1]])

    async def test_old_step_order_dialog_cannot_save_after_logout(self):
        from account_security import logoutUser
        projectId = projects.saveProject(self.user['userId'], 'Порядок', 'Животные', '', '')[2]
        ids = [projects.saveProjectStep(projectId, name, self.user['userId'])[2] for name in ('Основа', 'Сборка')]
        view = self.mount(ft.View('/projects', controls=[createProjectsTab(self.page, self.user)]))
        find(view, ft.TextButton, text='Порядок этапов').on_click(None)
        dialog = next(c for c in self.page.overlay if isinstance(c, ft.AlertDialog) and c.open)
        find(dialog, ft.ReorderableListView).on_reorder(SimpleNamespace(old_index=0, new_index=1))
        logoutUser(self.user['sessionToken'])
        find(dialog, ft.ElevatedButton, text='Сохранить порядок').on_click(None)
        self.assertEqual([s['stepId'] for s in projects.getProjectSteps(projectId, self.user['userId'])], ids)

    async def test_profile_theme_switch_updates_the_current_background(self):
        view = self.mount(createHomeView(self.page))
        nav = find(view, ft.NavigationBar)
        nav.selected_index = 4
        nav.on_change(SimpleNamespace(control=nav))
        dropdown = find(view, ft.Dropdown, label='Тема приложения')
        dropdown.value = 'dark'
        find(view, ft.ElevatedButton, text='Сохранить настройки').on_click(None)
        self.assertEqual(self.page.theme_mode, ft.ThemeMode.DARK)
        self.assertEqual(view.bgcolor, ft.Colors.SURFACE)
        self.assertEqual(view.controls[0].bgcolor, ft.Colors.SURFACE)
        self.assertEqual(database.getUserByEmail('test@email.com')['themeMode'], 'dark')

    async def test_android_login_is_restored_after_restart_and_logout_forgets_it(self):
        import device_session
        self.page._set_attr('platform', 'android')
        view = self.mount(createAuthView(self.page))
        find(view, ft.ElevatedButton, text='Войти').on_click(None)
        self.assertIsNotNone(device_session.restoreDeviceSession(self.page))
        from profile_service import saveUserSettings
        saveUserSettings(self.user['userId'], 'dark', 'ru', False)
        self.page.session.clear()
        with patch.object(self.page, 'run_task'), patch.dict(os.environ, {'LEPKA_FORCE_LOCAL': '1'}):
            main(self.page)
        self.assertEqual(self.page.session.get('currentUser')['userId'], self.user['userId'])
        self.assertEqual(self.page.theme_mode, ft.ThemeMode.DARK)
        logoutPage(self.page)
        self.assertIsNone(device_session.restoreDeviceSession(self.page))

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
        step = projects.getProjectSteps(projectId, userId)[0]
        projects.saveProjectStepPhoto(projectId, step['stepId'], userId, photo())
        checkbox = find(view, ft.Checkbox)
        checkbox.value = True
        checkbox.on_change(SimpleNamespace(control=checkbox))
        self.assertEqual(projects.getUserProjects(userId)[0]['progressPercent'], 100)
        find(view, ft.IconButton, icon=ft.Icons.DELETE_OUTLINE).on_click(None)
        dialog = next(c for c in reversed(self.page.overlay) if isinstance(c, ft.AlertDialog) and c.open)
        find(dialog, ft.ElevatedButton, text='Подтвердить удаление').on_click(None)
        self.assertEqual(projects.getProjectSteps(projectId, userId), [])
        # Удаление проекта проверяем с этапом, а не только с пустой карточкой.
        find(view, ft.TextField, label='Новый этап').value = 'Слепить уши'
        find(view, ft.IconButton, icon=ft.Icons.ADD_CIRCLE).on_click(None)
        find(view, ft.IconButton, icon=ft.Icons.DELETE).on_click(None)
        dialog = next(c for c in reversed(self.page.overlay) if isinstance(c, ft.AlertDialog) and c.open)
        find(dialog, ft.ElevatedButton, text='Подтвердить удаление').on_click(None)
        self.assertEqual(projects.getUserProjects(userId), [])
        connection = database.getConnection()
        try:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM projectSteps').fetchone()[0], 0)
        finally:
            connection.close()

    async def test_stale_profile_handler_cannot_save_after_logout(self):
        from views.profile_tab import createProfileTab
        view = self.mount(ft.View('/profile', controls=[createProfileTab(self.page, self.user['nickname'], self.user['email'])]))
        field = find(view, ft.TextField, label='Никнейм')
        save = find(view, ft.ElevatedButton, text='Сохранить профиль')
        field.value = 'changed_name'
        logoutPage(self.page)
        save.on_click(None)
        self.assertIsNone(getSessionUser(self.user['sessionToken']))
        self.assertEqual(database.getUserByEmail(self.user['email'])['nickname'], self.user['nickname'])
        self.assertEqual(self.page.route, '/auth')

    async def test_stale_profile_handler_cannot_save_after_account_switch(self):
        from views.profile_tab import createProfileTab
        from password_service import createPasswordHash
        view = self.mount(ft.View('/profile', controls=[createProfileTab(self.page, self.user['nickname'], self.user['email'])]))
        find(view, ft.TextField, label='Никнейм').value = 'changed_name'
        save = find(view, ft.ElevatedButton, text='Сохранить профиль')
        passwordHash, salt = createPasswordHash('OtherPass123')
        database.createUser('other@example.com', passwordHash, salt, 'other')
        other = loginUser('other@example.com', 'OtherPass123')[2]
        self.page.session.set('currentUser', other)
        save.on_click(None)
        self.assertEqual(database.getUserByEmail(self.user['email'])['nickname'], self.user['nickname'])
        self.assertEqual(database.getUserByEmail(other['email'])['nickname'], 'other')
        self.assertEqual(self.page.session.get('currentUser')['userId'], other['userId'])

    async def test_revoked_session_cannot_navigate_to_private_tab(self):
        view = self.mount(createHomeView(self.page))
        nav = find(view, ft.NavigationBar)
        self.assertTrue(changeUserPassword(self.user['userId'], 'Test123456', 'Changed123', 'Changed123')[0])
        nav.selected_index = 3
        nav.on_change(SimpleNamespace(control=nav))
        self.assertEqual(self.page.route, '/auth')
        self.assertIsNone(self.page.session.get('currentUser'))

    async def test_recovery_dialog_uses_delivered_code_without_showing_it(self):
        view = self.mount(createAuthView(self.page))
        find(view, ft.TextButton, text='Забыли пароль?').on_click(None)
        dialog = next(c for c in self.page.overlay if isinstance(c, ft.AlertDialog))
        with patch('account_security.sendAccountCode') as mail:
            find(dialog, ft.OutlinedButton, text='Получить код').on_click(None)
            code = mail.call_args.args[1]
        self.assertFalse(any(isinstance(c, ft.Text) and code in (c.value or '') for c in walk(dialog)))
        find(dialog, ft.TextField, label='Код из письма').value = code
        find(dialog, ft.TextField, label='Новый пароль').value = 'Changed123'
        find(dialog, ft.TextField, label='Повторите новый пароль').value = 'Changed123'
        find(dialog, ft.ElevatedButton, text='Сменить пароль').on_click(None)
        self.assertFalse(dialog.open)
        self.assertFalse(loginUser(self.user['email'], 'Test123456')[0])
        self.assertTrue(loginUser(self.user['email'], 'Changed123')[0])

    async def test_registration_form_requires_confirmation_and_displays_field_errors(self):
        view = self.mount(createAuthView(self.page))
        tabs = find(view, ft.Tabs)
        tabs.selected_index = 1
        tabs.on_change(SimpleNamespace(control=tabs))
        register = find(view, ft.ElevatedButton, text='Зарегистрироваться')
        register.on_click(None)
        self.assertIsNotNone(find(view, ft.TextField, label='Никнейм').error_text)
        find(view, ft.TextField, label='Email').value = 'new@example.com'
        find(view, ft.TextField, label='Никнейм').value = 'new_user'
        find(view, ft.TextField, label='Пароль').value = 'NewPass123'
        find(view, ft.TextField, label='Подтверждение пароля').value = 'NewPass123'
        find(view, ft.Checkbox).value = True
        with patch('account_security.sendAccountCode') as mail:
            register.on_click(None)
            code = mail.call_args.args[1]
        self.assertFalse(loginUser('new@example.com', 'NewPass123')[0])
        dialog = next(c for c in self.page.overlay if isinstance(c, ft.AlertDialog))
        find(dialog, ft.TextField, label='Код из письма').value = code
        find(dialog, ft.ElevatedButton, text='Подтвердить email').on_click(None)
        self.assertFalse(dialog.open)
        self.assertTrue(loginUser('new@example.com', 'NewPass123')[0])

    async def test_email_change_dialog_and_account_delete_confirmation(self):
        from views.profile_tab import createProfileTab
        view = self.mount(ft.View('/profile', controls=[createProfileTab(self.page, self.user['nickname'], self.user['email'])]))
        find(view, ft.OutlinedButton, text='Изменить email').on_click(None)
        dialog = next(c for c in self.page.overlay if isinstance(c, ft.AlertDialog))
        find(dialog, ft.TextField, label='Новый email').value = 'changed@example.com'
        find(dialog, ft.TextField, label='Текущий пароль').value = 'Test123456'
        with patch('account_security.sendAccountCode') as mail:
            find(dialog, ft.OutlinedButton, text='Получить код').on_click(None)
            code = mail.call_args.args[1]
        find(dialog, ft.TextField, label='Код из письма').value = code
        find(dialog, ft.ElevatedButton, text='Подтвердить email').on_click(None)
        self.assertEqual(self.page.route, '/auth')
        self.assertIsNone(self.page.session.get('currentUser'))
        user = loginUser('changed@example.com', 'Test123456')[2]
        self.page.session.set('currentUser', user)
        view = self.mount(ft.View('/profile', controls=[createProfileTab(self.page, user['nickname'], user['email'])]))
        find(view, ft.TextField, label='Пароль для удаления аккаунта').value = 'Test123456'
        find(view, ft.ElevatedButton, text='Удалить аккаунт').on_click(None)
        self.assertIsNotNone(database.getUserByEmail('changed@example.com'))
        confirm = next(c for c in self.page.overlay if isinstance(c, ft.AlertDialog))
        find(confirm, ft.TextButton, text='Удалить').on_click(None)
        self.assertIsNone(database.getUserByEmail('changed@example.com'))
        self.assertIsNone(self.page.session.get('currentUser'))

    async def test_other_comments_remain_visible_under_deleted_post(self):
        from views.home_view import createPostCard
        from auth_service import deleteUserAccount
        from post_service import getCommunityPosts
        from password_service import createPasswordHash
        passwordHash, salt = createPasswordHash('OtherPass123')
        otherId = database.createUser('other@example.com', passwordHash, salt, 'other')
        post = database.createPost(self.user['userId'], 'Котик', 'Описание котика', 'Животные', '')
        database.createPostComment(post, otherId, 'Сохранённый чужой комментарий')
        self.assertTrue(deleteUserAccount(self.user['userId'], 'Test123456')[0])
        item = getCommunityPosts()[0]
        view = self.mount(ft.View('/post', controls=[createPostCard(self.page, item, None, lambda: None)]))
        self.assertEqual(find(view, ft.Text, value='Сохранённый чужой комментарий').value,
                         'Сохранённый чужой комментарий')
        self.assertTrue(item['isDeleted'])

    async def test_android_without_api_cannot_start_local_account_mode(self):
        with patch('main.getApiUrl', return_value=''):
            self.page._set_attr('platform', 'android')
            with patch('main.initializeDatabase') as initialize, patch('main.ensureDemoUser') as demo:
                main(self.page)
                initialize.assert_not_called()
                demo.assert_not_called()
            self.assertTrue(any(isinstance(control, ft.Text) and 'HTTPS' in (control.value or '')
                                for control in walk(self.page)))

    async def test_android_explicit_local_demo_starts_without_api(self):
        self.page._set_attr('platform', 'android')
        with patch.dict(os.environ, {'LEPKA_FORCE_LOCAL': '1'}), patch('main.getApiUrl', return_value=''):
            with patch('main.initializeDatabase') as initialize, patch('main.ensureDemoUser') as demo:
                main(self.page)
                initialize.assert_called_once()
                demo.assert_called_once()
        self.assertFalse(any(isinstance(control, ft.Text) and 'задайте HTTPS' in (control.value or '')
                             for control in walk(self.page)))

    def openToolsTab(self, factory):
        return self.mount(ft.View('/tools', controls=[factory(self.page, self.user)]))

    def chooseBaseColor(self, view, name):
        gesture = next(control for control in walk(view) if isinstance(control, ft.GestureDetector)
            and any(isinstance(child, ft.Text) and child.value == name for child in walk(control)))
        gesture.on_tap(None)

    async def test_color_form_save_open_delete_and_invalid_weight(self):
        from views.home_view import createColorsTab
        from color_service import getUserColorMixtures
        view = self.openToolsTab(createColorsTab)
        self.chooseBaseColor(view, 'Белый')
        self.chooseBaseColor(view, 'Чёрный')
        weight = find(view, ft.TextField, label='Общий вес смеси (граммы)')
        weight.value = 'НЕ ЧИСЛО'
        find(view, ft.ElevatedButton, text='Сохранить смесь').on_click(None)
        self.assertEqual(getUserColorMixtures(self.user['userId']), [])
        self.assertIsNotNone(weight.error_text)
        find(view, ft.ElevatedButton, text='Подобрать рецепт').on_click(None)
        self.assertFalse(any(isinstance(control, ft.Text) and control.value == 'Подбираю рецепт...'
                             for control in walk(view)))
        weight.value = '100,25'
        find(view, ft.ElevatedButton, text='Сохранить смесь').on_click(None)
        saved = getUserColorMixtures(self.user['userId'])
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0]['resultHex'], '#808080')
        find(view, ft.IconButton, tooltip='Открыть рецепт').on_click(None)
        self.assertEqual(float(weight.value), 100.25)
        find(view, ft.IconButton, tooltip='Удалить смесь').on_click(None)
        self.assertEqual(getUserColorMixtures(self.user['userId']), [])

    async def test_color_browser_export_downloads_actual_png(self):
        from urllib.parse import urlsplit
        from fastapi.testclient import TestClient
        from web_app import createWebApp
        from views.home_view import createColorsTab
        self.page._set_attr('web', 'false')
        self.page.data = {'isWebServer': True}
        self.connection.page_url = 'ws://127.0.0.1:8550/ws'
        view = self.openToolsTab(createColorsTab)
        self.chooseBaseColor(view, 'Белый')
        self.chooseBaseColor(view, 'Чёрный')
        with patch.object(self.page, 'launch_url', autospec=True) as launch:
            find(view, ft.OutlinedButton, text='Экспорт PNG').on_click(None)
            url = launch.call_args.args[0]
            self.assertEqual(urlsplit(url).scheme, 'http')
            self.assertEqual(launch.call_args.kwargs['web_window_name'], '_self')
        with TestClient(createWebApp()) as client:
            response = client.get(urlsplit(url).path)
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.content.startswith(b'\x89PNG'))
            self.assertIn('attachment', response.headers['content-disposition'])
        export = find(view, ft.OutlinedButton, text='Экспорт PNG')
        logoutPage(self.page)
        with patch.object(self.page, 'launch_url', autospec=True) as launch:
            export.on_click(None)
            launch.assert_not_called()

    async def test_native_png_save_does_not_overwrite_existing_file(self):
        from pathlib import Path
        from views.home_view import createColorsTab
        self.page._set_attr('web', 'false')
        view = self.openToolsTab(createColorsTab)
        self.chooseBaseColor(view, 'Белый')
        self.chooseBaseColor(view, 'Чёрный')
        with patch.object(ft.FilePicker, 'save_file', autospec=True):
            find(view, ft.OutlinedButton, text='Экспорт PNG').on_click(None)
        picker = next(control for control in self.page.overlay if isinstance(control, ft.FilePicker))
        path = Path(self.temp.name) / 'recipe.png'
        picker.on_result(SimpleNamespace(path=str(path)))
        original = path.read_bytes()
        self.assertTrue(original.startswith(b'\x89PNG'))
        picker.on_result(SimpleNamespace(path=str(path)))
        self.assertEqual(path.read_bytes(), original)

    async def test_invalid_color_percentage_does_not_change_recipe(self):
        from views.home_view import createColorsTab
        view = self.openToolsTab(createColorsTab)
        self.chooseBaseColor(view, 'Белый')
        self.chooseBaseColor(view, 'Чёрный')
        field = next(control for control in walk(view) if isinstance(control, ft.TextField)
                     and control.on_submit is not None and control.width == 70)
        for value in ('nan', '-1', '101', 'НЕ ЧИСЛО'):
            field.value = value
            field.on_submit(SimpleNamespace(control=field))
            self.assertEqual([control.value for control in walk(view) if isinstance(control, ft.Slider)], [50, 50])
            self.assertIsNotNone(field.error_text)

    async def test_catalog_filters_and_video_filter_are_real(self):
        from views.home_view import createSearchTab
        view = self.openToolsTab(createSearchTab)
        level = find(view, ft.Dropdown, label='Сложность')
        level.value = 'Начинающий'
        level.on_change(None)
        duration = find(view, ft.Dropdown, label='Время до (минут)')
        duration.value = '30'
        duration.on_change(None)
        self.assertEqual(len([c for c in walk(view) if isinstance(c, ft.TextButton) and c.text == 'Открыть']), 1)
        videos = find(view, ft.Checkbox, label='Только с видео')
        videos.value = True
        videos.on_change(None)
        self.assertFalse(any(isinstance(c, ft.TextButton) and c.text == 'Открыть' for c in walk(view)))

    async def test_lesson_progress_restores_and_adds_all_steps_to_project(self):
        from views.home_view import createSearchTab
        from lesson_service import getUserLessonState, getLessonById
        view = self.openToolsTab(createSearchTab)
        find(view, ft.TextButton, text='Открыть').on_click(None)
        firstMaterial = next(c for c in walk(view) if isinstance(c, ft.Checkbox) and c.label != 'Шаг выполнен')
        firstMaterial.value = True
        firstMaterial.on_change(SimpleNamespace(control=firstMaterial))
        find(view, ft.ElevatedButton, text='Следующий').on_click(None)
        state = getUserLessonState(self.user['userId'], 1)
        self.assertEqual(state['lastStep'], 1)
        self.assertEqual(state['completedSteps'], [0])
        self.assertEqual(state['checkedMaterials'], [0])
        view = self.openToolsTab(createSearchTab)
        find(view, ft.TextButton, text='Открыть').on_click(None)
        self.assertTrue(any(isinstance(c, ft.Text) and c.value == 'Шаг 2 из 6' for c in walk(view)))
        find(view, ft.ElevatedButton, text='Добавить как проект').on_click(None)
        project = projects.getUserProjects(self.user['userId'])[0]
        self.assertEqual([step['stepDescription'] for step in project['stepItems']], getLessonById(1)['steps'])

    async def test_idea_controls_create_project_with_checklist(self):
        from views.home_view import createSearchTab
        view = self.openToolsTab(createSearchTab)
        for label, value in (('Тематика идеи', 'Фэнтези'), ('Сложность идеи', 'Начинающий'),
                             ('Цветовая гамма', 'Тёплая'), ('Количество цветов', '5')):
            find(view, ft.Dropdown, label=label).value = value
        find(view, ft.ElevatedButton, text='Сгенерировать идею').on_click(None)
        find(view, ft.ElevatedButton, text='Добавить в проекты').on_click(None)
        project = projects.getUserProjects(self.user['userId'])[0]
        self.assertEqual(project['categoryName'], 'Фэнтези')
        self.assertEqual(len(project['stepItems']), 4)
        self.assertIn('Начинающий', project['descriptionText'])

    async def test_project_calendar_and_edit_dialogs(self):
        from datetime import datetime
        from views.home_view import createProjectsTab
        projectId = projects.saveProject(self.user['userId'], 'Котик', 'Животные', '', '', ['Первый этап'])[2]
        view = self.openToolsTab(createProjectsTab)
        dateField = find(view, ft.TextField, label='Дедлайн')
        find(view, ft.IconButton, tooltip='Выбрать дату').on_click(None)
        picker = next(c for c in self.page.overlay if isinstance(c, ft.DatePicker))
        picker.value = datetime(2020, 4, 25)
        picker.on_change(SimpleNamespace(control=picker))
        self.assertEqual(dateField.value, '25.04.2020')
        find(view, ft.IconButton, tooltip='Изменить проект').on_click(None)
        dialog = next(c for c in self.page.overlay if isinstance(c, ft.AlertDialog) and c.open)
        find(dialog, ft.TextField, label='Название проекта').value = 'Новый котик'
        find(dialog, ft.ElevatedButton, text='Сохранить изменения').on_click(None)
        self.assertEqual(projects.getUserProjects(self.user['userId'])[0]['projectName'], 'Новый котик')
        find(view, ft.IconButton, tooltip='Изменить этап').on_click(None)
        dialog = next(c for c in self.page.overlay if isinstance(c, ft.AlertDialog) and c.open)
        find(dialog, ft.TextField, label='Описание этапа').value = 'Обновлённый этап'
        find(dialog, ft.ElevatedButton, text='Сохранить этап').on_click(None)
        self.assertEqual(projects.getProjectSteps(projectId, self.user['userId'])[0]['stepDescription'], 'Обновлённый этап')

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
        self.assertFalse(loginUser('student@example.com', 'Student123')[0])
        with patch('account_security.sendAccountCode') as mail:
            self.assertTrue(requestRegistrationCode('student@example.com')[0])
            self.assertTrue(confirmRegistration('student@example.com', mail.call_args.args[1])[0])
        self.assertTrue(loginUser('student@example.com', 'Student123')[0])
        self.assertTrue(changeUserPassword(user['userId'], 'Student123', 'NewPass123', 'NewPass123')[0])
        self.assertFalse(loginUser('student@example.com', 'Student123')[0])
        self.assertTrue(loginUser('student@example.com', 'NewPass123')[0])
        with patch('account_security.sendAccountCode') as mail:
            self.assertTrue(requestPasswordRecovery('student@example.com')[0])
            self.assertTrue(changePasswordByEmail('student@example.com', 'ResetPass123', 'ResetPass123', mail.call_args.args[1])[0])
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
