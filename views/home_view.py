from ui_helpers import authenticatedAction, getCurrentUser, isWebClient, serverAction, confirmAction, createLoadError, showMessage as showPageMessage
from api_client import ApiError
import base64
import colorsys
import math
from urllib.parse import urlsplit
import struct
import threading
import zlib

import flet as ft
import uuid
from datetime import datetime
from pathlib import Path

from color_service import (
    BASE_COLORS, calculateMixedColor, calculateRecipe,
    findClosestRecipeForTargetColor, getUserColorMixtures,
    saveColorMixture, validateHexColor, deleteColorMixture, normalizeWeight, normalizeSelectedColors, normalizeProportion
)
from lesson_service import (SEARCH_CATEGORIES, IDEA_THEMES, IDEA_LEVELS, IDEA_PALETTES,
                            generateRandomIdea, getLessonById, searchLessons, getUserLessonState, saveUserLessonState)
from color_export import createRecipePng,createRecipePdf
from file_export import exportBytes
from clay_tools import recipeLengths
from views.color_scan import openColorScan
from download_service import createDownload
from date_field import createDeadlineField
from photo_picker import createPhotoPicker
from views.community_tab import createHomeTab, createPostCard
from views.project_sharing import createProjectSharing
from community_gateway import CommunityClient

from project_service import (
    PROJECT_CATEGORIES, changeProjectStepStatus, getUserProjects,
    removeProject, removeProjectStep, saveProject, saveProjectStep, editProject, editProjectStep,
    getProjectStepPhoto, saveProjectStepPhoto, removeProjectStepPhoto,
)
from views.profile_tab import createProfileTab
from views.project_step_order import createStepOrderButton
from views.project_transfer import createProjectExport, createProjectImport
from views.project_statistics import createProjectStatistics
from views.project_planner import createDeadlineSummary
from views.clay_tools_view import createClayTools
from lesson_library import (favoriteLessonIds,normalizeSearchQuery,recentSearches,rememberSearch,
                            clearSearchHistory,searchSuggestions,lessonSearchResults)
from views.lesson_library_view import createLessonFavorite,createLessonNotebook,createLessonShare
from views.model_gallery import createModelCard
from model_service import searchModels
from learning_assets import MODEL_ITEMS

from design_system import PRIMARY_COLOR
from design_system import SECONDARY_COLOR
LIGHT_BACKGROUND_COLOR = "#FFFFFF"
DARK_BACKGROUND_COLOR = "#121212"
DARK_TEXT_COLOR = "#222222"


def getPageBackgroundColor(page):
    return ft.Colors.SURFACE

