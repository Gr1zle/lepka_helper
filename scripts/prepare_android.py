"""Готовит отдельную папку сборки без баз, .env и сервера.

Запуск: python scripts/prepare_android.py --output ../lepka-android
Файл конфигурации получает только публичный адрес API, не переменные окружения.
"""
import argparse
import json
from pathlib import Path
import shutil
import sys
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app_info import APP_VERSION
from learning_assets import MODEL_ASSETS,STEP_ASSETS
MODULES = (
    'account_gateway', 'account_security', 'api_client', 'app_info', 'app_paths', 'app_state', 'project_planner', 'model_import', 'model_upload',
    'auth_service', 'color_export', 'color_service', 'community_gateway', 'database', 'date_field',
    'download_service', 'device_session', 'lesson_service', 'lesson_library', 'mail_service', 'password_service',
    'photo_service', 'photo_upload', 'photo_picker', 'post_service', 'profile_service',
    'project_service', 'project_sharing', 'project_archive', 'project_backups', 'project_statistics', 'project_upload', 'clay_tools', 'workshop_service', 'remote_account_cache', 'ui_helpers', 'validators', 'mesh_renderer','model_service','learning_assets',
)
VIEWS = ('auth_view', 'about_dialog', 'home_view', 'community_tab', 'project_sharing', 'project_step_order', 'project_transfer', 'project_statistics', 'project_planner', 'clay_tools_view', 'lesson_library_view', 'model_import', 'model_gallery','model_view','workshop_view', 'profile_tab', 'splash_view', 'onboarding_view')
ASSETS = ('fonts/DejaVuSans.ttf', 'fonts/LICENSE-DejaVu.txt',
          *(f'lessons/lesson_{index}.svg' for index in range(1, 7)),*MODEL_ASSETS,*STEP_ASSETS)


def prepareAndroid(output, apiUrl=None, localDemo=False):
    output = Path(output).expanduser().resolve()
    # Новая папка: ни исходники, ни существующая сборка не заменяются.
    if output == ROOT or ROOT in output.parents or output in ROOT.parents:
        raise ValueError('Выберите новую папку вне репозитория')
    if apiUrl is None and localDemo:
        apiUrl = ''
    if apiUrl is None:
        config = json.loads((ROOT / 'assets' / 'client_config.json').read_text(encoding='utf-8'))
        apiUrl = config.get('apiBaseUrl', '')
    if not isinstance(apiUrl, str):
        raise ValueError('Адрес API должен быть строкой')
    if localDemo and apiUrl:
        raise ValueError('Для локальной демоверсии адрес API должен быть пустым')
    if apiUrl:
        address = urlsplit(apiUrl)
        if (address.scheme != 'https' or not address.hostname or address.username or address.password
                or address.query or address.fragment):
            raise ValueError('Для APK нужен публичный HTTPS-адрес API без ключей и паролей')
    output.mkdir(parents=True, exist_ok=False)
    for module in MODULES:
        shutil.copyfile(ROOT / (module + '.py'), output / (module + '.py'))
    shutil.copyfile(ROOT / 'main.py', output / 'app_main.py')
    (output / 'views').mkdir()
    for view in VIEWS:
        shutil.copyfile(ROOT / 'views' / (view + '.py'), output / 'views' / (view + '.py'))
    (output / 'assets').mkdir()
    for name in ASSETS:
        destination = output / 'assets' / name
        destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(ROOT / 'assets' / name, destination)
    (output / 'assets' / 'client_config.json').write_text(
        json.dumps({'apiBaseUrl': apiUrl.rstrip('/')}, ensure_ascii=False), encoding='utf-8')
    (output / 'main.py').write_text(
        ('import os\nos.environ["LEPKA_FORCE_LOCAL"] = "1"\n' if localDemo else '') +
        'from pathlib import Path\nimport flet as ft\nfrom app_main import main\n\n'
        'ft.app(target=main, assets_dir=str(Path(__file__).resolve().parent / "assets"))\n', encoding='utf-8')
    # В APK не требуются uvicorn и FastAPI сервера. Starlette используется общими
    # модулями скачивания/загрузки, хотя HTTP-маршруты запускаются только на ПК.
    (output / 'requirements.txt').write_text(
        'flet==0.28.3\nrequests==2.32.3\nPillow==12.3.0\nstarlette==0.46.2\n', encoding='utf-8')
    (output / 'pyproject.toml').write_text(('''[project]
name = "lepka-helper"
version = "APP_VERSION_PLACEHOLDER"
description = "Помощник по лепке"
requires-python = ">=3.12"

[tool.flet]
org = "ru.gr1zle"
product = "Помощник по лепке"

[tool.flet.android]
split_per_abi = true
min_sdk_version = 28

[tool.flet.android.permission]
"android.permission.INTERNET" = true

[tool.flet.flutter]
build_args = ["--target-platform=android-arm64"]
''').replace('APP_VERSION_PLACEHOLDER', APP_VERSION), encoding='utf-8')
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    parser.add_argument('--api-url', default=None)
    parser.add_argument('--local-demo', action='store_true', help='Локальная проверка Android без сервера')
    options = parser.parse_args()
    try:
        path = prepareAndroid(options.output, options.api_url, options.local_demo)
    except (ValueError, OSError) as error:
        parser.exit(1, f'{error}\n')
    print(f'Папка сборки: {path}')
    if options.local_demo:
        print('Локальная демоверсия: test@email.com / Test123456. Общего интернет-сообщества нет.')
    else:
        print('Если адрес API пуст, Android покажет сообщение о необходимости настройки сервера.')
