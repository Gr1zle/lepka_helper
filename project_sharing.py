"""Связь личного проекта с палитрой и публикацией.

Публикация хранит отдельную копию только явно выбранных фото, этапов и смесей.
Личные заметки, дедлайн и идентификаторы проекта в неё не попадают.
"""
import json
from contextlib import nullcontext

from color_service import normalizeMixture
from database import openDatabase, createPostWithPhotos
from post_service import (POST_CATEGORIES, validatePostTitle, validatePostDescription, normalizeTags)
from lesson_service import IDEA_LEVELS

MAX_PROJECT_MIXTURES = 10


def readMixture(mixtureJson):
    try:
        mixture = json.loads(mixtureJson)
        return normalizeMixture(mixture['mixtureName'], mixture['resultHex'],
                                mixture['totalWeight'], mixture['recipeItems'])
    except (KeyError, TypeError, ValueError, OverflowError):
        raise ValueError('Рецепт повреждён. Исходные данные не изменены') from None


def getProjectMixtures(projectId, userId):
    with openDatabase() as connection:
        records = connection.execute('''SELECT pm.projectMixtureId, pm.mixtureJson
            FROM projectMixtures AS pm JOIN projects AS pr ON pr.projectId = pm.projectId
            WHERE pm.projectId = ? AND pr.userId = ? ORDER BY pm.projectMixtureId''', (projectId, userId)).fetchall()
    mixtures = []
    for record in records:
        try:
            mixture = readMixture(record['mixtureJson'])
        except ValueError:
            mixture = {'mixtureName': 'Повреждённый рецепт', 'resultHex': '#808080', 'recipeError': True}
        mixtures.append({**mixture, 'projectMixtureId': record['projectMixtureId']})
    return mixtures


def addProjectMixture(projectId, userId, mixtureId):
    with openDatabase() as connection:
        connection.execute('BEGIN IMMEDIATE')
        project = connection.execute('''SELECT pr.projectId FROM projects AS pr
            JOIN users AS usr ON usr.userId = pr.userId
            WHERE pr.projectId = ? AND pr.userId = ? AND usr.isBlocked = 0''', (projectId, userId)).fetchone()
        source = connection.execute('SELECT * FROM colorMixtures WHERE mixtureId = ? AND userId = ?',
                                    (mixtureId, userId)).fetchone()
        if project is None or source is None:
            return False, 'Проект или смесь не найдены либо недоступны'
        try:
            mixture = normalizeMixture(source['mixtureName'], source['resultHex'], source['totalWeight'],
                                       json.loads(source['recipeJson']))
        except (ValueError, TypeError, OverflowError):
            return False, 'Рецепт повреждён. Исходные данные не изменены'
        mixtureJson = json.dumps(mixture, ensure_ascii=False)
        records = connection.execute('SELECT mixtureJson FROM projectMixtures WHERE projectId = ?', (projectId,)).fetchall()
        if any(record['mixtureJson'] == mixtureJson for record in records):
            return False, 'Эта смесь уже добавлена в проект'
        if len(records) >= MAX_PROJECT_MIXTURES:
            return False, 'В проект можно добавить не больше 10 смесей'
        connection.execute('INSERT INTO projectMixtures (projectId, mixtureJson) VALUES (?, ?)', (projectId, mixtureJson))
    return True, 'Смесь добавлена в проект'


def removeProjectMixture(projectId, userId, projectMixtureId):
    with openDatabase() as connection:
        cursor = connection.execute('''DELETE FROM projectMixtures WHERE projectMixtureId = ? AND projectId = ?
            AND projectId IN (SELECT pr.projectId FROM projects AS pr JOIN users AS usr ON usr.userId = pr.userId
            WHERE pr.userId = ? AND usr.isBlocked = 0)''', (projectMixtureId, projectId, userId))
        return cursor.rowcount > 0


def validateSelectedIds(selectedIds, maximumCount):
    if (not isinstance(selectedIds, list) or len(selectedIds) > maximumCount
            or any(type(selectedId) is not int or selectedId < 1 for selectedId in selectedIds)
            or len(set(selectedIds)) != len(selectedIds)):
        raise ValueError('Проверьте выбранные фотографии и смеси')