def createSearchTab(page, currentUser, startEmpty=False, catalogMode=False):
    resultColumn = ft.ResponsiveRow(spacing=12,run_spacing=12)
    resultHeading=ft.Text('Результаты поиска',size=18,weight=ft.FontWeight.BOLD,visible=not startEmpty)
    ideaContainer = ft.Container()
    mainContentColumn = ft.Column(spacing=14)

    selectedLessonId = {"value": None}
    selectedStepIndex = {"value": 0}
    lessonState = {"value": None}
    searchVersion = {'value':0}
    owner = currentUser.get('sessionToken') if currentUser else None
    noteDraft=page.session.get('lessonNoteDraft') or {}
    if noteDraft.get('owner')!=owner:noteDraft={'owner':owner}
    page.session.set('lessonNoteDraft',noteDraft)
    cached = page.session.get('lessonSearchWorkspace') or {}
    if cached.get('owner') != owner:
        cached = {}
    suggestions = ft.Column(spacing=0)
    suggestionBox = ft.Container(content=suggestions,visible=False)
    history = ft.ExpansionTile(title=ft.Text('Недавние поиски'),controls=[],initially_expanded=False,
                               visible=currentUser is not None)

    searchField = ft.TextField(
        label="Поиск уроков и работ",
        hint_text="Например: котик, еда, дракон",
        prefix_icon=ft.Icons.SEARCH,
        border_radius=12,
        value=cached.get('query',''),
        max_length=120,
    )

    categoryDropdown = ft.Dropdown(
        label="Категория",
        value=cached.get('category','Все'),
        border_radius=12,
        options=[
            ft.dropdown.Option(categoryName)
            for categoryName in SEARCH_CATEGORIES
        ],
    )

    levelDropdown = ft.Dropdown(label='Сложность', value=cached.get('level','Все'),
        options=[ft.dropdown.Option(value) for value in ['Все', *IDEA_LEVELS]])
    timeDropdown = ft.Dropdown(label='Время до (минут)', value=cached.get('time','Любое'),
        options=[ft.dropdown.Option(value) for value in ['Любое', '30', '60', '120']])
    videoCheckbox = ft.Checkbox(label='Только с видео', value=cached.get('video',False))
    favoritesCheckbox = ft.Checkbox(label='Только избранные уроки',value=cached.get('favorites',False),disabled=currentUser is None)
    progressCheckbox = ft.Checkbox(label='Продолжить начатые уроки',value=cached.get('progress',False),disabled=currentUser is None)
    offlineCheckbox = ft.Checkbox(label='Только встроенные уроки и модели (офлайн)',value=cached.get('offline',False))
    sortDropdown = ft.Dropdown(label='Сортировка уроков',value=cached.get('sort','Релевантность'),
        options=[ft.dropdown.Option(value) for value in ('Релевантность','По времени','По названию')])
    ideaThemeDropdown = ft.Dropdown(label='Тематика идеи', value='Случайная',
        options=[ft.dropdown.Option(value) for value in ['Случайная', *IDEA_THEMES]])
    ideaLevelDropdown = ft.Dropdown(label='Сложность идеи', value='Случайная',
        options=[ft.dropdown.Option(value) for value in ['Случайная', *IDEA_LEVELS]])
    ideaPaletteDropdown = ft.Dropdown(label='Цветовая гамма', value='Случайная',
        options=[ft.dropdown.Option(value) for value in IDEA_PALETTES])
    ideaCountDropdown = ft.Dropdown(label='Количество цветов', value='3',
        options=[ft.dropdown.Option(str(value)) for value in range(1, 6)])

    def lessonAction(callback):
        return authenticatedAction(page, currentUser)(callback) if currentUser else callback

    def showMessage(messageText, isError=False):
        showPageMessage(page, messageText, isError)

    @authenticatedAction(page, currentUser)
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
            stepDescriptions=ideaData["steps"],
        )

        if not successStatus:
            showMessage(messageText, True)
            return

        showMessage("Идея добавлена в проекты")

    @authenticatedAction(page, currentUser)
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
            stepDescriptions=lessonItem["steps"],
        )

        if not successStatus:
            showMessage(messageText, True)
            return

        showMessage("Урок добавлен в проекты")

    @lessonAction
    def showLessonDetail(lessonId):
        saveWorkspace()
        if noteDraft.get('lessonId') != lessonId:
            noteDraft.pop('lessonId',None)
            noteDraft.pop('value',None)
        selectedLessonId["value"] = lessonId
        lessonState['value'] = getUserLessonState(currentUser['userId'], lessonId) if currentUser else {
            'lastStep': 0, 'completedSteps': [], 'checkedMaterials': [], 'isCompleted': False}
        selectedStepIndex['value'] = lessonState['value']['lastStep']
        refreshMainContent()
        page.update()

    def showSearchContent():
        navigate=page.session.get('navigateHomeTab')
        if callable(navigate):
            navigate(1)
            return
        selectedLessonId["value"] = None
        selectedStepIndex["value"] = 0
        refreshSearchResults()
        refreshMainContent()
        page.update()

    def createLessonDetail(lessonItem):
        steps = lessonItem["steps"]
        currentStepIndex = selectedStepIndex["value"]
        currentStepText = steps[currentStepIndex]
        state = lessonState['value']
        progressValue = len(state['completedSteps']) / len(steps)

        materialsText = ", ".join(lessonItem["materials"])
        def enlarge(event):
            dialog=ft.AlertDialog(title=ft.Text(f"Схема шага {currentStepIndex+1}"),
                content=ft.Container(width=500,height=360,content=ft.InteractiveViewer(min_scale=1,max_scale=4,
                    content=ft.Image(src=lessonItem['stepImages'][currentStepIndex],fit=ft.ImageFit.CONTAIN))),
                actions=[ft.TextButton('Закрыть',on_click=lambda event:page.close(dialog))])
            page.open(dialog)
        model=next(item for item in MODEL_ITEMS if item['lessonId']==lessonItem['lessonId'])
        def openModel(event):
            page.session.set('modelReturnLesson',lessonItem['lessonId'])
            page.go('/models/'+model['modelId'])

        def persistState():
            state['lastStep'] = selectedStepIndex['value']
            if currentUser:
                lessonState['value'] = saveUserLessonState(currentUser['userId'], lessonItem['lessonId'], state)

        @lessonAction
        def handlePreviousStep(event):
            selectedStepIndex['value'] = max(0, selectedStepIndex['value'] - 1)
            persistState()
            refreshMainContent()
            page.update()

        @lessonAction
        def handleNextStep(event):
            if currentUser and currentStepIndex not in state['completedSteps']:
                state['completedSteps'].append(currentStepIndex)
            selectedStepIndex['value'] = min(len(steps) - 1, currentStepIndex + 1)
            persistState()
            refreshMainContent()
            if currentStepIndex == len(steps) - 1:
                completed = lessonState['value']['isCompleted'] if currentUser else False
                showMessage('Урок завершён' if completed else 'Для сохранения завершения отметьте все шаги после входа', not completed)
            page.update()

        @lessonAction
        def handleStepChecked(event):
            values = state['completedSteps']
            if event.control.value and currentStepIndex not in values:
                values.append(currentStepIndex)
            elif not event.control.value and currentStepIndex in values:
                values.remove(currentStepIndex)
            persistState()
            refreshMainContent()
            page.update()

        def materialControl(index, material):
            @lessonAction
            def change(event):
                checked = state['checkedMaterials']
                if event.control.value and index not in checked:
                    checked.append(index)
                elif not event.control.value and index in checked:
                    checked.remove(index)
                persistState()
                page.update()
            return ft.Checkbox(label=material, value=index in state['checkedMaterials'],
                               disabled=currentUser is None, on_change=change)

        return ft.Column(
            spacing=14,
            controls=[
                ft.TextButton(
                    text="← Назад к поиску",
                    on_click=lambda event: showSearchContent(),
                ),
                ft.Row(wrap=True,controls=[createLessonFavorite(page,currentUser,lessonItem['lessonId'],refreshMainContent),
                                           createLessonShare(page,currentUser,lessonItem['lessonId'])]),
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
                                *[materialControl(index, material) for index, material in enumerate(lessonItem['materials'])],
                                ft.Text('Прогресс сохраняется после входа' if currentUser is None else 'Отметки сохраняются автоматически', size=12),
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
                                    color=ft.Colors.SECONDARY,
                                    bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                                ),
                                ft.Container(
                                    height=190,
                                    border_radius=18,
                                    bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                                    alignment=ft.alignment.center,
                                    content=ft.Image(src=lessonItem['stepImages'][currentStepIndex], fit=ft.ImageFit.CONTAIN),
                                ),
                                ft.Text('3D-схема текущего этапа, не фотография', size=12),
                                ft.Row(wrap=True,controls=[ft.TextButton('Увеличить схему',on_click=enlarge),
                                    ft.TextButton('3D этой фигурки',on_click=openModel)]),
                                ft.Text(
                                    currentStepText,
                                    size=16,
                                    color=ft.Colors.WHITE if page.theme_mode == ft.ThemeMode.DARK else DARK_TEXT_COLOR,
                                ),
                                ft.Checkbox(label='Шаг выполнен', value=currentStepIndex in state['completedSteps'],
                                    disabled=currentUser is None, on_change=handleStepChecked),
                                ft.Text('Урок завершён' if state['isCompleted'] else f"Выполнено шагов: {len(state['completedSteps'])} из {len(steps)}"),
                                ft.Row(
                                    wrap=True,
                                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                    controls=[
                                        ft.ElevatedButton(
                                            text="Предыдущий",
                                            icon=ft.Icons.ARROW_BACK,
                                            disabled=currentStepIndex == 0,
                                            height=44,
                                            on_click=handlePreviousStep,
                                        ),
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
                createLessonNotebook(page,currentUser,lessonItem['lessonId'],noteDraft),
            ],
        )

    def createLessonCard(lessonItem):
        tagText = ", ".join(lessonItem["tags"])
        state = getUserLessonState(currentUser['userId'],lessonItem['lessonId']) if currentUser else None

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
                                    bgcolor=ft.Colors.PRIMARY_CONTAINER,
                                    alignment=ft.alignment.center,
                                    content=ft.Image(src=lessonItem['previewImage'], fit=ft.ImageFit.CONTAIN),
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
                                            color=ft.Colors.ON_SURFACE_VARIANT,
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
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        ),
                        ft.Text(
                            f"Теги: {tagText}",
                            size=12,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        ),
                        ft.Row(
                            controls=[
                                ft.Text(
                                    (f"Шагов: {len(state['completedSteps'])}/{len(lessonItem['steps'])}" if state else 'Встроенный урок'),
                                    size=12,
                                    color=ft.Colors.ON_SURFACE_VARIANT,
                                ),
                                ft.Text(
                                    ('Завершён' if state and state['isCompleted'] else ''),
                                    size=12,
                                    color=ft.Colors.ON_SURFACE_VARIANT,
                                ),
                                ft.Container(expand=True),
                                ft.TextButton(
                                    text="Открыть",
                                    on_click=lambda event, currentLessonId=lessonItem["lessonId"]: showLessonDetail(currentLessonId),
                                ),
                            ],
                        ),
                        createLessonFavorite(page,currentUser,lessonItem['lessonId'],refreshSearchResults),
                    ],
                    spacing=8,
                ),
            ),
        )

    def refreshSearchResults():
        resultHeading.visible=True
        searchVersion['value'] += 1
        version = searchVersion['value']
        query = normalizeSearchQuery(searchField.value or '')
        saveWorkspace()
        if query and len(query)<2:
            resultColumn.controls = [ft.Text('Введите не меньше двух символов для поиска.')]
            return
        lessonItems = searchLessons(query, categoryDropdown.value, levelDropdown.value,
                                    None if timeDropdown.value == 'Любое' else timeDropdown.value, videoCheckbox.value)
        lessonItems = lessonSearchResults(lessonItems,query,currentUser['userId'] if currentUser else None,
            favoritesCheckbox.value,progressCheckbox.value,sortDropdown.value)
        controls = [createLessonCard(item) for item in lessonItems]
        if not catalogMode and not favoritesCheckbox.value and not progressCheckbox.value and not videoCheckbox.value:
            models=searchModels(query,categoryDropdown.value,levelDropdown.value,
                None if timeDropdown.value=='Любое' else timeDropdown.value,userId=currentUser['userId'] if currentUser else None)
            if models:
                controls.append(ft.Text('3D-модели',size=18,weight=ft.FontWeight.BOLD))
                controls.extend(createModelCard(page,item) for item in models)
        if not (offlineCheckbox.value or favoritesCheckbox.value or progressCheckbox.value):
            try:
                works = CommunityClient(currentUser).getPosts(search={
                    'queryText':query,'categoryName':categoryDropdown.value,'levelName':levelDropdown.value,
                    'maxTime':None if timeDropdown.value=='Любое' else timeDropdown.value,'onlyVideo':videoCheckbox.value})
                if works:
                    controls.append(ft.Text('Работы сообщества',size=18,weight=ft.FontWeight.BOLD))
                    from views.discovery import createPostTile
                    controls.extend(createPostTile(page,item,currentUser,lambda:(refreshSearchResults(),page.update())) for item in works)
            except ApiError as error:
                if error.statusCode==401:
                    if (page.session.get('currentUser') or {}).get('sessionToken')==owner:
                        raise
                    return
                controls.append(createLoadError(page,error,handleSearchChange))
        if not controls:
            empty = ('В избранном пока нет уроков. Откройте урок и нажмите «В избранное».'
                if favoritesCheckbox.value and currentUser and not favoriteLessonIds(currentUser['userId']) else
                'Ничего не найдено. Попробуйте изменить запрос или фильтры.')
            controls.append(ft.Text(empty))
        if searchVersion['value']==version and (page.session.get('currentUser') or {}).get('sessionToken')==owner:
            from design_system import polish
            for control in controls:
                if isinstance(control,ft.Card):control.col={'xs':12,'md':6}
                elif not isinstance(control,ft.Container):control.col=12
                polish(control)
            resultColumn.controls = controls

    def saveWorkspace():
        page.session.set('lessonSearchWorkspace',dict(owner=owner,query=searchField.value or '',
            category=categoryDropdown.value,level=levelDropdown.value,time=timeDropdown.value,
            video=videoCheckbox.value,favorites=favoritesCheckbox.value,progress=progressCheckbox.value,
            offline=offlineCheckbox.value,sort=sortDropdown.value))

    @authenticatedAction(page,currentUser)
    def clearHistory(event):
        @authenticatedAction(page,currentUser)
        def confirm():
            clearSearchHistory(currentUser['userId'])
            refreshHistory()
            page.update()
        confirmAction(page,'Очистить историю поиска?','Будут удалены только ваши недавние запросы на этом устройстве.',confirm)

    def refreshHistory():
        history.controls = []
        if currentUser:
            for query in recentSearches(currentUser['userId']):
                history.controls.append(ft.TextButton(query,on_click=lambda event,value=query:useQuery(value)))
            history.controls.append(ft.TextButton('Очистить историю',on_click=clearHistory))

    def refreshSuggestions():
        values = searchSuggestions(searchField.value or '',currentUser['userId'] if currentUser else None)
        suggestions.controls = [ft.TextButton(value,on_click=lambda event,value=value:useQuery(value)) for value in values]
        suggestionBox.visible = bool(values)
        suggestionBox.height = min(200,len(values)*44)
        suggestions.scroll = ft.ScrollMode.AUTO

    @lessonAction
    def useQuery(value):
        searchField.value = value
        submitSearch(None)

    @serverAction(page)
    @lessonAction
    def handleSearchChange(event=None):
        if selectedLessonId['value'] is not None:
            return
        try:
            searchField.error_text = None
            if getattr(event,'control',None) is searchField:
                refreshSuggestions()
            else:
                suggestionBox.visible = False
            refreshSearchResults()
        except ValueError as error:
            searchField.error_text = str(error)
        page.update()

    @serverAction(page)
    @lessonAction
    def submitSearch(event):
        if selectedLessonId['value'] is not None:
            return
        try:
            query = normalizeSearchQuery(searchField.value or '')
            if query and len(query)<2:
                raise ValueError('Введите не меньше двух символов')
            if currentUser and query:
                rememberSearch(currentUser['userId'],query)
            refreshHistory()
            suggestionBox.visible = False
            refreshSearchResults()
            searchField.error_text = None
        except ValueError as error:
            searchField.error_text = str(error)
        page.update()

    def handleGenerateIdea(event):
        ideaData = generateRandomIdea(ideaThemeDropdown.value, ideaLevelDropdown.value,
                                      ideaPaletteDropdown.value, int(ideaCountDropdown.value))

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
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        ),
                        ft.Text(
                            f"Сложность: {ideaData['level']}",
                            size=13,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        ),
                        ft.Text(
                            f"Примерное время: {ideaData['estimatedTime']} минут",
                            size=13,
                            color=ft.Colors.ON_SURFACE_VARIANT,
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
                ft.Row(wrap=True,controls=[
                    ft.OutlinedButton('3D-галерея',icon=ft.Icons.VIEW_IN_AR_OUTLINED,on_click=lambda event:page.go('/models')),
                    ft.OutlinedButton('Материалы преподавателей' if catalogMode else 'Учебный каталог',icon=ft.Icons.SCHOOL_OUTLINED,on_click=lambda event:page.go('/catalog') if catalogMode else __import__('views.discovery',fromlist=['openBuiltinCatalog']).openBuiltinCatalog(page,currentUser))]),
                ft.Row(wrap=True,controls=[ft.ElevatedButton('Найти',icon=ft.Icons.SEARCH,on_click=submitSearch),
                                           ft.TextButton('Сбросить фильтры',on_click=resetFilters)]),
                suggestionBox,
                history,
                favoritesCheckbox,
                ft.ExpansionTile(title=ft.Text('Фильтры уроков'),initially_expanded=False,
                    controls=[categoryDropdown,levelDropdown,timeDropdown,videoCheckbox,progressCheckbox,offlineCheckbox,sortDropdown]),
                resultHeading,
                resultColumn,
                ft.ExpansionTile(title=ft.Text('Генератор идей'),initially_expanded=False,controls=[
                ideaThemeDropdown,
                ideaLevelDropdown,
                ideaPaletteDropdown,
                ideaCountDropdown,
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
                ]),
            ]
        )

        if startEmpty or catalogMode:
            mainContentColumn.controls=[c for c in mainContentColumn.controls if not (isinstance(c,ft.Text) and c.value=='Поиск и идеи')]

    @lessonAction
    def resetFilters(event):
        searchField.value = ''
        categoryDropdown.value = levelDropdown.value = 'Все'
        timeDropdown.value = 'Любое'
        videoCheckbox.value = favoritesCheckbox.value = progressCheckbox.value = offlineCheckbox.value = False
        sortDropdown.value = 'Релевантность'
        if catalogMode:offlineCheckbox.value=True
        handleSearchChange(None)

    searchField.on_change = handleSearchChange
    searchField.on_submit = submitSearch
    categoryDropdown.on_change = handleSearchChange
    levelDropdown.on_change = handleSearchChange
    timeDropdown.on_change = handleSearchChange
    videoCheckbox.on_change = handleSearchChange
    favoritesCheckbox.on_change = handleSearchChange
    progressCheckbox.on_change = handleSearchChange
    offlineCheckbox.on_change = handleSearchChange
    sortDropdown.on_change = handleSearchChange

    if catalogMode:
        offlineCheckbox.value=True
        offlineCheckbox.disabled=True
        searchField.label='Поиск в учебном каталоге'
    refreshHistory()
    pendingLesson = page.session.get('openBuiltinLesson')
    page.session.set('openBuiltinLesson',None)
    if type(pendingLesson) is int and getLessonById(pendingLesson):
        showLessonDetail(pendingLesson)
    else:
        if not startEmpty:refreshSearchResults()
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
    barMassField=ft.TextField(label='Масса целого бруска, г',value='20',keyboard_type=ft.KeyboardType.NUMBER)
    barLengthField=ft.TextField(label='Длина целого бруска, см',value='8',keyboard_type=ft.KeyboardType.NUMBER)
    lengthEnabled=ft.Checkbox(label='Показывать длину в сантиметрах',value=False)
    mixtureSearch=ft.TextField(label='Поиск моих смесей по названию или HEX',max_length=120)
    recipeSearchState = {"token": 0}

    recipeColumn = ft.Column(spacing=8)
    savedMixturesColumn = ft.Column(spacing=8)
    selectedColorsColumn = ft.Column(spacing=8)

    def showMessage(messageText, isError=False):
        showPageMessage(page, messageText, isError)

    def getTextColorForBackground(hexColor):
        from design_system import swatchTextColor
        return swatchTextColor(hexColor)

    def getTotalWeight():
        try:
            weight = normalizeWeight((totalWeightField.value or '').strip())
            totalWeightField.error_text = None
            return weight
        except ValueError as error:
            totalWeightField.error_text = str(error)
            raise

    def normalizeAndRedistribute(changedColor=None, newValue=None):
        if not selectedColors:
            return

        if len(selectedColors) == 1:
            selectedColors[0]["proportion"] = 100.0
            return

        if changedColor is not None and newValue is not None:
            fixedValue = normalizeProportion(newValue)
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

        normalized = normalizeSelectedColors(selectedColors)
        for item, result in zip(selectedColors, normalized):
            item['proportion'] = result['proportion']

    resultColorText = ft.Text("#FFFFFF", size=32, weight=ft.FontWeight.BOLD)
    resultColorBox = ft.Container(
        height=112,
        border_radius=20,
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
        max_length=80,
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
        color=ft.Colors.ON_SURFACE_VARIANT,
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
        savedMixturesColumn.controls = []

        if not currentUser:
            savedMixturesColumn.controls.append(
                ft.Text("Войдите в аккаунт для просмотра смесей", color=ft.Colors.ON_SURFACE_VARIANT)
            )
            return

        mixtures = getUserColorMixtures(currentUser["userId"])

        if not mixtures:
            savedMixturesColumn.controls.append(
                ft.Text("Пока нет сохранённых смесей", color=ft.Colors.ON_SURFACE_VARIANT)
            )
            return

        words=(mixtureSearch.value or '').casefold().split()
        mixtures=[m for m in mixtures if all(word in (m['mixtureName']+' '+m['resultHex']).casefold() for word in words)]
        if not mixtures:savedMixturesColumn.controls.append(ft.Text('Смесей по этому запросу нет.'))
        for mixture in mixtures:
            @authenticatedAction(page, currentUser)
            def handleDeleteMixture(event, currentMixtureId=mixture["mixtureId"]):
                deleteColorMixture(currentUser["userId"], currentMixtureId)
                refreshSavedMixtures()
                page.update()
                showMessage("Смесь удалена")

            @authenticatedAction(page, currentUser)
            def handleOpenMixture(event, item=dict(mixture)):
                if item['recipeError']:
                    showMessage('Сохранённый рецепт повреждён. Исходные данные не изменены', True)
                    return
                selectedColors[:] = [{**color, 'proportion': color['percent']} for color in item['recipeItems']]
                totalWeightField.value = str(item['totalWeight'])
                mixtureNameField.value = item['mixtureName']
                refreshRecipe()
                showMix=page.session.get('showColorMix')
                if callable(showMix):showMix()
                page.update()

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
                                            "Рецепт повреждён" if mixture["recipeError"] else f"{mixture['resultHex']} • {mixture['totalWeight']} г",
                                            size=12,
                                            color=ft.Colors.ON_SURFACE_VARIANT,
                                        ),
                                    ],
                                ),
                                ft.IconButton(icon=ft.Icons.OPEN_IN_NEW, tooltip='Открыть рецепт', on_click=handleOpenMixture),
                                ft.IconButton(
                                    icon=ft.Icons.DELETE,
                                    tooltip="Удалить смесь",
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

        try:
            totalWeight = getTotalWeight()
        except ValueError:
            totalWeight = None
        resultHex = calculateMixedColor(selectedColors) if selectedColors else "#FFFFFF"
        recipeItems = calculateRecipe(selectedColors, totalWeight) if selectedColors and totalWeight is not None else []

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
                    bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                    content=ft.Text(
                        "Добавьте оттенки из палитры выше.",
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    ),
                )
            )
        else:
            for colorItem in selectedColors:
                def handleSliderChange(event, currentColor=colorItem):
                    try:
                        normalizeAndRedistribute(currentColor, float(event.control.value))
                    except (ValueError, TypeError):
                        showMessage("Введите долю от 0 до 100", True)
                        return
                    refreshRecipe()
                    page.update()

                def handlePercentSubmit(event, currentColor=colorItem):
                    try:
                        value = normalizeProportion(event.control.value or '0')
                    except ValueError as error:
                        event.control.error_text = str(error)
                        event.control.value = str(currentColor['proportion'])
                        page.update()
                        showMessage(str(error), True)
                        return
                    event.control.error_text = None

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

        if lengthEnabled.value and recipeItems:
            try:
                for item in recipeLengths(recipeItems,barMassField.value,barLengthField.value):
                    recipeColumn.controls.append(ft.Text(f"{item['name']}: {item['centimeters']:g} см"))
            except ValueError as error:recipeColumn.controls.append(ft.Text(str(error),color=ft.Colors.RED))

        if not recipeItems:
            recipeColumn.controls.append(
                ft.Text("Рецепт появится после выбора минимум одного цвета.", color=ft.Colors.ON_SURFACE_VARIANT)
            )

    def handleColorClick(event, colorItem):
        if any(color["colorId"] == colorItem["colorId"] for color in selectedColors):
            showMessage("Цвет уже выбран", True)
            return

        if len(selectedColors) >= 5:
            showMessage("Максимум 5 цветов", True)
            return

        newProportion = 100.0 / (len(selectedColors) + 1)
        for item in selectedColors:
            item["proportion"] *= (100.0 - newProportion) / 100.0
        selectedColors.append(
            {
                "colorId": colorItem["colorId"],
                "name": colorItem["name"],
                "hex": colorItem["hex"],
                "proportion": newProportion,
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
        recipeSearchState["token"] += 1
        currentToken = recipeSearchState["token"]
        targetHex = normalizeTargetHexText(targetHexField.value)

        try:
            if not validateHexColor(targetHex):
                raise ValueError("Введите цвет в формате HEX, например #8A4F3A")
            totalWeight = getTotalWeight()
        except ValueError as error:
            targetResultText.value = str(error)
            targetRecipeText.value = "—"
            showMessage(str(error), True)
            safePageUpdate()
            return

        targetHexField.value = targetHex
        updateTargetSelectedPreview(targetHex)
        targetRecipeText.value = "..."
        targetRecipeText.color = ft.Colors.BLACK
        targetResultText.value = "Подбираю рецепт..."
        safePageUpdate()

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

    @authenticatedAction(page, currentUser)
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

        try:
            weight = getTotalWeight()
            resultHex = calculateMixedColor(selectedColors)
            recipeItems = calculateRecipe(selectedColors, weight)
            saveColorMixture(currentUser['userId'], mixtureName, resultHex, weight, recipeItems)
        except ValueError as error:
            showMessage(str(error), True)
            return

        refreshSavedMixtures()
        page.update()
        showMessage("Смесь сохранена")

    def colorAction(callback):
        return authenticatedAction(page, currentUser)(callback) if currentUser else callback

    @colorAction
    def handleExportRecipe(event,asPdf=False):
        try:
            calibration=(barMassField.value,barLengthField.value) if lengthEnabled.value else None
            content=(createRecipePdf if asPdf else createRecipePng)(mixtureNameField.value,selectedColors,getTotalWeight(),calibration)
            exportBytes(page,currentUser,content,'lepka-recipe.'+('pdf' if asPdf else 'png'),'application/pdf' if asPdf else 'image/png')
        except (ValueError,OSError) as error:showMessage(str(error),True)

    @colorAction
    def scanColor(event):
        if not currentUser:showMessage('Войдите для выбора цвета с камеры или фото',True);return
        def apply(hexColor):
            targetHexField.value=hexColor;updateTargetSelectedPreview(hexColor);page.update()
        openColorScan(page,currentUser,apply,lambda color:handleColorClick(None,color))

    def createPaletteButton(colorItem, onTap):
        return ft.GestureDetector(
            on_tap=lambda event, currentColor=colorItem: onTap(event, currentColor),
            content=ft.Container(
                width=78,
                height=64,
                border_radius=16,
                bgcolor=colorItem["hex"],
                padding=3,
                alignment=ft.alignment.bottom_center,
                border=ft.border.all(1, ft.Colors.GREY_300),
                content=ft.Text(
                    colorItem["name"],
                    size=10,
                    weight=ft.FontWeight.BOLD,
                    text_align=ft.TextAlign.CENTER,
                    color=getTextColorForBackground(colorItem["hex"]),
                ),
            ),
        )

    def createRealColorWheel():
        from color_wheel import createColorWheelBase64, getColorWheelHexAtPoint
        def choose(event):
            value = getColorWheelHexAtPoint(event.local_x, event.local_y, 220)
            if value:
                handleTargetColorClick(event, {'hex': value})
        return ft.GestureDetector(on_tap_down=choose, content=ft.Image(
            src_base64=createColorWheelBase64(220), width=220, height=220, fit=ft.ImageFit.CONTAIN))

    colorGrid = ft.Row(wrap=True,spacing=8,run_spacing=8)
    for color in BASE_COLORS:
        colorGrid.controls.append(createPaletteButton(color, handleColorClick))
    mixtureSearch.on_change=colorAction(lambda e:(refreshSavedMixtures(),page.update()))

    targetColorWheel = createRealColorWheel()

    totalWeightField.on_change = lambda event: (refreshRecipe(), page.update())
    lengthEnabled.on_change=lambda event:(refreshRecipe(),page.update())

    updateTargetSelectedPreview(targetHexField.value)
    refreshRecipe()
    refreshSavedMixtures()

    layout = ft.ListView(
        build_controls_on_demand=False,
        expand=True,
        spacing=16,
        padding=16,
        controls=[
            ft.Text("Смешивание цветов", size=26, weight=ft.FontWeight.BOLD),
            createClayTools(page, currentUser),
            resultColorBox,

            ft.Text("Базовая палитра", size=18, weight=ft.FontWeight.BOLD),
            ft.Text("Нажмите на цвет, чтобы добавить его в смесь.", size=13, color=ft.Colors.ON_SURFACE_VARIANT),
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
            ft.ExpansionTile(title=ft.Text('Расчёт длины пластилина (см)'),controls=[ft.Container(padding=12,content=ft.Column(spacing=12,controls=[barMassField,barLengthField,lengthEnabled,
                ft.Text('Введите массу и длину своего целого бруска. Формула: масса компонента / масса бруска × длина бруска. Для всех цветов предполагаются одинаковые бруски.'),
                ft.TextButton('Пересчитать сантиметры',on_click=lambda e:(refreshRecipe(),page.update()))]))]),
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
                        "Экспорт PNG",
                        icon=ft.Icons.FILE_DOWNLOAD,
                        on_click=handleExportRecipe,
                    ),
                    ft.OutlinedButton('Экспорт PDF',icon=ft.Icons.PICTURE_AS_PDF,on_click=lambda e:handleExportRecipe(e,asPdf=True)),
                ],
                spacing=10,
            ),

            ft.Text("Рецепт", size=18, weight=ft.FontWeight.BOLD),
            ft.Card(content=ft.Container(padding=16, content=recipeColumn)),

            ft.Divider(),
            ft.Text("Подбор рецепта", size=18, weight=ft.FontWeight.BOLD),
            ft.OutlinedButton('Сканировать цвет с камеры',icon=ft.Icons.CAMERA_ALT_OUTLINED,on_click=scanColor),
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
                color=ft.Colors.ON_SURFACE_VARIANT,
            ),
            ft.Container(
                alignment=ft.alignment.center,
                content=ft.Row(
                    controls=[
                        targetColorWheel,
                        targetPreviewColumn,
                    ],
                    spacing=12,
                    wrap=True,
                    alignment=ft.MainAxisAlignment.CENTER,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            ),

            ft.Divider(),
            ft.Text("Мои смеси", size=18, weight=ft.FontWeight.BOLD),
            mixtureSearch,
            savedMixturesColumn,
        ],
    )

    from design_system import workspace, disclosure, polish
    controls=layout.controls
    pick=next(i for i,c in enumerate(controls) if isinstance(c,ft.Text) and c.value=='Подбор рецепта')
    saved=next(i for i,c in enumerate(controls) if isinstance(c,ft.Text) and c.value=='Мои смеси')
    mix=controls[2:pick-1]
    tools=disclosure('Инструменты мастерской',[controls[1]],ft.Icons.HANDYMAN_OUTLINED)
    mixing=ft.ResponsiveRow(spacing=20,run_spacing=16,controls=[
        ft.Column(mix[1:4],spacing=12,col={'xs':12,'md':6}),
        ft.Column([mix[0],*mix[4:],tools],spacing=12,col={'xs':12,'md':6})])
    layout=workspace(page,'Цвета', [('Смешать',[mixing]),('Подобрать',controls[pick+1:saved-1]),('Мои смеси',controls[saved+1:])])
    page.session.set('showColorMix',lambda:layout.select_workspace(0))
    return polish(layout)


