import base64
import colorsys
import math
import struct
import threading
import zlib

import flet as ft
import uuid
from datetime import datetime
from pathlib import Path

from auth_service import deleteUserAccount
from color_service import (
    BASE_COLORS, calculateMixedColor, calculateRecipe,
    findClosestRecipeForTargetColor, getUserColorMixtures,
    saveColorMixture, validateHexColor, deleteColorMixture
)
from lesson_service import SEARCH_CATEGORIES, generateRandomIdea, getLessonById, searchLessons
from post_service import (
    POST_CATEGORIES, getCommunityPosts, getPostComments, checkPostLikedByUser,
    removePost, removePostComment, savePost, savePostComment, togglePostLike
)
from project_service import (
    PROJECT_CATEGORIES, changeProjectStepStatus, getUserProjects,
    removeProject, removeProjectStep, saveProject, saveProjectStep
)
from profile_service import (
    AGE_CATEGORIES, FAVORITE_COLOR_OPTIONS, LANGUAGE_OPTIONS,
    THEME_OPTIONS, getUserProfile, saveUserProfile, saveUserSettings, changeUserPassword
)

PRIMARY_COLOR = "#FF6B6B"
SECONDARY_COLOR = "#4ECDC4"
LIGHT_BACKGROUND_COLOR = "#FFFFFF"
DARK_BACKGROUND_COLOR = "#121212"
DARK_TEXT_COLOR = "#222222"


def getPageBackgroundColor(page):
    return "#121212" if page.theme_mode == ft.ThemeMode.DARK else "#FFFFFF"

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