def normalizeWorkshopInfo(workshopInfo):
    if not isinstance(workshopInfo, dict) or workshopInfo.get('level') not in IDEA_LEVELS:
        raise ValueError('Выберите сложность мастер-класса из списка')
    minutes = workshopInfo.get('timeMinutes')
    if isinstance(minutes, bool) or not str(minutes).strip().isdecimal():
        raise ValueError('Укажите время целым числом от 1 до 1440 минут')
    minutes = int(minutes)
    if not 1 <= minutes <= 1440:
        raise ValueError('Укажите время целым числом от 1 до 1440 минут')
    normalized = {'level': workshopInfo['level'], 'timeMinutes': minutes}
    for key, minimum in (('materials', 1), ('tools', 0)):
        entries = workshopInfo.get(key)
        if (not isinstance(entries, list) or not minimum <= len(entries) <= 30
                or any(not isinstance(entry, str) or not 1 <= len(entry.strip()) <= 120 for entry in entries)):
            raise ValueError('Укажите 1–30 материалов и до 30 инструментов, каждый не длиннее 120 символов')
        normalized[key] = list(dict.fromkeys(entry.strip() for entry in entries))
    return normalized


def prepareProjectPublication(projectId, userId, titleText, descriptionText, categoryName, tagsText,
                               resultStepId, otherStepIds, projectMixtureIds, workshopInfo=None, existingConnection=None):
    if not isinstance(titleText, str) or not isinstance(descriptionText, str):
        return False, 'Введите название и описание работы', None
    titleText, descriptionText = titleText.strip(), descriptionText.strip()
    for error in (validatePostTitle(titleText), validatePostDescription(descriptionText)):
        if error:
            return False, error, None
    if categoryName not in POST_CATEGORIES:
        return False, 'Выберите категорию из списка', None
    try:
        tagsText = normalizeTags(tagsText)
        maximumSteps = 100 if workshopInfo is not None else 10
        validateSelectedIds(otherStepIds, maximumSteps - 1)
        validateSelectedIds([resultStepId, *otherStepIds], maximumSteps)
        validateSelectedIds(projectMixtureIds, MAX_PROJECT_MIXTURES)
        if workshopInfo is not None:
            workshopInfo = normalizeWorkshopInfo(workshopInfo)
    except ValueError as error:
        return False, str(error), None

    context = openDatabase() if existingConnection is None else nullcontext(existingConnection)
    with context as connection:
        # Проверки и копирование выполняются в одной транзакции: проект нельзя
        # удалить или изменить между проверкой владельца и сохранением фото.
        if existingConnection is None:
            connection.execute('BEGIN')
        project = connection.execute('''SELECT pr.projectId FROM projects AS pr
            JOIN users AS usr ON usr.userId = pr.userId
            WHERE pr.projectId = ? AND pr.userId = ? AND usr.isBlocked = 0''', (projectId, userId)).fetchone()
        if project is None:
            return False, 'Проект не найден или недоступен', None
        photos, steps, mixtures = [], [], []
        selectedSteps = []
        stepOrder = {}
        for stepId in [resultStepId, *otherStepIds]:
            step = connection.execute('SELECT stepDescription, photoImage, sortOrder FROM projectSteps WHERE projectId = ? AND stepId = ?',
                                      (projectId, stepId)).fetchone()
            if step is None or (not step['photoImage'] and (workshopInfo is None or stepId == resultStepId)):
                return False, 'Добавьте фото выбранного этапа или измените выбор', None
            position = len(photos) if step['photoImage'] else None
            selectedSteps.append((stepId, {'description': step['stepDescription'], 'photoPosition': position}))
            stepOrder[stepId] = (step['sortOrder'], stepId)
            if step['photoImage']:
                photos.append(bytes(step['photoImage']))
                if len(photos) > 10:
                    return False, 'В публикации допускается не больше 10 фото', None
        # Обложка остаётся первой фотографией, шаги читаются в порядке проекта.
        if workshopInfo is not None:
            selectedSteps.sort(key=lambda item: stepOrder[item[0]])
        steps = [step for stepId, step in selectedSteps]
        for mixtureId in projectMixtureIds:
            record = connection.execute('SELECT mixtureJson FROM projectMixtures WHERE projectId = ? AND projectMixtureId = ?',
                                        (projectId, mixtureId)).fetchone()
            if record is None:
                return False, 'Выбранная смесь не найдена в этом проекте', None
            try:
                mixtures.append(readMixture(record['mixtureJson']))
            except ValueError as error:
                return False, str(error), None
        details = {'steps': steps, 'mixtures': mixtures}
        if workshopInfo is not None:
            details.update(formatVersion=2, workshopInfo=workshopInfo)
        details = json.dumps(details, ensure_ascii=False)
    return True, 'Материалы публикации подготовлены', {
        'titleText': titleText, 'descriptionText': descriptionText, 'categoryName': categoryName,
        'tagsText': tagsText, 'photos': photos, 'projectDetailsJson': details}


