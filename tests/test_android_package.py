"""Проверка состава папки APK до запуска внешних инструментов сборки."""
import ast
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import prepare_android as android


class AndroidPackageTests(unittest.TestCase):
    def test_local_demo_is_explicit_and_does_not_include_an_api_address(self):
        with tempfile.TemporaryDirectory() as folder:
            output = android.prepareAndroid(Path(folder) / 'demo', localDemo=True)
            entrypoint = (output / 'main.py').read_text(encoding='utf-8')
            self.assertIn('os.environ["LEPKA_FORCE_LOCAL"] = "1"', entrypoint)
            self.assertLess(entrypoint.index('LEPKA_FORCE_LOCAL'), entrypoint.index('from app_main'))
            self.assertEqual(json.loads((output / 'assets/client_config.json').read_text()),
                             {'apiBaseUrl': ''})
            with self.assertRaises(ValueError):
                android.prepareAndroid(Path(folder) / 'conflict', 'https://api.example.com', True)

    def test_real_client_staging_has_native_entrypoint_and_no_server_or_data(self):
        with tempfile.TemporaryDirectory() as folder:
            output = android.prepareAndroid(Path(folder) / 'client', 'https://api.example.com')
            for source in output.rglob('*.py'):
                ast.parse(source.read_text(encoding='utf-8'))
            self.assertIn('ft.app(target=main', (output / 'main.py').read_text(encoding='utf-8'))
            self.assertIn('from app_main import main', (output / 'main.py').read_text(encoding='utf-8'))
            self.assertFalse((output / 'backend').exists())
            self.assertFalse(any(output.rglob('*.db')))
            self.assertFalse(any(output.rglob('.env*')))
            self.assertEqual(json.loads((output / 'assets/client_config.json').read_text()),
                             {'apiBaseUrl': 'https://api.example.com'})
            self.assertNotIn('fastapi', (output / 'requirements.txt').read_text())
            self.assertTrue((output / 'assets/fonts/DejaVuSans.ttf').is_file())
            self.assertIn('min_sdk_version = 28', (output / 'pyproject.toml').read_text(encoding='utf-8'))
            self.assertIn('--target-platform=android-arm64', (output / 'pyproject.toml').read_text(encoding='utf-8'))
            with self.assertRaises(FileExistsError):
                android.prepareAndroid(output)

    def test_whitelist_ignores_unlisted_files_and_environment_secrets(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / 'source'
            root.mkdir()
            (root / 'views').mkdir()
            (root / 'assets/fonts').mkdir(parents=True)
            (root / 'assets/lessons').mkdir()
            for name in (*android.MODULES, 'main'):
                (root / (name + '.py')).write_text('# safe source\n')
            for name in android.VIEWS:
                (root / 'views' / (name + '.py')).write_text('# safe view\n')
            for name in android.ASSETS:
                (root / 'assets' / name).write_bytes(b'asset')
            for name in ('.env', 'personal.db', 'extra.py', 'assets/fonts/private.txt'):
                (root / name).write_text('PRIVATE_SENTINEL')
            with patch.object(android, 'ROOT', root), patch.dict('os.environ', {'LEPKA_MAIL_API_KEY': 'PRIVATE_SENTINEL'}):
                output = android.prepareAndroid(Path(folder) / 'stage', '')
            for file in output.rglob('*'):
                if file.is_file():
                    self.assertNotIn(b'PRIVATE_SENTINEL', file.read_bytes())

    def test_invalid_api_urls_and_source_paths_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            for url in ('http://127.0.0.1:8000', 'https://user:password@example.com',
                        'https://example.com?key=secret', 'https://example.com#token'):
                with self.subTest(url=url), self.assertRaises(ValueError):
                    android.prepareAndroid(Path(folder) / 'stage', url)
        with self.assertRaises(ValueError):
            android.prepareAndroid(android.ROOT / 'build/android')