def createPostCard(page, postItem, currentUser, refreshCallback):
    canDelete = currentUser is not None and postItem["userId"] == currentUser["userId"]

    commentsColumn = ft.Column(spacing=6)

    commentField = ft.TextField(
        label="Комментарий",
        hint_text="Напишите комментарий...",
        multiline=True,
        min_lines=1,
        max_lines=3,
        border_radius=12,
    )

    def showMessage(messageText, isError=False):
        page.snack_bar = ft.SnackBar(
            content=ft.Text(messageText),
            bgcolor=ft.Colors.RED_400 if isError else ft.Colors.GREEN_400,
        )
        page.snack_bar.open = True
        page.update()

    def refreshComments():
        commentsColumn.controls.clear()

        commentItems = getPostComments(postItem["postId"])

        if len(commentItems) == 0:
            commentsColumn.controls.append(
                ft.Text(
                    "Комментариев пока нет.",
                    size=12,
                    color=ft.Colors.GREY_600,
                )
            )
            return

        for commentItem in commentItems:
            canDeleteComment = (
                currentUser is not None
                and commentItem["userId"] == currentUser["userId"]
            )

            commentControls = [
                ft.CircleAvatar(
                    radius=14,
                    content=ft.Text(
                        commentItem["nickname"][:1].upper(),
                        size=11,
                    ),
                    bgcolor=SECONDARY_COLOR,
                    color=ft.Colors.WHITE,
                ),
                ft.Column(
                    expand=True,
                    spacing=2,
                    controls=[
                        ft.Text(
                            commentItem["nickname"],
                            size=12,
                            weight=ft.FontWeight.BOLD,
                            color=ft.Colors.WHITE if page.theme_mode == ft.ThemeMode.DARK else ft.Colors.BLACK,
                        ),
                        ft.Text(
                            commentItem["commentText"],
                            size=12,
                            color=ft.Colors.WHITE if page.theme_mode == ft.ThemeMode.DARK else ft.Colors.GREY_700,
                        ),
                    ],
                ),
            ]

            if canDeleteComment:
                def handleDeleteComment(
                    event,
                    currentCommentId=commentItem["commentId"],
                ):
                    removePostComment(
                        currentCommentId,
                        currentUser["userId"],
                    )
                    refreshComments()
                    showMessage("Комментарий удалён")
                    page.update()

                commentControls.append(
                    ft.IconButton(
                        icon=ft.Icons.DELETE,
                        icon_size=18,
                        icon_color=ft.Colors.RED_300,
                        on_click=handleDeleteComment,
                    )
                )

                commentBackgroundColor = "#2A2A2A" if page.theme_mode == ft.ThemeMode.DARK else "#F7F7F7"

                commentsColumn.controls.append(
                    ft.Container(
                        padding=8,
                        border_radius=12,
                        bgcolor=commentBackgroundColor,
                        content=ft.Row(
                            controls=commentControls,
                            spacing=8,
                            vertical_alignment=ft.CrossAxisAlignment.START,
                        ),
                    )
                )

    def handleLike(event):
        if currentUser is None:
            showMessage("Сначала войдите в аккаунт", True)
            return

        isLiked, likesCount = togglePostLike(
            postItem["postId"],
            currentUser["userId"],
        )

        postItem["likesCount"] = likesCount

        refreshCallback()

        if isLiked:
            showMessage("Лайк добавлен")
        else:
            showMessage("Лайк снят")

        page.update()

    def handleDelete(event):
        removePost(postItem["postId"], currentUser["userId"])
        refreshCallback()
        showMessage("Публикация удалена")
        page.update()

    def handleAddComment(event):
        if currentUser is None:
            showMessage("Сначала войдите в аккаунт", True)
            return

        successStatus, messageText, commentId = savePostComment(
            postItem["postId"],
            currentUser["userId"],
            commentField.value,
        )

        if not successStatus:
            showMessage(messageText, True)
            return

        commentField.value = ""
        refreshComments()
        showMessage(messageText)
        page.update()

    controls = [
        ft.Row(
            controls=[
                ft.CircleAvatar(
                    content=ft.Text(postItem["nickname"][:1].upper()),
                    bgcolor=SECONDARY_COLOR,
                    color=ft.Colors.WHITE,
                ),
                ft.Column(
                    expand=True,
                    controls=[
                        ft.Text(
                            postItem["titleText"],
                            size=17,
                            weight=ft.FontWeight.BOLD,
                        ),
                        ft.Text(
                            f"Автор: {postItem['nickname']} · {postItem['categoryName']}",
                            size=12,
                            color=ft.Colors.GREY_600,
                        ),
                    ],
                    spacing=2,
                ),
            ],
            spacing=10,
        ),
        ft.Container(
            height=150,
            border_radius=18,
            bgcolor="#F5F5F5",
            alignment=ft.alignment.center,
            content=ft.Icon(
                name=ft.Icons.IMAGE,
                size=64,
                color=ft.Colors.GREY_500,
            ),
        ),
        ft.Text(
            postItem["descriptionText"],
            size=14,
            color=ft.Colors.GREY_700,
        ),
    ]

    if postItem["tagsText"]:
        controls.append(
            ft.Text(
                f"Теги: {postItem['tagsText']}",
                size=12,
                color=ft.Colors.GREY_600,
            )
        )

    isPostLiked = False

    if currentUser is not None:
        isPostLiked = checkPostLikedByUser(
            postItem["postId"],
            currentUser["userId"],
        )

    likeButtonText = f"❤️ {postItem['likesCount']}" if isPostLiked else f"🤍 {postItem['likesCount']}"

    actionControls = [
        ft.TextButton(
            text=likeButtonText,
            on_click=handleLike,
        ),
    ]

    if canDelete:
        actionControls.append(
            ft.TextButton(
                text="Удалить",
                on_click=handleDelete,
            )
        )

    controls.append(
        ft.Row(
            controls=actionControls,
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )
    )

    refreshComments()

    controls.extend(
        [
            ft.Divider(),
            ft.Text(
                "Комментарии",
                size=14,
                weight=ft.FontWeight.BOLD,
            ),
            commentsColumn,
            ft.Row(
                controls=[
                    ft.Container(
                        expand=True,
                        content=commentField,
                    ),
                    ft.IconButton(
                        icon=ft.Icons.SEND,
                        icon_color=PRIMARY_COLOR,
                        on_click=handleAddComment,
                    ),
                ],
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        ]
    )

    return ft.Card(
        elevation=2,
        content=ft.Container(
            padding=14,
            content=ft.Column(
                controls=controls,
                spacing=10,
            ),
        ),
    )

def createHomeTab(page, currentUser, nickname):
    postListColumn = ft.Column(spacing=10)

    postTitleField = ft.TextField(
        label="Название работы",
        hint_text="Например: Милый котик",
        prefix_icon=ft.Icons.EDIT,
        border_radius=12,
    )

    postDescriptionField = ft.TextField(
        label="Описание",
        hint_text="Расскажите, что вы слепили",
        multiline=True,
        min_lines=3,
        max_lines=5,
        border_radius=12,
    )

    postCategoryDropdown = ft.Dropdown(
        label="Категория",
        value=POST_CATEGORIES[0],
        border_radius=12,
        options=[
            ft.dropdown.Option(categoryName)
            for categoryName in POST_CATEGORIES
        ],
    )

    postTagsField = ft.TextField(
        label="Теги через запятую",
        hint_text="котик, животные, кавай",
        prefix_icon=ft.Icons.TAG,
        border_radius=12,
    )

    def showMessage(messageText, isError=False):
        page.snack_bar = ft.SnackBar(
            content=ft.Text(messageText),
            bgcolor=ft.Colors.RED_400 if isError else ft.Colors.GREEN_400,
        )
        page.snack_bar.open = True
        page.update()

    def clearPostForm():
        postTitleField.value = ""
        postDescriptionField.value = ""
        postCategoryDropdown.value = POST_CATEGORIES[0]
        postTagsField.value = ""

    def refreshPosts():
        postListColumn.controls.clear()

        postItems = getCommunityPosts()

        if len(postItems) == 0:
            postListColumn.controls.append(
                ft.Container(
                    padding=16,
                    border_radius=12,
                    bgcolor="#F5F5F5",
                    content=ft.Text(
                        "Публикаций пока нет. Добавьте первую работу.",
                        color=ft.Colors.GREY_700,
                    ),
                )
            )
            return

        for postItem in postItems:
            postListColumn.controls.append(
                createPostCard(page, postItem, currentUser, refreshPosts)
            )

    def handleCreatePost(event):
        if currentUser is None:
            showMessage("Сначала войдите в аккаунт", True)
            return

        successStatus, messageText, postId = savePost(
            currentUser["userId"],
            postTitleField.value,
            postDescriptionField.value,
            postCategoryDropdown.value,
            postTagsField.value,
        )

        if not successStatus:
            showMessage(messageText, True)
            return

        clearPostForm()
        refreshPosts()
        showMessage(messageText)
        page.update()

    refreshPosts()

    return ft.ListView(
        expand=True,
        spacing=12,
        padding=ft.padding.only(left=16, right=16, top=16, bottom=16),
        controls=[
            ft.Row(
                controls=[
                    ft.CircleAvatar(
                        content=ft.Text(nickname[:1].upper()),
                        bgcolor=SECONDARY_COLOR,
                        color=ft.Colors.WHITE,
                    ),
                    ft.Column(
                        controls=[
                            ft.Text(
                                f"Привет, {nickname}!",
                                size=22,
                                weight=ft.FontWeight.BOLD,
                            ),
                            ft.Text(
                                "Что будем лепить сегодня?",
                                size=14,
                                color=ft.Colors.GREY_600,
                            ),
                        ],
                        spacing=2,
                    ),
                ],
                spacing=12,
            ),
            ft.Container(
                padding=18,
                border_radius=18,
                bgcolor=PRIMARY_COLOR,
                content=ft.Column(
                    controls=[
                        ft.Text(
                            "Челлендж недели",
                            size=13,
                            color=ft.Colors.WHITE,
                            weight=ft.FontWeight.BOLD,
                        ),
                        ft.Text(
                            "Слепи милого котика",
                            size=22,
                            color=ft.Colors.WHITE,
                            weight=ft.FontWeight.BOLD,
                        ),
                        ft.Text(
                            "Опубликуй работу в сообщество и собери лайки.",
                            size=14,
                            color=ft.Colors.WHITE,
                        ),
                    ],
                    spacing=6,
                ),
            ),
            ft.Text(
                "Опубликовать работу",
                size=18,
                weight=ft.FontWeight.BOLD,
            ),
            ft.Card(
                elevation=2,
                content=ft.Container(
                    padding=16,
                    content=ft.Column(
                        controls=[
                            postTitleField,
                            postDescriptionField,
                            postCategoryDropdown,
                            postTagsField,
                            ft.Container(
                                height=120,
                                border_radius=18,
                                bgcolor="#F5F5F5",
                                alignment=ft.alignment.center,
                                content=ft.Column(
                                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                                    alignment=ft.MainAxisAlignment.CENTER,
                                    controls=[
                                        ft.Icon(
                                            name=ft.Icons.IMAGE,
                                            size=42,
                                            color=ft.Colors.GREY_500,
                                        ),
                                        ft.Text(
                                            "Фото работы добавим позже",
                                            size=13,
                                            color=ft.Colors.GREY_600,
                                        ),
                                    ],
                                ),
                            ),
                            ft.ElevatedButton(
                                text="Опубликовать",
                                icon=ft.Icons.PUBLISH,
                                height=48,
                                style=ft.ButtonStyle(
                                    bgcolor=SECONDARY_COLOR,
                                    color=ft.Colors.WHITE,
                                    shape=ft.RoundedRectangleBorder(radius=12),
                                ),
                                on_click=handleCreatePost,
                            ),
                        ],
                        spacing=12,
                    ),
                ),
            ),
            ft.Text(
                "Лента сообщества",
                size=18,
                weight=ft.FontWeight.BOLD,
            ),
            postListColumn,
        ],
    )


def createSearchTab(page, currentUser):
    resultColumn = ft.Column(spacing=10)
    ideaContainer = ft.Container()
    mainContentColumn = ft.Column(spacing=14)

    selectedLessonId = {"value": None}
    selectedStepIndex = {"value": 0}

    searchField = ft.TextField(
        label="Поиск уроков, моделей и работ",
        hint_text="Например: котик, еда, дракон",
        prefix_icon=ft.Icons.SEARCH,
        border_radius=12,
    )

    categoryDropdown = ft.Dropdown(
        label="Категория",
        value="Все",
        border_radius=12,
        options=[
            ft.dropdown.Option(categoryName)
            for categoryName in SEARCH_CATEGORIES
        ],
    )

    def showMessage(messageText, isError=False):
        page.snack_bar = ft.SnackBar(
            content=ft.Text(messageText),
            bgcolor=ft.Colors.RED_400 if isError else ft.Colors.GREEN_400,
        )
        page.snack_bar.open = True
        page.update()

    def handleCreateProjectFromIdea(ideaData):
        if currentUser is None:
            showMessage("Сначала войдите в аккаунт", True)
            return

        projectName = ideaData["title"].replace("Слепить: ", "")

        descriptionText = (
            f"{ideaData['description']}\n\n"
            f"Сложность: {ideaData['level']}\n"
            f"Примерное время выполнения: {ideaData['estimatedTime']} минут\n"
            f"Рекомендуемые цвета: {', '.join(ideaData['colors'])}"
        )

        successStatus, messageText, projectId = saveProject(
            currentUser["userId"],
            projectName,
            ideaData["theme"],
            "",
            descriptionText,
        )

        if not successStatus:
            showMessage(messageText, True)
            return

        showMessage("Идея добавлена в проекты")

    def handleCreateProjectFromLesson(lessonItem):
        if currentUser is None:
            showMessage("Сначала войдите в аккаунт", True)
            return

        descriptionText = (
            f"{lessonItem['description']}\n\n"
            f"Уровень: {lessonItem['level']}\n"
            f"Примерное время выполнения: {lessonItem['timeMinutes']} минут\n"
            f"Материалы: {', '.join(lessonItem['materials'])}"
        )

        successStatus, messageText, projectId = saveProject(
            currentUser["userId"],
            lessonItem["title"],
            lessonItem["category"],
            "",
            descriptionText,
        )

        if not successStatus:
            showMessage(messageText, True)
            return

        showMessage("Урок добавлен в проекты")

    def showLessonDetail(lessonId):
        selectedLessonId["value"] = lessonId
        selectedStepIndex["value"] = 0
        refreshMainContent()
        page.update()

    def showSearchContent():
        selectedLessonId["value"] = None
        selectedStepIndex["value"] = 0
        refreshMainContent()
        page.update()

    def createLessonDetail(lessonItem):
        steps = lessonItem["steps"]
        currentStepIndex = selectedStepIndex["value"]
        currentStepText = steps[currentStepIndex]
        progressValue = (currentStepIndex + 1) / len(steps)

        materialsText = ", ".join(lessonItem["materials"])

        def handlePreviousStep(event):
            if selectedStepIndex["value"] > 0:
                selectedStepIndex["value"] -= 1
                refreshMainContent()
                page.update()

        def handleNextStep(event):
            if selectedStepIndex["value"] < len(steps) - 1:
                selectedStepIndex["value"] += 1
                refreshMainContent()
                page.update()
            else:
                showMessage("Урок завершён")

        return ft.Column(
            spacing=14,
            controls=[
                ft.TextButton(
                    text="← Назад к поиску",
                    on_click=lambda event: showSearchContent(),
                ),
                ft.Container(
                    padding=18,
                    border_radius=18,
                    bgcolor=PRIMARY_COLOR,
                    content=ft.Column(
                        spacing=8,
                        controls=[
                            ft.Text(
                                lessonItem["title"],
                                size=24,
                                weight=ft.FontWeight.BOLD,
                                color=ft.Colors.WHITE,
                            ),
                            ft.Text(
                                f"{lessonItem['category']} · {lessonItem['level']} · {lessonItem['timeMinutes']} мин",
                                size=14,
                                color=ft.Colors.WHITE,
                            ),
                            ft.Text(
                                lessonItem["description"],
                                size=14,
                                color=ft.Colors.WHITE,
                            ),
                        ],
                    ),
                ),
                ft.Card(
                    elevation=2,
                    content=ft.Container(
                        padding=16,
                        content=ft.Column(
                            spacing=8,
                            controls=[
                                ft.Text(
                                    "Материалы и инструменты",
                                    size=18,
                                    weight=ft.FontWeight.BOLD,
                                ),
                                ft.Text(
                                    materialsText,
                                    size=14,
                                    color=ft.Colors.GREY_700,
                                ),
                            ],
                        ),
                    ),
                ),
                ft.Card(
                    elevation=2,
                    content=ft.Container(
                        padding=16,
                        content=ft.Column(
                            spacing=12,
                            controls=[
                                ft.Text(
                                    f"Шаг {currentStepIndex + 1} из {len(steps)}",
                                    size=18,
                                    weight=ft.FontWeight.BOLD,
                                ),
                                ft.ProgressBar(
                                    value=progressValue,
                                    color=SECONDARY_COLOR,
                                    bgcolor="#DDDDDD",
                                ),
                                ft.Container(
                                    height=150,
                                    border_radius=18,
                                    bgcolor="#F5F5F5",
                                    alignment=ft.alignment.center,
                                    content=ft.Icon(
                                        name=ft.Icons.IMAGE,
                                        size=64,
                                        color=ft.Colors.GREY_500,
                                    ),
                                ),
                                ft.Text(
                                    currentStepText,
                                    size=16,
                                    color=DARK_TEXT_COLOR,
                                ),
                                ft.Row(
                                    controls=[
                                        ft.ElevatedButton(
                                            text="Предыдущий",
                                            icon=ft.Icons.ARROW_BACK,
                                            disabled=currentStepIndex == 0,
                                            height=44,
                                            on_click=handlePreviousStep,
                                        ),
                                        ft.Container(expand=True),
                                        ft.ElevatedButton(
                                            text="Следующий" if currentStepIndex < len(steps) - 1 else "Завершить",
                                            icon=ft.Icons.ARROW_FORWARD,
                                            height=44,
                                            style=ft.ButtonStyle(
                                                bgcolor=SECONDARY_COLOR,
                                                color=ft.Colors.WHITE,
                                                shape=ft.RoundedRectangleBorder(radius=12),
                                            ),
                                            on_click=handleNextStep,
                                        ),
                                    ],
                                ),
                            ],
                        ),
                    ),
                ),
                ft.ElevatedButton(
                    text="Добавить как проект",
                    icon=ft.Icons.ADD,
                    height=48,
                    style=ft.ButtonStyle(
                        bgcolor=PRIMARY_COLOR,
                        color=ft.Colors.WHITE,
                        shape=ft.RoundedRectangleBorder(radius=12),
                    ),
                    on_click=lambda event: handleCreateProjectFromLesson(lessonItem),
                ),
            ],
        )

    def createLessonCard(lessonItem):
        tagText = ", ".join(lessonItem["tags"])

        return ft.Card(
            elevation=2,
            content=ft.Container(
                padding=14,
                content=ft.Column(
                    controls=[
                        ft.Row(
                            controls=[
                                ft.Container(
                                    width=52,
                                    height=52,
                                    border_radius=16,
                                    bgcolor="#FFF0F0",
                                    alignment=ft.alignment.center,
                                    content=ft.Icon(
                                        name=ft.Icons.SCHOOL,
                                        color=PRIMARY_COLOR,
                                        size=28,
                                    ),
                                ),
                                ft.Column(
                                    expand=True,
                                    controls=[
                                        ft.Text(
                                            lessonItem["title"],
                                            size=17,
                                            weight=ft.FontWeight.BOLD,
                                        ),
                                        ft.Text(
                                            f"{lessonItem['category']} · {lessonItem['level']} · {lessonItem['timeMinutes']} мин",
                                            size=12,
                                            color=ft.Colors.GREY_600,
                                        ),
                                    ],
                                    spacing=2,
                                ),
                            ],
                            spacing=12,
                        ),
                        ft.Text(
                            lessonItem["description"],
                            size=13,
                            color=ft.Colors.GREY_700,
                        ),
                        ft.Text(
                            f"Теги: {tagText}",
                            size=12,
                            color=ft.Colors.GREY_600,
                        ),
                        ft.Row(
                            controls=[
                                ft.Text(
                                    f"👁 {lessonItem['views']}",
                                    size=12,
                                    color=ft.Colors.GREY_600,
                                ),
                                ft.Text(
                                    f"❤ {lessonItem['likes']}",
                                    size=12,
                                    color=ft.Colors.GREY_600,
                                ),
                                ft.Container(expand=True),
                                ft.TextButton(
                                    text="Открыть",
                                    on_click=lambda event, currentLessonId=lessonItem["lessonId"]: showLessonDetail(currentLessonId),
                                ),
                            ],
                        ),
                    ],
                    spacing=8,
                ),
            ),
        )

    def refreshSearchResults():
        resultColumn.controls.clear()

        lessonItems = searchLessons(searchField.value or "", categoryDropdown.value)

        if len(lessonItems) == 0:
            resultColumn.controls.append(
                ft.Container(
                    padding=16,
                    border_radius=12,
                    bgcolor="#F5F5F5",
                    content=ft.Text(
                        "Ничего не найдено. Попробуйте изменить запрос или категорию.",
                        color=ft.Colors.GREY_700,
                    ),
                )
            )
        else:
            for lessonItem in lessonItems:
                resultColumn.controls.append(createLessonCard(lessonItem))

    def handleSearchChange(event):
        refreshSearchResults()
        refreshMainContent()
        page.update()

    def handleGenerateIdea(event):
        ideaData = generateRandomIdea()

        colorControls = []

        for colorHex in ideaData["colors"]:
            colorControls.append(
                ft.Container(
                    width=34,
                    height=34,
                    border_radius=17,
                    bgcolor=colorHex,
                )
            )

        ideaContainer.content = ft.Card(
            elevation=2,
            content=ft.Container(
                padding=16,
                content=ft.Column(
                    controls=[
                        ft.Text(
                            ideaData["title"],
                            size=20,
                            weight=ft.FontWeight.BOLD,
                        ),
                        ft.Text(
                            ideaData["description"],
                            size=14,
                            color=ft.Colors.GREY_700,
                        ),
                        ft.Text(
                            f"Сложность: {ideaData['level']}",
                            size=13,
                            color=ft.Colors.GREY_600,
                        ),
                        ft.Text(
                            f"Примерное время: {ideaData['estimatedTime']} минут",
                            size=13,
                            color=ft.Colors.GREY_600,
                        ),
                        ft.Row(
                            controls=colorControls,
                            spacing=8,
                        ),
                        ft.ElevatedButton(
                            text="Добавить в проекты",
                            icon=ft.Icons.ADD,
                            height=44,
                            style=ft.ButtonStyle(
                                bgcolor=SECONDARY_COLOR,
                                color=ft.Colors.WHITE,
                                shape=ft.RoundedRectangleBorder(radius=12),
                            ),
                            on_click=lambda event, currentIdea=ideaData: handleCreateProjectFromIdea(currentIdea),
                        ),
                    ],
                    spacing=10,
                ),
            ),
        )

        refreshMainContent()
        page.update()

    def refreshMainContent():
        mainContentColumn.controls.clear()

        if selectedLessonId["value"] is not None:
            lessonItem = getLessonById(selectedLessonId["value"])

            if lessonItem is None:
                mainContentColumn.controls.append(
                    ft.Text("Урок не найден", color=ft.Colors.RED_400)
                )
            else:
                mainContentColumn.controls.append(createLessonDetail(lessonItem))

            return

        mainContentColumn.controls.extend(
            [
                ft.Text(
                    "Поиск и идеи",
                    size=24,
                    weight=ft.FontWeight.BOLD,
                ),
                searchField,
                categoryDropdown,
                ft.Text(
                    "Генератор идей",
                    size=18,
                    weight=ft.FontWeight.BOLD,
                ),
                ft.ElevatedButton(
                    text="Сгенерировать идею",
                    icon=ft.Icons.AUTO_AWESOME,
                    height=48,
                    style=ft.ButtonStyle(
                        bgcolor=PRIMARY_COLOR,
                        color=ft.Colors.WHITE,
                        shape=ft.RoundedRectangleBorder(radius=12),
                    ),
                    on_click=handleGenerateIdea,
                ),
                ideaContainer,
                ft.Text(
                    "Результаты поиска",
                    size=18,
                    weight=ft.FontWeight.BOLD,
                ),
                resultColumn,
            ]
        )

    searchField.on_change = handleSearchChange
    categoryDropdown.on_change = handleSearchChange

    refreshSearchResults()
    refreshMainContent()

    return ft.ListView(
        expand=True,
        spacing=14,
        padding=ft.padding.only(left=16, right=16, top=16, bottom=16),
        controls=[
            mainContentColumn,
        ],
    )

def createColorsTab(page, currentUser):
    selectedColors = []
    recipeSearchState = {"token": 0}

    recipeColumn = ft.Column(spacing=8)
    savedMixturesColumn = ft.Column(spacing=8)
    selectedColorsColumn = ft.Column(spacing=8)

    def showMessage(messageText, isError=False):
        page.snack_bar = ft.SnackBar(
            content=ft.Text(messageText),
            bgcolor=ft.Colors.RED_400 if isError else ft.Colors.GREEN_400,
        )
        page.snack_bar.open = True
        page.update()

    def getTextColorForBackground(hexColor):
        return ft.Colors.BLACK if hexColor.upper() in ["#FFFFFF", "#F5DEB3", "#FFD60A"] else ft.Colors.WHITE

    def getTotalWeight():
        try:
            totalWeight = float((totalWeightField.value or "100").replace(",", "."))
        except ValueError:
            totalWeight = 100

        return totalWeight if totalWeight > 0 else 100

    def normalizeAndRedistribute(changedColor=None, newValue=None):
        if not selectedColors:
            return

        if len(selectedColors) == 1:
            selectedColors[0]["proportion"] = 100.0
            return

        if changedColor is not None and newValue is not None:
            fixedValue = max(0.0, min(100.0, float(newValue)))
            changedColor["proportion"] = fixedValue

            otherColors = [color for color in selectedColors if color is not changedColor]
            remainingValue = max(0.0, 100.0 - fixedValue)
            otherTotal = sum(color["proportion"] for color in otherColors)

            if otherTotal <= 0:
                equalValue = remainingValue / len(otherColors) if otherColors else 0
                for color in otherColors:
                    color["proportion"] = equalValue
            else:
                for color in otherColors:
                    color["proportion"] = color["proportion"] / otherTotal * remainingValue
        else:
            totalValue = sum(color["proportion"] for color in selectedColors)

            if totalValue <= 0:
                equalValue = 100.0 / len(selectedColors)
                for color in selectedColors:
                    color["proportion"] = equalValue
            else:
                for color in selectedColors:
                    color["proportion"] = color["proportion"] / totalValue * 100.0

        roundedTotal = 0
        for color in selectedColors[:-1]:
            color["proportion"] = round(color["proportion"], 1)
            roundedTotal += color["proportion"]

        selectedColors[-1]["proportion"] = round(max(0.0, 100.0 - roundedTotal), 1)

    resultColorText = ft.Text("#FFFFFF", size=32, weight=ft.FontWeight.BOLD)
    resultColorBox = ft.Container(
        height=150,
        border_radius=24,
        bgcolor="#FFFFFF",
        alignment=ft.alignment.center,
        content=resultColorText,
    )

    miniResultText = ft.Text("#FFFFFF", size=11, weight=ft.FontWeight.BOLD)
    miniResultBox = ft.Container(
        width=82,
        height=54,
        border_radius=14,
        bgcolor="#FFFFFF",
        alignment=ft.alignment.center,
        content=miniResultText,
        border=ft.border.all(1, ft.Colors.GREY_300),
    )

    totalWeightField = ft.TextField(
        label="Общий вес смеси (граммы)",
        value="100",
        keyboard_type=ft.KeyboardType.NUMBER,
        border_radius=12,
    )

    mixtureNameField = ft.TextField(
        label="Название смеси",
        value="Моя новая смесь",
        border_radius=12,
    )

    targetHexField = ft.TextField(
        label="Целевой цвет (HEX)",
        value="#8A4F3A",
        prefix_icon=ft.Icons.SEARCH,
        border_radius=12,
    )

    targetResultText = ft.Text(
        "Введите HEX-цвет или выберите его из палитры",
        size=13,
        color=ft.Colors.GREY_600,
    )

    targetSelectedText = ft.Text("#8A4F3A", size=11, weight=ft.FontWeight.BOLD)
    targetSelectedBox = ft.Container(
        width=92,
        height=54,
        border_radius=14,
        bgcolor="#8A4F3A",
        alignment=ft.alignment.center,
        content=targetSelectedText,
        border=ft.border.all(1, ft.Colors.GREY_300),
    )

    targetRecipeText = ft.Text("—", size=11, weight=ft.FontWeight.BOLD)
    targetRecipeBox = ft.Container(
        width=92,
        height=54,
        border_radius=14,
        bgcolor="#FFFFFF",
        alignment=ft.alignment.center,
        content=targetRecipeText,
        border=ft.border.all(1, ft.Colors.GREY_300),
    )

    targetPreviewColumn = ft.Column(
        width=110,
        spacing=8,
        controls=[
            ft.Text("Цель", size=12, weight=ft.FontWeight.BOLD),
            targetSelectedBox,
            ft.Text("Рецепт", size=12, weight=ft.FontWeight.BOLD),
            targetRecipeBox,
        ],
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
    )

    def refreshSavedMixtures():
        savedMixturesColumn.controls.clear()

        if not currentUser:
            savedMixturesColumn.controls.append(
                ft.Text("Войдите в аккаунт для просмотра смесей", color=ft.Colors.GREY_600)
            )
            return

        mixtures = getUserColorMixtures(currentUser["userId"])

        if not mixtures:
            savedMixturesColumn.controls.append(
                ft.Text("Пока нет сохранённых смесей", color=ft.Colors.GREY_600)
            )
            return

        for mixture in mixtures:
            def handleDeleteMixture(event, currentMixtureId=mixture["mixtureId"]):
                deleteColorMixture(currentUser["userId"], currentMixtureId)
                refreshSavedMixtures()
                showMessage("Смесь удалена")

            savedMixturesColumn.controls.append(
                ft.Card(
                    content=ft.Container(
                        padding=12,
                        content=ft.Row(
                            controls=[
                                ft.Container(
                                    width=48,
                                    height=48,
                                    border_radius=24,
                                    bgcolor=mixture["resultHex"],
                                ),
                                ft.Column(
                                    expand=True,
                                    spacing=2,
                                    controls=[
                                        ft.Text(mixture["mixtureName"], weight=ft.FontWeight.BOLD),
                                        ft.Text(
                                            f"{mixture['resultHex']} • {mixture['totalWeight']} г",
                                            size=12,
                                            color=ft.Colors.GREY_600,
                                        ),
                                    ],
                                ),
                                ft.IconButton(
                                    icon=ft.Icons.DELETE,
                                    icon_color=ft.Colors.RED_400,
                                    on_click=handleDeleteMixture,
                                ),
                            ],
                            spacing=10,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                    ),
                )
            )

    def refreshRecipe():
        recipeColumn.controls.clear()
        selectedColorsColumn.controls.clear()

        normalizeAndRedistribute()

        totalWeight = getTotalWeight()
        resultHex = calculateMixedColor(selectedColors) if selectedColors else "#FFFFFF"
        recipeItems = calculateRecipe(selectedColors, totalWeight) if selectedColors else []

        resultColorBox.bgcolor = resultHex
        resultColorText.value = resultHex
        resultColorText.color = getTextColorForBackground(resultHex)

        miniResultBox.bgcolor = resultHex
        miniResultText.value = resultHex
        miniResultText.color = getTextColorForBackground(resultHex)

        if not selectedColors:
            selectedColorsColumn.controls.append(
                ft.Container(
                    padding=12,
                    border_radius=12,
                    bgcolor="#F5F5F5",
                    content=ft.Text(
                        "Выберите цвета из базовой палитры ниже.",
                        color=ft.Colors.GREY_700,
                    ),
                )
            )
        else:
            for colorItem in selectedColors:
                def handleSliderChange(event, currentColor=colorItem):
                    normalizeAndRedistribute(currentColor, float(event.control.value))
                    refreshRecipe()
                    page.update()

                def handlePercentSubmit(event, currentColor=colorItem):
                    try:
                        value = float((event.control.value or "0").replace(",", "."))
                    except ValueError:
                        showMessage("Введите число процента", True)
                        return

                    normalizeAndRedistribute(currentColor, value)
                    refreshRecipe()
                    page.update()

                def handleRemoveColor(event, currentColor=colorItem):
                    if currentColor in selectedColors:
                        selectedColors.remove(currentColor)
                    refreshRecipe()
                    page.update()

                selectedColorsColumn.controls.append(
                    ft.Card(
                        content=ft.Container(
                            padding=12,
                            content=ft.Column(
                                spacing=8,
                                controls=[
                                    ft.Row(
                                        controls=[
                                            ft.Container(
                                                width=38,
                                                height=38,
                                                border_radius=19,
                                                bgcolor=colorItem["hex"],
                                                border=ft.border.all(1, ft.Colors.GREY_300),
                                            ),
                                            ft.Text(colorItem["name"], expand=True, weight=ft.FontWeight.W_500),
                                            ft.Text(
                                                f"{round(colorItem['proportion'], 1)}%",
                                                weight=ft.FontWeight.BOLD,
                                            ),
                                            ft.IconButton(
                                                icon=ft.Icons.DELETE,
                                                icon_color=ft.Colors.RED_400,
                                                on_click=handleRemoveColor,
                                            ),
                                        ],
                                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                    ),
                                    ft.Row(
                                        controls=[
                                            ft.Slider(
                                                min=0,
                                                max=100,
                                                value=colorItem["proportion"],
                                                expand=True,
                                                on_change=handleSliderChange,
                                            ),
                                            ft.TextField(
                                                value=str(round(colorItem["proportion"], 1)),
                                                width=70,
                                                text_align=ft.TextAlign.CENTER,
                                                keyboard_type=ft.KeyboardType.NUMBER,
                                                on_submit=handlePercentSubmit,
                                            ),
                                        ],
                                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                    ),
                                ],
                            ),
                        ),
                    )
                )

        for recipeItem in recipeItems:
            recipeColumn.controls.append(
                ft.Row(
                    controls=[
                        ft.Container(
                            width=28,
                            height=28,
                            border_radius=14,
                            bgcolor=recipeItem["hex"],
                            border=ft.border.all(1, ft.Colors.GREY_300),
                        ),
                        ft.Text(recipeItem["name"], expand=True),
                        ft.Text(
                            f"{recipeItem['percent']}% • {recipeItem['grams']} г",
                            weight=ft.FontWeight.BOLD,
                        ),
                    ],
                    spacing=10,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                )
            )

        if not recipeItems:
            recipeColumn.controls.append(
                ft.Text("Рецепт появится после выбора минимум одного цвета.", color=ft.Colors.GREY_600)
            )

    def handleColorClick(event, colorItem):
        if any(color["colorId"] == colorItem["colorId"] for color in selectedColors):
            showMessage("Цвет уже выбран", True)
            return

        if len(selectedColors) >= 5:
            showMessage("Максимум 5 цветов", True)
            return

        selectedColors.append(
            {
                "colorId": colorItem["colorId"],
                "name": colorItem["name"],
                "hex": colorItem["hex"],
                "proportion": 0.0,
            }
        )

        refreshRecipe()
        page.update()

    def normalizeTargetHexText(hexColor):
        cleanHex = (hexColor or "").strip().upper()

        if cleanHex and not cleanHex.startswith("#"):
            cleanHex = f"#{cleanHex}"

        return cleanHex

    def updateTargetSelectedPreview(hexColor):
        cleanHex = normalizeTargetHexText(hexColor)

        if not validateHexColor(cleanHex):
            return

        targetSelectedBox.bgcolor = cleanHex
        targetSelectedText.value = cleanHex
        targetSelectedText.color = getTextColorForBackground(cleanHex)

    def updateTargetRecipePreview(hexColor):
        cleanHex = normalizeTargetHexText(hexColor)

        if not validateHexColor(cleanHex):
            return

        targetRecipeBox.bgcolor = cleanHex
        targetRecipeText.value = cleanHex
        targetRecipeText.color = getTextColorForBackground(cleanHex)

    def applyRecipeResult(recipeResult):
        selectedColors.clear()

        for colorItem in recipeResult["selectedColors"]:
            selectedColors.append(
                {
                    "colorId": colorItem["colorId"],
                    "name": colorItem["name"],
                    "hex": colorItem["hex"],
                    "proportion": colorItem["proportion"],
                }
            )

        mixtureNameField.value = f"Рецепт для {recipeResult['targetHex']}"
        targetResultText.value = (
            f"Ближайший результат: {recipeResult['resultHex']}. "
            f"Погрешность: {recipeResult['distance']}."
        )
        updateTargetRecipePreview(recipeResult["resultHex"])

        refreshRecipe()

    def safePageUpdate():
        try:
            page.update()
        except AssertionError:
            pass
        except Exception:
            pass

    def handleFindRecipe(event):
        targetHex = normalizeTargetHexText(targetHexField.value)

        if not validateHexColor(targetHex):
            showMessage("Введите цвет в формате HEX, например #8A4F3A", True)
            return

        recipeSearchState["token"] += 1
        currentToken = recipeSearchState["token"]

        targetHexField.value = targetHex
        updateTargetSelectedPreview(targetHex)
        targetRecipeText.value = "..."
        targetRecipeText.color = ft.Colors.BLACK
        targetResultText.value = "Подбираю рецепт..."
        safePageUpdate()

        totalWeight = getTotalWeight()

        def runRecipeSearch():
            try:
                recipeResult = findClosestRecipeForTargetColor(targetHex, totalWeight)
            except Exception:
                if currentToken != recipeSearchState["token"]:
                    return

                targetResultText.value = "Не получилось подобрать рецепт для этого цвета."
                safePageUpdate()
                return

            if currentToken != recipeSearchState["token"]:
                return

            applyRecipeResult(recipeResult)
            safePageUpdate()

        threading.Thread(target=runRecipeSearch, daemon=True).start()

    def handleTargetColorClick(event, colorItem):
        targetHexField.value = colorItem["hex"]
        handleFindRecipe(event)

    def handleSaveMixture(event):
        if not currentUser:
            showMessage("Войдите в аккаунт", True)
            return

        if len(selectedColors) < 2:
            showMessage("Нужно минимум 2 цвета", True)
            return

        mixtureName = mixtureNameField.value.strip()
        if len(mixtureName) < 3:
            showMessage("Название слишком короткое", True)
            return

        normalizeAndRedistribute()

        resultHex = calculateMixedColor(selectedColors)
        recipeItems = calculateRecipe(selectedColors, getTotalWeight())

        saveColorMixture(
            currentUser["userId"],
            mixtureName,
            resultHex,
            getTotalWeight(),
            recipeItems,
        )

        refreshSavedMixtures()
        showMessage("Смесь сохранена")

    def handleExportRecipe(event):
        if len(selectedColors) < 2:
            showMessage("Для экспорта выберите минимум 2 цвета", True)
            return

        totalWeight = getTotalWeight()
        resultHex = calculateMixedColor(selectedColors)
        recipeItems = calculateRecipe(selectedColors, totalWeight)

        recipeLines = [
            "Рецепт смеси Lepka Helper",
            f"Название: {mixtureNameField.value.strip() or 'Моя смесь'}",
            f"Итоговый цвет: {resultHex}",
            f"Общий вес: {totalWeight} г",
            "",
            "Состав:",
        ]

        for recipeItem in recipeItems:
            recipeLines.append(
                f"- {recipeItem['name']}: {recipeItem['percent']}% / {recipeItem['grams']} г"
            )

        exportDirectory = Path("exports")
        exportDirectory.mkdir(exist_ok=True)

        exportPath = exportDirectory / f"recipe_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        exportPath.write_text("\n".join(recipeLines), encoding="utf-8")

        showMessage(f"Рецепт экспортирован: {exportPath}")

    def createPaletteButton(colorItem, onTap):
        return ft.GestureDetector(
            on_tap=lambda event, currentColor=colorItem: onTap(event, currentColor),
            content=ft.Container(
                width=70,
                height=70,
                border_radius=16,
                bgcolor=colorItem["hex"],
                padding=6,
                alignment=ft.alignment.bottom_center,
                border=ft.border.all(1, ft.Colors.GREY_300),
                content=ft.Text(
                    colorItem["name"],
                    size=9,
                    weight=ft.FontWeight.BOLD,
                    text_align=ft.TextAlign.CENTER,
                    color=getTextColorForBackground(colorItem["hex"]),
                ),
            ),
        )

    def rgbToHex(redValue, greenValue, blueValue):
        return "#{:02X}{:02X}{:02X}".format(
            int(round(redValue * 255)),
            int(round(greenValue * 255)),
            int(round(blueValue * 255)),
        )

    def getColorWheelHexAtPoint(xPosition, yPosition, wheelSize):
        center = wheelSize / 2
        dx = xPosition - center
        dy = center - yPosition
        radius = math.sqrt(dx * dx + dy * dy)
        maxRadius = wheelSize / 2

        if radius > maxRadius:
            return None

        saturation = min(1.0, radius / maxRadius)
        hue = (math.atan2(dy, dx) / (2 * math.pi)) % 1.0

        if saturation < 0.04:
            return "#FFFFFF"

        redValue, greenValue, blueValue = colorsys.hsv_to_rgb(hue, saturation, 1.0)
        return rgbToHex(redValue, greenValue, blueValue)

    def createPngChunk(chunkType, chunkData):
        chunkHeader = struct.pack(">I", len(chunkData)) + chunkType + chunkData
        checksum = zlib.crc32(chunkHeader[4:]) & 0xFFFFFFFF
        return chunkHeader + struct.pack(">I", checksum)

    def createColorWheelBase64(wheelSize):
        rawRows = []

        for yPosition in range(wheelSize):
            rowBytes = bytearray()
            rowBytes.append(0)

            for xPosition in range(wheelSize):
                center = wheelSize / 2
                dx = xPosition - center
                dy = center - yPosition
                radius = math.sqrt(dx * dx + dy * dy)
                maxRadius = wheelSize / 2 - 1

                if radius > maxRadius:
                    rowBytes.extend([255, 255, 255, 0])
                    continue

                saturation = min(1.0, radius / maxRadius)
                hue = (math.atan2(dy, dx) / (2 * math.pi)) % 1.0
                redValue, greenValue, blueValue = colorsys.hsv_to_rgb(hue, saturation, 1.0)

                rowBytes.extend([
                    int(round(redValue * 255)),
                    int(round(greenValue * 255)),
                    int(round(blueValue * 255)),
                    255,
                ])

            rawRows.append(bytes(rowBytes))

        pngHeader = b"\x89PNG\r\n\x1a\n"
        imageHeader = struct.pack(">IIBBBBB", wheelSize, wheelSize, 8, 6, 0, 0, 0)
        imageData = zlib.compress(b"".join(rawRows), 9)
        pngBytes = (
            pngHeader
            + createPngChunk(b"IHDR", imageHeader)
            + createPngChunk(b"IDAT", imageData)
            + createPngChunk(b"IEND", b"")
        )

        return base64.b64encode(pngBytes).decode("ascii")

    def createColorWheelTapArea(colorItem, leftPosition, topPosition, touchSize):
        return ft.Container(
            left=leftPosition,
            top=topPosition,
            width=touchSize,
            height=touchSize,
            content=ft.GestureDetector(
                on_tap=lambda event, currentColor=colorItem: handleTargetColorClick(event, currentColor),
                content=ft.Container(
                    width=touchSize,
                    height=touchSize,
                    bgcolor="#01000000",
                ),
            ),
        )

    def createRealColorWheel():
        wheelSize = 220
        touchSize = 11
        wheelControls = [
            ft.Image(
                src_base64=createColorWheelBase64(wheelSize),
                width=wheelSize,
                height=wheelSize,
                fit=ft.ImageFit.CONTAIN,
            )
        ]

        colorId = 1000

        for topPosition in range(0, wheelSize, touchSize):
            for leftPosition in range(0, wheelSize, touchSize):
                centerX = leftPosition + touchSize / 2
                centerY = topPosition + touchSize / 2
                hexColor = getColorWheelHexAtPoint(centerX, centerY, wheelSize)

                if hexColor is None:
                    continue

                colorId += 1
                wheelControls.append(
                    createColorWheelTapArea(
                        {
                            "colorId": colorId,
                            "name": hexColor,
                            "hex": hexColor,
                        },
                        leftPosition,
                        topPosition,
                        touchSize,
                    )
                )

        return ft.Container(
            width=wheelSize,
            height=wheelSize,
            alignment=ft.alignment.center,
            content=ft.Stack(
                width=wheelSize,
                height=wheelSize,
                controls=wheelControls,
            ),
        )

    colorGrid = ft.GridView(
        expand=False,
        runs_count=5,
        max_extent=80,
        spacing=10,
        run_spacing=10,
        child_aspect_ratio=1,
        height=190,
    )
    for color in BASE_COLORS:
        colorGrid.controls.append(createPaletteButton(color, handleColorClick))

    targetColorWheel = createRealColorWheel()

    def prewarmRecipeSearch():
        try:
            findClosestRecipeForTargetColor(targetHexField.value, getTotalWeight())
        except Exception:
            pass

    threading.Thread(target=prewarmRecipeSearch, daemon=True).start()

    totalWeightField.on_change = lambda event: (refreshRecipe(), page.update())

    updateTargetSelectedPreview(targetHexField.value)
    refreshRecipe()
    refreshSavedMixtures()

    return ft.ListView(
        expand=True,
        spacing=16,
        padding=16,
        controls=[
            ft.Text("Смешивание цветов", size=26, weight=ft.FontWeight.BOLD),
            resultColorBox,

            ft.Text("Базовая палитра", size=18, weight=ft.FontWeight.BOLD),
            ft.Text("Нажмите на цвет, чтобы добавить его в смесь.", size=13, color=ft.Colors.GREY_600),
            colorGrid,

            ft.Row(
                controls=[
                    ft.Text("Выбранные цвета", size=18, weight=ft.FontWeight.BOLD, expand=True),
                    miniResultBox,
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            selectedColorsColumn,

            totalWeightField,
            mixtureNameField,

            ft.Column(
                controls=[
                    ft.ElevatedButton(
                        "Сохранить смесь",
                        icon=ft.Icons.SAVE,
                        on_click=handleSaveMixture,
                        style=ft.ButtonStyle(bgcolor=PRIMARY_COLOR, color=ft.Colors.WHITE),
                    ),
                    ft.OutlinedButton(
                        "Экспорт TXT",
                        icon=ft.Icons.FILE_DOWNLOAD,
                        on_click=handleExportRecipe,
                    ),
                ],
                spacing=10,
            ),

            ft.Text("Рецепт", size=18, weight=ft.FontWeight.BOLD),
            ft.Card(content=ft.Container(padding=16, content=recipeColumn)),

            ft.Divider(),
            ft.Text("Подбор рецепта", size=18, weight=ft.FontWeight.BOLD),
            targetHexField,
            ft.ElevatedButton(
                "Подобрать рецепт",
                icon=ft.Icons.SEARCH,
                on_click=handleFindRecipe,
                style=ft.ButtonStyle(bgcolor=SECONDARY_COLOR, color=ft.Colors.WHITE),
            ),
            targetResultText,
            ft.Text("Цветовой круг для подбора", size=18, weight=ft.FontWeight.BOLD),
            ft.Text(
                "Нажмите на оттенок в круге — он подставится в HEX и сразу подберёт рецепт.",
                size=13,
                color=ft.Colors.GREY_600,
            ),
            ft.Container(
                alignment=ft.alignment.center,
                content=ft.Row(
                    controls=[
                        targetColorWheel,
                        targetPreviewColumn,
                    ],
                    spacing=12,
                    alignment=ft.MainAxisAlignment.CENTER,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            ),

            ft.Divider(),
            ft.Text("Мои смеси", size=18, weight=ft.FontWeight.BOLD),
            savedMixturesColumn,
        ],
    )


def createProjectsTab(page, currentUser):
    projectListColumn = ft.Column(spacing=10)

    projectNameField = ft.TextField(
        label="Название проекта",
        hint_text="Например: Милый котик",
        prefix_icon=ft.Icons.EDIT,
        border_radius=12,
    )

    categoryDropdown = ft.Dropdown(
        label="Категория",
        border_radius=12,
        options=[
            ft.dropdown.Option(categoryName)
            for categoryName in PROJECT_CATEGORIES
        ],
        value=PROJECT_CATEGORIES[0],
    )

    deadlineField = ft.TextField(
        label="Дедлайн",
        hint_text="Например: 25.04.2026",
        prefix_icon=ft.Icons.DATE_RANGE,
        border_radius=12,
    )

    descriptionField = ft.TextField(
        label="Описание / заметки",
        hint_text="Что нужно слепить, какие цвета использовать и т.д.",
        multiline=True,
        min_lines=3,
        max_lines=5,
        border_radius=12,
    )

    def showMessage(messageText, isError=False):
        page.snack_bar = ft.SnackBar(
            content=ft.Text(messageText),
            bgcolor=ft.Colors.RED_400 if isError else ft.Colors.GREEN_400,
        )
        page.snack_bar.open = True
        page.update()

    def clearProjectForm():
        projectNameField.value = ""
        categoryDropdown.value = PROJECT_CATEGORIES[0]
        deadlineField.value = ""
        descriptionField.value = ""

    def refreshProjectList():
        projectListColumn.controls.clear()

        if currentUser is None:
            projectListColumn.controls.append(
                ft.Text(
                    "Войдите в аккаунт, чтобы создавать и видеть проекты.",
                    color=ft.Colors.GREY_600,
                )
            )
            return

        projectItems = getUserProjects(currentUser["userId"])

        if len(projectItems) == 0:
            projectListColumn.controls.append(
                ft.Container(
                    padding=16,
                    border_radius=12,
                    bgcolor="#F5F5F5",
                    content=ft.Text(
                        "Пока нет проектов. Создайте первый проект выше.",
                        color=ft.Colors.GREY_700,
                    ),
                )
            )
            return

        for projectItem in projectItems:
            deadlineText = projectItem["deadlineDate"]

            if not deadlineText:
                deadlineText = "Без дедлайна"

            descriptionText = projectItem["descriptionText"]

            if not descriptionText:
                descriptionText = "Описание не добавлено"

            def handleDeleteProject(event, currentProjectId=projectItem["projectId"]):
                removeProject(currentProjectId, currentUser["userId"])
                showMessage("Проект удалён")
                refreshProjectList()
                page.update()

            newStepField = ft.TextField(
                label="Новый этап",
                hint_text="Например: слепить основу",
                border_radius=12,
            )

            stepControls = []

            if len(projectItem["stepItems"]) == 0:
                stepControls.append(
                    ft.Text(
                        "Этапов пока нет. Добавьте первый этап ниже.",
                        size=12,
                        color=ft.Colors.GREY_600,
                    )
                )
            else:
                for stepItem in projectItem["stepItems"]:
                    def handleStepChange(event, currentProjectId=projectItem["projectId"], currentStepId=stepItem["stepId"]):
                        changeProjectStepStatus(
                            currentProjectId,
                            currentStepId,
                            event.control.value,
                        )
                        refreshProjectList()
                        page.update()

                    def handleDeleteStep(event, currentProjectId=projectItem["projectId"], currentStepId=stepItem["stepId"]):
                        removeProjectStep(currentProjectId, currentStepId)
                        showMessage("Этап удалён")
                        refreshProjectList()
                        page.update()

                    stepControls.append(
                        ft.Row(
                            controls=[
                                ft.Checkbox(
                                    value=stepItem["isCompleted"],
                                    on_change=handleStepChange,
                                ),
                                ft.Text(
                                    stepItem["stepDescription"],
                                    expand=True,
                                    size=13,
                                ),
                                ft.IconButton(
                                    icon=ft.Icons.DELETE_OUTLINE,
                                    icon_size=18,
                                    icon_color=ft.Colors.RED_300,
                                    on_click=handleDeleteStep,
                                ),
                            ],
                            spacing=4,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        )
                    )

            def handleAddStep(event, currentProjectId=projectItem["projectId"], fieldControl=newStepField):
                successStatus, messageText, stepId = saveProjectStep(
                    currentProjectId,
                    fieldControl.value,
                )

                if not successStatus:
                    showMessage(messageText, True)
                    return

                fieldControl.value = ""
                showMessage(messageText)
                refreshProjectList()
                page.update()

            stepsBlock = ft.Column(
                controls=[
                    ft.Divider(),
                    ft.Text(
                        "Этапы проекта",
                        size=15,
                        weight=ft.FontWeight.BOLD,
                    ),
                    *stepControls,
                    ft.Row(
                        controls=[
                            ft.Container(expand=True, content=newStepField),
                            ft.IconButton(
                                icon=ft.Icons.ADD_CIRCLE,
                                icon_color=SECONDARY_COLOR,
                                on_click=handleAddStep,
                            ),
                        ],
                        spacing=8,
                    ),
                ],
                spacing=6,
            )

            projectListColumn.controls.append(
                ft.Card(
                    elevation=2,
                    content=ft.Container(
                        padding=14,
                        content=ft.Column(
                            controls=[
                                ft.Row(
                                    controls=[
                                        ft.Container(
                                            width=46,
                                            height=46,
                                            border_radius=23,
                                            bgcolor="#EFFFFD",
                                            alignment=ft.alignment.center,
                                            content=ft.Icon(
                                                name=ft.Icons.CHECKLIST,
                                                color=SECONDARY_COLOR,
                                                size=26,
                                            ),
                                        ),
                                        ft.Column(
                                            expand=True,
                                            controls=[
                                                ft.Text(
                                                    projectItem["projectName"],
                                                    size=17,
                                                    weight=ft.FontWeight.BOLD,
                                                ),
                                                ft.Text(
                                                    f"{projectItem['categoryName']} · {deadlineText}",
                                                    size=12,
                                                    color=ft.Colors.GREY_600,
                                                ),
                                            ],
                                            spacing=2,
                                        ),
                                        ft.IconButton(
                                            icon=ft.Icons.DELETE,
                                            icon_color=ft.Colors.RED_400,
                                            on_click=handleDeleteProject,
                                        ),
                                    ],
                                    spacing=10,
                                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                ),
                                ft.Text(
                                    descriptionText,
                                    size=13,
                                    color=ft.Colors.GREY_700,
                                ),
                                ft.ProgressBar(
                                    value=projectItem["progressPercent"] / 100,
                                    color=SECONDARY_COLOR,
                                    bgcolor="#DDDDDD",
                                ),
                                ft.Text(
                                    f"Прогресс: {projectItem['progressPercent']}%",
                                    size=12,
                                    color=ft.Colors.GREY_600,
                                ),
                                stepsBlock,
                            ],
                            spacing=8,
                        ),
                    ),
                )
            )

    def handleCreateProject(event):
        if currentUser is None:
            showMessage("Сначала войдите в аккаунт", True)
            return

        successStatus, messageText, projectId = saveProject(
            currentUser["userId"],
            projectNameField.value,
            categoryDropdown.value,
            deadlineField.value,
            descriptionField.value,
        )

        if not successStatus:
            showMessage(messageText, True)
            return

        clearProjectForm()
        refreshProjectList()
        showMessage(messageText)
        page.update()

    refreshProjectList()

    return ft.ListView(
        expand=True,
        spacing=14,
        padding=ft.padding.only(left=16, right=16, top=16, bottom=16),
        controls=[
            ft.Text(
                "Мои проекты",
                size=24,
                weight=ft.FontWeight.BOLD,
            ),
            ft.Card(
                elevation=2,
                content=ft.Container(
                    padding=16,
                    content=ft.Column(
                        controls=[
                            ft.Text(
                                "Создание проекта",
                                size=18,
                                weight=ft.FontWeight.BOLD,
                            ),
                            projectNameField,
                            categoryDropdown,
                            deadlineField,
                            descriptionField,
                            ft.ElevatedButton(
                                text="Сохранить проект",
                                icon=ft.Icons.SAVE,
                                height=48,
                                style=ft.ButtonStyle(
                                    bgcolor=SECONDARY_COLOR,
                                    color=ft.Colors.WHITE,
                                    shape=ft.RoundedRectangleBorder(radius=12),
                                ),
                                on_click=handleCreateProject,
                            ),
                        ],
                        spacing=12,
                    ),
                ),
            ),
            ft.Text(
                "Список проектов",
                size=18,
                weight=ft.FontWeight.BOLD,
            ),
            projectListColumn,
        ],
    )

def createProfileTab(page, nickname, email):
    currentUser = page.session.get("currentUser")

    if currentUser is None:
        profileData = None
    else:
        profileData = getUserProfile(currentUser["userId"])

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

    selectedAvatarPath = profileData.get("avatarPath", "") or ""

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
        foreground_image_src=selectedAvatarPath if selectedAvatarPath else None,
        content=None if selectedAvatarPath else ft.Text(
            profileData["nickname"][:1].upper(),
            size=30,
            weight=ft.FontWeight.BOLD,
        ),
        bgcolor=SECONDARY_COLOR,
        color=ft.Colors.WHITE,
    )

    editAvatarControl = ft.CircleAvatar(
        radius=42,
        foreground_image_src=selectedAvatarPath if selectedAvatarPath else None,
        content=None if selectedAvatarPath else ft.Text(
            profileData["nickname"][:1].upper(),
            size=30,
            weight=ft.FontWeight.BOLD,
        ),
        bgcolor=SECONDARY_COLOR,
        color=ft.Colors.WHITE,
    )

    avatarHintText = ft.Text(
        "Аватар выбран" if selectedAvatarPath else "Аватар не выбран",
        size=12,
        color=ft.Colors.GREY_600,
    )

    avatarPicker = ft.FilePicker()

    def refreshAvatar():
        avatarLetter = nicknameField.value[:1].upper() if nicknameField.value else "?"

        for avatarControl in [headerAvatarControl, editAvatarControl]:
            avatarControl.foreground_image_src = selectedAvatarPath if selectedAvatarPath else None
            avatarControl.content = None if selectedAvatarPath else ft.Text(
                avatarLetter,
                size=30,
                weight=ft.FontWeight.BOLD,
            )
        avatarHintText.value = "Аватар выбран" if selectedAvatarPath else "Аватар не выбран"
        page.update()

    def handleAvatarPicked(event):
        nonlocal selectedAvatarPath

        if event.files is None or len(event.files) == 0:
            return

        selectedFile = event.files[0]
        selectedAvatarPath = selectedFile.path or selectedFile.name or ""
        refreshAvatar()

    def handlePickAvatar(event):
        avatarPicker.pick_files(
            allow_multiple=False,
            allowed_extensions=["jpg", "jpeg", "png", "webp"],
            dialog_title="Выберите аватар",
        )

    def handleRemoveAvatar(event):
        nonlocal selectedAvatarPath
        selectedAvatarPath = ""
        refreshAvatar()

    avatarPicker.on_result = handleAvatarPicked
    page.overlay.append(avatarPicker)

    def showMessage(messageText, isError=False):
        page.snack_bar = ft.SnackBar(
            content=ft.Text(messageText),
            bgcolor=ft.Colors.RED_400 if isError else ft.Colors.GREEN_400,
        )
        page.snack_bar.open = True
        page.update()

    def handleLogout(event):
        page.session.clear()
        page.go("/auth")

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
            selectedAvatarPath,
        )

        if not successStatus:
            showMessage(messageText, True)
            return

        page.session.set(
            "currentUser",
            {
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

    def handleChangePassword(event):
        if currentUser is None:
            showMessage("Сначала войдите в аккаунт", True)
            return

        successStatus, messageText = changeUserPassword(
            currentUser["userId"],
            currentPasswordField.value,
            newPasswordField.value,
            repeatPasswordField.value,
        )

        if not successStatus:
            showMessage(messageText, True)
            return

        currentPasswordField.value = ""
        newPasswordField.value = ""
        repeatPasswordField.value = ""
        page.session.clear()
        showMessage(messageText)
        page.go("/auth")

    def handleSaveSettings(event):
        if currentUser is None:
            showMessage("Сначала войдите в аккаунт", True)
            return

        successStatus, messageText, updatedProfile = saveUserSettings(
            currentUser["userId"],
            themeDropdown.value,
            languageDropdown.value,
            notificationsSwitch.value,
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

    def handleDeleteAccount(event):
        if currentUser is None:
            showMessage("Сначала войдите в аккаунт", True)
            return

        if not deletePasswordField.value:
            showMessage("Введите пароль для подтверждения", True)
            return

        def closeDialog(event):
            confirmDialog.open = False
            page.update()

        def confirmDelete(event):
            successStatus, messageText = deleteUserAccount(
                currentUser["email"],
                deletePasswordField.value,
            )

            confirmDialog.open = False

            if not successStatus:
                showMessage(messageText, True)
                return

            page.session.clear()
            showMessage(messageText)
            page.go("/auth")

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

        page.dialog = confirmDialog
        confirmDialog.open = True
        page.update()

    colorWrapControls = []

    for colorName in FAVORITE_COLOR_OPTIONS:
        checkboxControl = ft.Checkbox(
            label=colorName,
            value=colorName in profileData["favoriteColors"],
        )

        favoriteColorCheckboxes.append(checkboxControl)
        colorWrapControls.append(checkboxControl)

    def createStatItem(countText, labelText, itemColor, backgroundColor):
        return ft.Container(
            expand=True,
            padding=12,
            border_radius=12,
            bgcolor=backgroundColor,
            content=ft.Column(
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Text(
                        str(countText),
                        size=24,
                        weight=ft.FontWeight.BOLD,
                        color=itemColor,
                    ),
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
                                            ft.Row(
                                                controls=[
                                                    ft.OutlinedButton(
                                                        text="Выбрать фото",
                                                        icon=ft.Icons.PHOTO_CAMERA,
                                                        on_click=handlePickAvatar,
                                                    ),
                                                    ft.OutlinedButton(
                                                        text="Убрать",
                                                        icon=ft.Icons.DELETE_OUTLINE,
                                                        on_click=handleRemoveAvatar,
                                                    ),
                                                ],
                                                wrap=True,
                                                spacing=8,
                                            ),
                                        ],
                                        spacing=8,
                                    ),
                                ],
                                spacing=14,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                            nicknameField,
                            bioField,
                            ageDropdown,
                            ft.Text(
                                "Любимые цвета, максимум 5",
                                size=13,
                                color=ft.Colors.GREY_600,
                            ),
                            ft.Wrap(
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


def createHomeView(page: ft.Page):
    currentUser = page.session.get("currentUser")

    if currentUser:
        nickname = currentUser["nickname"]
        email = currentUser["email"]
    else:
        nickname = "Гость"
        email = "guest@example.com"

    content_area = ft.Container(expand=True)

    def update_tab(e):
        idx = e.control.selected_index
        if idx == 0:
            content_area.content = createHomeTab(page, currentUser, nickname)
        elif idx == 1:
            content_area.content = createSearchTab(page, currentUser)
        elif idx == 2:
            content_area.content = createColorsTab(page, currentUser)
        elif idx == 3:
            content_area.content = createProjectsTab(page, currentUser)
        elif idx == 4:
            content_area.content = createProfileTab(page, nickname, email)

        page.update()

    nav_bar = ft.NavigationBar(
        selected_index=0,
        on_change=update_tab,
        destinations=[
            ft.NavigationDestination(icon=ft.Icons.HOME_OUTLINED, selected_icon=ft.Icons.HOME, label="Главная"),
            ft.NavigationDestination(icon=ft.Icons.SEARCH, selected_icon=ft.Icons.SEARCH, label="Поиск"),
            ft.NavigationDestination(icon=ft.Icons.PALETTE_OUTLINED, selected_icon=ft.Icons.PALETTE, label="Цвета"),
            ft.NavigationDestination(icon=ft.Icons.FOLDER_OUTLINED, selected_icon=ft.Icons.FOLDER, label="Проекты"),
            ft.NavigationDestination(icon=ft.Icons.PERSON_OUTLINE, selected_icon=ft.Icons.PERSON, label="Профиль"),
        ],
    )

    # Загружаем первый таб
    content_area.content = createHomeTab(page, currentUser, nickname)

    return ft.View(
        "/home",
        padding=0,
        controls=[
            ft.Container(
                expand=True,
                bgcolor=getPageBackgroundColor(page),
                content=ft.Column([
                    ft.Container(expand=True, content=content_area),
                    nav_bar
                ], expand=True)
            )
        ]
    )