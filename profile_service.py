from password_service import createPasswordHash, checkPassword
from validators import validatePassword
import json

from database import (
    getUserByNickname,
    getUserPasswordById,
    getUserProfileById,
    updateUserPassword,
    updateUserProfile,
    updateUserSettings,
)
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
    except Exception:
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
    }


def saveUserProfile(userId, nickname, bioText, ageCategory, favoriteColors, avatarPath=""):
    nickname = nickname.strip()
    bioText = bioText.strip()
    avatarPath = avatarPath.strip() if avatarPath else ""

    nicknameError = validateNickname(nickname)
    if nicknameError:
        return False, nicknameError, None

    if len(bioText) > 500:
        return False, "Биография должна быть не длиннее 500 символов", None

    if ageCategory not in AGE_CATEGORIES:
        return False, "Выберите корректную возрастную категорию", None

    if len(favoriteColors) > 5:
        return False, "Можно выбрать не больше 5 любимых цветов", None

    for colorName in favoriteColors:
        if colorName not in FAVORITE_COLOR_OPTIONS:
            return False, "Выберите корректные любимые цвета", None

    existingNicknameUser = getUserByNickname(nickname)

    if existingNicknameUser and existingNicknameUser["userId"] != userId:
        return False, "Такой никнейм уже занят", None

    favoriteColorsJson = json.dumps(favoriteColors, ensure_ascii=False)

    updateUserProfile(
        userId,
        nickname,
        bioText,
        ageCategory,
        favoriteColorsJson,
        avatarPath,
    )

    updatedProfile = getUserProfile(userId)

    return True, "Профиль сохранён", updatedProfile


def saveUserSettings(userId, themeMode, languageCode, notificationsEnabled):
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

    userPasswordRecord = getUserPasswordById(userId)

    if userPasswordRecord is None:
        return False, "Пользователь не найден"

    if not checkPassword(
        currentPassword,
        userPasswordRecord["passwordHash"],
        userPasswordRecord["passwordSalt"],
    ):
        return False, "Текущий пароль указан неверно"

    passwordHash, passwordSalt = createPasswordHash(newPassword)
    updateUserPassword(userId, passwordHash, passwordSalt)

    return True, "Пароль успешно изменён. Выполните вход снова"
