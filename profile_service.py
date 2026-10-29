from password_service import createPasswordHash, checkPassword
from validators import validatePassword
import json
import sqlite3
import time
import base64

from account_security import revokeUserSessions
from database import openDatabase

from database import (
    getUserByNickname,
    getUserProfileById,
    updateUserProfile,
    updateUserSettings,
    setUserAvatar,
)
from photo_service import prepareAvatar
from validators import validateNickname


AGE_CATEGORIES = [
    "Ребёнок до 12 лет",
    "Подросток 13–17",
    "Взрослый 18+",
]


FAVORITE_COLOR_OPTIONS = [
    "Белый",
    "Чёрный",
    "Красный",
    "Оранжевый",
    "Жёлтый",
    "Зелёный",
    "Голубой",
    "Синий",
    "Фиолетовый",
    "Розовый",
    "Коричневый",
    "Бежевый",
]

THEME_OPTIONS = [
    {"name": "Светлая", "value": "light"},
    {"name": "Тёмная", "value": "dark"},
]


LANGUAGE_OPTIONS = [
    {"name": "Русский", "value": "ru"},
    {"name": "English", "value": "en"},
]


def validateNewPassword(newPassword):
    return validatePassword(newPassword)


def getUserProfile(userId):
    userRecord = getUserProfileById(userId)

    if userRecord is None:
        return None

    try:
        favoriteColors = json.loads(userRecord["favoriteColorsJson"])
    except (ValueError, TypeError):
        favoriteColors = []

    if not isinstance(favoriteColors, list):
        favoriteColors = []

    return {
        "userId": userRecord["userId"],
        "email": userRecord["email"],
        "nickname": userRecord["nickname"],
        "roleName": userRecord["roleName"],
        "bioText": userRecord["bioText"] or "",
        "ageCategory": userRecord["ageCategory"] or AGE_CATEGORIES[2],
        "favoriteColors": favoriteColors,
        "themeMode": userRecord["themeMode"] or "light",
        "languageCode": userRecord["languageCode"] or "ru",
        "notificationsEnabled": bool(userRecord["notificationsEnabled"]),
        "avatarPath": userRecord["avatarPath"] or "",
        "avatarImage": base64.b64encode(userRecord['avatarImage']).decode('ascii')
                       if isinstance(userRecord['avatarImage'], bytes) else '',
    }


def saveUserAvatar(userId, imageData):
    try:
        normalized = prepareAvatar('avatar.png', imageData)
    except ValueError as error:
        return False, str(error), None
    if not setUserAvatar(userId, normalized):
        return False, 'Аккаунт недоступен', None
    return True, 'Аватар сохранён', getUserProfile(userId)


def removeUserAvatar(userId):
    if not setUserAvatar(userId, None):
        return False, 'Аккаунт недоступен', None
    return True, 'Аватар удалён', getUserProfile(userId)


def saveUserProfile(userId, nickname, bioText, ageCategory, favoriteColors, avatarPath=""):
    if getUserProfile(userId) is None:
        return False, "Пользователь не найден", None
    nickname = (nickname or "").strip()
    bioText = (bioText or "").strip()
    avatarPath = avatarPath.strip() if avatarPath else ""

    nicknameError = validateNickname(nickname)
    if nicknameError:
        return False, nicknameError, None

    if len(bioText) > 500:
        return False, "Биография должна быть не длиннее 500 символов", None

    if ageCategory not in AGE_CATEGORIES:
        return False, "Выберите корректную возрастную категорию", None

    if not isinstance(favoriteColors, list):
        return False, "Выберите любимые цвета из списка", None
    favoriteColors = list(dict.fromkeys(favoriteColors))
    if len(favoriteColors) > 5:
        return False, "Можно выбрать не больше 5 любимых цветов", None

    for colorName in favoriteColors:
        if colorName not in FAVORITE_COLOR_OPTIONS:
            return False, "Выберите корректные любимые цвета", None

    existingNicknameUser = getUserByNickname(nickname)

    if existingNicknameUser and existingNicknameUser["userId"] != userId:
        return False, "Такой никнейм уже занят", None

    favoriteColorsJson = json.dumps(favoriteColors, ensure_ascii=False)

    try:
        updateUserProfile(
            userId, nickname, bioText, ageCategory, favoriteColorsJson, avatarPath,
        )
    except sqlite3.IntegrityError:
        return False, "Такой никнейм уже занят", None

    updatedProfile = getUserProfile(userId)

    if updatedProfile is None:
        return False, "Пользователь не найден", None
    return True, "Профиль сохранён", updatedProfile


def saveUserSettings(userId, themeMode, languageCode, notificationsEnabled):
    if getUserProfile(userId) is None:
        return False, "Пользователь не найден", None
    if not isinstance(notificationsEnabled, bool):
        return False, "Некорректное значение уведомлений", None
    allowedThemeValues = []

    for themeItem in THEME_OPTIONS:
        allowedThemeValues.append(themeItem["value"])

    allowedLanguageValues = []

    for languageItem in LANGUAGE_OPTIONS:
        allowedLanguageValues.append(languageItem["value"])

    if themeMode not in allowedThemeValues:
        return False, "Выберите корректную тему", None

    if languageCode not in allowedLanguageValues:
        return False, "Выберите корректный язык", None

    updateUserSettings(
        userId,
        themeMode,
        languageCode,
        notificationsEnabled,
    )

    updatedProfile = getUserProfile(userId)

    if updatedProfile is None:
        return False, "Пользователь не найден", None
    return True, "Настройки сохранены", updatedProfile


def changeUserPassword(userId, currentPassword, newPassword, repeatedNewPassword):
    currentPassword = currentPassword or ""
    newPassword = newPassword or ""
    repeatedNewPassword = repeatedNewPassword or ""

    if not currentPassword:
        return False, "Введите текущий пароль"

    passwordError = validateNewPassword(newPassword)
    if passwordError:
        return False, passwordError

    if newPassword != repeatedNewPassword:
        return False, "Подтверждение пароля не совпадает"

    if currentPassword == newPassword:
        return False, "Новый пароль должен отличаться от текущего"

    with openDatabase() as connection:
        connection.execute('BEGIN IMMEDIATE')
        userRecord = connection.execute('SELECT * FROM users WHERE userId = ? AND isBlocked = 0', (userId,)).fetchone()
        if userRecord is None:
            return False, "Пользователь не найден"
        if userRecord['passwordBlockedUntil'] > time.time():
            return False, "Смена пароля заблокирована на 5 минут"
        if not checkPassword(currentPassword, userRecord['passwordHash'], userRecord['passwordSalt']):
            failures = userRecord['passwordFailures'] + 1 if userRecord['passwordBlockedUntil'] == 0 else 1
            blockedUntil = time.time() + 300 if failures >= 3 else 0
            connection.execute('UPDATE users SET passwordFailures = ?, passwordBlockedUntil = ? WHERE userId = ?',
                               (failures, blockedUntil, userId))
            return False, "Текущий пароль указан неверно"
        passwordHash, passwordSalt = createPasswordHash(newPassword)
        connection.execute(
            """UPDATE users SET passwordHash = ?, passwordSalt = ?, passwordFailures = 0,
            passwordBlockedUntil = 0 WHERE userId = ?""", (passwordHash, passwordSalt, userId)
        )
        revokeUserSessions(connection, userId)
    return True, "Пароль успешно изменён. Все сессии завершены. Выполните вход снова"
