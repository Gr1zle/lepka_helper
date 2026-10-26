import flet as ft

def createProfileEditView(page: ft.Page):

    currentUser = page.session.get("currentUser")

    nicknameField = ft.TextField(value=currentUser["nickname"], label="Никнейм")
    bioField = ft.TextField(label="О себе", multiline=True)

    ageDropdown = ft.Dropdown(
        label="Возраст",
        options=[
            ft.dropdown.Option("child", "Ребёнок"),
            ft.dropdown.Option("teen", "Подросток"),
            ft.dropdown.Option("adult", "Взрослый"),
        ],
    )

    statusText = ft.Text()

    def saveProfile(e):
        currentUser["nickname"] = nicknameField.value
        page.session.set("currentUser", currentUser)

        statusText.value = "Сохранено"
        statusText.color = ft.colors.GREEN
        page.update()

    return ft.View(
        "/profile/edit",
        controls=[
            ft.Column(
                [
                    ft.Container(height=40),

                    nicknameField,
                    bioField,
                    ageDropdown,

                    ft.ElevatedButton("Сохранить", on_click=saveProfile),

                    statusText,
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                expand=True,
            )
        ],
    )