import flet as ft
import asyncio

from database import initializeDatabase
from auth_service import ensureDemoUser
from views.splash_view import createSplashView
from views.onboarding_view import createOnboardingView
from views.auth_view import createAuthView
from views.home_view import createHomeView

APP_TITLE = "Lepka Helper"
PRIMARY_COLOR = "#FF6B6B"
SECONDARY_COLOR = "#4ECDC4"


def main(page: ft.Page):
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

    def route_change(e):
        page.views.clear()

        if page.route == "/" or page.route == "":
            page.views.append(createSplashView(page))
        elif page.route == "/onboarding":
            page.views.append(createOnboardingView(page))
        elif page.route == "/auth":
            page.views.append(createAuthView(page))
        elif page.route == "/home":
            page.views.append(createHomeView(page))
        else:
            page.go("/")

        page.update()

    def view_pop(e):
        if len(page.views) > 1:
            page.views.pop()
            page.go(page.views[-1].route)

    page.on_route_change = route_change
    page.on_view_pop = view_pop
    page.go("/")


if __name__ == "__main__":
    ft.app(target=main, view=ft.AppView.WEB_BROWSER)  # для теста, потом поменяешь на FLET_APP