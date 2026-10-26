import flet as ft

def createProfileView(page: ft.Page):

    currentUser = page.session.get("currentUser")

    def goToEdit(e):
        page.go("/profile/edit")

    return ft.View(
        "/profile",
        controls=[
            ft.Column(
                [
                    ft.Container(height=40),

                    ft.Icon(name=ft.Icons.ACCOUNT_CIRCLE, size=100),

                    ft.Text(currentUser["nickname"], size=20, weight=ft.FontWeight.BOLD),
                    ft.Text(currentUser["email"], size=14, color=ft.Colors.GREY),

                    ft.Container(height=20),

                    ft.ElevatedButton("Редактировать профиль", on_click=goToEdit),

                    ft.Container(height=20),

                    ft.ElevatedButton("Выйти", on_click=lambda e: logout(page)),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                expand=True,
            )
        ],
    )


def logout(page):
    page.session.remove("currentUser")
    page.go("/auth")