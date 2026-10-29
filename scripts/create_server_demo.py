"""Однократное создание тестового пользователя в существующей серверной базе.

Запуск из корня: python -m scripts.create_server_demo
Каталог берётся из LEPKA_SERVER_DATA_DIR или --data-dir. Пароли существующих
аккаунтов не заменяются, пользовательская база не создаётся по случайному пути.
"""
import argparse
import os
from pathlib import Path


def createServerDemo(dataDirectory):
    if not dataDirectory:
        raise ValueError('Задайте прежний LEPKA_SERVER_DATA_DIR или параметр --data-dir')
    target = Path(dataDirectory).expanduser().resolve() / 'accounts.db'
    if not target.is_file():
        raise ValueError('Серверная accounts.db не найдена в указанном каталоге. Сначала запустите API')
    import database
    from auth_service import ensureDemoUser
    from password_service import checkPassword
    previous = database.DATABASE_PATH
    try:
        database.DATABASE_PATH = target
        user = ensureDemoUser()
        if user is None:
            raise ValueError('Ник test_user занят другим аккаунтом. Существующие данные не изменены')
        record = database.getUserByEmail('test@email.com')
        available = (record['emailVerified'] and not record['isBlocked']
                     and checkPassword('Test123456', record['passwordHash'], record['passwordSalt']))
        if not available:
            raise ValueError('Аккаунт test@email.com уже существует с другими настройками или паролем. Он не изменён')
        return user
    finally:
        database.DATABASE_PATH = previous


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', default=os.environ.get('LEPKA_SERVER_DATA_DIR'))
    options = parser.parse_args()
    try:
        createServerDemo(options.data_dir)
    except ValueError as error:
        parser.exit(1, str(error) + '\n')
    print('Тестовый вход готов: test@email.com / Test123456. Почта не требуется.')
