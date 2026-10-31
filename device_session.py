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
