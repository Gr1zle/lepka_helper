"""Единый вход для интерфейса: прежние локальные сервисы или HTTP API.

При заданном адресе API переключения на локальную авторизацию при ошибке нет.
Сервер отвечает за аккаунт; локальные проекты и смеси пока не синхронизируются.
"""
import sqlite3

import account_security as localSecurity
import auth_service as localAccounts
import profile_service as localProfiles
from api_client import ApiError, apiRequest, getApiUrl
from database import deleteUserDataById
from remote_account_cache import cacheRemoteUser, forgetRemoteSession, requireCachedUser


def pairRequest(method, path, payload, sessionToken=None):
    try:
        response = apiRequest(method, path, payload, sessionToken)
        return True, response.get('message', 'Готово')
    except ApiError as error:
        if error.statusCode == 401 and sessionToken:
            raise
        return False, str(error)


def registerUser(email, password, passwordConfirmation, nickname, isPolicyAccepted):
    if not getApiUrl():
        return localAccounts.registerUser(email, password, passwordConfirmation, nickname, isPolicyAccepted)
    try:
        response = apiRequest('POST', '/auth/register', {
            'email': email, 'password': password, 'passwordConfirmation': passwordConfirmation,
            'nickname': nickname, 'isPolicyAccepted': isPolicyAccepted})
        return True, response.get('message', 'Аккаунт создан. Подтвердите email'), response['data']
    except ApiError as error:
        return False, str(error), None


def loginUser(email, password):
    if not getApiUrl():
        return localAccounts.loginUser(email, password)
    try:
        response = apiRequest('POST', '/auth/login', {'email': email, 'password': password})
        data = response['data']
        token = data.get('sessionToken') if isinstance(data, dict) else None
        return True, response.get('message', 'Вход выполнен'), cacheRemoteUser(data, token)
    except ApiError as error:
        return False, str(error), None


def ensureDemoUser():
    return None if getApiUrl() else localAccounts.ensureDemoUser()


def getSessionUser(sessionToken):
    if not getApiUrl():
        return localSecurity.getSessionUser(sessionToken)
    if not sessionToken:
        return None
    try:
        response = apiRequest('GET', '/auth/me', sessionToken=sessionToken)
        return cacheRemoteUser(response['data'], sessionToken)
    except ApiError as error:
        if error.statusCode == 401:
            forgetRemoteSession(sessionToken)
            return None
        raise


def logoutUser(sessionToken):
    if not getApiUrl():
        return localSecurity.logoutUser(sessionToken)
    if not sessionToken:
        return
    try:
        apiRequest('POST', '/auth/logout', sessionToken=sessionToken)
    finally:
        forgetRemoteSession(sessionToken)


def requestRegistrationCode(email):
    if not getApiUrl():
        return localAccounts.requestRegistrationCode(email)
    return pairRequest('POST', '/auth/registration/code', {'email': email})


def confirmRegistration(email, code):
    if not getApiUrl():
        return localSecurity.confirmRegistration(email, code)
    return pairRequest('POST', '/auth/registration/confirm', {'email': email, 'code': code})


def requestPasswordRecovery(email):
    if not getApiUrl():
        return localAccounts.requestPasswordRecovery(email)
    return pairRequest('POST', '/auth/recovery/code', {'email': email})


def changePasswordByEmail(email, newPassword, newPasswordConfirmation, recoveryCode=None):
    if not getApiUrl():
        return localAccounts.changePasswordByEmail(email, newPassword, newPasswordConfirmation, recoveryCode)
    return pairRequest('POST', '/auth/recovery/confirm', {
        'email': email, 'newPassword': newPassword, 'newPasswordConfirmation': newPasswordConfirmation,
        'recoveryCode': recoveryCode or ''})


def getUserProfile(userId, sessionToken=None):
    if not getApiUrl():
        return localProfiles.getUserProfile(userId)
    requireCachedUser(userId, sessionToken)
    data = apiRequest('GET', '/profile', sessionToken=sessionToken)['data']
    return cacheRemoteUser(data, sessionToken)


def profileRequest(userId, method, path, payload, sessionToken):
    try:
        requireCachedUser(userId, sessionToken)
        response = apiRequest(method, path, payload, sessionToken)
        return True, response.get('message', 'Готово'), cacheRemoteUser(response['data'], sessionToken)
    except ApiError as error:
        if error.statusCode == 401:
            raise
        return False, str(error), None


def saveUserProfile(userId, nickname, bioText, ageCategory, favoriteColors, avatarPath='', sessionToken=None):
    if not getApiUrl():
        return localProfiles.saveUserProfile(userId, nickname, bioText, ageCategory, favoriteColors, avatarPath)
    return profileRequest(userId, 'PUT', '/profile', {
        'nickname': nickname, 'bioText': bioText, 'ageCategory': ageCategory,
        'favoriteColors': favoriteColors, 'avatarPath': avatarPath}, sessionToken)


def saveUserSettings(userId, themeMode, languageCode, notificationsEnabled, sessionToken=None):
    if not getApiUrl():
        return localProfiles.saveUserSettings(userId, themeMode, languageCode, notificationsEnabled)
    return profileRequest(userId, 'PUT', '/profile/settings', {
        'themeMode': themeMode, 'languageCode': languageCode,
        'notificationsEnabled': notificationsEnabled}, sessionToken)


def accountRequest(userId, method, path, payload, sessionToken):
    try:
        requireCachedUser(userId, sessionToken)
        return pairRequest(method, path, payload, sessionToken)
    except ApiError as error:
        if error.statusCode == 401:
            raise
        return False, str(error)


def changeUserPassword(userId, currentPassword, newPassword, repeatedNewPassword, sessionToken=None):
    if not getApiUrl():
        return localProfiles.changeUserPassword(userId, currentPassword, newPassword, repeatedNewPassword)
    return accountRequest(userId, 'POST', '/account/password', {
        'currentPassword': currentPassword, 'newPassword': newPassword,
        'repeatedNewPassword': repeatedNewPassword}, sessionToken)


def requestEmailChange(userId, password, newEmail, sessionToken=None):
    if not getApiUrl():
        return localAccounts.requestEmailChange(userId, password, newEmail)
    return accountRequest(userId, 'POST', '/account/email/code',
                          {'password': password, 'newEmail': newEmail}, sessionToken)


def confirmEmailChange(userId, newEmail, code, sessionToken=None):
    if not getApiUrl():
        return localAccounts.confirmEmailChange(userId, newEmail, code)
    return accountRequest(userId, 'POST', '/account/email/confirm', {'newEmail': newEmail, 'code': code}, sessionToken)


def deleteUserAccount(userId, password, sessionToken=None):
    if not getApiUrl():
        return localAccounts.deleteUserAccount(userId, password)
    success, message = accountRequest(userId, 'DELETE', '/account', {'password': password}, sessionToken)
    if success:
        # Удаляем только записи этого серверного аккаунта в текущей локальной базе.
        try:
            deleteUserDataById(userId)
        except sqlite3.Error as error:
            raise ApiError('Аккаунт удалён на сервере, но локальную очистку завершить не удалось', 401) from error
    return success, message
