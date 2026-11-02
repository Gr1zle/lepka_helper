from localization import tr, term
import flet as ft

def createProfileEditView(page: ft.Page):

    currentUser = page.session.get("currentUser")

    nicknameField = ft.TextField(value=currentUser["nickname"], label=tr(page, 'Никнейм'))
    bioField = ft.TextField(label=tr(page, 'О себе'), multiline=True)

    ageDropdown = ft.Dropdown(
        label=tr(page, 'Возраст'),
        options=[
            ft.dropdown.Option("child", tr(page, 'Ребёнок')),
            ft.dropdown.Option("teen", tr(page, 'Подросток')),
            ft.dropdown.Option("adult", tr(page, 'Взрослый')),
        ],
    )

    statusText = ft.Text()

    def saveProfile(e):
        currentUser["nickname"] = nicknameField.value
        page.session.set("currentUser", currentUser)

        statusText.value = tr(page, 'Сохранено')
        statusText.color = ft.Colors.GREEN
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

                    ft.ElevatedButton(tr(page, 'Сохранить'), on_click=saveProfile),

                    statusText,
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                expand=True,
            )
        ],
    )