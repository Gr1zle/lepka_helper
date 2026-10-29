"""Аватар и приватные фото этапов: отдельная временная база и настоящие контролы Flet."""
import asyncio
import base64
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
import database as db
import profile_service as profiles
import project_service as projects
from photo_service import prepareAvatar
from image_fixtures import photo
from test_startup import MemoryConnection, find, walk
from ui_helpers import logoutPage
from web_app import createWebApp


class MediaTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        patcher = patch.object(db, 'DATABASE_PATH', Path(self.temp.name) / 'media.db')
        patcher.start()
        self.addCleanup(patcher.stop)
        db.initializeDatabase()
        auth_service.ensureDemoUser()
        self.user = auth_service.loginUser('test@email.com', 'Test123456')[2]
        self.owner = self.user['userId']
        self.other = db.createUser('other@example.com', '', '', 'other')
        self.project = projects.saveProject(self.owner, 'Котик', 'Животные', '', '')[2]
        self.step = projects.saveProjectStep(self.project, 'Слепить основу', self.owner)[2]
        source = photo()
        self.png = prepareAvatar(source['name'], source['data'])

    def test_avatar_is_circular_png_and_survives_profile_save_and_reinitialize(self):
        success, message, result = profiles.saveUserAvatar(self.owner, self.png)
        self.assertTrue(success, message)
        imageData = base64.b64decode(result['avatarImage'])
        with Image.open(BytesIO(imageData)) as image:
            self.assertEqual(image.size, (512, 512))
            self.assertEqual(image.format, 'PNG')
            self.assertEqual(image.getpixel((0, 0))[3], 0)
            self.assertEqual(image.getpixel((256, 256))[3], 255)
            self.assertFalse(image.getexif())
        self.assertTrue(profiles.saveUserProfile(self.owner, 'new_owner', 'Биография', 'Взрослый 18+', ['Белый'])[0])
        db.initializeDatabase()
        self.assertEqual(profiles.getUserProfile(self.owner)['avatarImage'], result['avatarImage'])
        from account_security import logoutUser
        logoutUser(self.user['sessionToken'])
        user = auth_service.loginUser('test@email.com', 'Test123456')[2]
        self.assertEqual(profiles.getUserProfile(user['userId'])['avatarImage'], result['avatarImage'])
        self.assertEqual(profiles.getUserProfile(self.other)['avatarImage'], '')

    def test_avatar_invalid_upload_preserves_old_image_and_explicit_delete_clears_it(self):
        profiles.saveUserAvatar(self.owner, self.png)
        old = profiles.getUserProfile(self.owner)['avatarImage']
        self.assertFalse(profiles.saveUserAvatar(self.owner, b'not an image')[0])
        self.assertEqual(profiles.getUserProfile(self.owner)['avatarImage'], old)
        self.assertTrue(profiles.removeUserAvatar(self.owner)[0])
        self.assertEqual(profiles.getUserProfile(self.owner)['avatarImage'], '')

    def test_old_avatar_path_and_completed_step_are_not_overwritten_by_migration(self):
        with db.openDatabase() as connection:
            connection.execute('UPDATE users SET avatarPath = ? WHERE userId = ?', ('legacy.png', self.owner))
            connection.execute('UPDATE projectSteps SET isCompleted = 1 WHERE stepId = ?', (self.step,))
        db.initializeDatabase()
        self.assertEqual(profiles.getUserProfile(self.owner)['avatarPath'], 'legacy.png')
        self.assertEqual(projects.getUserProjects(self.owner)[0]['progressPercent'], 100)
        self.assertFalse(projects.getProjectSteps(self.project, self.owner)[0]['hasPhoto'])
        projects.changeProjectStepStatus(self.project, self.step, False, self.owner)
        with self.assertRaises(ValueError):
            projects.changeProjectStepStatus(self.project, self.step, True, self.owner)

    def test_step_photo_is_private_and_wrong_project_or_owner_cannot_replace_it(self):
        self.assertTrue(projects.saveProjectStepPhoto(self.project, self.step, self.owner, photo())[0])
        old = db.getProjectStepPhoto(self.project, self.step, self.owner)
        self.assertTrue(old.startswith(b'\xff\xd8'))
        self.assertIsNone(db.getProjectStepPhoto(self.project, self.step, self.other))
        otherProject = projects.saveProject(self.owner, 'Другой котик', 'Животные', '', '')[2]
        self.assertFalse(projects.saveProjectStepPhoto(otherProject, self.step, self.owner, photo())[0])
        self.assertFalse(projects.saveProjectStepPhoto(self.project, self.step, self.other, photo())[0])
        self.assertFalse(projects.removeProjectStepPhoto(self.project, self.step, self.other)[0])
        self.assertEqual(db.getProjectStepPhoto(self.project, self.step, self.owner), old)

    def test_completion_requires_photo_in_both_service_and_sql(self):
        self.assertFalse(db.updateProjectStepStatus(self.project, self.step, True, self.owner))
        with self.assertRaises(ValueError):
            projects.changeProjectStepStatus(self.project, self.step, True, self.owner)
        self.assertEqual(projects.getUserProjects(self.owner)[0]['progressPercent'], 0)
        self.assertTrue(projects.saveProjectStepPhoto(self.project, self.step, self.owner, photo())[0])
        self.assertEqual(projects.changeProjectStepStatus(self.project, self.step, True, self.owner), 100)
        self.assertFalse(projects.removeProjectStepPhoto(self.project, self.step, self.owner)[0])
        self.assertTrue(projects.saveProjectStepPhoto(self.project, self.step, self.owner, photo())[0])
        self.assertEqual(projects.getUserProjects(self.owner)[0]['progressPercent'], 100)
        projects.changeProjectStepStatus(self.project, self.step, False, self.owner)
        self.assertTrue(projects.removeProjectStepPhoto(self.project, self.step, self.owner)[0])
        self.assertIsNone(db.getProjectStepPhoto(self.project, self.step, self.owner))

    def test_invalid_step_image_does_not_replace_existing_photo(self):
        projects.saveProjectStepPhoto(self.project, self.step, self.owner, photo())
        old = db.getProjectStepPhoto(self.project, self.step, self.owner)
        self.assertFalse(projects.saveProjectStepPhoto(self.project, self.step, self.owner, {'name':'bad.png','data':b'bad'})[0])
        self.assertEqual(db.getProjectStepPhoto(self.project, self.step, self.owner), old)

    def test_deleting_project_step_or_account_removes_embedded_images(self):
        profiles.saveUserAvatar(self.owner, self.png)
        projects.saveProjectStepPhoto(self.project, self.step, self.owner, photo())
        self.assertEqual(projects.removeProjectStep(self.project, self.step, self.owner), 0)
        self.assertIsNone(db.getProjectStepPhoto(self.project, self.step, self.owner))
        self.step = projects.saveProjectStep(self.project, 'Другой этап', self.owner)[2]
        projects.saveProjectStepPhoto(self.project, self.step, self.owner, photo())
        self.assertTrue(projects.removeProject(self.project, self.owner))
        with db.openDatabase() as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM projectSteps').fetchone()[0], 0)
        self.assertTrue(auth_service.deleteUserAccount(self.owner, 'Test123456')[0])
        self.assertIsNone(db.getUserProfileById(self.owner))


