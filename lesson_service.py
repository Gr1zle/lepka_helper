import random
import copy
import json

from database import getLessonProgress, saveLessonProgress, getUserProfileById


LESSON_ITEMS = [
    {
        "lessonId": 1,
        "title": "Милый котик из пластилина",
        "category": "Животные",
        "level": "Начинающий",
        "timeMinutes": 35,
        "tags": ["кот", "животные", "кавай"],
        "description": "Простой урок по созданию маленького котика из пластилина.",
        "likes": 124,
        "views": 920,
        "materials": ["серый пластилин", "белый пластилин", "розовый пластилин", "стек"],
        "steps": [
            "Скатайте большой серый шарик — это будет туловище котика.",
            "Скатайте шарик поменьше и прикрепите его сверху как голову.",
            "Сделайте два маленьких треугольника и прикрепите ушки.",
            "Добавьте белую мордочку и розовый носик.",
            "Сделайте лапки, хвост и маленькие глазки.",
            "Аккуратно разгладьте соединения стеком.",
        ],
    },
    {
        "lessonId": 2,
        "title": "Пицца из пластилина",
        "category": "Еда",
        "level": "Начинающий",
        "timeMinutes": 25,
        "tags": ["еда", "пицца", "миниатюра"],
        "description": "Создание миниатюрной пиццы с сыром, томатами и зеленью.",
        "likes": 88,
        "views": 640,
        "materials": ["бежевый пластилин", "жёлтый пластилин", "красный пластилин", "зелёный пластилин"],
        "steps": [
            "Сделайте плоский круг из бежевого пластилина.",
            "Добавьте тонкий жёлтый слой сверху — это сыр.",
            "Скатайте маленькие красные кружочки для томатов.",
            "Добавьте зелёные кусочки как зелень.",
            "Слегка прижмите детали, чтобы они держались.",
        ],
    },
    {
        "lessonId": 3,
        "title": "Маленький дракон",
        "category": "Персонажи",
        "level": "Средний",
        "timeMinutes": 60,
        "tags": ["дракон", "фэнтези", "персонаж"],
        "description": "Фигурка дракона с крыльями и хвостом для более опытных пользователей.",
        "likes": 215,
        "views": 1500,
        "materials": ["зелёный пластилин", "жёлтый пластилин", "белый пластилин", "стек"],
        "steps": [
            "Слепите овальное туловище дракона.",
            "Сделайте голову и вытянутую мордочку.",
            "Добавьте длинный хвост, постепенно сужающийся к концу.",
            "Слепите две лапки и прикрепите их снизу.",
            "Сделайте крылья из двух плоских треугольников.",
            "Добавьте глаза, зубы и маленькие рожки.",
            "Украсьте спинку дракона шипами.",
        ],
    },
    {
        "lessonId": 4,
        "title": "Машинка из пластилина",
        "category": "Транспорт",
        "level": "Начинающий",
        "timeMinutes": 40,
        "tags": ["машина", "транспорт", "колёса"],
        "description": "Простой урок по созданию машинки из базовых форм.",
        "likes": 76,
        "views": 530,
        "materials": ["синий пластилин", "чёрный пластилин", "белый пластилин", "стек"],
        "steps": [
            "Слепите прямоугольную основу машинки.",
            "Добавьте верхнюю часть корпуса.",
            "Сделайте четыре чёрных колеса.",
            "Прикрепите колёса по бокам.",
            "Добавьте белые окна и фары.",
            "Сгладьте края корпуса.",
        ],
    },
    {
        "lessonId": 5,
        "title": "Аниме-персонаж",
        "category": "Аниме",
        "level": "Продвинутый",
        "timeMinutes": 120,
        "tags": ["аниме", "персонаж", "лицо"],
        "description": "Сложный урок по лепке персонажа в стиле аниме.",
        "likes": 340,
        "views": 2100,
        "materials": ["телесный пластилин", "чёрный пластилин", "цветной пластилин", "стек"],
        "steps": [
            "Сделайте основу головы овальной формы.",
            "Наметьте расположение глаз, носа и рта.",
            "Добавьте большие глаза в стиле аниме.",
            "Слепите волосы из тонких прядей.",
            "Создайте туловище и одежду персонажа.",
            "Соедините голову и тело.",
            "Добавьте мелкие детали: аксессуары, складки одежды, выражение лица.",
        ],
    },
    {
        "lessonId": 6,
        "title": "Кавайный медвежонок",
        "category": "Кавай",
        "level": "Средний",
        "timeMinutes": 50,
        "tags": ["медведь", "кавай", "животные"],
        "description": "Милый медвежонок с большими глазами и маленькими лапками.",
        "likes": 198,
        "views": 1300,
        "materials": ["коричневый пластилин", "бежевый пластилин", "чёрный пластилин", "розовый пластилин"],
        "steps": [
            "Скатайте круглое туловище медвежонка.",
            "Сделайте голову чуть меньше туловища.",
            "Добавьте круглые ушки.",
            "Слепите бежевую мордочку.",
            "Добавьте большие чёрные глазки.",
            "Сделайте лапки и маленький розовый румянец.",
        ],
    },
]