def createProjectsTab(page, currentUser, mode="all", onCreated=None, projectId=None, onChanged=None):
    projectListColumn = ft.Column(spacing=10)
    statisticsCard = createProjectStatistics(page, currentUser) if currentUser and mode!='create' else ft.Container()
    deadlineSummary = ft.Container()
    requested = page.session.get('plannerProject') or {}
    page.session.set('plannerProject', None)
    projectTarget = {'id': projectId if mode=='detail' else requested.get('projectId') if currentUser and requested.get('owner')==currentUser.get('sessionToken') else None}
    @authenticatedAction(page,currentUser)
    def showAllProjects(event):
        projectTarget['id']=None
        refreshProjectList();page.update()
    showAllButton=ft.TextButton('Показать все проекты',on_click=showAllProjects,visible=projectTarget['id'] is not None)

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

    deadlineField = createDeadlineField(page)

    descriptionField = ft.TextField(
        label="Описание / заметки",
        hint_text="Что нужно слепить, какие цвета использовать и т.д.",
        multiline=True,
        min_lines=3,
        max_lines=5,
        border_radius=12,
    )

    def showMessage(messageText, isError=False):
        showPageMessage(page, messageText, isError)

    def clearProjectForm():
        projectNameField.value = ""
        categoryDropdown.value = PROJECT_CATEGORIES[0]
        deadlineField.value = ""
        descriptionField.value = ""

    def refreshProjectList():
        if mode=='create':return
        # Собираем замену вне живого дерева. Промежуточный page.update() с пустым
        # списком портил размеры ленивых элементов после закрытия редактора.
        newProjectControls = []

        if currentUser is None:
            newProjectControls.append(
                ft.Text(
                    "Войдите в аккаунт, чтобы создавать и видеть проекты.",
                    color=ft.Colors.ON_SURFACE_VARIANT,
                )
            )
            projectListColumn.controls = newProjectControls
            return

        if mode=='list':
            from database import getProjectsByUserId
            projectItems=[dict(row) for row in getProjectsByUserId(currentUser["userId"])]
        else:projectItems = getUserProjects(currentUser["userId"])
        statisticsCard.data()
        deadlineSummary.content = createDeadlineSummary(page,currentUser)
        showAllButton.visible = projectTarget['id'] is not None
        if projectTarget['id'] is not None:
            projectItems = [item for item in projectItems if item['projectId']==projectTarget['id']]

        if len(projectItems) == 0:
            newProjectControls.append(
                ft.Container(
                    padding=16,
                    border_radius=12,
                    bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                    content=ft.Text(
                        "Выбранный проект недоступен. Нажмите «Показать все проекты»." if projectTarget['id'] is not None else "Пока нет проектов. Создайте первый проект выше.",
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    ),
                )
            )
            projectListColumn.controls = newProjectControls
            return

        for projectItem in projectItems:
            if mode=='list':
                from views.discovery import creationDialog
                @authenticatedAction(page,currentUser)
                def openProject(event,pid=projectItem['projectId']):
                    body=createProjectsTab(page,currentUser,mode='detail',projectId=pid,
                        onChanged=lambda:(refreshProjectList(),page.update()))
                    creationDialog(page,'Проект',body)
                newProjectControls.append(ft.Card(data=projectItem['projectId'],content=ft.ListTile(
                    title=ft.Text(projectItem['projectName'],weight=ft.FontWeight.W_600),
                    subtitle=ft.Text(projectItem['categoryName']+' · '+(projectItem['deadlineDate'] or 'Без дедлайна')),
                    trailing=ft.Icon(ft.Icons.CHEVRON_RIGHT),on_click=openProject)))
                continue
            deadlineText = projectItem["deadlineDate"]

            if not deadlineText:
                deadlineText = "Без дедлайна"

            descriptionText = projectItem["descriptionText"]

            if not descriptionText:
                descriptionText = "Описание не добавлено"

            @authenticatedAction(page, currentUser)
            def handleDeleteProject(event, currentProjectId=projectItem["projectId"]):
                @authenticatedAction(page, currentUser)
                def delete():
                    deleted = removeProject(currentProjectId, currentUser["userId"])
                    showMessage("Проект удалён" if deleted else "Проект не найден или недоступен", not deleted)
                    refreshProjectList()
                    page.update()
                confirmAction(page, 'Удалить личный проект?',
                    'Будут удалены его этапы, фото и смеси проекта. Опубликованный мастер-класс сохранится.', delete)

            @authenticatedAction(page, currentUser)
            def handleEditProject(event, currentProject=projectItem):
                nameField = ft.TextField(label='Название проекта', value=currentProject['projectName'])
                categoryField = ft.Dropdown(label='Категория', value=currentProject['categoryName'],
                    options=[ft.dropdown.Option(value) for value in PROJECT_CATEGORIES])
                dateField = createDeadlineField(page, currentProject['deadlineDate'])
                notesField = ft.TextField(label='Описание / заметки', value=currentProject['descriptionText'], multiline=True)

                @authenticatedAction(page, currentUser)
                def save(event):
                    success, message = editProject(currentProject['projectId'], currentUser['userId'],
                        nameField.value, categoryField.value, dateField.value, notesField.value)
                    if success:
                        page.close(dialog)
                        refreshProjectList()
                    showMessage(message, not success)
                    page.update()

                dialog = ft.AlertDialog(modal=True, title=ft.Text('Редактирование проекта'),
                    content=ft.Column(tight=True, scroll=ft.ScrollMode.AUTO,
                                      controls=[nameField, categoryField, dateField, notesField]),
                    actions=[ft.TextButton(text='Отмена', on_click=lambda event: page.close(dialog)),
                             ft.ElevatedButton(text='Сохранить изменения', on_click=save)])
                page.open(dialog)

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
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    )
                )
            else:
                for stepItem in projectItem["stepItems"]:
                    @authenticatedAction(page, currentUser)
                    def handleStepChange(event, currentProjectId=projectItem["projectId"], currentStepId=stepItem["stepId"]):
                        try:
                            progress = changeProjectStepStatus(currentProjectId, currentStepId,
                                                               event.control.value, currentUser['userId'])
                        except ValueError as error:
                            showMessage(str(error), True)
                            refreshProjectList()
                            page.update()
                            return
                        if progress is None:
                            showMessage("Этап не найден или недоступен", True)
                        refreshProjectList()
                        page.update()

                    @authenticatedAction(page, currentUser)
                    def handleDeleteStep(event, currentProjectId=projectItem["projectId"], currentStepId=stepItem["stepId"]):
                        @authenticatedAction(page, currentUser)
                        def delete():
                            progress = removeProjectStep(currentProjectId, currentStepId, currentUser["userId"])
                            showMessage("Этап удалён" if progress is not None else "Этап не найден или недоступен", progress is None)
                            refreshProjectList()
                            page.update()
                        confirmAction(page, 'Удалить этап?', 'Будут удалены этап и его фото. Прогресс проекта пересчитается.', delete)

                    @authenticatedAction(page, currentUser)
                    def handleEditStep(event, currentProjectId=projectItem['projectId'], currentStep=dict(stepItem)):
                        textField = ft.TextField(label='Описание этапа', value=currentStep['stepDescription'], multiline=True)

                        @authenticatedAction(page, currentUser)
                        def save(event):
                            success, message = editProjectStep(currentProjectId, currentStep['stepId'],
                                                              currentUser['userId'], textField.value)
                            if success:
                                page.close(dialog)
                                refreshProjectList()
                            showMessage(message, not success)
                            page.update()

                        dialog = ft.AlertDialog(modal=True, title=ft.Text('Редактирование этапа'), content=textField,
                            actions=[ft.TextButton(text='Отмена', on_click=lambda event: page.close(dialog)),
                                     ft.ElevatedButton(text='Сохранить этап', on_click=save)])
                        page.open(dialog)

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
                                ft.IconButton(icon=ft.Icons.EDIT_OUTLINED, tooltip="Изменить этап", on_click=handleEditStep),
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

                    def photoSelected(photo, projectId=projectItem['projectId'], stepId=stepItem['stepId']):
                        success, message = saveProjectStepPhoto(projectId, stepId, currentUser['userId'], photo)
                        if success:
                            refreshProjectList()
                        return success, message

                    @authenticatedAction(page, currentUser)
                    def deletePhoto(event, projectId=projectItem['projectId'], stepId=stepItem['stepId']):
                        success, message = removeProjectStepPhoto(projectId, stepId, currentUser['userId'])
                        if success:
                            refreshProjectList()
                        showMessage(message, not success)
                        page.update()

                    if stepItem['hasPhoto']:
                        data = getProjectStepPhoto(projectItem['projectId'], stepItem['stepId'], currentUser['userId'])
                        if data:
                            stepControls.append(ft.Image(src_base64=base64.b64encode(data).decode(),
                                                         height=150, fit=ft.ImageFit.CONTAIN))
                        stepControls.append(ft.TextButton('Убрать фото этапа', on_click=deletePhoto))
                    else:
                        hint = ('Старый завершённый этап: добавьте фото' if stepItem['isCompleted']
                                else 'Добавьте фото перед завершением этапа')
                        stepControls.append(ft.Text(hint, size=12))
                    stepControls.append(createPhotoPicker(page, currentUser, photoSelected,
                        'Заменить фото этапа' if stepItem['hasPhoto'] else 'Добавить фото этапа'))
                    stepControls.append(ft.Divider())

            @authenticatedAction(page, currentUser)
            def handleAddStep(event, currentProjectId=projectItem["projectId"], fieldControl=newStepField):
                successStatus, messageText, stepId = saveProjectStep(
                    currentProjectId,
                    fieldControl.value,
                    currentUser["userId"],
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

            detailCard = ft.Card(
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
                                                color=ft.Colors.SECONDARY,
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
                                                    color=ft.Colors.ON_SURFACE_VARIANT,
                                                ),
                                            ],
                                            spacing=2,
                                        ),
                                        ft.IconButton(icon=ft.Icons.EDIT, tooltip="Изменить проект", on_click=handleEditProject),
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
                                    color=ft.Colors.ON_SURFACE_VARIANT,
                                ),
                                ft.ProgressBar(
                                    value=projectItem["progressPercent"] / 100,
                                    color=ft.Colors.SECONDARY,
                                    bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                                ),
                                ft.Text(
                                    f"Прогресс: {projectItem['progressPercent']}%",
                                    size=12,
                                    color=ft.Colors.ON_SURFACE_VARIANT,
                                ),
                                createProjectSharing(page, currentUser, projectItem, refreshProjectList),
                                createStepOrderButton(page, currentUser, projectItem['projectId'], refreshProjectList),
                                createProjectExport(page, currentUser, projectItem['projectId']),
                                stepsBlock,
                            ],
                            spacing=8,
                        ),
                    ),
                )
            newProjectControls.append(detailCard)

        projectListColumn.controls = newProjectControls
        if onChanged:onChanged()

    @authenticatedAction(page, currentUser)
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
        if onCreated:onCreated(projectId)
        showMessage(messageText)
        page.update()

    refreshProjectList()

    layout = ft.ListView(
        expand=True,
        build_controls_on_demand=False,
        spacing=14,
        padding=ft.padding.only(left=16, right=16, top=16, bottom=16),
        controls=[
            ft.Text(
                "Мои проекты",
                size=24,
                weight=ft.FontWeight.BOLD,
            ),
            showAllButton,
            *([projectListColumn] if projectTarget['id'] is not None else []),
            statisticsCard,
            deadlineSummary,
            createProjectImport(page, currentUser, refreshProjectList) if currentUser else ft.Container(),
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
            *([] if projectTarget['id'] is not None else [projectListColumn]),
        ],
    )

    from design_system import disclosure, polish
    controls=layout.controls
    createIndex=next(i for i,c in enumerate(controls) if isinstance(c,ft.Card) and isinstance(c.content,ft.Container) and isinstance(c.content.content,ft.Column) and any(isinstance(t,ft.Text) and t.value=='Создание проекта' for t in c.content.content.controls))
    form=controls[createIndex].content.content.controls[1:]
    if mode=='create':layout.controls=[ft.Column(form,spacing=14)]
    elif mode=='detail':layout.controls=[projectListColumn]
    elif mode=='all':return polish(layout)
    else:
        overview=controls[2:createIndex] if projectTarget['id'] is None else controls[3:createIndex]
        layout.controls=[ft.Column(spacing=14,controls=[ft.Text('Мои проекты',size=24,weight=ft.FontWeight.W_600),projectListColumn,
            disclosure('Обзор и перенос проектов',overview,ft.Icons.INSIGHTS_OUTLINED)])]
    return polish(layout)

