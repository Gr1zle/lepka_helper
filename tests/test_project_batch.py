import base64
import copy
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from starlette.applications import Starlette
from starlette.routing import Route
import database as db
import project_service as projects
from project_archive import exportProject, importProject, decodeProject
from project_statistics import getProjectStatistics
from clay_tools import calculateClay, ClayTimer
from photo_service import preparePhoto
from image_fixtures import photo
from auth_service import ensureDemoUser, loginUser
from account_security import logoutUser
from project_upload import createProjectUpload, uploadProject, takeProjectUpload
from download_service import createDownload, downloadRecipe


class ProjectArchiveTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        p = patch.object(db, 'DATABASE_PATH', Path(folder.name)/'test.db')
        p.start()
        self.addCleanup(p.stop)
        db.initializeDatabase()
        mode = patch('account_gateway.getApiUrl', return_value='')
        mode.start()
        self.addCleanup(mode.stop)
        ensureDemoUser()
        self.user = loginUser('test@email.com', 'Test123456')[2]
        self.other = db.createUser('other@example.com', 'hash', 'salt', 'other')
        self.project = projects.saveProject(self.user['userId'], 'Котик', 'Животные', '', 'Заметки')[2]
        self.ids = [projects.saveProjectStep(self.project, name, self.user['userId'])[2] for name in ('Основа', 'Детали')]
        projects.saveProjectStepPhoto(self.project, self.ids[0], self.user['userId'], photo())
        projects.changeProjectStepStatus(self.project, self.ids[0], True, self.user['userId'])

    def count(self):
        with db.openDatabase() as c:
            return tuple(c.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] for table in ('projects', 'projectSteps', 'projectMixtures'))

    def test_round_trip_preserves_order_notes_photos_status_and_owner_is_current_user(self):
        projects.saveProjectStepOrder(self.project, self.user['userId'], self.ids[::-1], self.ids)
        content = exportProject(self.project, self.user['userId'])
        self.assertNotIn(b'userId', content)
        newId = importProject(self.other, content)
        self.assertNotEqual(newId, self.project)
        self.assertIsNone(db.getProjectById(newId, self.user['userId']))
        restored = projects.getProjectSteps(newId, self.other)
        self.assertEqual([s['stepDescription'] for s in restored], ['Детали', 'Основа'])
        self.assertEqual([s['isCompleted'] for s in restored], [False, True])
        self.assertTrue(projects.getProjectStepPhoto(newId, restored[1]['stepId'], self.other))
        self.assertEqual(db.getProjectById(newId, self.other)['descriptionText'], 'Заметки')
        self.assertEqual(db.getProjectById(newId, self.other)['progressPercent'], 50)
        self.assertEqual(len(projects.getProjectSteps(self.project, self.user['userId'])), 2)
        with self.assertRaises(ValueError):
            exportProject(self.project, self.other)

    def test_invalid_files_never_leave_partial_records(self):
        body = json.loads(exportProject(self.project, self.user['userId']))
        variants = [b'not json', b'[]', b'\xff']
        for mutate in (lambda d: d.update(version=2), lambda d: d.update(userId=self.other),
                       lambda d: d['steps'][0].update(photo='broken'),
                       lambda d: d['steps'][1].update(completed=True),
                       lambda d: d['project'].update(deadline='31.04.2026'),
                       lambda d: d.update(mixtures=[{}])):
            item = copy.deepcopy(body)
            mutate(item)
            variants.append(json.dumps(item).encode())
        before = self.count()
        for content in variants:
            with self.subTest(content=content[:50]), self.assertRaises(ValueError):
                importProject(self.other, content)
            self.assertEqual(self.count(), before)

    def test_sql_failure_rolls_back_project_and_all_children(self):
        content = exportProject(self.project, self.user['userId'])
        before = self.count()
        from project_archive import createProjectWithSteps
        def failAfterInsert(*args, **kwargs):
            createProjectWithSteps(*args, **kwargs)
            raise RuntimeError('storage failed after insert')
        with patch('project_archive.createProjectWithSteps', side_effect=failAfterInsert):
            with self.assertRaises(RuntimeError):
                importProject(self.other, content)
        self.assertEqual(self.count(), before)

    def test_recipe_roundtrip_and_archive_limits(self):
        from color_service import BASE_COLORS, calculateRecipe, saveColorMixture
        from project_sharing import addProjectMixture, getProjectMixtures
        recipe = calculateRecipe([{**item,'proportion':50} for item in BASE_COLORS[:2]],100)
        mixture = saveColorMixture(self.user['userId'],'Серая смесь','#808080',100,recipe)
        addProjectMixture(self.project,self.user['userId'],mixture)
        content = exportProject(self.project,self.user['userId'])
        imported = importProject(self.other,content)
        self.assertEqual(getProjectMixtures(imported,self.other)[0]['recipeItems'], recipe)
        with patch('project_archive.MAX_ARCHIVE_BYTES', 10), self.assertRaises(ValueError):
            decodeProject(content)
        body = json.loads(content)
        body['steps'] = [body['steps'][0]] * 101
        with self.assertRaises(ValueError):
            importProject(self.other,json.dumps(body).encode())

    def test_device_backups_are_owner_scoped_and_reject_paths(self):
        from project_backups import saveBackup,listBackups,readBackup,deleteBackup
        with tempfile.TemporaryDirectory() as folder, patch('project_backups.DATA_DIRECTORY',Path(folder)):
            content = exportProject(self.project,self.user['userId'])
            name = saveBackup(self.user['userId'],content)
            self.assertEqual(listBackups(self.user['userId']),[name])
            self.assertEqual(listBackups(self.other),[])
            self.assertEqual(readBackup(self.user['userId'],name),content)
            with self.assertRaises(OSError):
                readBackup(self.other,name)
            with self.assertRaises(ValueError):
                readBackup(self.user['userId'],'../../private.json')
            deleteBackup(self.user['userId'],name)
            self.assertEqual(listBackups(self.user['userId']),[])

    def test_http_upload_and_download_are_one_time_bounded_and_session_checked(self):
        content = exportProject(self.project, self.user['userId'])
        app = Starlette(routes=[Route('/uploads/{ticket}', uploadProject, methods=['PUT']),
                                Route('/downloads/{ticket}', downloadRecipe, methods=['GET'])])
        with TestClient(app) as client:
            ticket = createProjectUpload(self.user)
            self.assertEqual(client.put('/uploads/'+ticket, content=content).status_code, 200)
            self.assertEqual(takeProjectUpload(ticket, self.user['userId']), content)
            self.assertEqual(client.put('/uploads/'+ticket, content=content).status_code, 404)
            ticket = createProjectUpload(self.user)
            with patch('project_upload.MAX_ARCHIVE_BYTES', 10):
                self.assertEqual(client.put('/uploads/'+ticket, content=content, headers={'content-length': '1'}).status_code, 413)
            ticket = createDownload(content, 'lepka-project.json', 'application/json', self.user)
            response = client.get('/downloads/'+ticket)
            self.assertEqual(response.content, content)
            self.assertIn('lepka-project.json', response.headers['content-disposition'])
            self.assertEqual(client.get('/downloads/'+ticket).status_code, 404)
            upload = createProjectUpload(self.user)
            download = createDownload(content, 'lepka-project.json', 'application/json', self.user)
            logoutUser(self.user['sessionToken'])
            self.assertEqual(client.put('/uploads/'+upload, content=content).status_code, 401)
            self.assertEqual(client.get('/downloads/'+download).status_code, 401)

    def test_completion_statistics_transition_reopen_and_imported_undated(self):
        projects.saveProjectStepPhoto(self.project, self.ids[1], self.user['userId'], photo())
        projects.changeProjectStepStatus(self.project, self.ids[1], True, self.user['userId'])
        stamp = db.getProjectById(self.project, self.user['userId'])['completedAt']
        self.assertTrue(stamp)
        with db.openDatabase() as c:
            c.execute("UPDATE projects SET completedAt='2025-12-31T23:59:00Z' WHERE projectId=?", (self.project,))
        stats = getProjectStatistics(self.user['userId'], 2025, 12)
        self.assertEqual((stats['month'], stats['year'], stats['completed']), (1,1,1))
        self.assertEqual(getProjectStatistics(self.other, 2025, 12)['completed'], 0)
        imported = importProject(self.user['userId'], exportProject(self.project, self.user['userId']))
        self.assertIsNone(db.getProjectById(imported, self.user['userId'])['completedAt'])
        self.assertEqual(getProjectStatistics(self.user['userId'], 2025, 12)['undated'], 1)
        projects.changeProjectStepStatus(self.project, self.ids[1], False, self.user['userId'])
        self.assertIsNone(db.getProjectById(self.project, self.user['userId'])['completedAt'])
        self.assertEqual(getProjectStatistics(self.user['userId'], 2025, 12)['year'], 0)

    def test_rounding_does_not_mark_large_incomplete_project_as_completed(self):
        steps = [{'isCompleted':True}]*9999 + [{'isCompleted':False}]
        with patch('project_service.getProjectSteps',return_value=steps):
            self.assertLess(projects.calculateProjectProgress(self.project,self.user['userId']),100)


