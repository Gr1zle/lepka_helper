"""Перенос личного проекта: ограниченный JSON, без ID владельца и путей файлов."""
import base64
import json
from database import openDatabase, createProjectWithSteps
from project_service import normalizeProjectData, validateStepDescription
from project_sharing import readMixture
from photo_service import preparePhoto

MAX_ARCHIVE_BYTES = 20 * 1024 * 1024
MAX_STEPS = 100


def decodeProject(content):
    if not isinstance(content, bytes) or not 0 < len(content) <= MAX_ARCHIVE_BYTES:
        raise ValueError('JSON проекта должен быть не больше 20 МБ')
    try:
        data = json.loads(content.decode('utf-8-sig'))
        if (not isinstance(data, dict) or set(data) != {'format', 'version', 'project', 'steps', 'mixtures'}
                or data['format'] != 'lepka-helper-project' or type(data['version']) is not int or data['version'] != 1):
            raise ValueError('Неподдерживаемый формат проекта')
        project = data['project']
        if not isinstance(project, dict) or set(project) != {'name', 'category', 'deadline', 'notes'}:
            raise ValueError('Некорректное описание проекта')
        if any(not isinstance(value, str) for value in project.values()):
            raise ValueError('Поля проекта должны быть текстом')
        normalized = dict(zip(('projectName', 'categoryName', 'deadlineDate', 'descriptionText'),
            normalizeProjectData(project['name'], project['category'], project['deadline'], project['notes'])))
        steps, mixtures = data['steps'], data['mixtures']
        if not isinstance(steps, list) or len(steps) > MAX_STEPS:
            raise ValueError('В файле допускается не больше 100 этапов')
        if not isinstance(mixtures, list) or len(mixtures) > 10:
            raise ValueError('В файле допускается не больше 10 рецептов')
        cleanSteps = []
        for step in steps:
            if not isinstance(step, dict) or set(step) != {'description', 'completed', 'photo'}:
                raise ValueError('Некорректный этап проекта')
            error = validateStepDescription(step['description'])
            if error:
                raise ValueError(error)
            if type(step['completed']) is not bool:
                raise ValueError('Отметка этапа должна быть true или false')
            image = None
            if step['photo'] is not None:
                if not isinstance(step['photo'], str):
                    raise ValueError('Некорректная фотография этапа')
                try:
                    rawImage = base64.b64decode(step['photo'], validate=True)
                except ValueError:
                    raise ValueError('Некорректная фотография этапа') from None
                image = preparePhoto('step.jpg', rawImage)['data']
            if step['completed'] and image is None:
                raise ValueError('Для завершённого этапа необходимо фото')
            cleanSteps.append({'description': step['description'].strip(), 'completed': step['completed'], 'image': image})
        cleanMixtures = [readMixture(json.dumps(item)) for item in mixtures]
        return {'project': normalized, 'steps': cleanSteps, 'mixtures': cleanMixtures}
    except (json.JSONDecodeError, UnicodeError, KeyError, TypeError, OverflowError, RecursionError) as error:
        raise ValueError('Не удалось прочитать JSON проекта') from error


def exportProject(projectId, userId):
    with openDatabase() as connection:
        connection.execute('BEGIN')
        project = connection.execute('SELECT * FROM projects WHERE projectId=? AND userId=?', (projectId, userId)).fetchone()
        if project is None:
            raise ValueError('Проект не найден или недоступен')
        steps = connection.execute('SELECT * FROM projectSteps WHERE projectId=? ORDER BY sortOrder,stepId', (projectId,)).fetchall()
        if len(steps) > MAX_STEPS:
            raise ValueError('Для переноса допускается не больше 100 этапов')
        body = {'format': 'lepka-helper-project', 'version': 1,
            'project': {'name': project['projectName'], 'category': project['categoryName'],
                        'deadline': project['deadlineDate'], 'notes': project['descriptionText'] or ''},
            'steps': [{'description': step['stepDescription'], 'completed': bool(step['isCompleted']),
                       'photo': base64.b64encode(step['photoImage']).decode() if step['photoImage'] else None} for step in steps],
            'mixtures': [json.loads(row['mixtureJson']) for row in connection.execute(
                'SELECT mixtureJson FROM projectMixtures WHERE projectId=? ORDER BY projectMixtureId', (projectId,))]}
        content = json.dumps(body, ensure_ascii=False, indent=2).encode('utf-8')
    decodeProject(content)  # Экспортируем только файл, который можно восстановить.
    return content


def importProject(userId, content):
    data = decodeProject(content)  # Полная проверка и обработка фото до записи.
    project = data['project']
    with openDatabase() as connection:
        connection.execute('BEGIN IMMEDIATE')
        owner = connection.execute('SELECT userId FROM users WHERE userId=? AND isBlocked=0', (userId,)).fetchone()
        if owner is None:
            raise ValueError('Аккаунт недоступен')
        projectId = createProjectWithSteps(userId, project['projectName'], project['categoryName'], project['deadlineDate'],
            project['descriptionText'], [step['description'] for step in data['steps']], existingConnection=connection)
        ids = [row['stepId'] for row in connection.execute('SELECT stepId FROM projectSteps WHERE projectId=? ORDER BY sortOrder', (projectId,))]
        connection.executemany('UPDATE projectSteps SET photoImage=?,isCompleted=? WHERE stepId=?',
            [(step['image'], int(step['completed']), stepId) for stepId, step in zip(ids, data['steps'])])
        connection.executemany('INSERT INTO projectMixtures (projectId,mixtureJson) VALUES (?,?)',
            [(projectId, json.dumps(item, ensure_ascii=False)) for item in data['mixtures']])
        count = len(data['steps'])
        progress = round(sum(step['completed'] for step in data['steps']) / count * 100, 1) if count else 0
        # Для импортированного завершённого проекта дата завершения неизвестна.
        connection.execute('UPDATE projects SET progressPercent=? WHERE projectId=?', (progress, projectId))
    return projectId
