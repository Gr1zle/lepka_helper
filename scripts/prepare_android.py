"""Готовит отдельную папку сборки без баз, .env и сервера.

Запуск: python scripts/prepare_android.py --output ../lepka-android
Файл конфигурации получает только публичный адрес API, не переменные окружения.
"""
import argparse
import json
import hashlib
import base64
import csv
from io import StringIO
from zipfile import ZipFile,ZIP_DEFLATED
from pathlib import Path
import shutil
import sys
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app_info import APP_VERSION
from learning_assets import MODEL_ASSETS,STEP_ASSETS
MODULES = (
    'learning_catalog','catalog_client','catalog_upload','catalog_media','catalog_sync','device_notifications','delivery_settings','secure_device','offline_access','offline_mutations','community_cache','community_outbox','deferred_community','publication_drafts','connection_monitor','personal_vault','personal_snapshot','personal_checkpoints','personal_sync','color_wheel','personal_notices','notification_center','account_gateway', 'account_security', 'api_client', 'app_info', 'app_paths', 'app_state', 'project_planner', 'model_import', 'model_upload', 'moderation_service','moderation_gateway','role_service','challenge_service','challenge_gateway','contest_entry','activity_service','social_feed','feed_service',
    'auth_service', 'color_export', 'color_service', 'community_gateway', 'database', 'date_field',
    'download_service', 'device_session', 'lesson_service', 'lesson_library', 'mail_service', 'password_service',
    'photo_service', 'photo_upload', 'photo_picker', 'post_service', 'profile_service',
    'project_service', 'project_sharing', 'project_archive', 'project_backups', 'project_statistics', 'project_upload', 'clay_tools', 'workshop_service', 'remote_account_cache', 'ui_helpers', 'validators', 'mesh_renderer','model_service','learning_assets',
)
VIEWS = ('auth_view', 'about_dialog', 'home_view', 'community_tab', 'project_sharing', 'project_step_order', 'project_transfer', 'project_statistics', 'project_planner', 'clay_tools_view', 'lesson_library_view', 'model_import', 'model_gallery','model_view','workshop_view', 'profile_tab', 'splash_view', 'onboarding_view','admin_view','moderation_actions','challenge_view','community_notices','contest_picker','admin_permissions','role_editor','report_history','server_connection','personal_notice_settings','personal_data','offline_controls','notification_delivery','learning_catalog','catalog_file_picker')
ASSETS = ('fonts/DejaVuSans.ttf', 'fonts/LICENSE-DejaVu.txt',
          *(f'lessons/lesson_{index}.svg' for index in range(1, 7)),*MODEL_ASSETS,*STEP_ASSETS)

NATIVE_FILES=('pubspec.yaml','lib/lepka_platform.dart','android/build.gradle','android/src/main/AndroidManifest.xml',
    'android/src/main/java/ru/gr1zle/lepka_platform/LepkaPlatformPlugin.java','android/src/main/java/ru/gr1zle/lepka_platform/Notifications.java')


def nativeWheel(output):
    """A normal Flet extension wheel survives a cold dependency rebuild."""
    files={'flutter/lepka_platform/'+name:(ROOT/'native/lepka_platform'/name).read_bytes() for name in NATIVE_FILES}
    digest=hashlib.sha256(b''.join(name.encode()+files[name] for name in sorted(files))).hexdigest()[:12]
    version='0.1.0+'+digest;metadata='lepka_platform-'+version+'.dist-info'
    files['lepka_platform/__init__.py']=b''
    files[metadata+'/METADATA']=f'Metadata-Version: 2.1\nName: lepka-platform\nVersion: {version}\nRequires-Python: >=3.12\nRequires-Dist: flet==0.28.3\n'.encode()
    files[metadata+'/WHEEL']=b'Wheel-Version: 1.0\nGenerator: lepka-prepare-android\nRoot-Is-Purelib: true\nTag: py3-none-any\n'
    record=StringIO();writer=csv.writer(record,lineterminator='\n')
    for name,content in sorted(files.items()):writer.writerow([name,'sha256='+base64.urlsafe_b64encode(hashlib.sha256(content).digest()).decode().rstrip('='),len(content)])
    writer.writerow([metadata+'/RECORD','','']);files[metadata+'/RECORD']=record.getvalue().encode()
    wheel=output/'build'/f'lepka_platform-{version}-py3-none-any.whl';wheel.parent.mkdir(parents=True,exist_ok=True)
    with ZipFile(wheel,'x',ZIP_DEFLATED) as archive:
        for name,content in sorted(files.items()):archive.writestr(name,content)
    return wheel


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
    wheel=nativeWheel(output)
    for name in NATIVE_FILES:
        target=output/'build'/'flutter-packages'/'lepka_platform'/name
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(ROOT/'native'/'lepka_platform'/name,target)
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
        'flet==0.28.3\nflet-video==0.1.1\nrequests==2.32.3\nPillow==12.3.0\nstarlette==0.46.2\n', encoding='utf-8')
    (output / 'pyproject.toml').write_text(('''[project]
name = "lepka-helper"
version = "APP_VERSION_PLACEHOLDER"
description = "Помощник по лепке"
requires-python = ">=3.12"
dependencies = DEPS_PLACEHOLDER

[tool.flet]
org = "ru.gr1zle"
product = "Помощник по лепке"

[tool.flet.android]
split_per_abi = true
target_arch = ["arm64-v8a"]
min_sdk_version = 28

[tool.flet.android.permission]
"android.permission.INTERNET" = true

[tool.flet.flutter]
build_args = ["--target-platform=android-arm64"]

# Compatible with Flutter 3.29 / Android SDK 35; avoid unbounded native upgrades.
[tool.flet.flutter.pubspec.dependency_overrides]
media_kit = "1.2.0"
media_kit_video = "1.3.0"
media_kit_libs_video = "1.0.5"
media_kit_libs_android_video = "1.3.7"
screen_brightness_android = "2.1.2"
''').replace('APP_VERSION_PLACEHOLDER', APP_VERSION).replace('DEPS_PLACEHOLDER',json.dumps([
    'flet==0.28.3','flet-video==0.1.1','requests==2.32.3','Pillow==12.3.0','starlette==0.46.2',
    'lepka-platform @ '+wheel.as_uri()])), encoding='utf-8')
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