def createHomeView(page: ft.Page):
    try:
        currentUser = getCurrentUser(page)
    except ApiError:
        # Только оболочка и сообщение об ошибке. Действия по-прежнему требуют
        # проверки настоящей сессии; локального входа вместо API здесь нет.
        currentUser = page.session.get('currentUser')

    if currentUser:
        nickname = currentUser["nickname"]
        email = currentUser["email"]
    else:
        nickname = "Гость"
        email = "guest@example.com"

    content_area = ft.Container(expand=True)
    from views.community_notices import createNoticeButton
    from views.offline_controls import createConnectionBanner
    connectionBanner=createConnectionBanner(page,currentUser)

    @serverAction(page)
    def loadTab(index):
        try:
            page.session.set('resizeDiscovery',None)
            if currentUser is not None:
                sessionUser = getCurrentUser(page)
                if sessionUser is None:
                    page.go('/auth')
                    return
                if sessionUser['sessionToken'] != currentUser['sessionToken']:
                    return
            factories = [lambda: createHomeTab(page, currentUser, nickname, mode="feed"),
                         lambda: createSearchTab(page, currentUser), lambda: createColorsTab(page, currentUser),
                         lambda: createProjectsTab(page, currentUser, mode="list"), lambda: createProfileTab(page, nickname, email),
                         lambda: createNoticeButton(page,currentUser,asTab=True)]
            if not 0 <= index < len(factories):
                return
            page.session.set('homeTab',index)
            from design_system import polish
            content_area.content = polish(factories[index]())
        except ApiError as error:
            if error.statusCode == 401:
                raise
            content_area.content = createLoadError(page, error, lambda: loadTab(index))
        page.update()

    def update_tab(event):
        loadTab(event.control.selected_index)

    initialTab = page.session.get('homeTab')
    if type(initialTab) is not int or not 0 <= initialTab < 6:
        initialTab = 0
    nav_bar = ft.NavigationBar(
        selected_index=1 if initialTab==5 else (0 if initialTab==1 else initialTab),
        on_change=update_tab,
        destinations=[
            ft.NavigationBarDestination(icon=ft.Icons.HOME_OUTLINED, selected_icon=ft.Icons.HOME, label="Главная"),
            ft.NavigationBarDestination(icon=ft.Icons.NOTIFICATIONS_OUTLINED, selected_icon=ft.Icons.NOTIFICATIONS, label="Входящие"),
            ft.NavigationBarDestination(icon=ft.Icons.PALETTE_OUTLINED, selected_icon=ft.Icons.PALETTE, label="Цвета"),
            ft.NavigationBarDestination(icon=ft.Icons.FOLDER_OUTLINED, selected_icon=ft.Icons.FOLDER, label="Проекты"),
            ft.NavigationBarDestination(icon=ft.Icons.PERSON_OUTLINE, selected_icon=ft.Icons.PERSON, label="Профиль"),
        ],
    )

    from design_system import ICON
    labels=['Главная','Уведомления','Цвета','Проекты','Профиль']
    icons=[ft.Icons.HOME_OUTLINED,ft.Icons.NOTIFICATIONS_OUTLINED,ft.Icons.PALETTE_OUTLINED,ft.Icons.FOLDER_OUTLINED,ft.Icons.PERSON_OUTLINE]
    rail=ft.NavigationRail(expand=True,selected_index=nav_bar.selected_index,extended=False,
        min_width=80,min_extended_width=210,label_type=ft.NavigationRailLabelType.ALL,
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
        destinations=[ft.NavigationRailDestination(icon=icon,label=label) for icon,label in zip(icons,labels)])
    from views.discovery import openCreate
    createButton=ft.IconButton(ft.Icons.ADD_CIRCLE_OUTLINE,tooltip='Создать',on_click=authenticatedAction(page,currentUser)(lambda e:openCreate(page,currentUser)))
    brand=ft.Row([createButton,ft.Image(src=ICON,width=30,height=30,border_radius=10),
        ft.Text('Лепка',size=20,weight=ft.FontWeight.W_600)])
    sidebar=ft.Container(width=80,padding=ft.padding.only(top=16,bottom=16),
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
        content=ft.Column([ft.Container(content=ft.Image(src=ICON,width=42,height=42,border_radius=12),alignment=ft.alignment.center),rail],expand=True))
    content_frame=ft.Container(content=content_area,expand=True)
    main_column=ft.Column([ft.Container(content=brand,padding=ft.padding.only(left=16,top=10,bottom=4)),connectionBanner,content_frame],expand=True,spacing=0)
    body=ft.Row([sidebar,ft.Container(content=main_column,expand=True)],expand=True,spacing=0)
    def navigateHomeTab(index):
        nav_bar.selected_index=rail.selected_index=1 if index==5 else (0 if index==1 else index)
        loadTab(index)
    nav_bar.on_change=lambda e:navigateHomeTab(5 if e.control.selected_index==1 else e.control.selected_index)
    rail.on_change=lambda e:navigateHomeTab(5 if e.control.selected_index==1 else e.control.selected_index)
    def resize(event=None):
        width=page.width or 390
        wide=width>=760
        sidebar.visible=wide
        nav_bar.visible=not wide
        rail.extended=width>=1180
        rail.label_type=ft.NavigationRailLabelType.NONE if rail.extended else ft.NavigationRailLabelType.ALL
        sidebar.width=210 if rail.extended else 80
        available=width-(sidebar.width if wide else 0)
        # Centre the scrollable workspace, with a useful readable limit on PCs.
        content_area.width=min(1040,available)
        content_area.expand=False
        content_frame.alignment=ft.alignment.top_center
        discoveryResize=page.session.get('resizeDiscovery')
        if callable(discoveryResize):discoveryResize()
        if event:page.update()
    page.session.set('navigateHomeTab',navigateHomeTab)
    page.session.set('resizeHomeView',resize)
    loadTab(initialTab)
    resize()
    return ft.View('/home',padding=0,spacing=0,bgcolor=ft.Colors.SURFACE,controls=[
        ft.Container(expand=True,bgcolor=ft.Colors.SURFACE,content=ft.SafeArea(expand=True,
            content=ft.Column([body,nav_bar],expand=True,spacing=0)))])
