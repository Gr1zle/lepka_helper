"""Чтение опубликованного мастер-класса и личный прогресс читателя."""
import json
from contextlib import nullcontext

from database import openDatabase, createProjectWithSteps
from lesson_service import normalizeLessonState
from post_service import getCommunityPosts
from project_sharing import readPublishedProject


def getWorkshop(postId, existingConnection=None):
    context = openDatabase() if existingConnection is None else nullcontext(existingConnection)
    with context as connection:
        record = connection.execute('''SELECT posts.*, COALESCE(remoteAccounts.displayNickname, users.nickname) AS nickname
            FROM posts JOIN users ON users.userId = posts.userId
            LEFT JOIN remoteAccounts ON remoteAccounts.localUserId = users.userId
            WHERE posts.postId = ? AND posts.isDeleted = 0''', (postId,)).fetchone()
        details = readPublishedProject(record['projectDetailsJson']) if record else None
        if not details:
            return None
        photoIds = [photo['photoId'] for photo in connection.execute(
            'SELECT photoId FROM postPhotos WHERE postId = ? ORDER BY position', (postId,))]
        if any(step['photoPosition'] is not None and step['photoPosition'] >= len(photoIds) for step in details['steps']):
            return None
        info = details.get('workshopInfo')
        # Старый формат начинался с результата; при чтении переносим его в конец.
        steps = details['steps'] if info else [*details['steps'][1:], details['steps'][0]]
        return {'postId': postId, 'title': record['titleText'], 'description': record['descriptionText'],
                'category': record['categoryName'], 'nickname': record['nickname'],
                'level': info['level'] if info else None, 'timeMinutes': info['timeMinutes'] if info else None,
                'materials': info['materials'] if info else [], 'tools': info['tools'] if info else [],
                'steps': steps, 'photoIds': photoIds, 'mixtures': details['mixtures']}


def normalizeWorkshopState(workshop, state):
    # Формат отметок тот же, что у встроенных уроков. Чек-лист объединяет
    # материалы и инструменты, но хранится отдельно от прогресса уроков.
    return normalizeLessonState({'steps': workshop['steps'], 'materials': [*workshop['materials'], *workshop['tools']]}, state)


def getUserWorkshopState(userId, postId):
    workshop = getWorkshop(postId)
    if workshop is None:
        raise ValueError('Мастер-класс не найден или удалён')
    default = {'lastStep': 0, 'completedSteps': [], 'checkedMaterials': [], 'isCompleted': False}
    with openDatabase() as connection:
        row = connection.execute('SELECT stateJson FROM workshopProgress WHERE userId = ? AND postId = ?',
                                 (userId, postId)).fetchone()
    if row:
        try:
            return normalizeWorkshopState(workshop, json.loads(row['stateJson']))
        except (ValueError, TypeError, KeyError):
            pass  # Повреждённая запись остаётся нетронутой; интерфейс показывает начальное состояние.
    return default


def saveUserWorkshopState(userId, postId, state):
    with openDatabase() as connection:
        connection.execute('BEGIN IMMEDIATE')
        user = connection.execute('SELECT userId FROM users WHERE userId = ? AND isBlocked = 0', (userId,)).fetchone()
        workshop = getWorkshop(postId, connection)
        if user is None or workshop is None:
            raise ValueError('Мастер-класс или аккаунт недоступны')
        normalized = normalizeWorkshopState(workshop, state)
        connection.execute('''INSERT INTO workshopProgress (userId, postId, stateJson) VALUES (?, ?, ?)
            ON CONFLICT (userId, postId) DO UPDATE SET stateJson = excluded.stateJson''',
            (userId, postId, json.dumps(normalized)))
        return normalized


def addWorkshopAsProject(postId, userId):
    with openDatabase() as connection:
        connection.execute('BEGIN IMMEDIATE')
        user = connection.execute('SELECT userId FROM users WHERE userId = ? AND isBlocked = 0', (userId,)).fetchone()
        workshop = getWorkshop(postId, connection)
        if user is None or workshop is None:
            return False, 'Мастер-класс или аккаунт недоступны', None
        info = f"Мастер-класс: {workshop['title']}\nАвтор: {workshop['nickname']}\n"
        if workshop['level']:
            info += f"Сложность: {workshop['level']}\nВремя: {workshop['timeMinutes']} мин\n"
        info += 'Материалы и инструменты: ' + ', '.join([*workshop['materials'], *workshop['tools']]) + '\n'
        projectId = createProjectWithSteps(userId, workshop['title'][:80], workshop['category'], '',
            (info + workshop['description'])[:1500], [step['description'] for step in workshop['steps']], connection)
        connection.executemany('INSERT INTO projectMixtures (projectId, mixtureJson) VALUES (?, ?)',
            [(projectId, json.dumps(mixture, ensure_ascii=False)) for mixture in workshop['mixtures']])
    return True, 'Мастер-класс добавлен в проекты. Добавьте фото своих этапов по мере работы', projectId


def searchCommunityWorks(queryText, categoryName='Все', levelName='Все', maxTime=None, onlyVideo=False):
    if onlyVideo:
        return []  # У публикаций пока нет видео.
    queryText = (queryText or '').strip().casefold()
    if queryText and len(queryText) < 2:
        return []
    results = []
    for item in getCommunityPosts():
        if item['isDeleted'] or (categoryName != 'Все' and item['categoryName'] != categoryName):
            continue
        workshop = getWorkshop(item['postId'])
        if levelName != 'Все' and (not workshop or workshop['level'] != levelName):
            continue
        if maxTime is not None and (not workshop or workshop['timeMinutes'] is None or workshop['timeMinutes'] > int(maxTime)):
            continue
        searchable = ' '.join(str(item[key]) for key in ('titleText', 'descriptionText', 'tagsText', 'nickname'))
        if workshop:
            searchable += ' ' + ' '.join([*workshop['materials'], *workshop['tools'], workshop['level'] or ''])
        if all(word in searchable.casefold() for word in queryText.split()):
            results.append(item)
    return results
