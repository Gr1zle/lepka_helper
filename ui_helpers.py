from localization import clearSession
from localization import tr, term
"""Общие сообщения и проверка актуальности сессии перед действием."""
from functools import wraps
import flet as ft

from account_gateway import getSessionUser, logoutUser
from api_client import ApiError
from device_session import forgetDeviceSession


def isWebClient(page):
    state = page.data
    return bool(isinstance(state, dict) and state.get('isWebServer')) or page.web


def showMessage(page, messageText, isError=False):
    from localization import message as translateMessage
    page.open(ft.SnackBar(content=ft.Text(translateMessage(page,messageText)),
                         bgcolor=ft.Colors.RED_400 if isError else ft.Colors.GREEN_400))


def confirmAction(page, titleText, messageText, callback):
    """callback повторно проверяет сессию в момент подтверждения."""
    def confirm(event):
        page.close(dialog)
        callback()
    dialog = ft.AlertDialog(modal=True, title=ft.Text(titleText), content=ft.Text(messageText), actions=[
        ft.TextButton(tr(page, 'Отмена'), on_click=lambda event: page.close(dialog)),
        ft.ElevatedButton(tr(page, 'Подтвердить удаление'), on_click=confirm)])
    page.open(dialog)


def createLoadError(page, error, retry):
    return ft.Container(padding=24, content=ft.Column(spacing=16, controls=[
        ft.Icon(ft.Icons.CLOUD_OFF, size=48), ft.Text(tr(page, 'Не удалось открыть раздел'), size=22),
        ft.Text(str(error)), ft.Text(tr(page, 'Проверьте, запущен ли сервер, и повторите попытку.')),
        ft.ElevatedButton(tr(page, 'Повторить загрузку'), height=48, on_click=lambda event: retry()),
        ft.TextButton(tr(page, 'Выйти ко входу'), on_click=lambda event: logoutPage(page))]))


def serverAction(page):
    """Сетевая ошибка не превращается в выход; 401 завершает сессию."""
    def decorate(callback):
        @wraps(callback)
        def guarded(*args, **kwargs):
            try:
                return callback(*args, **kwargs)
            except ApiError as error:
                if error.statusCode == 401:
                    forgetDeviceSession(page)
                    clearSession(page)
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
    if currentUser.get('apiUrl') and currentUser.get('sessionExpiresAt') is not None and currentUser['sessionExpiresAt']<=__import__('time').time():
        forgetDeviceSession(page);clearSession(page);return None
    verifiedUser = getSessionUser(currentUser.get('sessionToken'))
    if verifiedUser is None or verifiedUser['userId'] != currentUser.get('userId'):
        forgetDeviceSession(page)
        clearSession(page)
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
        forgetDeviceSession(page)
        clearSession(page)
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
                showMessage(page, tr(page, 'Сессия завершена. Выполните вход снова'), True)
                if currentUser is None:
                    page.go('/auth')
                return None
            return callback(*args, **kwargs)
        return guarded
    return decorate
