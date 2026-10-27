"""Аккаунты: настоящий SQLite, временная база, письма перехватываются в памяти."""
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch, Mock

import database as db
import auth_service as auth
import account_security as security
import profile_service as profiles
from mail_service import MailDeliveryError, sendAccountCode
from validators import validateEmail, validateNickname, validatePassword


class AccountTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        databasePatch = patch.object(db, 'DATABASE_PATH', Path(folder.name) / 'test.db')
        databasePatch.start()
        self.addCleanup(databasePatch.stop)
        db.initializeDatabase()
        self.mailPatch = patch('account_security.sendAccountCode')
        self.mail = self.mailPatch.start()
        self.addCleanup(self.mailPatch.stop)
        auth.ensureDemoUser()
        self.user = auth.loginUser('test@email.com', 'Test123456')[2]
        self.userId = self.user['userId']

    def register(self, email='student@example.com', nickname='student'):
        success, message, user = auth.registerUser(email, 'Student123', 'Student123', nickname, True)
        self.assertTrue(success, message)
        return user

    def code(self, email='test@email.com', purpose='recovery'):
        success, message = security.requestAccountCode(email, purpose)
        self.assertTrue(success, message)
        return self.mail.call_args.args[1]

    def test_registration_requires_email_confirmation_and_code_is_single_use(self):
        user = self.register(' STUDENT@example.com ', ' student ')
        self.assertEqual(user['email'], 'student@example.com')
        self.assertNotIn('sessionToken', user)
        self.assertFalse(auth.loginUser(user['email'], 'Student123')[0])
        code = self.code(user['email'], 'registration')
        self.assertTrue(security.confirmRegistration(user['email'], code)[0])
        self.assertFalse(security.confirmRegistration(user['email'], code)[0])
        self.assertTrue(auth.loginUser(user['email'], 'Student123')[0])

    def test_invalid_registration_and_duplicate_email_or_nickname(self):
        for email, password, confirmation, nickname, consent in (
            (None, 'Student123', 'Student123', 'student', True),
            ('a@example.com', 'short', 'short', 'student', True),
            ('a@example.com', 'Student123', 'Mismatch123', 'student', True),
            ('a@example.com', 'Student123', 'Student123', None, True),
            ('a@example.com', 'Student123', 'Student123', 'student', False),
            ('a@example.com', 'Student123', 'Student123', 'student', 'yes'),
        ):
            self.assertFalse(auth.registerUser(email, password, confirmation, nickname, consent)[0])
        self.register()
        self.assertFalse(auth.registerUser(' STUDENT@example.com ', 'Student123', 'Student123', 'another', True)[0])
        self.assertFalse(auth.registerUser('another@example.com', 'Student123', 'Student123', 'student', True)[0])

    def test_input_boundaries_and_trailing_newlines(self):
        for email in ('a..b@example.com', '.a@example.com', 'a@-example.com', 'a@example..com', 'a@example.com\n', 'a@b'):
            self.assertIsNotNone(validateEmail(email))
        self.assertIsNone(validateEmail('student+tag@example.com'))
        for nickname in ('ab', 'a' * 21, 'student\n', 'has space'):
            self.assertIsNotNone(validateNickname(nickname))
        for nickname in ('abc', 'a' * 20, 'Мастер-1'):
            self.assertIsNone(validateNickname(nickname))
        for password in ('aA12345', 'aA1' + 'x' * 62, 'lower123', 'UPPER123', 'NoNumbers'):
            self.assertIsNotNone(validatePassword(password))
        self.assertIsNone(validatePassword('aA123456'))
        self.assertIsNone(validatePassword('aA1' + 'x' * 61))

    def test_login_blocks_after_five_failures_and_recovers_after_timeout(self):
        for _ in range(5):
            self.assertFalse(auth.loginUser('test@email.com', 'wrong')[0])
        db.initializeDatabase()  # Перезапуск не обходит блокировку.
        self.assertFalse(auth.loginUser('test@email.com', 'Test123456')[0])
        with patch('auth_service.time.time', return_value=time.time() + 901):
            self.assertTrue(auth.loginUser('test@email.com', 'Test123456')[0])
        self.assertEqual(db.getUserByEmail('test@email.com')['loginFailures'], 0)

    def test_successful_login_clears_previous_failures(self):
        for _ in range(4):
            auth.loginUser('test@email.com', 'wrong')
        self.assertTrue(auth.loginUser('test@email.com', 'Test123456')[0])
        self.assertFalse(auth.loginUser('test@email.com', 'wrong')[0])
        self.assertTrue(auth.loginUser('test@email.com', 'Test123456')[0])

    def test_blocked_user_and_unknown_user_cannot_log_in(self):
        with db.openDatabase() as connection:
            connection.execute('UPDATE users SET isBlocked = 1 WHERE userId = ?', (self.userId,))
        self.assertFalse(auth.loginUser('test@email.com', 'Test123456')[0])
        self.assertIsNone(security.getSessionUser(self.user['sessionToken']))
        self.assertFalse(auth.loginUser('missing@example.com', 'Test123456')[0])

    def test_password_cannot_be_reset_without_delivered_code(self):
        self.assertFalse(auth.changePasswordByEmail('test@email.com', 'ResetPass123', 'ResetPass123')[0])
        self.assertTrue(auth.loginUser('test@email.com', 'Test123456')[0])

    def test_recovery_code_is_not_returned_or_stored_as_plain_text(self):
        success, message = auth.requestPasswordRecovery('test@email.com')
        code = self.mail.call_args.args[1]
        self.assertTrue(success)
        self.assertNotIn(code, message)
        with db.openDatabase() as connection:
            record = connection.execute('SELECT * FROM accountCodes').fetchone()
            self.assertNotEqual(record['codeHash'], code)
        self.assertFalse(auth.requestPasswordRecovery('test@email.com')[0])

    def test_recovery_code_wrong_email_purpose_and_attempt_limit(self):
        code = self.code()
        self.assertFalse(security.confirmRegistration('test@email.com', code)[0])
        self.assertFalse(auth.changePasswordByEmail('other@example.com', 'ResetPass123', 'ResetPass123', code)[0])
        for _ in range(5):
            self.assertFalse(auth.changePasswordByEmail('test@email.com', 'ResetPass123', 'ResetPass123', 'bad')[0])
        self.assertFalse(auth.changePasswordByEmail('test@email.com', 'ResetPass123', 'ResetPass123', code)[0])
        with patch('account_security.time.time', return_value=time.time() + 61):
            nextCode = self.code()
        self.assertTrue(auth.changePasswordByEmail('test@email.com', 'ResetPass123', 'ResetPass123', nextCode)[0])

    def test_recovery_expires_and_new_code_replaces_old_one(self):
        code = self.code()
        with patch('account_security.time.time', return_value=time.time() + 601):
            self.assertFalse(auth.changePasswordByEmail('test@email.com', 'ResetPass123', 'ResetPass123', code)[0])
        with patch('account_security.time.time', return_value=time.time() + 61):
            with patch('account_security.secrets.randbelow', return_value=123456 if code != '123456' else 654321):
                nextCode = self.code()
        self.assertNotEqual(code, nextCode)
        self.assertFalse(auth.changePasswordByEmail('test@email.com', 'ResetPass123', 'ResetPass123', code)[0])
        self.assertTrue(auth.changePasswordByEmail('test@email.com', 'ResetPass123', 'ResetPass123', nextCode)[0])

    def test_successful_reset_is_single_use_and_revokes_all_sessions(self):
        second = auth.loginUser('test@email.com', 'Test123456')[2]
        code = self.code()
        self.assertTrue(auth.changePasswordByEmail('test@email.com', 'ResetPass123', 'ResetPass123', code)[0])
        for user in (self.user, second):
            self.assertIsNone(security.getSessionUser(user['sessionToken']))
        self.assertFalse(auth.changePasswordByEmail('test@email.com', 'Another123', 'Another123', code)[0])
        self.assertFalse(auth.loginUser('test@email.com', 'Test123456')[0])
        self.assertTrue(auth.loginUser('test@email.com', 'ResetPass123')[0])

    def test_failed_delivery_does_not_create_code_or_change_password(self):
        self.mail.side_effect = MailDeliveryError('Почта недоступна')
        self.assertFalse(auth.requestPasswordRecovery('test@email.com')[0])
        with db.openDatabase() as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM accountCodes').fetchone()[0], 0)
        self.assertTrue(auth.loginUser('test@email.com', 'Test123456')[0])

    def test_unknown_recovery_email_does_not_send_message(self):
        self.assertTrue(auth.requestPasswordRecovery('unknown@example.com')[0])
        self.mail.assert_not_called()

    def test_registration_confirmation_expires_after_24_hours(self):
        self.register()
        code = self.code('student@example.com', 'registration')
        with patch('account_security.time.time', return_value=time.time() + 86401):
            self.assertFalse(security.confirmRegistration('student@example.com', code)[0])

    def test_password_change_locks_after_three_errors_and_revokes_sessions(self):
        second = auth.loginUser('test@email.com', 'Test123456')[2]
        for _ in range(3):
            self.assertFalse(profiles.changeUserPassword(self.userId, 'wrong', 'Changed123', 'Changed123')[0])
        self.assertFalse(profiles.changeUserPassword(self.userId, 'Test123456', 'Changed123', 'Changed123')[0])
        with patch('profile_service.time.time', return_value=time.time() + 301):
            self.assertTrue(profiles.changeUserPassword(self.userId, 'Test123456', 'Changed123', 'Changed123')[0])
        self.assertIsNone(security.getSessionUser(self.user['sessionToken']))
        self.assertIsNone(security.getSessionUser(second['sessionToken']))

    def test_logout_revokes_only_selected_session_and_expired_token_is_rejected(self):
        second = auth.loginUser('test@email.com', 'Test123456')[2]
        security.logoutUser(self.user['sessionToken'])
        self.assertIsNone(security.getSessionUser(self.user['sessionToken']))
        self.assertIsNotNone(security.getSessionUser(second['sessionToken']))
        with patch('account_security.time.time', return_value=time.time() + security.SESSION_SECONDS + 1):
            self.assertIsNone(security.getSessionUser(second['sessionToken']))
        with db.openDatabase() as connection:
            stored = connection.execute('SELECT tokenHash FROM accountSessions').fetchone()[0]
            self.assertNotEqual(stored, second['sessionToken'])

    def test_profile_settings_round_trip_and_user_isolation(self):
        other = self.register()
        self.assertTrue(profiles.saveUserProfile(self.userId, 'Лепщик', 'Биография', profiles.AGE_CATEGORIES[0], ['Белый', 'Синий'])[0])
        self.assertTrue(profiles.saveUserSettings(self.userId, 'dark', 'en', False)[0])
        db.initializeDatabase()
        profile = profiles.getUserProfile(self.userId)
        self.assertEqual((profile['nickname'], profile['bioText'], profile['favoriteColors']), ('Лепщик', 'Биография', ['Белый', 'Синий']))
        self.assertEqual((profile['themeMode'], profile['languageCode'], profile['notificationsEnabled']), ('dark', 'en', False))
        self.assertEqual(profiles.getUserProfile(other['userId'])['nickname'], 'student')
        self.assertEqual(profiles.getUserProfile(other['userId'])['themeMode'], 'light')

    def test_invalid_profile_settings_missing_user_and_duplicate_nickname(self):
        self.register()
        before = profiles.getUserProfile(self.userId)
        for nickname, bio, age, colors in (
            ('student', '', profiles.AGE_CATEGORIES[0], []),
            ('a', '', profiles.AGE_CATEGORIES[0], []),
            ('valid', 'x' * 501, profiles.AGE_CATEGORIES[0], []),
            ('valid', '', 'invalid', []), ('valid', '', profiles.AGE_CATEGORIES[0], ['Не цвет']),
        ):
            self.assertFalse(profiles.saveUserProfile(self.userId, nickname, bio, age, colors)[0])
        for theme, language, notifications in (('blue', 'ru', True), ('light', 'fr', True), ('light', 'ru', 'false')):
            self.assertFalse(profiles.saveUserSettings(self.userId, theme, language, notifications)[0])
        self.assertEqual(profiles.getUserProfile(self.userId), before)
        self.assertFalse(profiles.saveUserProfile(99999, 'valid', '', profiles.AGE_CATEGORIES[0], [])[0])
        self.assertFalse(profiles.saveUserSettings(99999, 'light', 'ru', True)[0])

    def test_email_change_requires_password_code_and_matching_owner(self):
        other = self.register()
        self.assertFalse(auth.requestEmailChange(self.userId, 'wrong', 'new@example.com')[0])
        self.assertTrue(auth.requestEmailChange(self.userId, 'Test123456', 'new@example.com')[0])
        code = self.mail.call_args.args[1]
        self.assertFalse(auth.confirmEmailChange(other['userId'], 'new@example.com', code)[0])
        self.assertFalse(auth.confirmEmailChange(self.userId, 'wrong@example.com', code)[0])
        self.assertTrue(auth.confirmEmailChange(self.userId, 'new@example.com', code)[0])
        self.assertIsNone(db.getUserByEmail('test@email.com'))
        self.assertIsNone(security.getSessionUser(self.user['sessionToken']))
        self.assertTrue(auth.loginUser('new@example.com', 'Test123456')[0])
        self.assertFalse(auth.confirmEmailChange(self.userId, 'new@example.com', code)[0])

    def test_foreign_keys_reject_new_orphans(self):
        with db.openDatabase() as connection:
            self.assertEqual(connection.execute('PRAGMA foreign_keys').fetchone()[0], 1)
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("INSERT INTO projectSteps (projectId, stepDescription) VALUES (999999, 'Этап')")

    def test_delete_account_preserves_other_comments_and_removes_personal_data(self):
        other = self.register()
        post = db.createPost(self.userId, 'Котик', 'Описание котика', 'Животные', '')
        otherPost = db.createPost(other['userId'], 'Зайчик', 'Описание зайчика', 'Животные', '')
        db.createPostComment(post, other['userId'], 'Чужой комментарий')
        db.createPostComment(otherPost, self.userId, 'Мой комментарий')
        db.createPostLike(otherPost, self.userId)
        db.updatePostLikesCount(otherPost, 1)
        project = db.createProject(self.userId, 'Проект', 'Животные', '', '')
        db.createProjectStep(project, 'Этап', self.userId)
        db.createColorMixture(self.userId, 'Смесь', '#808080', 100, '[]')
        self.code()
        self.assertFalse(auth.deleteUserAccount(self.userId, 'wrong')[0])
        self.assertTrue(auth.deleteUserAccount(self.userId, 'Test123456')[0])
        self.assertIsNone(db.getUserByEmail('test@email.com'))
        self.assertIsNone(security.getSessionUser(self.user['sessionToken']))
        self.assertEqual(db.getProjectsByUserId(self.userId), [])
        self.assertEqual(db.getColorMixturesByUserId(self.userId), [])
        self.assertEqual(db.getCommentsByPostId(post)[0]['commentText'], 'Чужой комментарий')
        self.assertEqual(db.getCommentsByPostId(otherPost), [])
        self.assertIsNotNone(db.getUserByEmail(other['email']))
        with db.openDatabase() as connection:
            self.assertEqual(connection.execute('SELECT titleText FROM posts WHERE postId = ?', (post,)).fetchone()[0], 'Работа удалена пользователем')
            self.assertEqual(connection.execute('SELECT likesCount FROM posts WHERE postId = ?', (otherPost,)).fetchone()[0], 0)
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM projectSteps').fetchone()[0], 0)
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM accountCodes').fetchone()[0], 0)
            self.assertEqual(connection.execute('SELECT eventName FROM accountEvents').fetchone()[0], 'selfDelete')
            self.assertEqual(connection.execute('PRAGMA foreign_key_check').fetchall(), [])

    def test_delete_account_rolls_back_if_a_database_error_occurs(self):
        with db.openDatabase() as connection:
            connection.execute("CREATE TRIGGER reject_delete BEFORE DELETE ON users BEGIN SELECT RAISE(ABORT, 'test failure'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            auth.deleteUserAccount(self.userId, 'Test123456')
        self.assertIsNotNone(db.getUserByEmail('test@email.com'))
        self.assertIsNotNone(security.getSessionUser(self.user['sessionToken']))

    def test_simultaneous_reset_uses_code_only_once(self):
        from concurrent.futures import ThreadPoolExecutor
        code = self.code()
        def reset():
            return auth.changePasswordByEmail('test@email.com', 'ResetPass123', 'ResetPass123', code)[0]
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda index: reset(), range(2)))
        self.assertEqual(sorted(results), [False, True])

    def test_private_mixtures_projects_and_comment_deletion_are_scoped(self):
        other = self.register()
        mixture = db.createColorMixture(self.userId, 'Моя смесь', '#808080', 100, '[]')
        self.assertEqual(db.getColorMixturesByUserId(other['userId']), [])
        self.assertFalse(db.deleteColorMixtureById(other['userId'], mixture))
        self.assertEqual(len(db.getColorMixturesByUserId(self.userId)), 1)
        post = db.createPost(self.userId, 'Котик', 'Описание котика', 'Животные', '')
        comment = db.createPostComment(post, self.userId, 'Мой комментарий')
        db.deletePostCommentById(comment, other['userId'])
        self.assertEqual(len(db.getCommentsByPostId(post)), 1)
        self.assertFalse(db.deletePostById(post, other['userId']))
        self.assertTrue(db.deletePostById(post, self.userId))
        self.assertEqual(db.getCommentsByPostId(post), [])

    def test_like_count_and_comment_creation_reject_missing_posts(self):
        import post_service as posts
        self.assertEqual(posts.togglePostLike(999999, self.userId), (False, None))
        self.assertFalse(posts.savePostComment(999999, self.userId, 'Комментарий')[0])
        post = db.createPost(self.userId, 'Котик', 'Описание котика', 'Животные', '')
        self.assertEqual(posts.togglePostLike(post, self.userId), (True, 1))
        self.assertEqual(posts.togglePostLike(post, self.userId), (False, 0))
        self.assertEqual(posts.getCommunityPosts()[0]['likesCount'], 0)


