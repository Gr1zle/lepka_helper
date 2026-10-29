"""Профиль, настройки и действия с аккаунтом — отдельно от ленты и инструментов."""
import flet as ft
from api_client import getApiUrl

from account_gateway import (deleteUserAccount, requestEmailChange, confirmEmailChange,
                             getUserProfile, saveUserProfile, saveUserSettings, changeUserPassword, saveUserAvatar, removeUserAvatar)
from photo_picker import createPhotoPicker
from post_service import getCommunityPosts
from views.community_tab import createMyWorksButton
from project_service import getUserProjects
from profile_service import (
    AGE_CATEGORIES, FAVORITE_COLOR_OPTIONS, LANGUAGE_OPTIONS, THEME_OPTIONS,
)
from ui_helpers import authenticatedAction, getCurrentUser, logoutPage, serverAction, isWebClient, showMessage as showPageMessage

PRIMARY_COLOR = "#FF6B6B"
SECONDARY_COLOR = "#4ECDC4"


def createInfoCard(iconName, titleText, descriptionText):
    return ft.Card(
        elevation=2,
        content=ft.Container(
            padding=16,
            border_radius=12,
            content=ft.Row(
                controls=[
                    ft.Container(
                        width=52,
                        height=52,
                        border_radius=26,
                        bgcolor="#FFF0F0",
                        alignment=ft.alignment.center,
                        content=ft.Icon(
                            name=iconName,
                            size=28,
                            color=PRIMARY_COLOR,
                        ),
                    ),
                    ft.Container(
                        expand=True,
                        content=ft.Column(
                            controls=[
                                ft.Text(
                                    titleText,
                                    size=17,
                                    weight=ft.FontWeight.BOLD,
                                ),
                                ft.Text(
                                    descriptionText,
                                    size=13,
                                    color=ft.Colors.GREY_700,
                                ),
                            ],
                            spacing=4,
                        ),
                    ),
                ],
                spacing=14,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        ),
    )

def createProfileTab(page, nickname, email):
    currentUser = getCurrentUser(page)

    if currentUser is None:
        profileData = None
    else:
        profileData = getUserProfile(currentUser["userId"], currentUser.get("sessionToken"))

    if profileData is None:
        profileData = {
            "nickname": nickname,
            "email": email,
            "bioText": "",
            "ageCategory": AGE_CATEGORIES[2],
            "favoriteColors": [],
            "themeMode": "light",
            "languageCode": "ru",
            "notificationsEnabled": True,
            "avatarPath": "",
        }

    legacyAvatarPath = profileData.get("avatarPath", "") or ""
    avatarImage = profileData.get("avatarImage", "") or ""

    userPostsCount = 0
    userLikesCount = 0
    userProjectsCount = 0

    if currentUser is not None:
        userProjectItems = getUserProjects(currentUser["userId"])
        userProjectsCount = len(userProjectItems)

        for postItem in getCommunityPosts():
            if postItem["userId"] == currentUser["userId"]:
                userPostsCount += 1
                userLikesCount += postItem["likesCount"]

    nicknameField = ft.TextField(
        label="Никнейм",
        value=profileData["nickname"],
        prefix_icon=ft.Icons.PERSON,
        border_radius=12,
    )

    bioField = ft.TextField(
        label="О себе",
        value=profileData["bioText"],
        hint_text="Например: люблю лепить животных и персонажей",
        multiline=True,
        min_lines=3,
        max_lines=5,
        border_radius=12,
    )

    ageDropdown = ft.Dropdown(
        label="Возрастная категория",
        value=profileData["ageCategory"],
        border_radius=12,
        options=[
            ft.dropdown.Option(ageCategory)
            for ageCategory in AGE_CATEGORIES
        ],
    )

    currentThemeMode = profileData.get("themeMode", "light")
    currentLanguageCode = profileData.get("languageCode", "ru")
    currentNotificationsEnabled = profileData.get("notificationsEnabled", True)

    themeDropdown = ft.Dropdown(
        label="Тема приложения",
        value=currentThemeMode,
        border_radius=12,
        options=[
            ft.dropdown.Option(
                key=themeItem["value"],
                text=themeItem["name"],
            )
            for themeItem in THEME_OPTIONS
        ],
    )

    languageDropdown = ft.Dropdown(
        label="Язык приложения",
        value=currentLanguageCode,
        border_radius=12,
        options=[
            ft.dropdown.Option(
                key=languageItem["value"],
                text=languageItem["name"],
            )
            for languageItem in LANGUAGE_OPTIONS
        ],
    )

    notificationsSwitch = ft.Switch(
        label="Уведомления",
        value=currentNotificationsEnabled,
    )

    currentPasswordField = ft.TextField(
        label="Текущий пароль",
        password=True,
        can_reveal_password=True,
        prefix_icon=ft.Icons.LOCK,
        border_radius=12,
    )

    newPasswordField = ft.TextField(
        label="Новый пароль",
        password=True,
        can_reveal_password=True,
        prefix_icon=ft.Icons.LOCK_RESET,
        border_radius=12,
    )

    repeatPasswordField = ft.TextField(
        label="Повторите новый пароль",
        password=True,
        can_reveal_password=True,
        prefix_icon=ft.Icons.LOCK_RESET,
        border_radius=12,
    )

    deletePasswordField = ft.TextField(
        label="Пароль для удаления аккаунта",
        password=True,
        can_reveal_password=True,
        prefix_icon=ft.Icons.LOCK,
        border_radius=12,
    )

    favoriteColorCheckboxes = []

    profileNameText = ft.Text(
        profileData["nickname"],
        size=22,
        weight=ft.FontWeight.BOLD,
    )

    profileEmailText = ft.Text(
        profileData["email"],
        size=14,
        color=ft.Colors.GREY_600,
    )

    headerAvatarControl = ft.CircleAvatar(
        radius=42,
        foreground_image_src=None,
        content=ft.Text(
            profileData["nickname"][:1].upper(),
            size=30,
            weight=ft.FontWeight.BOLD,
        ),
        bgcolor=SECONDARY_COLOR,
        color=ft.Colors.WHITE,
    )

    editAvatarControl = ft.CircleAvatar(
        radius=42,
        foreground_image_src=None,
        content=ft.Text(
            profileData["nickname"][:1].upper(),
            size=30,
            weight=ft.FontWeight.BOLD,
        ),
        bgcolor=SECONDARY_COLOR,
        color=ft.Colors.WHITE,
    )

    avatarHintText = ft.Text('Фото сохраняется сразу. Обрезка до круга — по центру, 512 × 512.', size=12)

    def refreshAvatar():
        letter = nicknameField.value[:1].upper() if nicknameField.value else '?'
        legacy = legacyAvatarPath if not isWebClient(page) and not getApiUrl() else None
        for control in (headerAvatarControl, editAvatarControl):
            control.foreground_image_src = legacy if not avatarImage else None
            control.content = (ft.Image(src_base64=avatarImage, width=84, height=84, fit=ft.ImageFit.CONTAIN)
                               if avatarImage else (None if legacy else ft.Text(letter, size=30)))

    def avatarSelected(photo):
        nonlocal avatarImage, legacyAvatarPath
        success, message, updated = saveUserAvatar(currentUser['userId'], photo, currentUser.get('sessionToken'))
        if success:
            avatarImage = updated['avatarImage']
            legacyAvatarPath = ''
            refreshAvatar()
        return success, message

    @authenticatedAction(page, currentUser)
    def handleRemoveAvatar(event):
        nonlocal avatarImage, legacyAvatarPath
        success, message, _ = removeUserAvatar(currentUser['userId'], currentUser.get('sessionToken'))
        if success:
            avatarImage, legacyAvatarPath = '', ''
            refreshAvatar()
        showMessage(message, not success)
        page.update()

    avatarPickerControl = createPhotoPicker(page, currentUser, avatarSelected, 'Выбрать аватар')
    refreshAvatar()

    def showMessage(messageText, isError=False):
        showPageMessage(page, messageText, isError)

    @serverAction(page)
    def handleLogout(event):
        logoutPage(page)

    @authenticatedAction(page, currentUser)
    def handleSaveProfile(event):
        if currentUser is None:
            showMessage("Сначала войдите в аккаунт", True)
            return

        selectedFavoriteColors = []

        for checkboxControl in favoriteColorCheckboxes:
            if checkboxControl.value:
                selectedFavoriteColors.append(checkboxControl.label)

        successStatus, messageText, updatedProfile = saveUserProfile(
            currentUser["userId"],
            nicknameField.value,
            bioField.value,
            ageDropdown.value,
            selectedFavoriteColors,
            '' if getApiUrl() else legacyAvatarPath,
            sessionToken=currentUser.get("sessionToken"),
        )

        if not successStatus:
            showMessage(messageText, True)
            return

        page.session.set(
            "currentUser",
            {
                **currentUser,
                "userId": currentUser["userId"],
                "email": updatedProfile["email"],
                "nickname": updatedProfile["nickname"],
                "roleName": updatedProfile["roleName"],
            },
        )

        profileNameText.value = updatedProfile["nickname"]
        profileEmailText.value = updatedProfile["email"]
        refreshAvatar()
        showMessage(messageText)

    @authenticatedAction(page, currentUser)
    def handleChangeEmail(event):
        emailField = ft.TextField(label='Новый email')
        passwordField = ft.TextField(label='Текущий пароль', password=True, can_reveal_password=True)
        codeField = ft.TextField(label='Код из письма')

        @authenticatedAction(page, currentUser)
        def sendCode(event):
            success, message = requestEmailChange(currentUser['userId'], passwordField.value, emailField.value, currentUser.get("sessionToken"))
            showMessage(message, not success)

        @authenticatedAction(page, currentUser)
        def confirmCode(event):
            success, message = confirmEmailChange(currentUser['userId'], emailField.value, codeField.value, currentUser.get("sessionToken"))
            if success:
                logoutPage(page)
            showMessage(message, not success)

        dialog = ft.AlertDialog(
            modal=True, title=ft.Text('Изменение email'),
            content=ft.Column(tight=True, controls=[emailField, passwordField,
                ft.OutlinedButton(text='Получить код', on_click=sendCode), codeField]),
            actions=[ft.TextButton(text='Отмена', on_click=lambda event: page.close(dialog)),
                     ft.ElevatedButton(text='Подтвердить email', on_click=confirmCode)],
        )
        page.open(dialog)

    @authenticatedAction(page, currentUser)
    def handleChangePassword(event):
        if currentUser is None:
            showMessage("Сначала войдите в аккаунт", True)
            return

        successStatus, messageText = changeUserPassword(
            currentUser["userId"],
            currentPasswordField.value,
            newPasswordField.value,
            repeatPasswordField.value,
            sessionToken=currentUser.get("sessionToken"),
        )

        if not successStatus:
            showMessage(messageText, True)
            return

        currentPasswordField.value = ""
        newPasswordField.value = ""
        repeatPasswordField.value = ""
        logoutPage(page)
        showMessage(messageText)

    @authenticatedAction(page, currentUser)
    def handleSaveSettings(event):
        if currentUser is None:
            showMessage("Сначала войдите в аккаунт", True)
            return

        successStatus, messageText, updatedProfile = saveUserSettings(
            currentUser["userId"],
            themeDropdown.value,
            languageDropdown.value,
            notificationsSwitch.value,
            sessionToken=currentUser.get("sessionToken"),
        )

        if not successStatus:
            showMessage(messageText, True)
            return

        if updatedProfile["themeMode"] == "dark":
            page.theme_mode = ft.ThemeMode.DARK
        else:
            page.theme_mode = ft.ThemeMode.LIGHT

        showMessage(messageText)
        page.go("/home")

    @authenticatedAction(page, currentUser)
    def handleDeleteAccount(event):
        if currentUser is None:
            showMessage("Сначала войдите в аккаунт", True)
            return

        if not deletePasswordField.value:
            showMessage("Введите пароль для подтверждения", True)
            return

        def closeDialog(event):
            page.close(confirmDialog)

        @authenticatedAction(page, currentUser)
        def confirmDelete(event):
            successStatus, messageText = deleteUserAccount(
                currentUser["userId"],
                deletePasswordField.value,
                sessionToken=currentUser.get("sessionToken"),
            )

            page.close(confirmDialog)

            if not successStatus:
                showMessage(messageText, True)
                return

            logoutPage(page)
            showMessage(messageText)

        confirmDialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Удаление аккаунта"),
            content=ft.Text(
                "Все ваши данные, публикации, проекты, комментарии и цветовые смеси "
                "будут безвозвратно удалены. Продолжить?"
            ),
            actions=[
                ft.TextButton(
                    text="Отмена",
                    on_click=closeDialog,
                ),
                ft.TextButton(
                    text="Удалить",
                    on_click=confirmDelete,
                    style=ft.ButtonStyle(color=ft.Colors.RED_400),
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

        page.open(confirmDialog)

    colorWrapControls = []

    for colorName in FAVORITE_COLOR_OPTIONS:
        checkboxControl = ft.Checkbox(
            label=colorName,
            value=colorName in profileData["favoriteColors"],
        )

        favoriteColorCheckboxes.append(checkboxControl)
        colorWrapControls.append(checkboxControl)

    statNumbers = {}

    def refreshPostStats(postItems):
        statNumbers['Работ'].value = str(len(postItems))
        statNumbers['Лайков'].value = str(sum(item['likesCount'] for item in postItems))

    def createStatItem(countText, labelText, itemColor, backgroundColor):
        number = ft.Text(str(countText), size=24, weight=ft.FontWeight.BOLD, color=itemColor)
        statNumbers[labelText] = number
        return ft.Container(
            expand=True,
            padding=12,
            border_radius=12,
            bgcolor=backgroundColor,
            content=ft.Column(
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    number,
                    ft.Text(
                        labelText,
                        size=12,
                    ),
                ],
            ),
        )

    return ft.ListView(
        expand=True,
        spacing=14,
        padding=ft.padding.only(left=16, right=16, top=16, bottom=16),
        controls=[
            ft.Card(
                elevation=2,
                content=ft.Container(
                    padding=16,
                    content=ft.Row(
                        controls=[
                            headerAvatarControl,
                            ft.Column(
                                expand=True,
                                controls=[
                                    profileNameText,
                                    profileEmailText,
                                    ft.Text(
                                        "Личный профиль и настройки аккаунта",
                                        size=13,
                                        color=ft.Colors.GREY_600,
                                    ),
                                ],
                                spacing=4,
                            ),
                        ],
                        spacing=14,
                    ),
                ),
            ),

            ft.Card(
                elevation=2,
                content=ft.Container(
                    padding=16,
                    content=ft.Column(
                        controls=[
                            ft.Text(
                                "Редактирование профиля",
                                size=18,
                                weight=ft.FontWeight.BOLD,
                            ),
                            ft.Row(
                                controls=[
                                    editAvatarControl,
                                    ft.Column(
                                        expand=True,
                                        controls=[
                                            avatarHintText,
                                            avatarPickerControl,
                                            ft.OutlinedButton('Убрать аватар', icon=ft.Icons.DELETE_OUTLINE,
                                                              on_click=handleRemoveAvatar),
                                        ],
                                        spacing=8,
                                    ),
                                ],
                                spacing=14,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                            nicknameField,
                            ft.OutlinedButton(text="Изменить email", on_click=handleChangeEmail),
                            bioField,
                            ageDropdown,
                            ft.Text(
                                "Любимые цвета, максимум 5",
                                size=13,
                                color=ft.Colors.GREY_600,
                            ),
                            ft.Row(
                                wrap=True,
                                controls=colorWrapControls,
                                spacing=4,
                                run_spacing=0,
                            ),
                            ft.ElevatedButton(
                                text="Сохранить профиль",
                                icon=ft.Icons.SAVE,
                                height=48,
                                style=ft.ButtonStyle(
                                    bgcolor=SECONDARY_COLOR,
                                    color=ft.Colors.WHITE,
                                    shape=ft.RoundedRectangleBorder(radius=12),
                                ),
                                on_click=handleSaveProfile,
                            ),
                        ],
                        spacing=12,
                    ),
                ),
            ),

            ft.Card(
                elevation=2,
                content=ft.Container(
                    padding=16,
                    content=ft.Column(
                        controls=[
                            ft.Text(
                                "Безопасность",
                                size=18,
                                weight=ft.FontWeight.BOLD,
                            ),
                            ft.Text(
                                "Для смены пароля укажите текущий пароль, новый пароль и подтверждение.",
                                size=13,
                                color=ft.Colors.GREY_600,
                            ),
                            currentPasswordField,
                            newPasswordField,
                            repeatPasswordField,
                            ft.ElevatedButton(
                                text="Изменить пароль",
                                icon=ft.Icons.LOCK_RESET,
                                height=48,
                                style=ft.ButtonStyle(
                                    bgcolor=PRIMARY_COLOR,
                                    color=ft.Colors.WHITE,
                                    shape=ft.RoundedRectangleBorder(radius=12),
                                ),
                                on_click=handleChangePassword,
                            ),
                        ],
                        spacing=12,
                    ),
                ),
            ),

            ft.Card(
                elevation=2,
                content=ft.Container(
                    padding=16,
                    content=ft.Column(
                        controls=[
                            ft.Text(
                                "Статистика",
                                size=18,
                                weight=ft.FontWeight.BOLD,
                            ),
                            createMyWorksButton(page, currentUser, refreshPostStats),
                            ft.Row(
                                controls=[
                                    createStatItem(userPostsCount, "Работ", PRIMARY_COLOR, "#FFF0F0"),
                                    createStatItem(userLikesCount, "Лайков", SECONDARY_COLOR, "#EFFFFD"),
                                    createStatItem(userProjectsCount, "Проектов", ft.Colors.DEEP_PURPLE_400, "#F4F1FF"),
                                ],
                                spacing=8,
                            ),
                        ],
                        spacing=12,
                    ),
                ),
            ),

            ft.Card(
                elevation=2,
                content=ft.Container(
                    padding=16,
                    content=ft.Column(
                        controls=[
                            ft.Text(
                                "Настройки приложения",
                                size=18,
                                weight=ft.FontWeight.BOLD,
                            ),
                            themeDropdown,
                            languageDropdown,
                            notificationsSwitch,
                            ft.ElevatedButton(
                                text="Сохранить настройки",
                                icon=ft.Icons.SAVE,
                                height=48,
                                style=ft.ButtonStyle(
                                    bgcolor=SECONDARY_COLOR,
                                    color=ft.Colors.WHITE,
                                    shape=ft.RoundedRectangleBorder(radius=12),
                                ),
                                on_click=handleSaveSettings,
                            ),
                            ft.Divider(),
                            createInfoCard(
                                ft.Icons.FAVORITE,
                                "Избранное",
                                "Сохранённые уроки, модели и цветовые смеси.",
                            ),
                            ft.ElevatedButton(
                                text="Выйти из аккаунта",
                                icon=ft.Icons.LOGOUT,
                                height=48,
                                style=ft.ButtonStyle(
                                    bgcolor=PRIMARY_COLOR,
                                    color=ft.Colors.WHITE,
                                    shape=ft.RoundedRectangleBorder(radius=12),
                                ),
                                on_click=handleLogout,
                            ),
                        ],
                        spacing=12,
                    ),
                ),
            ),

            ft.Card(
                elevation=2,
                content=ft.Container(
                    padding=16,
                    content=ft.Column(
                        controls=[
                            ft.Text(
                                "Опасная зона",
                                size=18,
                                weight=ft.FontWeight.BOLD,
                                color=ft.Colors.RED_400,
                            ),
                            ft.Text(
                                "Удаление аккаунта находится в самом низу профиля. "
                                "Это действие нельзя отменить.",
                                size=13,
                                color=ft.Colors.GREY_600,
                            ),
                            deletePasswordField,
                            ft.ElevatedButton(
                                text="Удалить аккаунт",
                                icon=ft.Icons.DELETE_FOREVER,
                                height=48,
                                style=ft.ButtonStyle(
                                    bgcolor=ft.Colors.RED_400,
                                    color=ft.Colors.WHITE,
                                    shape=ft.RoundedRectangleBorder(radius=12),
                                ),
                                on_click=handleDeleteAccount,
                            ),
                        ],
                        spacing=12,
                    ),
                ),
            ),
        ],
    )


