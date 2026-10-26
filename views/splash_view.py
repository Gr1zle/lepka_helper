import asyncio
import flet as ft
from app_state import getAppState

APP_TITLE = "Lepka Helper"
APP_VERSION = "Версия 1.0.2"
PRIMARY_COLOR = "#FF6B6B"
SECONDARY_COLOR = "#4ECDC4"


def createSplashView(page):
    """Начальная заставка без блокирующего client_storage.get()."""

    async def redirectAfterDelay():
        await asyncio.sleep(1.2)

        if page.route != "/":
            return

        currentUser = page.session.get("currentUser")
        if currentUser is not None:
            page.go("/home")
            return

        isOnboardingCompleted = getAppState("isOnboardingCompleted", False)
        page.go("/auth" if isOnboardingCompleted else "/onboarding")

    page.run_task(redirectAfterDelay)

    logoBlock = ft.Container(
        width=122,
        height=122,
        border_radius=36,
        bgcolor=PRIMARY_COLOR,
        alignment=ft.alignment.center,
        shadow=ft.BoxShadow(
            blur_radius=24,
            spread_radius=1,
            color=ft.Colors.with_opacity(0.24, ft.Colors.BLACK),
            offset=ft.Offset(0, 8),
        ),
        content=ft.Icon(name=ft.Icons.BRUSH, size=68, color=ft.Colors.WHITE),
    )

    centerContent = ft.Column(
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        alignment=ft.MainAxisAlignment.CENTER,
        spacing=18,
        controls=[
            logoBlock,
            ft.Column(
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=6,
                controls=[
                    ft.Text(APP_TITLE, size=34, weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER),
                    ft.Text(
                        "Мобильный помощник для лепки из пластилина",
                        size=15,
                        text_align=ft.TextAlign.CENTER,
                        color=ft.Colors.GREY_700,
                    ),
                ],
            ),
            ft.ProgressRing(width=34, height=34, stroke_width=3, color=SECONDARY_COLOR),
        ],
    )

    return ft.View(
        route="/",
        padding=0,
        spacing=0,
        controls=[
            ft.Container(
                expand=True,
                gradient=ft.LinearGradient(
                    begin=ft.alignment.top_left,
                    end=ft.alignment.bottom_right,
                    colors=["#FFF6F6", "#FFFFFF", "#EFFFFD"],
                ),
                content=ft.SafeArea(
                    expand=True,
                    content=ft.Stack(
                        expand=True,
                        controls=[
                            ft.Container(
                                expand=True,
                                alignment=ft.alignment.center,
                                padding=ft.padding.symmetric(horizontal=30),
                                content=centerContent,
                            ),
                            ft.Container(
                                expand=True,
                                alignment=ft.alignment.bottom_center,
                                padding=ft.padding.only(bottom=22),
                                content=ft.Text(
                                    APP_VERSION,
                                    size=12,
                                    color=ft.Colors.GREY_600,
                                    text_align=ft.TextAlign.CENTER,
                                ),
                            ),
                        ],
                    ),
                ),
            )
        ],
    )
