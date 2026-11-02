from localization import tr, term, message as translateMessage
import flet as ft

from account_gateway import (changePasswordByEmail, loginUser, registerUser,
                          requestPasswordRecovery, requestRegistrationCode)
from account_gateway import confirmRegistration, logoutUser
from api_client import getApiUrl
from ui_helpers import serverAction, showMessage as showPageMessage
from account_gateway import getUserProfile
from validators import validateEmail, validateNickname, validatePassword, validatePasswordConfirmation
from app_info import APP_TITLE
from views.about_dialog import showDataInfo
from device_session import saveDeviceSession

from design_system import PRIMARY_COLOR
from design_system import SECONDARY_COLOR


def createAuthView(page):
    dialog = None
    remoteMode = bool(getApiUrl())
    from device_session import nativeClient
    rememberSession=ft.Switch(label=tr(page, 'Запомнить вход на этом устройстве'),value=True,visible=nativeClient(page))
    from views.server_connection import openServerConnection

    loginEmailField = ft.TextField(label="Email", value="" if remoteMode else "test@email.com", prefix_icon=ft.Icons.EMAIL, keyboard_type=ft.KeyboardType.EMAIL, border_radius=12)
    loginPasswordField = ft.TextField(label=tr(page, 'Пароль'), value="" if remoteMode else "Test123456", prefix_icon=ft.Icons.LOCK, password=True, can_reveal_password=True, border_radius=12)

    registerEmailField = ft.TextField(label="Email", prefix_icon=ft.Icons.EMAIL, keyboard_type=ft.KeyboardType.EMAIL, border_radius=12)
    registerNicknameField = ft.TextField(label=tr(page, 'Никнейм'), prefix_icon=ft.Icons.PERSON, border_radius=12)
    registerPasswordField = ft.TextField(label=tr(page, 'Пароль'), prefix_icon=ft.Icons.LOCK, password=True, can_reveal_password=True, border_radius=12)
    registerPasswordConfirmationField = ft.TextField(label=tr(page, 'Подтверждение пароля'), prefix_icon=ft.Icons.LOCK_OUTLINE, password=True, can_reveal_password=True, border_radius=12)
    policyCheckbox = ft.Checkbox(value=False, on_change=lambda event: page.update())
    policyRow = ft.Row(
        controls=[policyCheckbox, ft.Text(tr(page, 'Я согласен с условиями использования и обработки данных'), size=13, expand=True)],
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )

    activeFormContainer = ft.Container(width=360, alignment=ft.alignment.center)

    def showMessage(messageText, isError=False):
        showPageMessage(page, messageText, isError)

    def clearLoginErrors():
        loginEmailField.error_text = None
        loginPasswordField.error_text = None

    def clearRegisterErrors():
        registerEmailField.error_text = None
        registerNicknameField.error_text = None
        registerPasswordField.error_text = None
        registerPasswordConfirmationField.error_text = None

    @serverAction(page)
    def handleLogin(event):
        clearLoginErrors()
        loginEmailField.error_text = validateEmail((loginEmailField.value or '').strip().lower())
        loginPasswordField.error_text = None if loginPasswordField.value else tr(page, 'Введите пароль')
        if loginEmailField.error_text or loginPasswordField.error_text:
            page.update()
            return
        successStatus, messageText, userData = loginUser(loginEmailField.value, loginPasswordField.value)
        if not successStatus:
            showMessage(messageText, True)
            return

        previousUser = page.session.get("currentUser") or {}
        logoutUser(previousUser.get("sessionToken"))
        page.session.set("currentUser", userData)
        profileData = getUserProfile(userData["userId"], userData.get("sessionToken"))
        from localization import setLanguage
        if profileData:setLanguage(page,profileData.get('languageCode','ru'))
        page.theme_mode = ft.ThemeMode.DARK if profileData and profileData["themeMode"] == "dark" else ft.ThemeMode.LIGHT
        sessionSaved = saveDeviceSession(page, userData,rememberSession.value)
        showMessage(messageText)
        page.go("/home")
        if not sessionSaved:
            showMessage(tr(page, 'Вход выполнен, но сохранить его для перезапуска не удалось'), True)

    @serverAction(page)
    def handleRegister(event):
        clearRegisterErrors()
        fieldErrors = [
            (registerEmailField, validateEmail((registerEmailField.value or '').strip().lower())),
            (registerNicknameField, validateNickname((registerNicknameField.value or '').strip())),
            (registerPasswordField, validatePassword(registerPasswordField.value)),
            (registerPasswordConfirmationField, validatePasswordConfirmation(
                registerPasswordField.value, registerPasswordConfirmationField.value)),
        ]
        for field, error in fieldErrors:
            field.error_text = error
        if any(error for field, error in fieldErrors):
            page.update()
            return
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

        openRegistrationDialog(email=userData['email'])

    def openRegistrationDialog(event=None, email=None):
        nonlocal dialog
        emailField = ft.TextField(label=tr(page, 'Email аккаунта'), value=email or loginEmailField.value or '')
        codeField = ft.TextField(label=tr(page, 'Код из письма'), hint_text=tr(page, '6 цифр'))

        def sendCode(event=None):
            success, message = requestRegistrationCode(emailField.value)
            showMessage(message, not success)

        def confirmCode(event):
            success, message = confirmRegistration(emailField.value, codeField.value)
            if success:
                loginEmailField.value = emailField.value
                loginPasswordField.value = ''
                closeDialog()
            showMessage(message, not success)

        dialog = ft.AlertDialog(
            modal=True, title=ft.Text(tr(page, 'Подтверждение регистрации')),
            content=ft.Column(tight=True, controls=[
                ft.Text(tr(page, 'Код действует 24 часа. Вход станет доступен после подтверждения почты.')),
                emailField, ft.OutlinedButton(text=tr(page, 'Получить код'), on_click=sendCode), codeField]),
            actions=[ft.TextButton(text=tr(page, 'Отмена'), on_click=closeDialog),
                     ft.ElevatedButton(text=tr(page, 'Подтвердить email'), on_click=confirmCode)],
        )
        page.open(dialog)
        if email:
            sendCode()

    def closeDialog(event=None):
        if dialog is not None:
            page.close(dialog)

    def openPasswordRecoveryDialog(event):
        nonlocal dialog
        emailField = ft.TextField(label=tr(page, 'Email аккаунта'), value=loginEmailField.value or "", prefix_icon=ft.Icons.EMAIL, border_radius=12)
        codeField = ft.TextField(label=tr(page, 'Код из письма'), hint_text=tr(page, '6 цифр'), prefix_icon=ft.Icons.PIN, border_radius=12)
        newPasswordField = ft.TextField(label=tr(page, 'Новый пароль'), password=True, can_reveal_password=True, prefix_icon=ft.Icons.LOCK, border_radius=12)
        confirmPasswordField = ft.TextField(label=tr(page, 'Повторите новый пароль'), password=True, can_reveal_password=True, prefix_icon=ft.Icons.LOCK_OUTLINE, border_radius=12)
        infoText = ft.Text(tr(page, 'Код будет отправлен на почту. Он действует 10 минут; допускается 5 попыток.'), size=13, color=ft.Colors.ON_SURFACE_VARIANT)

        def sendRecoveryCode(event):
            emailValue = (emailField.value or "").strip().lower()
            emailError = validateEmail(emailValue)
            if emailError:
                emailField.error_text = emailError
                dialog.update()
                return

            successStatus, messageText = requestPasswordRecovery(emailValue)
            emailField.error_text = None
            infoText.value = translateMessage(page,messageText)
            dialog.update()
            if not successStatus:
                showMessage(messageText, True)

        def resetPassword(event):
            emailValue = (emailField.value or "").strip().lower()
            enteredCode = (codeField.value or "").strip()

            successStatus, messageText = changePasswordByEmail(
                emailValue, newPasswordField.value, confirmPasswordField.value, enteredCode)
            if not successStatus:
                showMessage(messageText, True)
                return

            closeDialog()
            loginEmailField.value = emailValue
            loginPasswordField.value = ""
            showMessage(messageText)

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(tr(page, 'Восстановление пароля')),
            content=ft.Container(
                width=340,
                content=ft.Column(
                    tight=True,
                    controls=[
                        infoText,
                        emailField,
                        ft.OutlinedButton(text=tr(page, 'Получить код'), icon=ft.Icons.MAIL, on_click=sendRecoveryCode),
                        codeField,
                        newPasswordField,
                        confirmPasswordField,
                    ],
                    spacing=10,
                ),
            ),
            actions=[
                ft.TextButton(text=tr(page, 'Отмена'), on_click=closeDialog),
                ft.ElevatedButton(text=tr(page, 'Сменить пароль'), on_click=resetPassword),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        page.open(dialog)

    loginForm = ft.Container(
        width=350,
        alignment=ft.alignment.center,
        padding=ft.padding.symmetric(horizontal=15, vertical=20),
        content=ft.Column(
            controls=[
                loginEmailField,
                loginPasswordField,
                ft.Text(tr(page, 'Вход через сервер') if remoteMode else tr(page, 'Локальный режим: данные на этом компьютере'), size=12),
                ft.TextButton(text=tr(page, 'Заполнить тестовые данные'), tooltip=tr(page, 'На сервере тестовый аккаунт нужно создать отдельно') if remoteMode else tr(page, 'Тестовый аккаунт на этом компьютере'), icon=ft.Icons.BOLT, on_click=lambda e: (setattr(loginEmailField, "value", "test@email.com"), setattr(loginPasswordField, "value", "Test123456"), page.update())),
                ft.ElevatedButton(
                    text=tr(page, 'Войти'),
                    icon=ft.Icons.LOGIN,
                    height=48,
                    width=320,
                    style=ft.ButtonStyle(bgcolor=PRIMARY_COLOR, color=ft.Colors.WHITE, shape=ft.RoundedRectangleBorder(radius=12)),
                    on_click=handleLogin,
                ),
                ft.TextButton(text=tr(page, 'Забыли пароль?'), on_click=openPasswordRecoveryDialog),
                ft.TextButton(text=tr(page, 'Подтвердить регистрацию'), on_click=openRegistrationDialog),
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
                ft.TextButton(tr(page, 'Условия использования и данные'), on_click=lambda event: showDataInfo(page)),
                ft.ElevatedButton(
                    text=tr(page, 'Зарегистрироваться'),
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

    from localization import language,setLanguage
    def changeLanguage(event):
        setLanguage(page,event.control.value)
        page.go('/auth')
    languagePicker=ft.Dropdown(label=tr(page,'Язык приложения'),value=language(page),width=180,
        options=[ft.dropdown.Option('ru','Русский'),ft.dropdown.Option('en','English')],on_change=changeLanguage)
    authTabs = ft.Tabs(
        selected_index=0,
        animation_duration=250,
        on_change=handleAuthTabChange,
        tabs=[ft.Tab(text=tr(page, 'Вход')), ft.Tab(text=tr(page, 'Регистрация'))],
        expand=False,
        tab_alignment=ft.TabAlignment.CENTER,
        indicator_color=PRIMARY_COLOR,
        label_color=PRIMARY_COLOR,
        unselected_label_color=ft.Colors.ON_SURFACE_VARIANT,
    )
    activeFormContainer.content = loginForm

    from design_system import polish
    return polish(ft.View(
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
                            ft.Container(height=12),
                            ft.Column(
                                controls=[
                                    ft.Image(src="icon.png", width=72, height=72, border_radius=22),
                                    ft.Text(tr(page, APP_TITLE), size=25, weight=ft.FontWeight.W_600, text_align=ft.TextAlign.CENTER),
                                    ft.Text(tr(page, 'От первого оттенка до готовой фигурки'), size=14, color=ft.Colors.ON_SURFACE_VARIANT, text_align=ft.TextAlign.CENTER),
                                ],
                                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                                spacing=6,
                            ),
                            ft.Container(height=12),
                            ft.Container(width=360, alignment=ft.alignment.center, content=authTabs),
                            ft.TextButton(tr(page, 'Подключение к серверу / Wi-Fi'), on_click=lambda e: openServerConnection(page)),
                            languagePicker,
                            rememberSession,
                            activeFormContainer,
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=0,
                    ),
                ),
            )
        ],
    ))
