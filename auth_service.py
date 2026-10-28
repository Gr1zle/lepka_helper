"""Регистрация и вход: проверки выполняются независимо от интерфейса Flet."""
import sqlite3
import time

from account_security import (
    checkAccountCode, createSession, makePublicUser, requestAccountCode,
    revokeUserSessions, issueAccountCode,
)
from database import createUser, deleteUserDataById, getUserByEmail, openDatabase
from password_service import createPasswordHash, checkPassword
from validators import validateEmail, validatePassword, validatePasswordConfirmation, validateNickname

LOGIN_ATTEMPT_LIMIT = 5
LOGIN_BLOCK_SECONDS = 15 * 60


def registerUser(email, password, passwordConfirmation, nickname, isPolicyAccepted):
    email = (email or '').strip().lower()
    nickname = (nickname or '').strip()
    for error in (validateEmail(email), validateNickname(nickname), validatePassword(password),
                  validatePasswordConfirmation(password, passwordConfirmation)):
        if error:
            return False, error, None
    if isPolicyAccepted is not True:
        return False, 'Необходимо согласиться с политикой конфиденциальности', None
    passwordHash, passwordSalt = createPasswordHash(password)
    # UNIQUE в БД защищает и от двух одновременных регистраций.
    try:
        with openDatabase() as connection:
            cursor = connection.execute(
                """INSERT INTO users (email, passwordHash, passwordSalt, nickname, emailVerified)
                VALUES (?, ?, ?, ?, 0)""", (email, passwordHash, passwordSalt, nickname)
            )
            userRecord = connection.execute('SELECT * FROM users WHERE userId = ?', (cursor.lastrowid,)).fetchone()
            return True, 'Аккаунт создан. Подтвердите email перед входом', makePublicUser(userRecord)
    except sqlite3.IntegrityError:
        return False, 'Email или никнейм уже занят', None


def loginUser(email, password):
    email = (email or '').strip().lower()
    emailError = validateEmail(email)
    if emailError:
        return False, emailError, None
    if not password:
        return False, 'Введите пароль', None
    with openDatabase() as connection:
        connection.execute('BEGIN IMMEDIATE')
        userRecord = connection.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
        if userRecord is None:
            return False, 'Неверный email или пароль', None
        if userRecord['isBlocked']:
            return False, 'Аккаунт заблокирован', None
        if userRecord['loginBlockedUntil'] > time.time():
            return False, 'Слишком много попыток. Повторите вход через 15 минут', None
        if not checkPassword(password, userRecord['passwordHash'], userRecord['passwordSalt']):
            failures = userRecord['loginFailures'] + 1 if userRecord['loginBlockedUntil'] == 0 else 1
            blockedUntil = time.time() + LOGIN_BLOCK_SECONDS if failures >= LOGIN_ATTEMPT_LIMIT else 0
            connection.execute('UPDATE users SET loginFailures = ?, loginBlockedUntil = ? WHERE userId = ?',
                               (failures, blockedUntil, userRecord['userId']))
            return False, 'Неверный email или пароль', None
        connection.execute('UPDATE users SET loginFailures = 0, loginBlockedUntil = 0 WHERE userId = ?',
                           (userRecord['userId'],))
        if not userRecord['emailVerified']:
            return False, 'Подтвердите email кнопкой «Подтвердить регистрацию»', None
        return True, f"Добро пожаловать, {userRecord['nickname']}!", createSession(connection, userRecord)


def requestPasswordRecovery(email):
    return requestAccountCode(email, 'recovery')


def requestRegistrationCode(email):
    return requestAccountCode(email, 'registration')


