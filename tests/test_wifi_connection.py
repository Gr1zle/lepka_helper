import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import api_client
import app_paths


class WifiConnectionTests(unittest.TestCase):
    def test_http_requires_explicit_permission_and_private_literal(self):
        with patch.dict('os.environ', {'LEPKA_ALLOW_LOCAL_API': '0'}):
            for address in ('http://192.168.1.2:8000', 'http://10.1.2.3', 'http://172.20.1.2'):
                with self.assertRaises(api_client.ApiError): api_client.validateApiUrl(address)
                self.assertEqual(api_client.validateApiUrl(address, True), address)
            for address in ('http://8.8.8.8', 'http://example.com', 'http://169.254.169.254',
                            'http://192.168.1.1@evil.com', 'http://192.168.1.1:bad',
                            'http://192.168.1.1/x', 'http://192.168.1.1?token=secret'):
                with self.assertRaises(api_client.ApiError): api_client.validateApiUrl(address, True)

    def test_saved_connection_overrides_demo_and_environment_without_modifying_bundle(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(app_paths, 'DATA_DIRECTORY', Path(folder)), patch.dict(
                'os.environ', {'LEPKA_FORCE_LOCAL': '1', 'LEPKA_API_URL': 'https://example.invalid'}):
            config = Path(folder) / 'server_connection.json'
            config.write_text(json.dumps({'apiBaseUrl': 'http://192.168.1.2:8000', 'allowLan': True}))
            self.assertEqual(api_client.getApiUrl(), 'http://192.168.1.2:8000')
            config.write_text(json.dumps({'apiBaseUrl': '', 'allowLan': False}))
            self.assertEqual(api_client.getApiUrl(), '')

    def test_lan_requests_ignore_proxy_and_do_not_redirect(self):
        with patch('api_client.getApiUrl', return_value='http://192.168.1.2:8000'), patch('api_client.requests.Session') as factory, patch('api_client._transports', type('Pool', (), {})()):
            session = factory.return_value
            session.request.return_value.status_code = 200
            session.request.return_value.json.return_value = {'data': {'ok': True}}
            self.assertEqual(api_client.apiRequest('GET', '/health'), {'data': {'ok': True}})
            self.assertFalse(session.trust_env)
            self.assertFalse(session.request.call_args.kwargs['allow_redirects'])

    def test_lan_pool_reuses_same_thread_address_without_saving_authorization(self):
        with patch('api_client.requests.Session') as factory, patch('api_client._transports', type('Pool', (), {})()):
            from api_client import lanTransport
            first=lanTransport('http://192.168.1.2:8000')
            self.assertIs(lanTransport('http://192.168.1.2:8000'),first)
            factory.assert_called_once()
            lanTransport('http://192.168.1.3:8000')
            first.close.assert_called_once()
            self.assertEqual(factory.call_count,2)


class WifiUiTests(unittest.IsolatedAsyncioTestCase):
    async def test_save_address_and_return_to_local_mode(self):
        import asyncio
        import flet as ft
        from test_startup import MemoryConnection, find
        from views.server_connection import openServerConnection
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as folder, patch.object(app_paths, 'DATA_DIRECTORY', Path(folder)), patch(
                'views.server_connection.DATA_DIRECTORY', Path(folder)), patch.dict('os.environ', {'LEPKA_FORCE_LOCAL': '1'}):
            page = ft.Page(MemoryConnection(), 'wifi-test', asyncio.get_running_loop())
            page.update()
            openServerConnection(page)
            dialog = page.overlay[-1]
            field = find(dialog, ft.TextField, label='Адрес сервера')
            field.value = 'http://192.168.1.2:8000'
            find(dialog, ft.Checkbox).value = True
            find(dialog, ft.TextButton, text='Сохранить').on_click(SimpleNamespace())
            self.assertEqual(api_client.getApiUrl(), field.value)
            self.assertTrue((Path(folder)/'server_connection.json').is_file())
            openServerConnection(page)
            find(page.overlay[-1], ft.TextButton, text='Локальный режим').on_click(SimpleNamespace())
            self.assertEqual(api_client.getApiUrl(), '')