def publishProject(projectId, userId, titleText, descriptionText, categoryName, tagsText,
                   resultStepId, otherStepIds, projectMixtureIds, workshopInfo=None):
    with openDatabase() as connection:
        connection.execute('BEGIN IMMEDIATE')
        success, message, payload = prepareProjectPublication(projectId, userId, titleText, descriptionText,
            categoryName, tagsText, resultStepId, otherStepIds, projectMixtureIds, workshopInfo, connection)
        if not success:
            return False, message, None
        postId = createPostWithPhotos(userId, **payload, existingConnection=connection)
    return True, 'Проект опубликован в сообществе', postId


def readPublishedProject(detailsJson):
    if not detailsJson:
        return None
    try:
        details = json.loads(detailsJson)
        steps, mixtures = details['steps'], details['mixtures']
        isWorkshop = details.get('formatVersion') == 2
        if (not isinstance(steps, list) or not 1 <= len(steps) <= (100 if isWorkshop else 10)
                or not isinstance(mixtures, list) or len(mixtures) > MAX_PROJECT_MIXTURES):
            raise ValueError()
        publicSteps = []
        photoPositions = []
        for index, step in enumerate(steps):
            position = step['photoPosition']
            if (not isinstance(step['description'], str) or not 3 <= len(step['description']) <= 1000
                    or (position is not None and (type(position) is not int or not 0 <= position < 10))
                    or (not isWorkshop and (type(position) is not int or position != index))):
                raise ValueError()
            if position is not None:
                photoPositions.append(position)
            publicSteps.append({'description': step['description'], 'photoPosition': position})
        if sorted(photoPositions) != list(range(len(photoPositions))) or not photoPositions:
            raise ValueError()
        result = {'steps': publicSteps, 'mixtures': [readMixture(json.dumps(mixture)) for mixture in mixtures]}
        if isWorkshop:
            result['workshopInfo'] = normalizeWorkshopInfo(details['workshopInfo'])
        return result
    except (KeyError, TypeError, ValueError, OverflowError):
        return None


def getPublishedProject(postId):
    with openDatabase() as connection:
        post = connection.execute('SELECT projectDetailsJson FROM posts WHERE postId = ? AND isDeleted = 0', (postId,)).fetchone()
        return readPublishedProject(post['projectDetailsJson']) if post else None


def copyPublishedMixture(postId, mixtureIndex, userId):
    with openDatabase() as connection:
        connection.execute('BEGIN IMMEDIATE')
        user = connection.execute('SELECT userId FROM users WHERE userId = ? AND isBlocked = 0', (userId,)).fetchone()
        post = connection.execute('SELECT projectDetailsJson FROM posts WHERE postId = ? AND isDeleted = 0', (postId,)).fetchone()
        details = readPublishedProject(post['projectDetailsJson']) if post else None
        if user is None or not details or type(mixtureIndex) is not int or not 0 <= mixtureIndex < len(details['mixtures']):
            return False, 'Публикация, рецепт или аккаунт недоступны', None
        mixture = details['mixtures'][mixtureIndex]
        return saveMixtureCopy(userId, mixture, connection)


def saveMixtureCopy(userId, mixture, existingConnection=None):
    mixture = normalizeMixture(mixture['mixtureName'], mixture['resultHex'], mixture['totalWeight'], mixture['recipeItems'])
    context = openDatabase() if existingConnection is None else nullcontext(existingConnection)
    with context as connection:
        if existingConnection is None:
            connection.execute('BEGIN IMMEDIATE')
        if connection.execute('SELECT userId FROM users WHERE userId = ? AND isBlocked = 0', (userId,)).fetchone() is None:
            return False, 'Аккаунт недоступен', None
        recipeJson = json.dumps(mixture['recipeItems'], ensure_ascii=False)
        existing = connection.execute('''SELECT mixtureId FROM colorMixtures
            WHERE userId = ? AND resultHex = ? AND totalWeight = ? AND recipeJson = ?''',
            (userId, mixture['resultHex'], mixture['totalWeight'], recipeJson)).fetchone()
        if existing:
            return True, 'Этот рецепт уже есть в вашей палитре', existing['mixtureId']
        cursor = connection.execute('''INSERT INTO colorMixtures
            (userId, mixtureName, resultHex, totalWeight, recipeJson) VALUES (?, ?, ?, ?, ?)''',
            (userId, mixture['mixtureName'], mixture['resultHex'], mixture['totalWeight'], recipeJson))
        return True, 'Рецепт сохранён. Откройте его на вкладке «Цвета»', cursor.lastrowid
