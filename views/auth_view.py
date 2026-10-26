import random
import flet as ft

from auth_service import changePasswordByEmail, loginUser, registerUser
from profile_service import getUserProfile
from validators import validateEmail

PRIMARY_COLOR = "#FF6B6B"
SECONDARY_COLOR = "#4ECDC4"


def createAuthView(page):
    recoveryCodeState = {"email": "", "code": ""}

    loginEmailField = ft.TextField(label="Email", value="test@email.com", prefix_icon=ft.Icons.EMAIL, keyboard_type=ft.KeyboardType.EMAIL, border_radius=12)
    loginPasswordField = ft.TextField(label="Пароль", value="Test123456", prefix_icon=ft.Icons.LOCK, password=True, can_reveal_password=True, border_radius=12)
    rememberMeSwitch = ft.Switch(label="Запомнить меня", value=True)

    registerEmailField = ft.TextField(label="Email", prefix_icon=ft.Icons.EMAIL, keyboard_type=ft.KeyboardType.EMAIL, border_radius=12)
    registerNicknameField = ft.TextField(label="Никнейм", prefix_icon=ft.Icons.PERSON, border_radius=12)
    registerPasswordField = ft.TextField(label="Пароль", prefix_icon=ft.Icons.LOCK, password=True, can_reveal_password=True, border_radius=12)
    registerPasswordConfirmationField = ft.TextField(label="Подтверждение пароля", prefix_icon=ft.Icons.LOCK_OUTLINE, password=True, can_reveal_password=True, border_radius=12)
    policyCheckbox = ft.Checkbox(value=False)
    policyRow = ft.Row(
        controls=[policyCheckbox, ft.Text("Я согласен с политикой конфиденциальности", size=13, expand=True)],
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )

    activeFormContainer = ft.Container(width=360, alignment=ft.alignment.center)

    def showMessage(messageText, isError=False):
        page.snack_bar = ft.SnackBar(
            content=ft.Text(messageText),
            bgcolor=ft.Colors.RED_400 if isError else ft.Colors.GREEN_400,
        )
        page.snack_bar.open = True
        page.update()

    def clearLoginErrors():
        loginEmailField.error_text = None
        loginPasswordField.error_text = None

    def clearRegisterErrors():
        registerEmailField.error_text = None
        registerNicknameField.error_text = None
        registerPasswordField.error_text = None
        registerPasswordConfirmationField.error_text = None

    def handleLogin(event):
        clearLoginErrors()
        successStatus, messageText, userData = loginUser(loginEmailField.value, loginPasswordField.value)
        if not successStatus:
            showMessage(messageText, True)
            return

        page.session.set("currentUser", userData)
        profileData = getUserProfile(userData["userId"])
        page.theme_mode = ft.ThemeMode.DARK if profileData and profileData["themeMode"] == "dark" else ft.ThemeMode.LIGHT
        showMessage(messageText)
        page.go("/home")

    def handleRegister(event):
        clearRegisterErrors()
        successStatus, messageText, userData = registerUser(
            registerEmailField.value,
            registerPasswordField.value,
            registerPasswordConfirmationField.value,
            registerNicknameField.value,
            policyCheckbox.value,
        )
        if not successStatus:
            showMessage(messageText, True)
            return

        page.session.set("currentUser", userData)
        page.theme_mode = ft.ThemeMode.LIGHT
        showMessage("Регистрация успешна. Email подтверждён в демонстрационном режиме.")
        page.go("/home")

    def handleGoogleStub(event):
        showMessage("Google-вход отмечен в ТЗ. В курсовом MVP показан как демонстрационная кнопка.", True)

    def closeDialog(event=None):
        if page.dialog:
            page.dialog.open = False
            page.update()

    def openPasswordRecoveryDialog(event):
        emailField = ft.TextField(label="Email аккаунта", value=loginEmailField.value or "", prefix_icon=ft.Icons.EMAIL, border_radius=12)
        codeField = ft.TextField(label="Код из письма", hint_text="6 цифр", prefix_icon=ft.Icons.PIN, border_radius=12)
        newPasswordField = ft.TextField(label="Новый пароль", password=True, can_reveal_password=True, prefix_icon=ft.Icons.LOCK, border_radius=12)
        confirmPasswordField = ft.TextField(label="Повторите новый пароль", password=True, can_reveal_password=True, prefix_icon=ft.Icons.LOCK_OUTLINE, border_radius=12)
        infoText = ft.Text("Введите email и нажмите «Получить код». Для курсовой код показывается прямо в сообщении.", size=13, color=ft.Colors.GREY_600)

        def sendRecoveryCode(event):
            emailValue = (emailField.value or "").strip().lower()
            emailError = validateEmail(emailValue)
            if emailError:
                emailField.error_text = emailError
                dialog.update()
                return

            recoveryCodeState["email"] = emailValue
            recoveryCodeState["code"] = str(random.randint(100000, 999999))
            emailField.error_text = None
            infoText.value = f"Демонстрационное письмо отправлено. Код: {recoveryCodeState['code']}"
            dialog.update()

        def resetPassword(event):
            emailValue = (emailField.value or "").strip().lower()
            enteredCode = (codeField.value or "").strip()

            if emailValue != recoveryCodeState["email"] or enteredCode != recoveryCodeState["code"]:
                showMessage("Неверный email или код восстановления", True)
                return

            successStatus, messageText = changePasswordByEmail(emailValue, newPasswordField.value, confirmPasswordField.value)
            if not successStatus:
                showMessage(messageText, True)
                return

            closeDialog()
            loginEmailField.value = emailValue
            loginPasswordField.value = ""
            showMessage(messageText)

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Восстановление пароля"),
            content=ft.Container(
                width=340,
                content=ft.Column(
                    tight=True,
                    controls=[
                        infoText,
                        emailField,
                        ft.OutlinedButton(text="Получить код", icon=ft.Icons.MAIL, on_click=sendRecoveryCode),
                        codeField,
                        newPasswordField,
                        confirmPasswordField,
                    ],
                    spacing=10,
                ),
            ),
            actions=[
                ft.TextButton(text="Отмена", on_click=closeDialog),
                ft.ElevatedButton(text="Сменить пароль", on_click=resetPassword),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        page.dialog = dialog
        dialog.open = True
        page.update()

    loginForm = ft.Container(
        width=350,
        alignment=ft.alignment.center,
        padding=ft.padding.symmetric(horizontal=15, vertical=20),
        content=ft.Column(
            controls=[
                loginEmailField,
                loginPasswordField,
                rememberMeSwitch,
                ft.TextButton(text="Заполнить тестовые данные", icon=ft.Icons.BOLT, on_click=lambda e: (setattr(loginEmailField, "value", "test@email.com"), setattr(loginPasswordField, "value", "Test123456"), page.update())),
                ft.ElevatedButton(
                    text="Войти",
                    icon=ft.Icons.LOGIN,
                    height=48,
                    width=320,
                    style=ft.ButtonStyle(bgcolor=PRIMARY_COLOR, color=ft.Colors.WHITE, shape=ft.RoundedRectangleBorder(radius=12)),
                    on_click=handleLogin,
                ),
                ft.OutlinedButton(text="Войти через Google", icon=ft.Icons.LOGIN, height=48, width=320, on_click=handleGoogleStub),
                ft.TextButton(text="Забыли пароль?", on_click=openPasswordRecoveryDialog),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=12,
        ),
    )

    registerForm = ft.Container(
        width=350,
        alignment=ft.alignment.center,
        padding=ft.padding.symmetric(horizontal=15, vertical=20),
        content=ft.Column(
            controls=[
                registerEmailField,
                registerNicknameField,
                registerPasswordField,
                registerPasswordConfirmationField,
                policyRow,
                ft.ElevatedButton(
                    text="Зарегистрироваться",
                    icon=ft.Icons.PERSON_ADD,
                    height=48,
                    width=320,
                    style=ft.ButtonStyle(bgcolor=SECONDARY_COLOR, color=ft.Colors.WHITE, shape=ft.RoundedRectangleBorder(radius=12)),
                    on_click=handleRegister,
                ),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=12,
        ),
    )

    def handleAuthTabChange(event):
        activeFormContainer.content = loginForm if authTabs.selected_index == 0 else registerForm
        activeFormContainer.update()

    authTabs = ft.Tabs(
        selected_index=0,
        animation_duration=250,
        on_change=handleAuthTabChange,
        tabs=[ft.Tab(text="Вход"), ft.Tab(text="Регистрация")],
        expand=False,
        tab_alignment=ft.TabAlignment.CENTER,
        indicator_color=PRIMARY_COLOR,
        label_color=PRIMARY_COLOR,
        unselected_label_color=ft.Colors.BLACK87,
    )
    activeFormContainer.content = loginForm

    return ft.View(
        route="/auth",
        padding=0,
        controls=[
            ft.SafeArea(
                expand=True,
                content=ft.Container(
                    expand=True,
                    padding=ft.padding.symmetric(horizontal=20, vertical=18),
                    alignment=ft.alignment.top_center,
                    content=ft.Column(
                        width=360,
                        expand=True,
                        scroll=ft.ScrollMode.AUTO,
                        controls=[
                            ft.Container(height=28),
                            ft.Column(
                                controls=[
                                    ft.Icon(name=ft.Icons.BRUSH, size=58, color=PRIMARY_COLOR),
                                    ft.Text("Lepka Helper", size=30, weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER),
                                    ft.Text("Помощник для лепки", size=17, color=ft.Colors.GREY_600, text_align=ft.TextAlign.CENTER),
                                ],
                                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                                spacing=6,
                            ),
                            ft.Container(height=28),
                            ft.Container(width=360, alignment=ft.alignment.center, content=authTabs),
                            activeFormContainer,
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=0,
                    ),
                ),
            )
        ],
    )