def changePasswordByEmail(email, newPassword, newPasswordConfirmation, recoveryCode=None):
    email = (email or '').strip().lower()
    for error in (validateEmail(email), validatePassword(newPassword),
                  validatePasswordConfirmation(newPassword, newPasswordConfirmation)):
        if error:
            return False, error
    with openDatabase() as connection:
        connection.execute('BEGIN IMMEDIATE')
        if not checkAccountCode(connection, email, 'recovery', recoveryCode):
            return False, 'Неверный или просроченный код. После 5 ошибок запросите новый'
        userRecord = connection.execute('SELECT * FROM users WHERE email = ? AND isBlocked = 0', (email,)).fetchone()
        if userRecord is None:
            return False, 'Аккаунт недоступен'
        passwordHash, passwordSalt = createPasswordHash(newPassword)
        connection.execute(
            """UPDATE users SET passwordHash = ?, passwordSalt = ?, loginFailures = 0,
            loginBlockedUntil = 0, passwordFailures = 0, passwordBlockedUntil = 0 WHERE userId = ?""",
            (passwordHash, passwordSalt, userRecord['userId']),
        )
        revokeUserSessions(connection, userRecord['userId'])
    return True, 'Пароль изменён. Все сессии завершены. Выполните вход снова'


def deleteUserAccount(userId, password):
    # Идентификатор берётся из сессии, email из формы для удаления не принимается.
    with openDatabase() as connection:
        connection.execute('BEGIN IMMEDIATE')
        userRecord = connection.execute('SELECT * FROM users WHERE userId = ? AND isBlocked = 0', (userId,)).fetchone()
        if userRecord is None:
            return False, 'Пользователь не найден'
        if not password or not checkPassword(password, userRecord['passwordHash'], userRecord['passwordSalt']):
            return False, 'Неверный пароль'
        if not deleteUserDataById(userId, connection):
            return False, 'Пользователь не найден'
    return True, 'Аккаунт удалён'


def ensureDemoUser():
    """Демонстрационная учётная запись; существующий пароль не заменяется."""
    userRecord = getUserByEmail('test@email.com')
    if userRecord is None:
        passwordHash, passwordSalt = createPasswordHash('Test123456')
        try:
            createUser('test@email.com', passwordHash, passwordSalt, 'test_user')
        except sqlite3.IntegrityError:
            # Не занимаем ник уже существующего пользователя.
            userRecord = getUserByEmail('test@email.com')
            if userRecord is None:
                return None
        userRecord = getUserByEmail('test@email.com')
    return makePublicUser(userRecord)


def requestEmailChange(userId, password, newEmail):
    newEmail = (newEmail or '').strip().lower()
    error = validateEmail(newEmail)
    if error:
        return False, error
    with openDatabase() as connection:
        connection.execute('BEGIN IMMEDIATE')
        record = connection.execute('SELECT * FROM users WHERE userId = ? AND isBlocked = 0', (userId,)).fetchone()
        if record is None or not password or not checkPassword(password, record['passwordHash'], record['passwordSalt']):
            return False, 'Неверный текущий пароль'
        if connection.execute('SELECT userId FROM users WHERE email = ?', (newEmail,)).fetchone():
            return False, 'Этот email уже используется'
        success, message = issueAccountCode(connection, newEmail, 'email', userId)
        if success:
            # У аккаунта может быть только один ожидающий новый адрес.
            connection.execute("DELETE FROM accountCodes WHERE userId = ? AND purpose = 'email' AND email != ?", (userId, newEmail))
        return success, message


def confirmEmailChange(userId, newEmail, code):
    newEmail = (newEmail or '').strip().lower()
    with openDatabase() as connection:
        connection.execute('BEGIN IMMEDIATE')
        record = connection.execute("SELECT userId FROM accountCodes WHERE email = ? AND purpose = 'email'", (newEmail,)).fetchone()
        if record is None or record['userId'] != userId:
            return False, 'Неверный или просроченный код'
        if not checkAccountCode(connection, newEmail, 'email', code):
            return False, 'Неверный или просроченный код'
        if connection.execute('SELECT userId FROM users WHERE email = ?', (newEmail,)).fetchone():
            return False, 'Этот email уже используется'
        connection.execute('UPDATE users SET email = ?, emailVerified = 1 WHERE userId = ?', (newEmail, userId))
        revokeUserSessions(connection, userId)
    return True, 'Email изменён. Выполните вход с новым адресом'