SEARCH_CATEGORIES = [
    "Все",
    "Животные",
    "Еда",
    "Персонажи",
    "Транспорт",
    "Аниме",
    "Кавай",
]


IDEA_THEMES = [
    "Животные",
    "Еда",
    "Персонажи",
    "Транспорт",
    "Кавай",
    "Фэнтези",
]


IDEA_LEVELS = [
    "Начинающий",
    "Средний",
    "Продвинутый",
]


IDEA_COLOR_SETS = [
    ["#FF6B6B", "#FFD60A", "#FFFFFF"],
    ["#4ECDC4", "#007AFF", "#FFFFFF"],
    ["#34C759", "#8B4513", "#F5DEB3"],
    ["#AF52DE", "#FF2D55", "#FFFFFF"],
    ["#000000", "#FFFFFF", "#FF9500"],
]


IDEA_OBJECTS = {
    "Животные": ["котик", "собачка", "лисёнок", "панда", "черепашка"],
    "Еда": ["пицца", "пончик", "бургер", "торт", "мороженое"],
    "Персонажи": ["рыцарь", "волшебник", "робот", "пират", "космонавт"],
    "Транспорт": ["машинка", "самолёт", "кораблик", "ракета", "поезд"],
    "Кавай": ["облачко", "звёздочка", "медвежонок", "сердечко", "котик"],
    "Фэнтези": ["дракон", "единорог", "грибной домик", "магический кристалл", "фея"],
}


IDEA_PALETTES = {
    'Тёплая': ['#FF3B30', '#FF9500', '#FFD60A', '#FF2D55', '#8B4513'],
    'Холодная': ['#007AFF', '#5AC8FA', '#AF52DE', '#34C759', '#FFFFFF'],
    'Случайная': ['#FF3B30', '#FF9500', '#FFD60A', '#34C759', '#007AFF', '#AF52DE', '#FFFFFF', '#000000'],
}


def searchLessons(searchText, categoryName='Все', levelName='Все', maxTime=None, onlyVideo=False):
    query = (searchText or '').strip().casefold()
    if categoryName not in SEARCH_CATEGORIES or levelName not in ['Все', *IDEA_LEVELS]:
        raise ValueError('Выберите категорию и сложность из списка')
    if maxTime not in (None, ''):
        if isinstance(maxTime, bool) or not str(maxTime).strip().isdecimal():
            raise ValueError('Время должно быть целым числом не меньше нуля')
        try:
            maxTime = int(maxTime)
        except (TypeError, ValueError):
            raise ValueError('Время должно быть целым числом не меньше нуля') from None
        if maxTime < 0:
            raise ValueError('Время должно быть целым числом не меньше нуля')
    else:
        maxTime = None
    result = []
    for lesson in LESSON_ITEMS:
        searchable = ' '.join([lesson['title'], lesson['description'], lesson['level'],
                               lesson['category'], *lesson['tags'], *lesson['materials']]).casefold()
        if (categoryName != 'Все' and lesson['category'] != categoryName
                or levelName != 'Все' and lesson['level'] != levelName
                or maxTime is not None and lesson['timeMinutes'] > maxTime
                or onlyVideo and not lesson.get('videoUrl')
                or not all(word in searchable for word in query.split())):
            continue
        result.append(copy.deepcopy(lesson))
    return result


