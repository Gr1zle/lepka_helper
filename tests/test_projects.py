"""Проекты: настоящая SQLite, отдельная временная база для каждого теста."""
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import database as db
import project_service as projects
from image_fixtures import photo


class ProjectTests(unittest.TestCase):
    def test_reordering_preserves_photos_completion_and_project_progress(self):
        second = projects.saveProjectStep(self.project, 'Вторая часть', self.owner)[2]
        third = projects.saveProjectStep(self.project, 'Третья часть', self.owner)[2]
        projects.saveProjectStepPhoto(self.project, second, self.owner, photo())
        projects.changeProjectStepStatus(self.project, second, True, self.owner)
        image = projects.getProjectStepPhoto(self.project, second, self.owner)
        before = dict(db.getProjectById(self.project, self.owner))
        self.assertTrue(projects.saveProjectStepOrder(self.project, self.owner,
            [third, second, self.step], [self.step, second, third])[0])
        self.assertEqual([s['stepId'] for s in projects.getProjectSteps(self.project, self.owner)], [third, second, self.step])
        self.assertEqual(projects.getProjectStepPhoto(self.project, second, self.owner), image)
        self.assertTrue(projects.getProjectSteps(self.project, self.owner)[1]['isCompleted'])
        self.assertEqual(dict(db.getProjectById(self.project, self.owner)), before)
        fourth = projects.saveProjectStep(self.project, 'Последняя часть', self.owner)[2]
        self.assertEqual([s['stepId'] for s in projects.getProjectSteps(self.project, self.owner)], [third, second, self.step, fourth])

    def test_reorder_rejects_foreign_missing_duplicate_and_stale_steps_atomically(self):
        second = projects.saveProjectStep(self.project, 'Вторая часть', self.owner)[2]
        original = [self.step, second]
        for user, ordered, expected in ((self.other, original[::-1], original),
                (self.owner, [second, second], original), (self.owner, [second], original),
                (self.owner, [second, self.otherStep], original),
                (self.owner, ['1', second], original), (self.owner, original[::-1], original[::-1])):
            before = self.snapshot()
            self.assertFalse(projects.saveProjectStepOrder(self.project, user, ordered, expected)[0])
            self.assertEqual(self.snapshot(), before)
        self.assertTrue(projects.saveProjectStepOrder(self.project, self.owner, original[::-1], original)[0])
        before = self.snapshot()
        self.assertFalse(projects.saveProjectStepOrder(self.project, self.owner, original, original)[0])
        self.assertEqual(self.snapshot(), before)
        projects.saveProjectStep(self.project, 'Новый этап из другого окна', self.owner)
        before = self.snapshot()
        self.assertFalse(projects.saveProjectStepOrder(self.project, self.owner, original, original[::-1])[0])
        self.assertEqual(self.snapshot(), before)

    def test_legacy_step_order_migration_preserves_data_and_does_not_reset_later_order(self):
        second = projects.saveProjectStep(self.project, 'Вторая часть', self.owner)[2]
        projects.saveProjectStepPhoto(self.project, second, self.owner, photo())
        image = projects.getProjectStepPhoto(self.project, second, self.owner)
        with db.openDatabase() as connection:
            connection.execute('ALTER TABLE projectSteps DROP COLUMN sortOrder')
            connection.execute("UPDATE projectSteps SET createdAt='2000-01-01' WHERE stepId=?", (second,))
        db.initializeDatabase()
        self.assertEqual([s['stepId'] for s in projects.getProjectSteps(self.project, self.owner)], [second, self.step])
        self.assertEqual(projects.getProjectStepPhoto(self.project, second, self.owner), image)
        self.assertTrue(projects.saveProjectStepOrder(self.project, self.owner, [self.step, second], [second, self.step])[0])
        db.initializeDatabase()
        self.assertEqual([s['stepId'] for s in projects.getProjectSteps(self.project, self.owner)], [self.step, second])
        self.assertEqual(len(projects.getProjectSteps(self.otherProject, self.other)), 1)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        databasePatch = patch.object(db, 'DATABASE_PATH', Path(self.temp.name) / 'test.db')
        databasePatch.start()
        self.addCleanup(databasePatch.stop)
        db.initializeDatabase()
        self.owner = db.createUser('owner@example.com', 'hash', 'salt', 'owner')
        self.other = db.createUser('other@example.com', 'hash', 'salt', 'other')
        self.project = self.createProject(self.owner)
        self.otherProject = self.createProject(self.other)
        self.step = projects.saveProjectStep(self.project, 'Слепить основу', self.owner)[2]
        self.otherStep = projects.saveProjectStep(self.otherProject, 'Чужой этап', self.other)[2]

    def createProject(self, userId, deadline=''):
        success, message, projectId = projects.saveProject(userId, 'Котик', 'Животные', deadline, '')
        self.assertTrue(success, message)
        return projectId

    def snapshot(self):
        connection = db.getConnection()
        try:
            return [list(map(tuple, connection.execute(f'SELECT * FROM {table} ORDER BY 1')))
                    for table in ('projects', 'projectSteps')]
        finally:
            connection.close()

    def test_invalid_deadlines_do_not_create_projects(self):
        before = self.snapshot()
        for value in ('НЕ ДАТА', '31.04.2026', '29.02.2025', '00.01.2026',
                      '01.13.2026', '01.01.0000', '1.04.2026', '2026-04-25',
                      '25.04.26', '25.04.2026 лишнее'):
            with self.subTest(deadline=value):
                success, message, projectId = projects.saveProject(
                    self.owner, 'Котик', 'Животные', value, '')
                self.assertFalse(success)
                self.assertTrue(message)
                self.assertIsNone(projectId)
                self.assertEqual(before, self.snapshot())

    def test_valid_deadlines_including_leap_and_past_dates(self):
        for value in ('25.04.2026', '29.02.2024', '31.12.2030', ' 01.01.2020 '):
            with self.subTest(deadline=value):
                projectId = self.createProject(self.owner, value)
                self.assertEqual(db.getProjectById(projectId, self.owner)['deadlineDate'], value.strip())

    def test_empty_deadline_is_optional(self):
        for value in ('', None, '   '):
            projectId = self.createProject(self.owner, value)
            self.assertEqual(db.getProjectById(projectId, self.owner)['deadlineDate'], '')

    def test_delete_removes_all_steps_and_preserves_other_project(self):
        projects.saveProjectStep(self.project, 'Ещё один этап', self.owner)
        otherBefore = tuple(db.getProjectById(self.otherProject, self.other))
        self.assertTrue(projects.removeProject(self.project, self.owner))
        self.assertIsNone(db.getProjectById(self.project, self.owner))
        # Проверяем таблицу напрямую: JOIN мог бы скрыть оставшиеся сироты.
        connection = db.getConnection()
        try:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM projectSteps WHERE projectId = ?',
                                                (self.project,)).fetchone()[0], 0)
        finally:
            connection.close()
        self.assertEqual(tuple(db.getProjectById(self.otherProject, self.other)), otherBefore)
        self.assertEqual(len(projects.getProjectSteps(self.otherProject, self.other)), 1)
        self.assertFalse(projects.removeProject(self.project, self.owner))

    def test_delete_is_atomic_if_database_rejects_project_deletion(self):
        connection = db.getConnection()
        try:
            connection.execute("""CREATE TRIGGER reject_delete BEFORE DELETE ON projects
                BEGIN SELECT RAISE(ABORT, 'test failure'); END""")
            connection.commit()
        finally:
            connection.close()
        before = self.snapshot()
        with self.assertRaises(sqlite3.IntegrityError):
            projects.removeProject(self.project, self.owner)
        self.assertEqual(self.snapshot(), before)

    def test_other_user_cannot_read_project_steps_or_progress(self):
        self.assertIsNone(db.getProjectById(self.project, self.other))
        self.assertEqual(projects.getProjectSteps(self.project, self.other), [])
        self.assertIsNone(projects.calculateProjectProgress(self.project, self.other))
        self.assertEqual([p['projectId'] for p in projects.getUserProjects(self.other)], [self.otherProject])
        self.assertEqual(len(projects.getProjectSteps(self.project, self.owner)), 1)

    def test_other_user_cannot_change_project_or_steps(self):
        before = self.snapshot()
        self.assertFalse(projects.removeProject(self.project, self.other))
        self.assertFalse(projects.saveProjectStep(self.project, 'Подставной этап', self.other)[0])
        self.assertIsNone(projects.changeProjectStepStatus(self.project, self.step, True, self.other))
        self.assertIsNone(projects.removeProjectStep(self.project, self.step, self.other))
        self.assertIsNone(projects.refreshProjectProgress(self.project, self.other))
        self.assertEqual(self.snapshot(), before)

    def test_step_id_must_belong_to_supplied_project(self):
        sameOwnerProject = self.createProject(self.owner)
        before = self.snapshot()
        for projectId, stepId in ((self.project, self.otherStep), (self.otherProject, self.step),
                                  (sameOwnerProject, self.step)):
            with self.subTest(project=projectId, step=stepId):
                self.assertIsNone(projects.changeProjectStepStatus(projectId, stepId, True, self.owner))
                self.assertIsNone(projects.removeProjectStep(projectId, stepId, self.owner))
                self.assertEqual(self.snapshot(), before)

    def test_database_operations_also_check_owner_and_project(self):
        before = self.snapshot()
        self.assertEqual(db.getProjectStepsByProjectId(self.project, self.other), [])
        self.assertIsNone(db.createProjectStep(self.project, 'Новый этап', self.other))
        self.assertFalse(db.updateProjectStepStatus(self.project, self.step, True, self.other))
        self.assertFalse(db.deleteProjectStepById(self.project, self.step, self.other))
        self.assertFalse(db.updateProjectProgress(self.project, 100, self.other))
        self.assertFalse(db.deleteProjectById(self.project, self.other))
        self.assertFalse(db.updateProjectStepStatus(self.project, self.otherStep, True, self.owner))
        self.assertFalse(db.deleteProjectStepById(self.project, self.otherStep, self.owner))
        self.assertEqual(self.snapshot(), before)

    def test_missing_ids_are_rejected_without_changes(self):
        missing = 999999
        before = self.snapshot()
        self.assertFalse(projects.saveProjectStep(missing, 'Новый этап', self.owner)[0])
        self.assertFalse(projects.removeProject(missing, self.owner))
        self.assertEqual(projects.getProjectSteps(missing, self.owner), [])
        self.assertIsNone(projects.refreshProjectProgress(missing, self.owner))
        self.assertIsNone(projects.changeProjectStepStatus(self.project, missing, True, self.owner))
        self.assertIsNone(projects.removeProjectStep(self.project, missing, self.owner))
        self.assertEqual(self.snapshot(), before)

    def test_owner_can_change_steps_and_progress(self):
        secondStep = projects.saveProjectStep(self.project, 'Слепить уши', self.owner)[2]
        self.assertTrue(projects.saveProjectStepPhoto(self.project, self.step, self.owner, photo())[0])
        self.assertEqual(projects.changeProjectStepStatus(self.project, self.step, True, self.owner), 50)
        self.assertEqual(db.getProjectById(self.project, self.owner)['progressPercent'], 50)
        self.assertEqual(projects.removeProjectStep(self.project, secondStep, self.owner), 100)
        self.assertEqual(projects.changeProjectStepStatus(self.project, self.step, False, self.owner), 0)
        self.assertEqual(projects.removeProjectStep(self.project, self.step, self.owner), 0)
        self.assertEqual(projects.getProjectSteps(self.project, self.owner), [])

    def test_invalid_step_is_not_added(self):
        before = self.snapshot()
        for description in ('', None, '  ', 'аб', 'x' * 1001):
            self.assertFalse(projects.saveProjectStep(self.project, description, self.owner)[0])
        self.assertEqual(self.snapshot(), before)


if __name__ == '__main__':
    unittest.main()
