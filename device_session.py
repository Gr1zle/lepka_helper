"""Восстановление местной Android-сессии из закрытого каталога приложения.

Серверные токены здесь не сохраняются. Пароль не записывается; каждый сохранённый
токен проверяется по accountSessions, включая срок действия и отзыв сессии.
"""
import json
import os
from pathlib import Path
import tempfile

import flet as ft
from api_client import getApiUrl
from app_paths import DATA_DIRECTORY
from account_security import getSessionUser

SESSION_FILE = DATA_DIRECTORY / 'device_session.json'


def supportsDeviceSession(page):
    try:
        platform = page.platform
    except ValueError:
        return False
    state = page.data
    webServer = isinstance(state, dict) and state.get('isWebServer')
    return (not page.web and not webServer
            and platform == ft.PagePlatform.ANDROID and not getApiUrl())


def forgetDeviceSession(page):
    if supportsDeviceSession(page):
        try:
            SESSION_FILE.unlink(missing_ok=True)
        except OSError:
            pass  # Отзыв токена всё равно проверяется по SQLite при следующем входе.


def saveDeviceSession(page, user):
    if not supportsDeviceSession(page):
        return True
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8',
                                         dir=SESSION_FILE.parent, delete=False) as stream:
            temporary = Path(stream.name)
            json.dump({'token': user['sessionToken']}, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, SESSION_FILE)
        return True
    except OSError:
        return False
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def restoreDeviceSession(page):
    if not supportsDeviceSession(page):
        return None
    try:
        record = json.loads(SESSION_FILE.read_text(encoding='utf-8'))
        token = record.get('token') if isinstance(record, dict) else None
        user = getSessionUser(token) if isinstance(token, str) and 0 < len(token) <= 256 else None
    except (OSError, ValueError):
        user = None
    if user is None:
        forgetDeviceSession(page)
    return user


# Сохраняем прежнее поведение местной Android-сессии и добавляем отдельный
# зашифрованный серверный вход. В JSON никогда не попадает серверный токен.
_saveLocalSession=saveDeviceSession
_restoreLocalSession=restoreDeviceSession
_forgetLocalSession=forgetDeviceSession


def nativeClient(page):
    try:return not page.web and not (isinstance(page.data,dict) and page.data.get('isWebServer')) and page.platform==ft.PagePlatform.ANDROID
    except ValueError:return False


def forgetDeviceSession(page):
    from app_state import setAppState
    if nativeClient(page) and getApiUrl():
        setAppState('remoteSessionDisabled',True)
        from secure_device import getProtectedSession
        storage=getProtectedSession(page)
        if storage:
            try:storage.delete()
            except OSError:pass
    else:_forgetLocalSession(page)


def saveDeviceSession(page,user,remember=True):
    if not remember:forgetDeviceSession(page);return True
    if not getApiUrl():return _saveLocalSession(page,user)
    if not nativeClient(page):return True
    from app_state import setAppState
    from offline_access import registerVerified
    from secure_device import getProtectedSession
    storage=getProtectedSession(page)
    if not storage or not registerVerified(user):return False
    record={key:user[key] for key in ('userId','serverUserId','email','nickname','roleName','sessionToken','sessionExpiresAt','apiUrl')}
    try:
        if not storage.write(json.dumps(record)):return False
        setAppState('remoteSessionDisabled',False);return True
    except (OSError,ValueError):return False


def restoreDeviceSession(page):
    if not getApiUrl():return _restoreLocalSession(page)
    if not nativeClient(page):return None
    from app_state import getAppState
    from offline_access import registerVerified
    from account_gateway import getSessionUser as remoteSession
    from api_client import ApiError
    if getAppState('remoteSessionDisabled',False):return None
    from secure_device import getProtectedSession
    storage=getProtectedSession(page)
    if not storage:return None
    try:
        raw=storage.read()
        if not raw:return None
        record=json.loads(raw)
        if not isinstance(record,dict):return None
        if record.get('apiUrl')!=getApiUrl() or not registerVerified(record):return None
        user=remoteSession(record['sessionToken'])
        if user is None:forgetDeviceSession(page)
        return user
    except (OSError,ValueError,KeyError,TypeError,ApiError):
        return None
