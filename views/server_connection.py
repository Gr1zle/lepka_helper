"""Настройка подключения до входа; смена сервера требует нового входа."""
import json
import os
import tempfile
import flet as ft
import requests
from api_client import ApiError, getApiUrl, validateApiUrl
from app_paths import DATA_DIRECTORY


def openServerConnection(page):
    address = ft.TextField(label='Адрес сервера', value=getApiUrl(), hint_text='http://192.168.1.20:8000')
    lan = ft.Checkbox(label='Разрешить HTTP в своей Wi-Fi сети', value=address.value.startswith('http://'))
    status = ft.Text('Компьютер и телефон должны быть в одной сети. HTTP не шифрует данные.')

    def checked():
        return validateApiUrl(address.value or '', allowLan=lan.value)

    def probe(e):
        try:
            url = checked()
            with requests.Session() as session:
                if url.startswith('http://'):
                    session.trust_env = False  # Домашние адреса не отправляем в корпоративный прокси.
                response = session.get(url + '/ready', timeout=(3, 5), allow_redirects=False)
            if response.status_code != 200 or response.json().get('status') != 'ready':
                raise ApiError('Сервер пока не готов')
            status.value = 'Сервер доступен. Можно сохранить адрес и войти.'
        except (ApiError, requests.RequestException, ValueError, AttributeError) as error:
            status.value = str(error) if isinstance(error, ApiError) else 'Нет связи. Проверьте адрес, Wi-Fi и брандмауэр компьютера.'
        page.update()

    def save(e, local=False):
        try:
            url = '' if local else checked()
            from device_session import forgetDeviceSession
            forgetDeviceSession(page)
            payload = {'apiBaseUrl': url, 'allowLan': bool(lan.value)}
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=DATA_DIRECTORY, delete=False) as stream:
                json.dump(payload, stream)
                temporary = stream.name
            os.replace(temporary, DATA_DIRECTORY / 'server_connection.json')
            page.session.set('currentUser', None)
            page.close(dialog)
            page.views.clear()
            page.go('/auth')
            if page.route == '/auth':
                from views.auth_view import createAuthView
                page.views[:] = [createAuthView(page)]
                page.update()
        except (ApiError, OSError) as error:
            status.value = str(error)
            page.update()

    dialog = ft.AlertDialog(title=ft.Text('Подключение к серверу'), content=ft.Column(
        [address, lan, status, ft.TextButton('Проверить связь', on_click=probe)], tight=True, width=360),
        actions=[ft.TextButton('Локальный режим', on_click=lambda e: save(e, True)),
                 ft.TextButton('Отмена', on_click=lambda e: page.close(dialog)),
                 ft.TextButton('Сохранить', on_click=save)])
    page.open(dialog)
