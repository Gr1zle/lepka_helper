import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import flet as ft
import database
import device_session as sessions
from auth_service import ensureDemoUser, loginUser
from account_security import logoutUser


class DeviceSessionTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.file = Path(folder.name) / 'device_session.json'
        for target, value in (('database.DATABASE_PATH', Path(folder.name)/'test.db'),
                              ('device_session.SESSION_FILE', self.file),
                              ('device_session.getApiUrl', '')):
            p = patch(target, return_value=value) if target.endswith('getApiUrl') else patch(target, value)
            p.start()
            self.addCleanup(p.stop)
        database.initializeDatabase()
        ensureDemoUser()
        self.user = loginUser('test@email.com', 'Test123456')[2]
        self.page = SimpleNamespace(platform=ft.PagePlatform.ANDROID, web=False, data=None)

    def test_saved_session_survives_restart_and_revoked_token_is_removed(self):
        self.assertTrue(sessions.saveDeviceSession(self.page, self.user))
        self.assertEqual(sessions.restoreDeviceSession(self.page)['userId'], self.user['userId'])
        self.assertEqual(set(json.loads(self.file.read_text())), {'token'})
        if os.name != 'nt':
            self.assertEqual(self.file.stat().st_mode & 0o777, 0o600)
        logoutUser(self.user['sessionToken'])
        self.assertIsNone(sessions.restoreDeviceSession(self.page))
        self.assertFalse(self.file.exists())

    def test_expired_session_and_corrupt_or_forged_file_do_not_log_in(self):
        sessions.saveDeviceSession(self.page, self.user)
        with database.openDatabase() as connection:
            connection.execute('UPDATE accountSessions SET expiresAt = 0')
        self.assertIsNone(sessions.restoreDeviceSession(self.page))
        for payload in ('not json', '[]', '{"token": "forged", "userId": 1}'):
            self.file.write_text(payload)
            self.assertIsNone(sessions.restoreDeviceSession(self.page))
            self.assertFalse(self.file.exists())

    def test_remote_tokens_and_browser_or_desktop_sessions_are_not_persisted(self):
        for page in (SimpleNamespace(platform=ft.PagePlatform.ANDROID, web=True, data=None),
                     SimpleNamespace(platform=ft.PagePlatform.ANDROID, web=False, data={'isWebServer': True}),
                     SimpleNamespace(platform=ft.PagePlatform.WINDOWS, web=False, data=None)):
            sessions.saveDeviceSession(page, self.user)
            self.assertFalse(self.file.exists())
        with patch('device_session.getApiUrl', return_value='https://server.example'):
            sessions.saveDeviceSession(self.page, self.user)
            self.assertFalse(self.file.exists())

    def test_unwritable_storage_does_not_block_login(self):
        with patch('device_session.tempfile.NamedTemporaryFile', side_effect=OSError):
            self.assertFalse(sessions.saveDeviceSession(self.page, self.user))
        self.assertIsNone(sessions.restoreDeviceSession(self.page))
