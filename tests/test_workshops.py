"""Опубликованные мастер-классы: порядок шагов, данные автора и прогресс читателя."""
import asyncio
import base64
import copy
import json
import sqlite3
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import flet as ft

import account_security
import database as db
import post_service as posts
import project_service as projects
import project_sharing as sharing
import workshop_service as workshops
from test_project_sharing import SharingFixture
from test_startup import MemoryConnection, find, walk
from ui_helpers import logoutPage


INFO = {'level': 'Средний', 'timeMinutes': 45,
        'materials': ['Серый пластилин', 'Белый пластилин'], 'tools': ['Стек', 'Доска для лепки']}


class WorkshopFixture(SharingFixture):
    def setUp(self):
        super().setUp()
        success, message, self.postId = self.publish(workshopInfo=INFO)
        self.assertTrue(success, message)


class WorkshopTests(WorkshopFixture, unittest.TestCase):
    def test_chronological_steps_have_correct_photos_and_explicit_author_metadata(self):
        workshop = workshops.getWorkshop(self.postId)
        self.assertEqual(workshop['level'], 'Средний')
        self.assertEqual(workshop['timeMinutes'], 45)
        self.assertEqual(workshop['materials'], INFO['materials'])
        self.assertEqual(workshop['tools'], INFO['tools'])
        self.assertEqual([step['description'] for step in workshop['steps']], ['Слепить основу', 'Готовый котик'])
        self.assertEqual([step['photoPosition'] for step in workshop['steps']], [1, 0])
        self.assertEqual(db.getPostPhoto(workshop['photoIds'][1]), db.getProjectStepPhoto(self.project, self.step, self.owner))
        self.assertEqual(db.getPostPhoto(workshop['photoIds'][0]), db.getProjectStepPhoto(self.project, self.result, self.owner))

    def test_metadata_validation_does_not_create_a_partial_publication(self):
        for changes in ({'level': 'Неведомый'}, {'timeMinutes': ''}, {'timeMinutes': True},
                        {'timeMinutes': 0}, {'timeMinutes': 1441}, {'timeMinutes': '2.5'},
                        {'materials': []}, {'materials': [' ']}, {'materials': ['x' * 121]},
                        {'tools': 'Стек'}, {'tools': ['Стек'] * 31}):
            with self.subTest(changes=changes):
                self.assertFalse(self.publish(workshopInfo={**INFO, **changes})[0])
        self.assertEqual(len(posts.getCommunityPosts()), 1)
        success, message, postId = self.publish(workshopInfo={**INFO, 'timeMinutes': '60',
            'materials': [' Серый пластилин ', 'Серый пластилин'], 'tools': []})
        self.assertTrue(success, message)
        self.assertEqual(workshops.getWorkshop(postId)['materials'], ['Серый пластилин'])

    def test_selected_text_step_is_not_lost_or_given_a_fake_photo(self):
        textStep = projects.saveProjectStep(self.project, 'Подготовьте рабочее место', self.owner)[2]
        postId = self.publish(workshopInfo=INFO, otherStepIds=[textStep, self.step])[2]
        workshop = workshops.getWorkshop(postId)
        self.assertEqual(len(workshop['steps']), 3)
        self.assertEqual(workshop['steps'][-1], {'description': 'Подготовьте рабочее место', 'photoPosition': None})
        self.assertEqual(len(workshop['photoIds']), 2)

    def test_hundred_steps_with_text_are_allowed_but_eleven_photos_are_not(self):
        textSteps = [projects.saveProjectStep(self.project, f'Текстовый этап {index}', self.owner)[2] for index in range(98)]
        success, message, postId = self.publish(workshopInfo=INFO, otherStepIds=[self.step, *textSteps])
        self.assertTrue(success, message)
        self.assertEqual(len(workshops.getWorkshop(postId)['steps']), 100)
        self.assertEqual(len(workshops.getWorkshop(postId)['photoIds']), 2)
        photoSteps = [self.addStep(self.project, self.owner, f'Этап с фото {index}') for index in range(9)]
        success, message, _ = self.publish(workshopInfo=INFO, otherStepIds=[self.step, *photoSteps])
        self.assertFalse(success)
        self.assertIn('10 фото', message)
        self.assertEqual(len(posts.getCommunityPosts()), 2)

    def test_corrupt_photo_positions_and_metadata_are_not_read(self):
        with db.openDatabase() as connection:
            original = json.loads(connection.execute('SELECT projectDetailsJson FROM posts WHERE postId = ?', (self.postId,)).fetchone()[0])
        invalid = []
        for position in (-1, True, 10, '1'):
            details = copy.deepcopy(original)
            details['steps'][0]['photoPosition'] = position
            invalid.append(details)
        details = copy.deepcopy(original)
        details['steps'][0]['photoPosition'] = 0
        invalid.append(details)  # Два шага ошибочно ссылаются на одну позицию.
        details = copy.deepcopy(original)
        details['workshopInfo']['level'] = 'несуществующая'
        invalid.append(details)
        for details in invalid:
            with db.openDatabase() as connection:
                connection.execute('UPDATE posts SET projectDetailsJson = ? WHERE postId = ?', (json.dumps(details), self.postId))
            self.assertIsNone(workshops.getWorkshop(self.postId))
            self.assertFalse(sharing.copyPublishedMixture(self.postId, 0, self.other)[0])

    def test_legacy_publication_opens_with_result_last_and_unknown_metadata(self):
        legacyId = self.publish()[2]
        workshop = workshops.getWorkshop(legacyId)
        self.assertIsNone(workshop['level'])
        self.assertIsNone(workshop['timeMinutes'])
        self.assertEqual(workshop['materials'], [])
        self.assertEqual([step['description'] for step in workshop['steps']], ['Слепить основу', 'Готовый котик'])
        self.assertEqual(len(workshop['mixtures']), 1)

    def test_reader_progress_is_private_persistent_and_separate_from_projects_and_lessons(self):
        state = {'lastStep': 1, 'completedSteps': [0], 'checkedMaterials': [0, 2]}
        saved = workshops.saveUserWorkshopState(self.other, self.postId, state)
        self.assertFalse(saved['isCompleted'])
        db.initializeDatabase()
        self.assertEqual(workshops.getUserWorkshopState(self.other, self.postId), saved)
        self.assertEqual(workshops.getUserWorkshopState(self.owner, self.postId)['completedSteps'], [])
        self.assertEqual(projects.getUserProjects(self.owner)[0]['progressPercent'], 0)
        self.assertIsNone(db.getLessonProgress(self.other, 1))

    def test_invalid_progress_is_rejected_without_overwriting_previous_state(self):
        state = {'lastStep': 1, 'completedSteps': [0], 'checkedMaterials': [0]}
        before = workshops.saveUserWorkshopState(self.other, self.postId, state)
        for changes in ({'lastStep': -1}, {'lastStep': True}, {'lastStep': 2},
                        {'completedSteps': [2]}, {'checkedMaterials': [4]}, {'checkedMaterials': [True]}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                workshops.saveUserWorkshopState(self.other, self.postId, {**state, **changes})
        self.assertEqual(workshops.getUserWorkshopState(self.other, self.postId), before)

    def test_corrupt_progress_is_not_rewritten_during_read(self):
        with db.openDatabase() as connection:
            connection.execute('INSERT INTO workshopProgress VALUES (?, ?, ?)', (self.other, self.postId, '{bad'))
        self.assertEqual(workshops.getUserWorkshopState(self.other, self.postId)['lastStep'], 0)
        with db.openDatabase() as connection:
            self.assertEqual(connection.execute('SELECT stateJson FROM workshopProgress').fetchone()[0], '{bad')

    def test_deletion_removes_progress_and_prevents_stale_saves(self):
        state = {'lastStep': 0, 'completedSteps': [], 'checkedMaterials': [1]}
        workshops.saveUserWorkshopState(self.other, self.postId, state)
        self.assertTrue(posts.removePost(self.postId, self.owner))
        self.assertIsNone(workshops.getWorkshop(self.postId))
        with self.assertRaises(ValueError):
            workshops.saveUserWorkshopState(self.other, self.postId, state)
        with db.openDatabase() as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM workshopProgress').fetchone()[0], 0)
        self.assertFalse(workshops.addWorkshopAsProject(self.postId, self.other)[0])

    def test_account_deletion_cleans_readers_progress_under_tombstone(self):
        workshops.saveUserWorkshopState(self.other, self.postId,
            {'lastStep': 0, 'completedSteps': [], 'checkedMaterials': [1]})
        posts.savePostComment(self.postId, self.other, 'Спасибо за мастер-класс')
        self.assertTrue(db.deleteUserDataById(self.owner))
        self.assertIsNone(workshops.getWorkshop(self.postId))
        self.assertEqual(len(posts.getPostComments(self.postId)), 1)
        with db.openDatabase() as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM workshopProgress').fetchone()[0], 0)
            self.assertEqual(connection.execute('PRAGMA foreign_key_check').fetchall(), [])

    def test_add_as_project_creates_readers_unfinished_steps_and_mixture_copies(self):
        success, message, projectId = workshops.addWorkshopAsProject(self.postId, self.other)
        self.assertTrue(success, message)
        self.assertIsNone(db.getProjectById(projectId, self.owner))
        project = projects.getUserProjects(self.other)[0]
        self.assertEqual(project['progressPercent'], 0)
        self.assertEqual([step['stepDescription'] for step in project['stepItems']], ['Слепить основу', 'Готовый котик'])
        self.assertFalse(any(step['hasPhoto'] for step in project['stepItems']))
        self.assertEqual(sharing.getProjectMixtures(projectId, self.other)[0]['recipeItems'], self.recipe)
        self.assertIn('Средний', project['descriptionText'])
        self.assertIn('Стек', project['descriptionText'])

    def test_project_copy_rolls_back_when_database_rejects_a_step(self):
        with db.openDatabase() as connection:
            connection.execute("""CREATE TRIGGER reject_copy BEFORE INSERT ON projectSteps
                WHEN NEW.stepDescription = 'Готовый котик' BEGIN SELECT RAISE(ABORT, 'test failure'); END""")
        with self.assertRaises(sqlite3.IntegrityError):
            workshops.addWorkshopAsProject(self.postId, self.other)
        self.assertEqual(projects.getUserProjects(self.other), [])

    def test_search_matches_material_tool_level_and_time_filters(self):
        self.assertEqual([item['postId'] for item in workshops.searchCommunityWorks('доска', levelName='Средний', maxTime=60)], [self.postId])
        self.assertEqual(workshops.searchCommunityWorks('доска', levelName='Начинающий'), [])
        self.assertEqual(workshops.searchCommunityWorks('доска', maxTime=30), [])
        self.assertEqual(workshops.searchCommunityWorks('доска', onlyVideo=True), [])
        self.assertEqual(workshops.searchCommunityWorks('д'), [])

    def test_blocked_or_missing_account_cannot_save_or_copy_workshop(self):
        with db.openDatabase() as connection:
            connection.execute('UPDATE users SET isBlocked = 1 WHERE userId = ?', (self.other,))
        for userId in (self.other, 999999):
            with self.assertRaises(ValueError):
                workshops.saveUserWorkshopState(userId, self.postId, {'lastStep': 0, 'completedSteps': [], 'checkedMaterials': []})
            self.assertFalse(workshops.addWorkshopAsProject(self.postId, userId)[0])


class WorkshopUiTests(WorkshopFixture, unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        with db.openDatabase() as connection:
            self.user = account_security.createSession(connection, db.getUserByEmail('reader@example.com'))
        self.page = ft.Page(MemoryConnection(), 'workshop', asyncio.get_running_loop())
        self.page.theme_mode = ft.ThemeMode.LIGHT
        self.page.session.set('currentUser', self.user)
        self.page.go = lambda route: setattr(self.page, 'route', route)

    def feed(self, currentUser):
        from views.community_tab import createHomeTab
        view = ft.View('/home', controls=[createHomeTab(self.page, currentUser, 'Читатель')])
        self.page.views[:] = [view]
        self.page.update()
        return view

    def open(self, currentUser):
        feed = self.feed(currentUser)
        find(feed, ft.OutlinedButton, text='Открыть мастер-класс').on_click(None)
        return self.page.views[-1]

    async def test_full_view_checklist_navigation_persistence_and_return_to_same_feed(self):
        view = self.open(self.user)
        parent = self.page.views[0]
        self.assertTrue(view.route.startswith('/workshop/'))
        self.assertTrue(any(isinstance(control, ft.Text) and 'Средний · 45 мин' in control.value for control in walk(view)))
        image = find(view, ft.Image)
        workshop = workshops.getWorkshop(self.postId)
        self.assertEqual(base64.b64decode(image.src_base64), db.getPostPhoto(workshop['photoIds'][1]))
        for label in ('Серый пластилин', 'Стек'):
            checkbox = find(view, ft.Checkbox, label=label)
            checkbox.value = True
            checkbox.on_change(SimpleNamespace(control=checkbox))
        find(view, ft.ElevatedButton, text='Следующий').on_click(None)
        state = workshops.getUserWorkshopState(self.other, self.postId)
        self.assertEqual(state['completedSteps'], [0])
        self.assertEqual(state['checkedMaterials'], [0, 2])
        self.assertEqual(state['lastStep'], 1)
        find(view, ft.TextButton, text='← Назад').on_click(None)
        self.assertIs(self.page.views[-1], parent)
        find(parent, ft.OutlinedButton, text='Открыть мастер-класс').on_click(None)
        view = self.page.views[-1]
        self.assertTrue(any(isinstance(control, ft.Text) and control.value == 'Шаг 2 из 2' for control in walk(view)))
        find(view, ft.ElevatedButton, text='Завершить').on_click(None)
        self.assertTrue(workshops.getUserWorkshopState(self.other, self.postId)['isCompleted'])

    async def test_guest_can_navigate_but_personal_actions_are_disabled(self):
        view = self.open(None)
        self.assertTrue(find(view, ft.Checkbox, label='Шаг выполнен').disabled)
        self.assertTrue(find(view, ft.ElevatedButton, text='Добавить как проект').disabled)
        self.assertTrue(find(view, ft.OutlinedButton, text='Сохранить рецепт в мою палитру').disabled)
        find(view, ft.ElevatedButton, text='Следующий').on_click(None)
        self.assertTrue(any(isinstance(control, ft.Text) and control.value == 'Шаг 2 из 2' for control in walk(view)))
        with db.openDatabase() as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM workshopProgress').fetchone()[0], 0)

    async def test_publication_form_requires_author_metadata_and_keeps_invalid_form_open(self):
        from views.home_view import createProjectsTab
        with db.openDatabase() as connection:
            author = account_security.createSession(connection, db.getUserByEmail('owner@example.com'))
        self.page.session.set('currentUser', author)
        root = ft.View('/projects', controls=[createProjectsTab(self.page, author)])
        self.page.views[:] = [root]
        self.page.update()
        find(root, ft.ElevatedButton, text='Опубликовать в сообщество').on_click(None)
        dialog = next(item for item in reversed(self.page.overlay) if isinstance(item, ft.AlertDialog))
        find(dialog, ft.TextField, label='Описание для сообщества').value = 'Подробное описание мастер-класса'
        find(dialog, ft.ElevatedButton, text='Опубликовать проект').on_click(None)
        self.assertTrue(dialog.open)
        self.assertEqual(len(posts.getCommunityPosts()), 1)
        find(dialog, ft.TextField, label='Время выполнения (минут)').value = '35'
        find(dialog, ft.TextField, label='Материалы — по одному на строку').value = 'Серый пластилин\nБелый пластилин'
        find(dialog, ft.TextField, label='Инструменты — по одному на строку').value = 'Стек'
        find(dialog, ft.Dropdown, label='Сложность мастер-класса').value = 'Продвинутый'
        find(dialog, ft.ElevatedButton, text='Опубликовать проект').on_click(None)
        self.assertFalse(dialog.open)
        workshop = workshops.getWorkshop(posts.getCommunityPosts()[0]['postId'])
        self.assertEqual(workshop['level'], 'Продвинутый')
        self.assertEqual(workshop['materials'], ['Серый пластилин', 'Белый пластилин'])
        self.assertEqual(workshop['tools'], ['Стек'])

    async def test_step_without_photo_shows_a_clear_text_message(self):
        textStep = projects.saveProjectStep(self.project, 'Шаг без фотографии', self.owner)[2]
        self.postId = self.publish(workshopInfo=INFO, otherStepIds=[self.step, textStep])[2]
        workshops.saveUserWorkshopState(self.other, self.postId,
            {'lastStep': 2, 'completedSteps': [], 'checkedMaterials': []})
        from views.workshop_view import createWorkshopView
        view = createWorkshopView(self.page, self.postId, self.user, lambda event: None)
        self.page.views[:] = [view]
        self.page.update()
        self.assertTrue(any(isinstance(control, ft.Text) and control.value ==
                            'Автор не добавил фотографию этого шага.' for control in walk(view)))

    async def test_stale_navigation_and_checklist_handlers_do_not_save_after_logout(self):
        view = self.open(self.user)
        nextStep = find(view, ft.ElevatedButton, text='Следующий').on_click
        checkbox = find(view, ft.Checkbox, label='Стек')
        logoutPage(self.page)
        nextStep(None)
        checkbox.value = True
        checkbox.on_change(SimpleNamespace(control=checkbox))
        self.assertEqual(workshops.getUserWorkshopState(self.other, self.postId)['checkedMaterials'], [])
        self.assertEqual(workshops.getUserWorkshopState(self.other, self.postId)['lastStep'], 0)

    async def test_narrow_and_wide_view_serializes_in_both_themes(self):
        for width in (320, 390, 1280):
            self.page._set_attr('width', width)
            for theme in (ft.ThemeMode.LIGHT, ft.ThemeMode.DARK):
                self.page.theme_mode = theme
                view = self.open(self.user)
                self.assertEqual(find(view, ft.ElevatedButton, text='Следующий').height, 48)
                self.assertIsInstance(find(view, ft.SafeArea), ft.SafeArea)

    async def test_system_back_preserves_existing_search_view(self):
        from main import main
        with patch('main.getApiUrl', return_value=''):
            main(self.page)
        view = self.open(self.user)
        parent = self.page.views[0]
        self.page.on_view_pop(SimpleNamespace(view=view))
        self.assertEqual(len(self.page.views), 1)
        self.assertIs(self.page.views[0], parent)


if __name__ == '__main__':
    unittest.main()
