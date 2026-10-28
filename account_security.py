"""Одноразовые коды и сессии. В SQLite хранятся только их хеши."""
import hashlib
import hmac
import secrets
import time

from database import openDatabase
from mail_service import MailDeliveryError, sendAccountCode

CODE_ATTEMPT_LIMIT = 5
CODE_RESEND_SECONDS = 60
SESSION_SECONDS = 12 * 60 * 60


def hashToken(token):
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def makePublicUser(userRecord):
    return {name: userRecord[name] for name in ('userId', 'email', 'nickname', 'roleName')}


def createSession(connection, userRecord):
    token = secrets.token_urlsafe(32)
    connection.execute('DELETE FROM accountSessions WHERE expiresAt <= ?', (time.time(),))
    connection.execute('INSERT INTO accountSessions VALUES (?, ?, ?)',
                       (hashToken(token), userRecord['userId'], time.time() + SESSION_SECONDS))
    userData = makePublicUser(userRecord)
    userData['sessionToken'] = token
    return userData


def getSessionUser(token):
    if not token:
        return None
    with openDatabase() as connection:
        record = connection.execute(
            """SELECT u.* FROM accountSessions AS s JOIN users AS u ON u.userId = s.userId
            WHERE s.tokenHash = ? AND s.expiresAt > ? AND u.isBlocked = 0 AND u.emailVerified = 1""",
            (hashToken(token), time.time()),
        ).fetchone()
        if record is None:
            return None
        userData = makePublicUser(record)
        userData['sessionToken'] = token
        return userData


def logoutUser(token):
    if token:
        with openDatabase() as connection:
            connection.execute('DELETE FROM accountSessions WHERE tokenHash = ?', (hashToken(token),))


def revokeUserSessions(connection, userId):
    connection.execute('DELETE FROM accountSessions WHERE userId = ?', (userId,))
    connection.execute('DELETE FROM accountCodes WHERE userId = ?', (userId,))


def requestAccountCode(email, purpose):
    email = (email or '').strip().lower()
    from validators import validateEmail
    emailError = validateEmail(email)
    if emailError:
        return False, emailError
    genericMessage = 'Если аккаунт подходит для операции, письмо с кодом отправлено'
    with openDatabase() as connection:
        connection.execute('BEGIN IMMEDIATE')
        userRecord = connection.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
        if userRecord is None or userRecord['isBlocked']:
            return True, genericMessage
        if purpose == 'registration' and userRecord['emailVerified']:
            return True, genericMessage
        success, message = issueAccountCode(connection, email, purpose, userRecord['userId'])
        return success, genericMessage if success else message


def issueAccountCode(connection, email, purpose, userId):
    """Выдаёт код после проверки прав вызывающей функцией."""
    previous = connection.execute('SELECT sentAt FROM accountCodes WHERE email = ? AND purpose = ?',
                                  (email, purpose)).fetchone()
    if previous and time.time() - previous['sentAt'] < CODE_RESEND_SECONDS:
        return False, 'Повторный код можно запросить через минуту'
    code = f'{secrets.randbelow(1000000):06d}'
    try:
        sendAccountCode(email, code, purpose)
    except MailDeliveryError as error:
        return False, str(error)
    lifetime = 24 * 60 * 60 if purpose == 'registration' else 10 * 60
    connection.execute(
        """INSERT OR REPLACE INTO accountCodes
        (email, purpose, userId, codeHash, expiresAt, sentAt, attempts)
        VALUES (?, ?, ?, ?, ?, ?, 0)""",
        (email, purpose, userId, hashToken(code), time.time() + lifetime, time.time()),
    )
    return True, 'Письмо с кодом отправлено'


def checkAccountCode(connection, email, purpose, code):
    """Вызывается внутри транзакции: проверка и последующая запись неразрывны."""
    record = connection.execute('SELECT * FROM accountCodes WHERE email = ? AND purpose = ?',
                                (email, purpose)).fetchone()
    if record is None or record['expiresAt'] <= time.time() or record['attempts'] >= CODE_ATTEMPT_LIMIT:
        return False
    if not hmac.compare_digest(record['codeHash'], hashToken((code or '').strip())):
        connection.execute('UPDATE accountCodes SET attempts = attempts + 1 WHERE email = ? AND purpose = ?',
                           (email, purpose))
        return False
    return True


def confirmRegistration(email, code):
    email = (email or '').strip().lower()
    with openDatabase() as connection:
        connection.execute('BEGIN IMMEDIATE')
        if not checkAccountCode(connection, email, 'registration', code):
            return False, 'Неверный или просроченный код. После 5 ошибок запросите новый'
        connection.execute('UPDATE users SET emailVerified = 1 WHERE email = ?', (email,))
        connection.execute("DELETE FROM accountCodes WHERE email = ? AND purpose = 'registration'", (email,))
    return True, 'Email подтверждён. Теперь можно войти'
