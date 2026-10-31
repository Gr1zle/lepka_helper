"""Личная библиотека встроенных уроков и история поиска в клиентской SQLite."""
import time
from database import openDatabase
from lesson_service import LESSON_ITEMS, getLessonById, getUserLessonState
from learning_assets import MODEL_ITEMS

MAX_NOTE_LENGTH = 2000
MAX_QUERY_LENGTH = 120


def requireLesson(lessonId):
    if type(lessonId) is not int or getLessonById(lessonId) is None:
        raise ValueError('Встроенный урок не найден')


def requireOwner(connection, userId):
    if connection.execute('SELECT userId FROM users WHERE userId=? AND isBlocked=0 AND roleName!=?',
                          (userId,'deleted')).fetchone() is None:
        raise ValueError('Аккаунт недоступен')


def favoriteLessonIds(userId):
    valid = {lesson['lessonId'] for lesson in LESSON_ITEMS}
    with openDatabase() as connection:
        return {row['lessonId'] for row in connection.execute('''SELECT f.lessonId FROM lessonFavorites f
            JOIN users u ON u.userId=f.userId WHERE f.userId=? AND u.isBlocked=0''',(userId,))} & valid


def saveLessonFavorite(userId, lessonId, selected):
    requireLesson(lessonId)
    if type(selected) is not bool:
        raise ValueError('Некорректная отметка избранного')
    with openDatabase() as connection:
        connection.execute('BEGIN IMMEDIATE')
        requireOwner(connection,userId)
        if selected:
            connection.execute('INSERT OR IGNORE INTO lessonFavorites(userId,lessonId) VALUES (?,?)',(userId,lessonId))
        else:
            connection.execute('DELETE FROM lessonFavorites WHERE userId=? AND lessonId=?',(userId,lessonId))
    return selected


def getLessonNote(userId,lessonId):
    requireLesson(lessonId)
    with openDatabase() as connection:
        record = connection.execute('''SELECT n.noteText FROM lessonNotes n JOIN users u ON u.userId=n.userId
            WHERE n.userId=? AND n.lessonId=? AND u.isBlocked=0''',(userId,lessonId)).fetchone()
    return record['noteText'] if record else ''


def saveLessonNote(userId,lessonId,text):
    requireLesson(lessonId)
    if not isinstance(text,str) or len(text)>MAX_NOTE_LENGTH:
        raise ValueError('Заметка должна содержать не больше 2000 символов')
    text = text.strip()
    with openDatabase() as connection:
        connection.execute('BEGIN IMMEDIATE')
        requireOwner(connection,userId)
        if text:
            connection.execute('''INSERT INTO lessonNotes(userId,lessonId,noteText) VALUES (?,?,?)
                ON CONFLICT(userId,lessonId) DO UPDATE SET noteText=excluded.noteText,updatedAt=CURRENT_TIMESTAMP''',
                (userId,lessonId,text))
        else:
            connection.execute('DELETE FROM lessonNotes WHERE userId=? AND lessonId=?',(userId,lessonId))
    return text


def normalizeSearchQuery(text):
    if not isinstance(text,str):
        raise ValueError('Введите текст запроса')
    text = ' '.join(text.split())
    if len(text)>MAX_QUERY_LENGTH:
        raise ValueError('Поисковый запрос должен быть не длиннее 120 символов')
    return text


def recentSearches(userId):
    with openDatabase() as connection:
        return [row['queryText'] for row in connection.execute('''SELECT h.queryText FROM searchHistory h
            JOIN users u ON u.userId=h.userId WHERE h.userId=? AND u.isBlocked=0
            ORDER BY h.lastUsed DESC,h.queryKey LIMIT 20''',(userId,))]


def rememberSearch(userId,text):
    text = normalizeSearchQuery(text)
    if len(text)<2:
        raise ValueError('Введите не меньше двух символов')
    with openDatabase() as connection:
        connection.execute('BEGIN IMMEDIATE')
        requireOwner(connection,userId)
        connection.execute('''INSERT INTO searchHistory(userId,queryKey,queryText,lastUsed) VALUES (?,?,?,?)
            ON CONFLICT(userId,queryKey) DO UPDATE SET queryText=excluded.queryText,lastUsed=excluded.lastUsed''',
            (userId,text.casefold(),text,time.time_ns()))
        connection.execute('''DELETE FROM searchHistory WHERE userId=? AND queryKey NOT IN
            (SELECT queryKey FROM searchHistory WHERE userId=? ORDER BY lastUsed DESC,queryKey LIMIT 20)''',(userId,userId))


def clearSearchHistory(userId):
    with openDatabase() as connection:
        connection.execute('DELETE FROM searchHistory WHERE userId=?',(userId,))


def searchSuggestions(text,userId=None):
    query = normalizeSearchQuery(text).casefold().replace('ё','е')
    if len(query)<2:
        return []
    candidates = recentSearches(userId) if userId is not None else []
    for lesson in LESSON_ITEMS:
        candidates.extend([lesson['title'],*lesson['tags'],*lesson['materials']])
    for model in MODEL_ITEMS:
        candidates.extend([f"3D {model['title']}",*model['tags']])
    seen, result = set(), []
    for index,value in enumerate(candidates):
        key = value.casefold().replace('ё','е')
        if key not in seen and all(word in key for word in query.split()):
            seen.add(key)
            result.append((not key.startswith(query),index,value))
    return [item[2] for item in sorted(result)[:10]]


def lessonSearchResults(items,text,userId=None,favoritesOnly=False,inProgressOnly=False,sort='Релевантность'):
    favorites = favoriteLessonIds(userId) if userId is not None else set()
    result = []
    for lesson in items:
        state = getUserLessonState(userId,lesson['lessonId']) if userId is not None else None
        if favoritesOnly and lesson['lessonId'] not in favorites:
            continue
        if inProgressOnly and (not state or state['isCompleted'] or not state['completedSteps'] and not state['checkedMaterials'] and not state['lastStep']):
            continue
        result.append(lesson)
    if sort == 'По времени':
        result.sort(key=lambda item:(item['timeMinutes'],item['title']))
    elif sort == 'По названию':
        result.sort(key=lambda item:item['title'].casefold())
    elif sort == 'Релевантность':
        query = normalizeSearchQuery(text).casefold()
        result.sort(key=lambda item:(not item['title'].casefold().startswith(query),
                                    -sum(word in item['title'].casefold() for word in query.split()),item['lessonId']))
    else:
        raise ValueError('Выберите способ сортировки')
    return result


def lessonShareText(lessonId):
    requireLesson(lessonId)
    lesson = getLessonById(lessonId)
    return (f"{lesson['title']}\n{lesson['category']} · {lesson['level']} · {lesson['timeMinutes']} мин\n\n"
            f"{lesson['description']}\n\nМатериалы: {', '.join(lesson['materials'])}\n\n"+
            '\n'.join(f'{index+1}. {step}' for index,step in enumerate(lesson['steps']))+
            '\n\nВстроенный урок приложения «Помощник по лепке».')
