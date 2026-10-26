import flet as ft
from app_state import setAppState

PRIMARY_COLOR = "#FF6B6B"
SECONDARY_COLOR = "#4ECDC4"

SLIDES = [
    {
        "icon": ft.Icons.PALETTE,
        "title": "Подбирай цвета",
        "text": "Смешивай 2–5 цветов пластилина, рассчитывай пропорции и сохраняй рецепты.",
    },
    {
        "icon": ft.Icons.VIEW_IN_AR,
        "title": "Изучай идеи",
        "text": "Ищи уроки, 3D-референсы и материалы по категориям: животные, еда, персонажи.",
    },
    {
        "icon": ft.Icons.GROUP,
        "title": "Делись работами",
        "text": "Публикуй готовые поделки, ставь лайки и оставляй комментарии другим пользователям.",
    },
    {
        "icon": ft.Icons.CHECKLIST,
        "title": "Веди проекты",
        "text": "Создавай личные проекты с дедлайнами, этапами и прогрессом выполнения.",
    },
]


def createOnboardingView(page):
    slideIndex = 0
    iconControl = ft.Icon(size=92, color=PRIMARY_COLOR)
    titleControl = ft.Text(size=28, weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER)
    textControl = ft.Text(
        size=15,
        text_align=ft.TextAlign.CENTER,
        color=ft.Colors.GREY_700,
        no_wrap=False,
    )
    dotsRow = ft.Row(alignment=ft.MainAxisAlignment.CENTER, spacing=8)
    backButton = ft.OutlinedButton(text="Назад", height=48, width=130)
    nextButton = ft.ElevatedButton(height=48, width=160)

    def finishOnboarding():
        setAppState("isOnboardingCompleted", True)
        page.go("/auth")

    def updateSlide():
        currentSlide = SLIDES[slideIndex]
        iconControl.name = currentSlide["icon"]
        titleControl.value = currentSlide["title"]
        textControl.value = currentSlide["text"]
        dotsRow.controls.clear()

        for index in range(len(SLIDES)):
            dotsRow.controls.append(
                ft.Container(
                    width=24 if index == slideIndex else 9,
                    height=9,
                    border_radius=5,
                    bgcolor=PRIMARY_COLOR if index == slideIndex else ft.Colors.GREY_300,
                )
            )

        backButton.visible = slideIndex > 0
        nextButton.text = "Начать" if slideIndex == len(SLIDES) - 1 else "Далее"

    def handleNext(event):
        nonlocal slideIndex
        if slideIndex == len(SLIDES) - 1:
            finishOnboarding()
            return
        slideIndex += 1
        updateSlide()
        page.update()

    def handleBack(event):
        nonlocal slideIndex
        if slideIndex > 0:
            slideIndex -= 1
            updateSlide()
            page.update()

    backButton.on_click = handleBack
    nextButton.on_click = handleNext
    nextButton.style = ft.ButtonStyle(
        bgcolor=PRIMARY_COLOR,
        color=ft.Colors.WHITE,
        shape=ft.RoundedRectangleBorder(radius=12),
    )
    updateSlide()

    skipButton = ft.TextButton(
        text="Пропустить",
        on_click=lambda event: finishOnboarding(),
    )

    return ft.View(
        route="/onboarding",
        padding=0,
        controls=[
            ft.SafeArea(
                content=ft.Container(
                    expand=True,
                    padding=ft.padding.only(left=28, right=28, top=16, bottom=22),
                    content=ft.Column(
                        expand=True,
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Row(
                                height=52,
                                alignment=ft.MainAxisAlignment.END,
                                controls=[skipButton],
                            ),
                            ft.Container(
                                expand=True,
                                alignment=ft.alignment.center,
                                content=ft.Column(
                                    width=330,
                                    tight=True,
                                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                                    spacing=18,
                                    controls=[
                                        ft.Container(
                                            width=150,
                                            height=150,
                                            border_radius=45,
                                            bgcolor="#FFF0F0",
                                            alignment=ft.alignment.center,
                                            content=iconControl,
                                        ),
                                        titleControl,
                                        ft.Container(
                                            width=320,
                                            content=textControl,
                                        ),
                                        dotsRow,
                                    ],
                                ),
                            ),
                            ft.Container(
                                height=72,
                                alignment=ft.alignment.center,
                                content=ft.Row(
                                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                    controls=[backButton, nextButton],
                                ),
                            ),
                        ],
                    ),
                )
            )
        ],
    )
