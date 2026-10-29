"""HTTP-транспорт клиента. Секрет Resend здесь не используется."""
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

import requests


class ApiError(Exception):
    def __init__(self, message, statusCode=0):
        super().__init__(message)
        self.statusCode = statusCode


def getApiUrl():
    # Явный режим запуска на ПК. Флаг не меняет файл настроек и базу сервера.
    if os.environ.get('LEPKA_FORCE_LOCAL') == '1':
        return ''
    address = os.environ.get('LEPKA_API_URL', '').strip()
    if not address:
        configPath = Path(__file__).resolve().parent / 'assets' / 'client_config.json'
        if configPath.exists():
            try:
                config = json.loads(configPath.read_text(encoding='utf-8'))
                if not isinstance(config, dict) or set(config) != {'apiBaseUrl'}:
                    raise ValueError('Разрешён только apiBaseUrl')
                address = config['apiBaseUrl'].strip()
            except (ValueError, TypeError, AttributeError, OSError) as error:
                raise ApiError('Не удалось прочитать адрес сервера из client_config.json') from error
    if not address:
        return ''
    parsed = urlsplit(address)
    localHttp = (os.environ.get('LEPKA_ALLOW_LOCAL_API') == '1'
                 and parsed.scheme == 'http' and parsed.hostname in ('127.0.0.1', 'localhost', '10.0.2.2'))
    if (not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment
            or (parsed.scheme != 'https' and not localHttp)):
        raise ApiError('Адрес API должен использовать HTTPS. HTTP разрешён только для явной локальной проверки')
    return address.rstrip('/')


def apiRequest(method, path, payload=None, sessionToken=None, imageData=None):
    baseUrl = getApiUrl()
    if not baseUrl:
        raise ApiError('Адрес сервера не задан')
    headers = {'Authorization': f'Bearer {sessionToken}'} if sessionToken else {}
    body = {'json': payload}
    if imageData is not None:
        headers['Content-Type'] = 'image/png'
        body = {'data': imageData}
    try:
        response = requests.request(method, baseUrl + path, **body, headers=headers,
                                    timeout=(5, 20), allow_redirects=False)
    except requests.RequestException as error:
        raise ApiError('Сервер недоступен. Повторите позже') from error
    try:
        data = response.json()
    except ValueError as error:
        statusCode = response.status_code if response.status_code >= 300 else 0
        raise ApiError('Сервер вернул некорректный ответ', statusCode) from error
    if response.status_code >= 300:
        message = data.get('detail') if isinstance(data, dict) else None
        raise ApiError(message if isinstance(message, str) else 'Не удалось выполнить запрос', response.status_code)
    if not isinstance(data, dict) or 'data' not in data:
        raise ApiError('Сервер вернул некорректный ответ')
    return data