class MediaUiTests(unittest.IsolatedAsyncioTestCase):
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
        self.page = ft.Page(MemoryConnection(), 'media', asyncio.get_running_loop())
        self.page.theme_mode = ft.ThemeMode.LIGHT
        self.page.session.set('currentUser', self.user)
        self.page.go = lambda route: setattr(self.page, 'route', route)

    def mount(self, control):
        view = ft.View('/media', controls=[control])
        self.page.views[:] = [view]
        self.page.update()
        return view

    def profile(self):
        from views.profile_tab import createProfileTab
        return self.mount(createProfileTab(self.page, self.user['nickname'], self.user['email']))

    def pick(self, view, label):
        find(view, ft.OutlinedButton, text=label).on_click(None)
        picker = next(c for c in self.page.overlay if isinstance(c, ft.FilePicker)
                      and isinstance(c.data, dict) and c.data.get('singlePhotoPicker'))
        data = photo()
        path = Path(self.temp.name) / data['name']
        path.write_bytes(data['data'])
        picker.on_result(SimpleNamespace(files=[SimpleNamespace(name=path.name, path=str(path), size=path.stat().st_size, id=1)],control=picker))
        return picker

    async def test_native_avatar_displays_as_image_and_restores_after_tab_reload(self):
        view = self.profile()
        self.pick(view, 'Выбрать аватар')
        images = [c for c in walk(view) if isinstance(c, ft.CircleAvatar) and isinstance(c.content, ft.Image)]
        self.assertEqual(len(images), 2)
        old = profiles.getUserProfile(self.user['userId'])['avatarImage']
        self.assertTrue(old)
        view = self.profile()
        self.assertEqual(find(view, ft.CircleAvatar).content.src_base64, old)
        find(view, ft.OutlinedButton, text='Убрать аватар').on_click(None)
        self.assertEqual(profiles.getUserProfile(self.user['userId'])['avatarImage'], '')
        self.assertIsInstance(find(view, ft.CircleAvatar).content, ft.Text)

    async def test_browser_avatar_upload_ignores_native_path_even_with_false_web_flag(self):
        self.page.data = {'isWebServer': True}
        self.page._set_attr('web', 'false')
        view = self.profile()
        with patch.object(ft.FilePicker, 'upload', autospec=True) as upload:
            self.pick(view, 'Выбрать аватар')
            target = upload.call_args.args[1][0]
        with TestClient(createWebApp()) as client:
            self.assertEqual(client.put(target.upload_url, content=photo()['data']).status_code, 200)
        picker = next(c for c in self.page.overlay if isinstance(c, ft.FilePicker) and isinstance(c.data,dict))
        picker.on_upload(SimpleNamespace(file_name=photo()['name'],progress=1,error=None,control=picker))
        self.assertTrue(profiles.getUserProfile(self.user['userId'])['avatarImage'])
        self.assertIsInstance(find(view, ft.CircleAvatar).content, ft.Image)

    async def test_cancel_and_stale_avatar_selection_do_not_change_profile(self):
        view = self.profile()
        find(view, ft.OutlinedButton, text='Выбрать аватар').on_click(None)
        picker = next(c for c in self.page.overlay if isinstance(c, ft.FilePicker))
        picker.on_result(SimpleNamespace(files=None,control=picker))
        self.assertEqual(profiles.getUserProfile(self.user['userId'])['avatarImage'], '')
        logoutPage(self.page)
        with patch('photo_picker.Path.open') as opened:
            picker.on_result(SimpleNamespace(files=[SimpleNamespace(name='private.png',path='/private.png',size=100,id=1)],control=picker))
            opened.assert_not_called()
        self.assertEqual(profiles.getUserProfile(self.user['userId'])['avatarImage'], '')

    async def test_photo_of_selected_step_and_progress_are_updated(self):
        from views.home_view import createProjectsTab
        project = projects.saveProject(self.user['userId'], 'Котик', 'Животные', '', '')[2]
        step = projects.saveProjectStep(project, 'Первый этап', self.user['userId'])[2]
        view = self.mount(createProjectsTab(self.page, self.user))
        checkbox = find(view, ft.Checkbox)
        checkbox.value = True
        checkbox.on_change(SimpleNamespace(control=checkbox))
        self.assertEqual(projects.getUserProjects(self.user['userId'])[0]['progressPercent'], 0)
        self.pick(view, 'Добавить фото этапа')
        self.assertIsNotNone(db.getProjectStepPhoto(project, step, self.user['userId']))
        checkbox = find(view, ft.Checkbox)
        checkbox.value = True
        checkbox.on_change(SimpleNamespace(control=checkbox))
        self.assertEqual(projects.getUserProjects(self.user['userId'])[0]['progressPercent'], 100)
        find(view, ft.TextButton, text='Убрать фото этапа').on_click(None)
        self.assertIsNotNone(db.getProjectStepPhoto(project, step, self.user['userId']))