class ClayToolTests(unittest.TestCase):
    def test_geometric_volumes_mass_reserve_and_invalid_input(self):
        self.assertEqual(calculateClay('Брусок', [2,3,4], '1,5', 10)['withReserve'], 39.6)
        self.assertAlmostEqual(calculateClay('Шар', [2], 1, 0)['volume'], 4*math.pi/3)
        self.assertAlmostEqual(calculateClay('Цилиндр', [2,3], 1, 0)['volume'], 3*math.pi)
        self.assertEqual(calculateClay('Объём', [100], 1.6, 0)['mass'], 160)
        for shape, dims, density, reserve in [('Объём', ['nan'],1,10), ('Шар',[-2],1,10), ('Брусок',[2],1,10),
                                             ('Объём',[1],0,10), ('Объём',[1],1,101), ('Объём',[1],1,'nan')]:
            with self.assertRaises(ValueError):
                calculateClay(shape,dims,density,reserve)

    def test_timer_pause_resume_reset_and_elapsed_time_without_ticks(self):
        clock = [100.0]
        timer = ClayTimer(lambda: clock[0])
        timer.start('1,5')
        clock[0] += 20
        self.assertEqual(timer.seconds(), 70)
        timer.pause()
        clock[0] += 1000
        self.assertEqual(timer.seconds(),70)
        timer.start()
        clock[0] += 71
        self.assertEqual(timer.display(),'00:00:00')
        self.assertFalse(timer.running)
        timer.reset()
        self.assertEqual(timer.seconds(),90)
        for value in ('nan',0,-1,1441):
            with self.assertRaises(ValueError):
                timer.start(value)