class MigrationTests(unittest.TestCase):
    def test_existing_account_password_and_old_orphan_are_preserved(self):
        from password_service import createPasswordHash
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'legacy.db'
            passwordHash, passwordSalt = createPasswordHash('Legacy123')
            with sqlite3.connect(path) as connection:
                connection.execute("""CREATE TABLE users (
                    userId INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT NOT NULL UNIQUE,
                    passwordHash TEXT NOT NULL, passwordSalt TEXT NOT NULL, nickname TEXT NOT NULL UNIQUE,
                    roleName TEXT NOT NULL DEFAULT 'user', isBlocked INTEGER NOT NULL DEFAULT 0,
                    createdAt TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
                connection.execute('INSERT INTO users (email, passwordHash, passwordSalt, nickname) VALUES (?, ?, ?, ?)',
                                   ('legacy@example.com', passwordHash, passwordSalt, 'legacy'))
            with patch.object(db, 'DATABASE_PATH', path):
                db.initializeDatabase()
                # Имитация записи, оставшейся от прежней версии без контроля FK.
                with sqlite3.connect(path) as connection:
                    connection.execute("INSERT INTO projectSteps (projectId, stepDescription) VALUES (99999, 'Старый этап')")
                db.initializeDatabase()
                self.assertTrue(auth.loginUser('legacy@example.com', 'Legacy123')[0])
                self.assertEqual(db.getUserByEmail('legacy@example.com')['passwordHash'], passwordHash)
                with db.openDatabase() as connection:
                    self.assertEqual(connection.execute('SELECT stepDescription FROM projectSteps').fetchone()[0], 'Старый этап')
                    self.assertEqual(len(connection.execute('PRAGMA foreign_key_check').fetchall()), 1)
                    self.assertEqual(connection.execute('PRAGMA foreign_keys').fetchone()[0], 1)


class MailTests(unittest.TestCase):
    def test_missing_configuration_fails_without_network_request(self):
        with patch.dict('os.environ', {}, clear=True), patch('mail_service.requests.post') as post:
            with self.assertRaises(MailDeliveryError):
                sendAccountCode('student@example.com', '123456', 'recovery')
            post.assert_not_called()

    def test_https_request_and_delivery_error(self):
        import requests
        with patch.dict('os.environ', {'LEPKA_MAIL_API_KEY': 'test-placeholder', 'LEPKA_MAIL_FROM': 'noreply@example.com'}):
            with patch('mail_service.requests.post', return_value=Mock()) as post:
                sendAccountCode('student@example.com', '123456', 'registration')
                self.assertEqual(post.call_args.args[0], 'https://api.resend.com/emails')
                self.assertEqual(post.call_args.kwargs['json']['to'], ['student@example.com'])
                self.assertIn('123456', post.call_args.kwargs['json']['text'])
                self.assertNotIn('verify', post.call_args.kwargs)  # TLS-проверка остаётся включённой.
            with patch('mail_service.requests.post', side_effect=requests.Timeout):
                with self.assertRaises(MailDeliveryError):
                    sendAccountCode('student@example.com', '123456', 'recovery')


if __name__ == '__main__':
    unittest.main()
