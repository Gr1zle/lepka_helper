"""Расчёты, PNG, уроки и проекты: временная SQLite, без пользовательских данных."""
from io import BytesIO
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image
from fastapi.testclient import TestClient

import color_service as colors
from color_export import createRecipePng
import database
import lesson_service as lessons
import project_service as projects
from image_fixtures import photo
from download_service import createDownload
from web_app import createWebApp


def selected(ids=(1, 2), proportions=(50, 50)):
    return [{**colors.BASE_COLORS[index - 1], 'proportion': value} for index, value in zip(ids, proportions)]


class ColorTests(unittest.TestCase):
    def test_white_black_equal_mix_and_default_weight(self):
        self.assertEqual(colors.calculateMixedColor(selected()), '#808080')
        recipe = colors.calculateRecipe(selected(), None)
        self.assertEqual([item['grams'] for item in recipe], [50, 50])
        self.assertEqual([item['percent'] for item in recipe], [50, 50])

    def test_normalization_and_rounding_preserve_total(self):
        for count in range(2, 6):
            for weight in (0.01, 1, 7, 100, 123.45):
                with self.subTest(count=count, weight=weight):
                    data = selected(range(1, count + 1), [1] * count)
                    before = json.dumps(data)
                    recipe = colors.calculateRecipe(data, weight)
                    self.assertAlmostEqual(sum(item['percent'] for item in recipe), 100)
                    self.assertAlmostEqual(sum(item['grams'] for item in recipe), weight)
                    self.assertEqual(json.dumps(data), before)
                    self.assertTrue(all(item['grams'] >= 0 for item in recipe))

    def test_invalid_doses_counts_ids_and_hex_are_rejected(self):
        badCases = [selected(proportions=(0, 0)), selected(proportions=(-1, 100)),
                    selected(proportions=(101, 1)), selected(proportions=(float('nan'), 50)),
                    selected(proportions=(float('inf'), 50)), selected(proportions=('text', 50)),
                    selected((1, 1)), [dict(colors.BASE_COLORS[0], proportion=50), dict(colors.BASE_COLORS[1], colorId=99, proportion=50)], selected(range(1, 7), [20] * 6),
                    [{'colorId': 1, 'hex': None, 'proportion': 100}], [None]]
        for value in badCases:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    colors.calculateRecipe(value, 100)
        self.assertEqual(colors.calculateMixedColor([]), '#FFFFFF')
        self.assertEqual(colors.calculateRecipe([], 100), [])

    def test_hex_rejects_prefix_sign_and_non_hex_characters(self):
        for value in ('#0x1234', '#+12345', '#GG0000', '123', None, 123):
            self.assertFalse(colors.validateHexColor(value))
        self.assertTrue(colors.validateHexColor('ffffff'))
        self.assertEqual(colors.normalizeHexColor(' #ff00aa '), '#FF00AA')

    def test_invalid_weights_do_not_silently_become_100_grams(self):
        for value in (0, -1, 0.001, 'НЕ ЧИСЛО', 'nan', 'inf', float('nan'), True):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    colors.calculateRecipe(selected(), value)
        self.assertEqual(colors.normalizeWeight('100,25'), 100.25)

    def test_png_contains_readable_recipe_data_and_result_color(self):
        data = createRecipePng('Белый и чёрный', selected(), 100)
        self.assertTrue(data.startswith(b'\x89PNG\r\n\x1a\n'))
        with Image.open(BytesIO(data)) as image:
            image.load()
            self.assertEqual(image.size, (1000, 570))
            self.assertEqual(image.getpixel((70, 195)), (128, 128, 128))
            recipe = json.loads(image.info['Recipe'])
            self.assertEqual(recipe['name'], 'Белый и чёрный')
            self.assertEqual(recipe['resultHex'], '#808080')
            self.assertEqual(recipe['items'][0]['name'], 'Белый')
            self.assertEqual(sum(item['grams'] for item in recipe['items']), 100)
        with self.assertRaises(ValueError):
            createRecipePng('Один цвет', selected((1,), (100,)), 100)

    def test_png_download_is_one_time_and_not_a_path_to_local_files(self):
        payload = createRecipePng('Рецепт', selected(), 100)
        ticket = createDownload(payload)
        with TestClient(createWebApp()) as client:
            head = client.head('/downloads/' + ticket)
            self.assertEqual(head.status_code, 200)
            self.assertEqual(int(head.headers['content-length']), len(payload))
            response = client.get('/downloads/' + ticket)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.content, payload)
            self.assertEqual(response.headers['content-type'], 'image/png')
            self.assertIn('attachment', response.headers['content-disposition'])
            self.assertEqual(response.headers['cache-control'], 'no-store')
            self.assertEqual(client.get('/downloads/' + ticket).status_code, 404)
            self.assertEqual(client.get('/downloads/not-a-ticket').status_code, 404)

    def test_expired_png_link_does_not_return_recipe(self):
        ticket = createDownload(b'fake-test-data')
        with TestClient(createWebApp()) as client, patch('download_service.time') as clock:
            clock.monotonic.return_value = float('inf')
            self.assertEqual(client.get('/downloads/' + ticket).status_code, 404)


class StoredToolsTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        dbPatch = patch.object(database, 'DATABASE_PATH', Path(folder.name) / 'test.db')
        dbPatch.start()
        self.addCleanup(dbPatch.stop)
        database.initializeDatabase()
        self.owner = database.createUser('owner@example.com', 'hash', 'salt', 'owner')
        self.other = database.createUser('other@example.com', 'hash', 'salt', 'other')

    def test_mixture_save_read_delete_and_owner_isolation(self):
        recipe = colors.calculateRecipe(selected(), 100)
        mixture = colors.saveColorMixture(self.owner, 'Моя смесь', '#808080', 100, recipe)
        self.assertEqual(colors.getUserColorMixtures(self.other), [])
        read = colors.getUserColorMixtures(self.owner)[0]
        self.assertEqual(read['recipeItems'], recipe)
        self.assertFalse(read['recipeError'])
        self.assertFalse(colors.deleteColorMixture(self.other, mixture))
        self.assertTrue(colors.deleteColorMixture(self.owner, mixture))
        self.assertEqual(colors.getUserColorMixtures(self.owner), [])

    def test_invalid_mixture_is_not_persisted(self):
        recipe = colors.calculateRecipe(selected(), 100)
        for name, color, weight, items in (('aa', '#808080', 100, recipe),
                ('valid', '#FF0000', 100, recipe), ('valid', '#808080', -1, recipe),
                ('valid', '#808080', 100, [dict(item, grams=1) for item in recipe])):
            with self.assertRaises(ValueError):
                colors.saveColorMixture(self.owner, name, color, weight, items)
        self.assertEqual(colors.getUserColorMixtures(self.owner), [])

    def test_corrupt_old_recipe_is_reported_without_rewriting_data(self):
        database.createColorMixture(self.owner, 'Старый рецепт', 'bad color', 100, '{broken json')
        read = colors.getUserColorMixtures(self.owner)[0]
        self.assertTrue(read['recipeError'])
        self.assertEqual(read['resultHex'], '#808080')
        raw = database.getColorMixturesByUserId(self.owner)[0]
        self.assertEqual(raw['recipeJson'], '{broken json')
        self.assertEqual(raw['resultHex'], 'bad color')
        recipe = colors.calculateRecipe(selected(), 100)
        del recipe[0]['name']
        database.createColorMixture(self.owner, 'Неполный рецепт', '#808080', 100, json.dumps(recipe))
        self.assertTrue(all(item['recipeError'] for item in colors.getUserColorMixtures(self.owner)))

    def test_lesson_progress_materials_and_owner_isolation_survive_reinitialization(self):
        lesson = lessons.getLessonById(1)
        state = {'lastStep': 2, 'completedSteps': [0, 1], 'checkedMaterials': [0, 2], 'isCompleted': True}
        saved = lessons.saveUserLessonState(self.owner, 1, state)
        self.assertFalse(saved['isCompleted'])
        database.initializeDatabase()
        self.assertEqual(lessons.getUserLessonState(self.owner, 1), saved)
        self.assertEqual(lessons.getUserLessonState(self.other, 1)['completedSteps'], [])
        state['completedSteps'] = list(range(len(lesson['steps'])))
        self.assertTrue(lessons.saveUserLessonState(self.owner, 1, state)['isCompleted'])
        state['completedSteps'].remove(0)
        self.assertFalse(lessons.saveUserLessonState(self.owner, 1, state)['isCompleted'])

    def test_invalid_lesson_progress_does_not_replace_valid_state(self):
        state = {'lastStep': 0, 'completedSteps': [0], 'checkedMaterials': []}
        lessons.saveUserLessonState(self.owner, 1, state)
        for invalid in ({}, dict(state, lastStep=99), dict(state, completedSteps=[True]),
                        dict(state, checkedMaterials=[99]), None):
            with self.assertRaises(ValueError):
                lessons.saveUserLessonState(self.owner, 1, invalid)
        self.assertEqual(lessons.getUserLessonState(self.owner, 1)['completedSteps'], [0])

    def test_delete_account_also_removes_lesson_progress(self):
        lessons.saveUserLessonState(self.owner, 1, {'lastStep': 0, 'completedSteps': [0], 'checkedMaterials': []})
        database.deleteUserDataById(self.owner)
        with database.openDatabase() as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM lessonProgress').fetchone()[0], 0)
            self.assertEqual(connection.execute('PRAGMA foreign_key_check').fetchall(), [])

    def test_project_and_all_lesson_steps_are_created_together(self):
        lesson = lessons.getLessonById(1)
        success, message, project = projects.saveProject(self.owner, lesson['title'], lesson['category'], '', lesson['description'], lesson['steps'])
        self.assertTrue(success, message)
        steps = projects.getProjectSteps(project, self.owner)
        self.assertEqual([item['stepDescription'] for item in steps], lesson['steps'])
        for item in steps:
            projects.saveProjectStepPhoto(project, item['stepId'], self.owner, photo())
        self.assertEqual(projects.changeProjectStepStatus(project, steps[0]['stepId'], True, self.owner), 16.7)
        for item in steps[1:]:
            projects.changeProjectStepStatus(project, item['stepId'], True, self.owner)
        self.assertEqual(projects.getUserProjects(self.owner)[0]['progressPercent'], 100)

    def test_project_creation_rolls_back_when_step_insert_fails(self):
        with database.openDatabase() as connection:
            connection.execute("CREATE TRIGGER reject_step BEFORE INSERT ON projectSteps BEGIN SELECT RAISE(ABORT, 'test failure'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            projects.saveProject(self.owner, 'Котик', 'Животные', '', '', ['Подготовить материал'])
        self.assertEqual(database.getProjectsByUserId(self.owner), [])

    def test_project_and_step_editing_check_owner_and_ids(self):
        project = projects.saveProject(self.owner, 'Котик', 'Животные', '', '', ['Подготовить материал'])[2]
        step = projects.getProjectSteps(project, self.owner)[0]['stepId']
        self.assertFalse(projects.editProject(project, self.other, 'Чужой', 'Животные', '', '')[0])
        self.assertFalse(projects.editProject(project, self.owner, 'Котик', 'Нет категории', '', '')[0])
        self.assertFalse(projects.editProject(project, self.owner, 'Котик', 'Животные', 'НЕ ДАТА', '')[0])
        self.assertTrue(projects.editProject(project, self.owner, 'Новый котик', 'Животные', '25.04.2026', '')[0])
        self.assertFalse(projects.editProjectStep(project, step, self.other, 'Изменённый этап')[0])
        otherProject = projects.saveProject(self.owner, 'Собачка', 'Животные', '', '')[2]
        self.assertFalse(projects.editProjectStep(otherProject, step, self.owner, 'Изменённый этап')[0])
        self.assertTrue(projects.editProjectStep(project, step, self.owner, 'Изменённый этап')[0])
        self.assertEqual(projects.getProjectSteps(project, self.owner)[0]['stepDescription'], 'Изменённый этап')


class CatalogTests(unittest.TestCase):
    def test_search_by_words_material_and_combined_filters(self):
        self.assertEqual([item['lessonId'] for item in lessons.searchLessons('ПИЦЦА', 'Еда', 'Начинающий', 30)], [2])
        self.assertEqual(lessons.searchLessons('пицца', 'Все', maxTime=20), [])
        self.assertTrue(lessons.searchLessons('стек', 'Все'))
        self.assertEqual(lessons.searchLessons('', 'Все', onlyVideo=True), [])
        self.assertEqual(lessons.searchLessons('', maxTime=0), [])
        for time in ('bad', -1, True, 1.5):
            with self.assertRaises(ValueError):
                lessons.searchLessons('', maxTime=time)

    def test_lesson_data_and_illustrations_are_available_offline(self):
        for lesson in lessons.LESSON_ITEMS:
            self.assertTrue(lesson['materials'])
            self.assertTrue(lesson['steps'])
            path = Path(__file__).resolve().parents[1] / 'assets' / lesson['previewImage']
            self.assertTrue(path.exists())
            self.assertIn('<svg', path.read_text(encoding='utf-8'))
        copy = lessons.getLessonById(1)
        copy['steps'].clear()
        self.assertTrue(lessons.getLessonById(1)['steps'])

    def test_illustrations_and_flet_bootstrap_are_served_by_web_app(self):
        with TestClient(createWebApp()) as client:
            response = client.get('/lessons/lesson_1.svg')
            self.assertEqual(response.status_code, 200)
            self.assertIn('<svg', response.text)
            self.assertIn('flutter_bootstrap.js', client.get('/').text)

    def test_idea_parameters_are_honored_for_every_color_count(self):
        for count in range(1, 6):
            idea = lessons.generateRandomIdea('Фэнтези', 'Начинающий', 'Тёплая', count)
            self.assertEqual(idea['theme'], 'Фэнтези')
            self.assertEqual(idea['level'], 'Начинающий')
            self.assertEqual(len(set(idea['colors'])), count)
            self.assertTrue(all(value in lessons.IDEA_PALETTES['Тёплая'] for value in idea['colors']))
            self.assertLessEqual(idea['estimatedTime'], 40)
            self.assertTrue(idea['steps'])
        with self.assertRaises(ValueError):
            lessons.generateRandomIdea(colorCount=6)
        with self.assertRaises(ValueError):
            lessons.generateRandomIdea(themeName='Неизвестная')


if __name__ == '__main__':
    unittest.main()
