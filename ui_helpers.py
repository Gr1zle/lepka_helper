"""Общие сообщения и проверка актуальности сессии перед действием."""
from functools import wraps
import flet as ft

from account_gateway import getSessionUser, logoutUser
from api_client import ApiError


def isWebClient(page):
    state = page.data
    return bool(isinstance(state, dict) and state.get('isWebServer')) or page.web


def showMessage(page, messageText, isError=False):
    page.open(ft.SnackBar(content=ft.Text(messageText),
                         bgcolor=ft.Colors.RED_400 if isError else ft.Colors.GREEN_400))


def serverAction(page):
    """Сетевая ошибка не превращается в выход; 401 завершает сессию."""
    def decorate(callback):
        @wraps(callback)
        def guarded(*args, **kwargs):
            try:
                return callback(*args, **kwargs)
            except ApiError as error:
                if error.statusCode == 401:
                    page.session.clear()
                    page.overlay.clear()
                    page.go('/auth')
                showMessage(page, str(error), True)
                return None
        return guarded
    return decorate


def getCurrentUser(page):
    currentUser = page.session.get('currentUser')
    if currentUser is None:
        return None
    verifiedUser = getSessionUser(currentUser.get('sessionToken'))
    if verifiedUser is None or verifiedUser['userId'] != currentUser.get('userId'):
        page.session.clear()
        return None
    page.session.set('currentUser', verifiedUser)
    return verifiedUser


def logoutPage(page):
    currentUser = page.session.get('currentUser') or {}
    errorMessage = None
    try:
        logoutUser(currentUser.get('sessionToken'))
    except ApiError:
        errorMessage = 'На устройстве выход выполнен. Сервер недоступен: отзыв токена не подтверждён'
    finally:
        page.session.clear()
        page.overlay.clear()
        page.go('/auth')
    if errorMessage:
        showMessage(page, errorMessage, True)


def authenticatedAction(page, expectedUser):
    """Старый обработчик не должен выполняться после выхода или смены аккаунта."""
    def decorate(callback):
        @serverAction(page)
        @wraps(callback)
        def guarded(*args, **kwargs):
            currentUser = getCurrentUser(page)
            if (currentUser is None or expectedUser is None
                    or currentUser.get('sessionToken') != expectedUser.get('sessionToken')):
                showMessage(page, 'Сессия завершена. Выполните вход снова', True)
                if currentUser is None:
                    page.go('/auth')
                return None
            return callback(*args, **kwargs)
        return guarded
    return decorate