def getLessonById(lessonId):
    return next((copy.deepcopy(lesson) for lesson in LESSON_ITEMS if lesson['lessonId'] == lessonId), None)


def generateRandomIdea(themeName=None, levelName=None, paletteName='Случайная', colorCount=3):
    themeName = random.choice(IDEA_THEMES) if not themeName or themeName == 'Случайная' else themeName
    levelName = random.choice(IDEA_LEVELS) if not levelName or levelName == 'Случайная' else levelName
    if themeName not in IDEA_THEMES or levelName not in IDEA_LEVELS or paletteName not in IDEA_PALETTES:
        raise ValueError('Выберите параметры генерации из списка')
    if type(colorCount) is not int or not 1 <= colorCount <= 5:
        raise ValueError('Выберите от 1 до 5 цветов')
    objectName = random.choice(IDEA_OBJECTS[themeName])
    colors = random.sample(IDEA_PALETTES[paletteName], colorCount)
    estimatedTime = random.choice({'Начинающий': [25, 35, 40], 'Средний': [45, 60, 75],
                                   'Продвинутый': [90, 120]}[levelName])
    return {'title': f'Слепить: {objectName}',
            'description': f'Тема: {themeName}. Сделайте фигурку «{objectName}» уровня «{levelName}».',
            'theme': themeName, 'level': levelName, 'colors': colors, 'estimatedTime': estimatedTime,
            'steps': ['Подготовить пластилин, инструменты и референс', 'Слепить основу фигурки',
                      'Добавить детали и соединить части', 'Проверить результат и оформить работу']}


def getUserLessonState(userId, lessonId):
    lesson = getLessonById(lessonId)
    if lesson is None:
        raise ValueError('Урок не найден')
    default = {'lastStep': 0, 'completedSteps': [], 'checkedMaterials': [], 'isCompleted': False}
    raw = getLessonProgress(userId, lessonId)
    if raw is None:
        return default
    try:
        state = json.loads(raw)
        return normalizeLessonState(lesson, state)
    except (ValueError, TypeError, KeyError):
        return default


def normalizeLessonState(lesson, state):
    if not isinstance(state, dict):
        raise ValueError('Некорректное состояние урока')
    step = state.get('lastStep')
    if type(step) is not int or not 0 <= step < len(lesson['steps']):
        raise ValueError('Некорректный номер шага')
    result = {'lastStep': step}
    for key, limit in (('completedSteps', len(lesson['steps'])), ('checkedMaterials', len(lesson['materials']))):
        values = state.get(key)
        if not isinstance(values, list) or any(type(value) is not int or not 0 <= value < limit for value in values):
            raise ValueError('Некорректные отметки урока')
        result[key] = sorted(set(values))
    result['isCompleted'] = len(result['completedSteps']) == len(lesson['steps'])
    return result


def saveUserLessonState(userId, lessonId, state):
    lesson = getLessonById(lessonId)
    if lesson is None or getUserProfileById(userId) is None:
        raise ValueError('Урок или пользователь не найден')
    normalized = normalizeLessonState(lesson, state)
    saveLessonProgress(userId, lessonId, json.dumps(normalized, ensure_ascii=False))
    return normalized


# Авторские схематичные иллюстрации, не фотографии готовых работ.
for lesson in LESSON_ITEMS:
    lesson['previewImage'] = f"lessons/lesson_{lesson['lessonId']}.svg"
