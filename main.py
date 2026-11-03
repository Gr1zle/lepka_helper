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
from device_session import restoreDeviceSession,nativeClient
from account_gateway import getUserProfile
from views.model_gallery import createModelGallery
from views.model_view import createModelView
from views.project_planner import createProjectPlanner
from views.admin_view import createAdminView
from views.challenge_view import createChallengeView
from views.reference_gallery import createReferenceGallery
from views.learning_catalog import createCatalogView,createCatalogDetail,createCatalogEditor

from design_system import PRIMARY_COLOR
from design_system import SECONDARY_COLOR


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
    initializeDatabase()
    ensureDemoUser()

    from localization import restoreLanguage,setLanguage,localizeHints
    restoreLanguage(page)
    page.theme_mode = ft.ThemeMode.LIGHT
    if apiUrl and nativeClient(page):
        from secure_device import attachProtectedSession
        attachProtectedSession(page)
    restoredUser = restoreDeviceSession(page)
    if restoredUser:
        page.session.set('currentUser', restoredUser)
        profile = getUserProfile(restoredUser['userId'], restoredUser.get('sessionToken'))
        if profile:setLanguage(page,profile.get('languageCode','ru'))
        if profile and profile.get('themeMode') == 'dark':
            page.theme_mode = ft.ThemeMode.DARK
    page.bgcolor = ft.Colors.SURFACE
    page.window.width = 390
    page.window.height = 780
    page.window.resizable = True
    page.window.min_width = 320
    page.window.min_height = 600
    page.padding = 0
    from design_system import makeTheme
    page.theme = makeTheme()
    page.dark_theme = makeTheme(True)

    originalUpdate=page.update
    def localizedUpdate(*controls):
        for control in (controls or [*page.views,*page.overlay]):localizeHints(page,control)
        return originalUpdate(*controls)
    page.update=localizedUpdate

    # Глобальные настройки
    page.session.set("PRIMARY_COLOR", PRIMARY_COLOR)
    page.session.set("SECONDARY_COLOR", SECONDARY_COLOR)

    from design_system import polish, presentView, resizeLayouts

    def displayViews(views):
        page.views[:] = [presentView(page,view) for view in views]
        page.update()

    @serverAction(page)
    def route_change(e):
        page.session.set('resizeHomeView',None)
        if not page.route.startswith('/models/'):
            page.session.set('resizeModelView',None)
            page.session.set('exitModelFullscreen',None)
        if page.route == "/" or page.route == "":
            view = createSplashView(page)
        elif page.route == "/onboarding":
            view = createOnboardingView(page)
        elif page.route == "/auth":
            view = createAuthView(page)
        elif page.route == "/home":
            returning=page.session.get('modelReturnLesson')
            page.session.set('modelReturnLesson',None)
            if returning:
                page.session.set('openBuiltinLesson',returning)
                page.session.set('homeTab',1)
            view = createHomeView(page)
        elif page.route == '/challenges':
            root=page.views[0] if page.views and page.views[0].route=='/home' else createHomeView(page)
            page.views[:]=[root,createChallengeView(page)]
            displayViews(page.views);return
        elif page.route == '/admin':
            root=page.views[0] if page.views and page.views[0].route=='/home' else createHomeView(page)
            page.views[:]=[root,createAdminView(page)]
            displayViews(page.views);return
        elif page.route == '/planner':
            root=page.views[0] if page.views and page.views[0].route=='/home' else createHomeView(page)
            page.views[:]=[root,createProjectPlanner(page)]
            displayViews(page.views);return
        elif page.route in ('/catalog','/catalog-admin') or page.route.startswith(('/catalog/','/catalog-edit/')):
            root=page.views[0] if page.views and page.views[0].route=='/home' else createHomeView(page)
            if page.route=='/catalog':catalogView=createCatalogView(page)
            elif page.route=='/catalog-admin':catalogView=createCatalogView(page,True)
            elif page.route.startswith('/catalog-edit/'):catalogView=createCatalogEditor(page,page.route[len('/catalog-edit/'):])
            else:catalogView=createCatalogDetail(page,page.route[len('/catalog/'):])
            page.views[:]=[root,catalogView];displayViews(page.views);return
        elif page.route == '/references':
            root=page.views[0] if page.views and page.views[0].route=='/home' else createHomeView(page)
            page.views[:]=[root,createReferenceGallery(page)];displayViews(page.views);return
        elif page.route == '/models':
            root=page.views[0] if page.views and page.views[0].route=='/home' else createHomeView(page)
            page.views[:]=[root,createModelGallery(page)]
            displayViews(page.views);return
        elif page.route.startswith('/models/'):
            root=page.views[0] if page.views and page.views[0].route=='/home' else createHomeView(page)
            parents=[root]
            if page.views and page.views[-1].route=='/models':parents.append(page.views[-1])
            if page.views and (page.views[-1].route or '').startswith('/catalog/'):parents.append(page.views[-1])
            page.views[:]=[*parents,createModelView(page,page.route[len('/models/'):])]
            displayViews(page.views);return
        else:
            page.go("/")
            return

        page.views[:] = [presentView(page,view)]
        page.update()

    def view_pop(e):
        exitFull=page.session.get('exitModelFullscreen')
        if callable(exitFull) and exitFull():return
        if len(page.views)>1 and page.views[-1].route.startswith('/models'):
            page.go(page.views[-2].route)
            return
        if len(page.views) > 1:
            removedView = page.views.pop()
            if removedView.route.startswith(('/workshop/','/discovery/')):
                page.update()  # Сохраняем вкладку поиска, фильтры и позицию ленты.
            else:
                page.go(page.views[-1].route)

    page.on_route_change = route_change
    page.on_view_pop = view_pop
    def resizeModel(event):
        resizeLayouts(page)
        callback=page.session.get('resizeHomeView')
        if callable(callback):callback(event)
        callback=page.session.get('resizeModelView')
        if callable(callback):callback(event)
    page.on_resized = resizeModel
    from connection_monitor import startConnectionMonitor
    startConnectionMonitor(page)
    from device_notifications import startNotificationMonitor
    startNotificationMonitor(page)
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
