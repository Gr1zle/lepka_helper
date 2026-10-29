"""Привязка серверного аккаунта к отдельному владельцу локальных проектов.

Числовые ID сервера и локальной базы могут совпасть у разных людей.
Поэтому они никогда не используются как взаимозаменяемые идентификаторы.
Пароли и ключ почты в этот кеш не записываются.
"""
import uuid

from account_security import hashToken
from api_client import ApiError, getApiUrl
from database import openDatabase


def cacheRemoteUser(userData, sessionToken):
    if (not isinstance(userData, dict) or type(userData.get('userId')) is not int
            or not all(isinstance(userData.get(key), str) for key in ('email', 'nickname', 'roleName'))
            or not isinstance(sessionToken, str) or not sessionToken):
        raise ApiError('Сервер вернул некорректные данные аккаунта')
    apiUrl = getApiUrl()
    remoteId = userData['userId']
    with openDatabase() as connection:
        connection.execute('BEGIN IMMEDIATE')
        record = connection.execute('SELECT localUserId FROM remoteAccounts WHERE apiUrl = ? AND remoteUserId = ?',
                                    (apiUrl, remoteId)).fetchone()
        if record is None:
            identity = uuid.uuid4().hex
            cursor = connection.execute(
                """INSERT INTO users (email, nickname, passwordHash, passwordSalt)
                VALUES (?, ?, '!remote-account!', '')""",
                (f'remote-{identity}@local.invalid', f'remote_{identity}'),
            )
            localId = cursor.lastrowid
            connection.execute('INSERT INTO remoteAccounts VALUES (?, ?, ?, ?)',
                               (apiUrl, remoteId, localId, userData['nickname']))
        else:
            localId = record['localUserId']
            connection.execute('UPDATE remoteAccounts SET displayNickname = ? WHERE localUserId = ?',
                               (userData['nickname'], localId))
        connection.execute('INSERT OR REPLACE INTO remoteSessionBindings VALUES (?, ?, ?)',
                           (hashToken(sessionToken), apiUrl, localId))
    return {**userData, 'userId': localId, 'serverUserId': remoteId,
            'apiUrl': apiUrl, 'sessionToken': sessionToken}


def requireCachedUser(userId, sessionToken):
    if not sessionToken:
        raise ApiError('Выполните вход снова', 401)
    with openDatabase() as connection:
        record = connection.execute(
            'SELECT localUserId FROM remoteSessionBindings WHERE tokenHash = ? AND apiUrl = ?',
            (hashToken(sessionToken), getApiUrl()),
        ).fetchone()
        if record is None or record['localUserId'] != userId:
            raise ApiError('Аккаунт не соответствует сессии', 401)


def forgetRemoteSession(sessionToken):
    if sessionToken:
        with openDatabase() as connection:
            connection.execute('DELETE FROM remoteSessionBindings WHERE tokenHash = ?', (hashToken(sessionToken),))
