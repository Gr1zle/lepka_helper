"""HTTP-транспорт клиента. Секрет Resend здесь не используется."""
import ipaddress
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

import requests


class ApiError(Exception):
    def __init__(self, message, statusCode=0):
        super().__init__(message)
        self.statusCode = statusCode


def validateApiUrl(address, allowLan=False):
    address = address.strip().rstrip('/')
    try:
        parsed = urlsplit(address)
        host = parsed.hostname
    except ValueError as error:
        raise ApiError('Некорректный адрес сервера') from error
    try:
        ip = ipaddress.ip_address(host or '')
        private = ip.version == 4 and (ip in ipaddress.ip_network('10.0.0.0/8') or
                  ip in ipaddress.ip_network('172.16.0.0/12') or ip in ipaddress.ip_network('192.168.0.0/16'))
    except ValueError:
        private = False
    local = host in ('127.0.0.1', 'localhost', '10.0.2.2')
    try:
        parsed.port
    except ValueError as error:
        raise ApiError('Некорректный порт сервера') from error
    if (not host or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path not in ('', '/') or (parsed.scheme != 'https' and
            not (parsed.scheme == 'http' and ((allowLan and (private or local)) or
                 (os.environ.get('LEPKA_ALLOW_LOCAL_API') == '1' and local))))):
        raise ApiError('Укажите HTTPS-адрес или HTTP-адрес компьютера в локальной сети')
    return address


def getApiUrl():
    from app_paths import DATA_DIRECTORY
    saved = DATA_DIRECTORY / 'server_connection.json'
    if saved.exists():
        try:
            config = json.loads(saved.read_text(encoding='utf-8'))
            address = config['apiBaseUrl']
            return validateApiUrl(address, allowLan=config.get('allowLan') is True) if address else ''
        except (ValueError, KeyError, TypeError, AttributeError, OSError) as error:
            raise ApiError('Не удалось прочитать настройки подключения') from error

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
    return validateApiUrl(address)


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
        if baseUrl.startswith('http://'):
            with requests.Session() as session:
                session.trust_env = False
                response = session.request(method, baseUrl + path, **body, headers=headers,
                                           timeout=(5, 20), allow_redirects=False)
        else:
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
