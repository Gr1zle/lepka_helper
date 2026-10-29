"""HTTP API: отдельная временная база, реальный FastAPI, почта в памяти."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.main import createApp
import database
from password_service import createPasswordHash


class BackendTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.client = TestClient(createApp(self.folder.name))
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)
        mailPatch = patch('account_security.sendAccountCode')
        self.mail = mailPatch.start()
        self.addCleanup(mailPatch.stop)
        passwordHash, salt = createPasswordHash('Student123')
        self.userId = database.createUser('owner@example.com', passwordHash, salt, 'owner')
        self.otherId = database.createUser('other@example.com', passwordHash, salt, 'other')

    def login(self, email='owner@example.com', password='Student123'):
        response = self.client.post('/auth/login', json={'email': email, 'password': password})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()['data']['sessionToken']

    def headers(self, token):
        return {'Authorization': f'Bearer {token}'}

    def profile(self, nickname='updated'):
        return {'nickname': nickname, 'bioText': 'Биография', 'ageCategory': 'Взрослый 18+',
                'favoriteColors': ['Белый'], 'avatarPath': ''}

    def test_registration_confirmation_login_and_logout(self):
        registration = self.client.post('/auth/register', json={
            'email': 'new@example.com', 'password': 'Student123',
            'passwordConfirmation': 'Student123', 'nickname': 'new_user', 'isPolicyAccepted': True})
        self.assertEqual(registration.status_code, 200)
        self.assertNotIn('sessionToken', registration.json()['data'])
        self.assertNotIn('passwordHash', registration.text)
        self.assertEqual(self.client.post('/auth/login', json={'email': 'new@example.com', 'password': 'Student123'}).status_code, 400)
        self.assertEqual(self.client.post('/auth/registration/code', json={'email': 'new@example.com'}).status_code, 200)
        code = self.mail.call_args.args[1]
        self.assertEqual(self.client.post('/auth/registration/confirm', json={'email': 'new@example.com', 'code': code}).status_code, 200)
        token = self.login('new@example.com')
        self.assertEqual(self.client.get('/auth/me', headers=self.headers(token)).json()['data']['email'], 'new@example.com')
        self.assertEqual(self.client.post('/auth/logout', headers=self.headers(token)).status_code, 200)
        self.assertEqual(self.client.get('/auth/me', headers=self.headers(token)).status_code, 401)
        self.assertEqual(self.client.post('/auth/logout', headers=self.headers(token)).status_code, 200)

    def test_profile_requires_bearer_and_cannot_select_another_owner(self):
        self.assertEqual(self.client.get('/profile').status_code, 401)
        self.assertEqual(self.client.get('/profile', headers=self.headers('invalid')).status_code, 401)
        token = self.login()
        headers = self.headers(token)
        body = self.profile()
        body['userId'] = self.otherId
        self.assertEqual(self.client.put('/profile', headers=headers, json=body).status_code, 422)
        self.assertEqual(self.client.get('/profile', headers=headers).json()['data']['nickname'], 'owner')
        self.assertEqual(self.client.put('/profile', headers=headers, json=self.profile()).status_code, 200)
        otherToken = self.login('other@example.com')
        self.assertEqual(self.client.get('/profile', headers=self.headers(otherToken)).json()['data']['nickname'], 'other')

    def test_avatar_upload_is_authenticated_and_owner_is_from_token(self):
        import base64
        from io import BytesIO
        from PIL import Image
        from image_fixtures import photo
        from photo_service import prepareAvatar
        source = photo()
        image = prepareAvatar(source['name'], source['data'])
        self.assertEqual(self.client.put('/profile/avatar', content=image).status_code, 401)
        token = self.login()
        response = self.client.put('/profile/avatar?userId=' + str(self.otherId),
                                   headers=self.headers(token), content=image)
        self.assertEqual(response.status_code, 200)
        value = response.json()['data']['avatarImage']
        with Image.open(BytesIO(base64.b64decode(value))) as saved:
            self.assertEqual(saved.size, (512, 512))
        other = self.login('other@example.com')
        self.assertEqual(self.client.get('/profile', headers=self.headers(other)).json()['data']['avatarImage'], '')
        self.assertEqual(self.client.get('/profile', headers=self.headers(token)).json()['data']['avatarImage'], value)

    def test_invalid_and_oversized_avatar_do_not_change_existing_image(self):
        from image_fixtures import photo
        from photo_service import prepareAvatar
        source = photo()
        token = self.login()
        headers = self.headers(token)
        response = self.client.put('/profile/avatar', headers=headers,
                                   content=prepareAvatar(source['name'], source['data']))
        old = response.json()['data']['avatarImage']
        self.assertEqual(self.client.put('/profile/avatar', headers=headers, content=b'bad').status_code, 400)
        self.assertEqual(self.client.put('/profile/avatar', headers=headers, content=b'x' * (2 * 1024 * 1024 + 1)).status_code, 413)
        self.assertEqual(self.client.get('/profile', headers=headers).json()['data']['avatarImage'], old)

    def test_avatar_delete_keeps_other_profile_fields_and_requires_active_session(self):
        from image_fixtures import photo
        from photo_service import prepareAvatar
        source = photo()
        token = self.login()
        headers = self.headers(token)
        self.client.put('/profile/avatar', headers=headers, content=prepareAvatar(source['name'], source['data']))
        self.assertEqual(self.client.delete('/profile/avatar').status_code, 401)
        self.assertEqual(self.client.delete('/profile/avatar', headers=headers).json()['data']['avatarImage'], '')
        self.assertEqual(self.client.get('/profile', headers=headers).json()['data']['nickname'], 'owner')
        self.client.post('/auth/logout', headers=headers)
        self.assertEqual(self.client.put('/profile/avatar', headers=headers, content=prepareAvatar(source['name'], source['data'])).status_code, 401)

    def test_settings_saved_and_role_escalation_rejected(self):
        token = self.login()
        body = {'themeMode': 'dark', 'languageCode': 'ru', 'notificationsEnabled': False}
        response = self.client.put('/profile/settings', headers=self.headers(token), json=body)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(self.client.get('/profile', headers=self.headers(token)).json()['data']['notificationsEnabled'])
        body['roleName'] = 'admin'
        self.assertEqual(self.client.put('/profile/settings', headers=self.headers(token), json=body).status_code, 422)
        self.assertEqual(self.client.get('/auth/me', headers=self.headers(token)).json()['data']['roleName'], 'user')

    def test_password_change_revokes_other_sessions(self):
        first, second = self.login(), self.login()
        result = self.client.post('/account/password', headers=self.headers(first), json={
            'currentPassword': 'Student123', 'newPassword': 'Changed123', 'repeatedNewPassword': 'Changed123'})
        self.assertEqual(result.status_code, 200, result.text)
        for token in (first, second):
            self.assertEqual(self.client.get('/auth/me', headers=self.headers(token)).status_code, 401)
        self.login(password='Changed123')

    def test_recovery_checks_code_on_server_and_revokes_sessions(self):
        token = self.login()
        body = {'email': 'owner@example.com', 'newPassword': 'ResetPass123',
                'newPasswordConfirmation': 'ResetPass123', 'recoveryCode': ''}
        self.assertEqual(self.client.post('/auth/recovery/confirm', json=body).status_code, 400)
        response = self.client.post('/auth/recovery/code', json={'email': 'owner@example.com'})
        code = self.mail.call_args.args[1]
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(code, response.text)
        body['recoveryCode'] = code
        self.assertEqual(self.client.post('/auth/recovery/confirm', json=body).status_code, 200)
        self.assertEqual(self.client.get('/auth/me', headers=self.headers(token)).status_code, 401)
        self.assertEqual(self.client.post('/auth/recovery/confirm', json=body).status_code, 400)
        self.login(password='ResetPass123')

    def test_new_email_code_bound_to_authenticated_account(self):
        owner, other = self.login(), self.login('other@example.com')
        self.assertEqual(self.client.post('/account/email/code', headers=self.headers(owner),
            json={'newEmail': 'new@example.com', 'password': 'Student123'}).status_code, 200)
        body = {'newEmail': 'new@example.com', 'code': self.mail.call_args.args[1]}
        self.assertEqual(self.client.post('/account/email/confirm', headers=self.headers(other), json=body).status_code, 400)
        self.assertEqual(self.client.post('/account/email/confirm', headers=self.headers(owner), json=body).status_code, 200)
        self.assertEqual(self.client.get('/auth/me', headers=self.headers(owner)).status_code, 401)
        self.login('new@example.com')

    def test_delete_requires_password_and_cannot_supply_other_user_id(self):
        token = self.login()
        headers = self.headers(token)
        self.assertEqual(self.client.request('DELETE', '/account', headers=headers,
                         json={'password': 'Student123', 'userId': self.otherId}).status_code, 422)
        self.assertEqual(self.client.request('DELETE', '/account', headers=headers,
                         json={'password': 'wrong'}).status_code, 400)
        self.assertEqual(self.client.request('DELETE', '/account', headers=headers,
                         json={'password': 'Student123'}).status_code, 200)
        self.assertEqual(self.client.get('/auth/me', headers=headers).status_code, 401)
        self.assertIsNotNone(database.getUserByEmail('other@example.com'))

    def test_api_errors_do_not_echo_passwords(self):
        password = 'SecretNotToEcho123' * 10
        response = self.client.post('/auth/login', json={'email': 'owner@example.com', 'password': password})
        self.assertEqual(response.status_code, 422)
        self.assertNotIn(password, response.text)
        self.assertNotIn('input', response.text)

    def test_public_endpoint_rate_limit(self):
        for index in range(31):
            response = self.client.post('/auth/registration/code', json={'email': 'unknown@example.com'})
            self.assertEqual(response.status_code, 200 if index < 30 else 429)
        self.mail.assert_not_called()

    def test_server_database_is_separate_from_client_default(self):
        self.assertEqual(database.DATABASE_PATH, Path(self.folder.name) / 'accounts.db')
        self.assertEqual(self.client.get('/health').json(), {'status': 'ok'})
        self.assertEqual(database.getUserByEmail('owner@example.com')['email'], 'owner@example.com')


if __name__ == '__main__':
    unittest.main()
