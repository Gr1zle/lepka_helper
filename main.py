import flet as ft
import argparse
import os
from pathlib import Path

from database import initializeDatabase
from account_gateway import ensureDemoUser
from api_client import ApiError, getApiUrl
from ui_helpers import serverAction
from views.splash_view import createSplashView
from views.onboarding_view import createOnboardingView
from views.auth_view import createAuthView
from views.home_view import createHomeView
from app_info import APP_TITLE

PRIMARY_COLOR = "#FF6B6B"
SECONDARY_COLOR = "#4ECDC4"


def main(page: ft.Page):
    try:
        isAndroid = page.platform == ft.PagePlatform.ANDROID
    except ValueError:
        isAndroid = False  # Транспорт ещё не сообщил платформу.
    try:
        apiUrl = getApiUrl()
    except ApiError as error:
        page.add(ft.Text(str(error)))
        return
    if isAndroid and not apiUrl and os.environ.get('LEPKA_FORCE_LOCAL') != '1':
        page.add(ft.Text('Для Android задайте HTTPS-адрес сервера в assets/client_config.json'))
        return
    initializeDatabase()
    ensureDemoUser()

    page.title = APP_TITLE
    page.theme_mode = ft.ThemeMode.LIGHT
    page.window.width = 390
    page.window.height = 780
    page.window.resizable = False
    page.padding = 0
    page.theme = ft.Theme(color_scheme_seed=PRIMARY_COLOR, visual_density=ft.VisualDensity.COMFORTABLE)
    page.dark_theme = ft.Theme(color_scheme_seed=PRIMARY_COLOR, visual_density=ft.VisualDensity.COMFORTABLE)

    # Глобальные настройки
    page.session.set("PRIMARY_COLOR", PRIMARY_COLOR)
    page.session.set("SECONDARY_COLOR", SECONDARY_COLOR)

    @serverAction(page)
    def route_change(e):
        if page.route == "/" or page.route == "":
            view = createSplashView(page)
        elif page.route == "/onboarding":
            view = createOnboardingView(page)
        elif page.route == "/auth":
            view = createAuthView(page)
        elif page.route == "/home":
            view = createHomeView(page)
        else:
            page.go("/")
            return

        page.views[:] = [view]
        page.update()

    def view_pop(e):
        if len(page.views) > 1:
            removedView = page.views.pop()
            if removedView.route.startswith('/workshop/'):
                page.update()  # Сохраняем вкладку поиска, фильтры и позицию ленты.
            else:
                page.go(page.views[-1].route)

    page.on_route_change = route_change
    page.on_view_pop = view_pop
    page.go("/")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Lepka Helper")
    parser.add_argument("--desktop", action="store_true", help="Открыть отдельное окно")
    parser.add_argument('--local', action='store_true', help='Запустить на ПК без API, с локальным тестовым входом')
    parser.add_argument("--port", type=int, default=8550, help="Порт веб-версии")
    options = parser.parse_args()
    if options.local:
        import os
        os.environ['LEPKA_FORCE_LOCAL'] = '1'
    if options.desktop:
        ft.app(target=main, view=ft.AppView.FLET_APP, host="127.0.0.1", port=options.port,
               assets_dir=str(Path(__file__).resolve().parent / "assets"))
    else:
        import socket
        import threading
        import time
        import webbrowser
        import uvicorn
        from web_app import createWebApp

        def openBrowser():
            for _ in range(100):
                try:
                    with socket.create_connection(('127.0.0.1', options.port), timeout=0.1):
                        webbrowser.open(f'http://127.0.0.1:{options.port}')
                        return
                except OSError:
                    time.sleep(0.05)

        threading.Thread(target=openBrowser, daemon=True).start()
        # Не записываем одноразовые адреса скачивания в access-log.
        uvicorn.run(createWebApp(), host='127.0.0.1', port=options.port, access_log=False)
