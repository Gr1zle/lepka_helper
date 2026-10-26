import re


EMAIL_PATTERN = r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$"
NICKNAME_PATTERN = r"^[A-Za-zА-Яа-яЁё0-9_-]{3,20}$"


def validateEmail(email):
    if not email:
        return "Введите email"

    if len(email) < 5 or len(email) > 100:
        return "Email должен быть от 5 до 100 символов"

    if not re.match(EMAIL_PATTERN, email):
        return "Введите корректный email"

    return None


def validatePassword(password):
    if not password:
        return "Введите пароль"

    if len(password) < 8:
        return "Пароль должен быть не короче 8 символов"

    if len(password) > 64:
        return "Пароль должен быть не длиннее 64 символов"

    if not re.search(r"[A-ZА-ЯЁ]", password):
        return "Пароль должен содержать хотя бы одну заглавную букву"

    if not re.search(r"[a-zа-яё]", password):
        return "Пароль должен содержать хотя бы одну строчную букву"

    if not re.search(r"\d", password):
        return "Пароль должен содержать хотя бы одну цифру"

    return None


def validatePasswordConfirmation(password, passwordConfirmation):
    if not passwordConfirmation:
        return "Повторите пароль"

    if password != passwordConfirmation:
        return "Пароли не совпадают"

    return None


def validateNickname(nickname):
    if not nickname:
        return "Введите никнейм"

    if not re.match(NICKNAME_PATTERN, nickname):
        return "Никнейм: 3–20 символов, буквы, цифры, _ или -"

    return None