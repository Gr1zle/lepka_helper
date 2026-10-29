"""Элементы публикации проекта и выбора сохранённых смесей."""
import base64

import flet as ft

from color_service import getUserColorMixtures
from project_service import getProjectSteps, getProjectStepPhoto
from project_sharing import getProjectMixtures, addProjectMixture, removeProjectMixture
from post_service import POST_CATEGORIES
from ui_helpers import authenticatedAction, showMessage
from lesson_service import IDEA_LEVELS
from community_gateway import CommunityClient


def createMixtureRecipe(mixture):
    lines = [ft.Row(wrap=True, controls=[
        ft.Container(width=32, height=32, bgcolor=mixture['resultHex'], border_radius=16),
        ft.Text(mixture['mixtureName'], weight=ft.FontWeight.BOLD)]),
        ft.Text(f"{mixture['resultHex']} · {mixture['totalWeight']:g} г", size=12)]
    for item in mixture['recipeItems']:
        lines.append(ft.Text(f"{item['name']}: {item['percent']:g}% — {item['grams']:g} г", size=12))
    return ft.Column(controls=lines, spacing=4)


def createPublishedProject(page, postId, currentUser):
    details = CommunityClient(currentUser).getWorkshop(postId)
    if not details:
        return ft.Container()
    def openDetail(event):
        from views.workshop_view import openWorkshop
        openWorkshop(page, postId, currentUser)
    if currentUser:
        openDetail = authenticatedAction(page, currentUser)(openDetail)
    caption = f"{details['level']} · {details['timeMinutes']} мин · " if details['level'] else ''
    return ft.Column(controls=[ft.Text(caption + f"Шагов: {len(details['steps'])}", size=12),
        ft.OutlinedButton('Открыть мастер-класс', icon=ft.Icons.MENU_BOOK, height=48, on_click=openDetail)])


def createProjectSharing(page, currentUser, projectItem, refreshCallback):
    client = CommunityClient(currentUser)
    projectId, userId = projectItem['projectId'], currentUser['userId']
    mixtures = getProjectMixtures(projectId, userId)
    controls = [ft.Text('Смеси проекта', weight=ft.FontWeight.BOLD)]
    for mixture in mixtures:
        @authenticatedAction(page, currentUser)
        def remove(event, mixtureId=mixture['projectMixtureId']):
            success = removeProjectMixture(projectId, userId, mixtureId)
            refreshCallback()
            showMessage(page, 'Смесь убрана из проекта' if success else 'Смесь недоступна', not success)
            page.update()
        controls.extend([ft.Text('Рецепт повреждён') if mixture.get('recipeError') else createMixtureRecipe(mixture),
                         ft.TextButton('Убрать смесь из проекта', on_click=remove)])
    if not mixtures:
        controls.append(ft.Text('Добавьте сохранённые смеси из своей палитры.', size=12))

    @authenticatedAction(page, currentUser)
    def chooseMixture(event):
        available = [item for item in getUserColorMixtures(userId) if not item['recipeError']]
        field = ft.Dropdown(label='Смесь из моей палитры', width=300,
            options=[ft.dropdown.Option(str(item['mixtureId']), item['mixtureName']) for item in available])

        @authenticatedAction(page, currentUser)
        def add(event):
            if field.value is None:
                showMessage(page, 'Выберите смесь из списка', True)
                return
            success, message = addProjectMixture(projectId, userId, int(field.value))
            if success:
                page.close(dialog)
                refreshCallback()
            showMessage(page, message, not success)
            page.update()

        dialog = ft.AlertDialog(title=ft.Text('Добавить смесь в проект'),
            content=ft.Column(tight=True, controls=[field, ft.Text(
                'Сначала сохраните рецепт на вкладке «Цвета».' if not available else
                'В проект сохраняется копия рецепта с пропорциями и массой.')]),
            actions=[ft.TextButton('Отмена', on_click=lambda event: page.close(dialog)),
                     ft.ElevatedButton('Добавить смесь', disabled=not available, on_click=add)])
        page.open(dialog)

    @authenticatedAction(page, currentUser)
    def openPublication(event):
        steps = getProjectSteps(projectId, userId)
        photoSteps = [step for step in steps if step['hasPhoto']]
        if not photoSteps:
            showMessage(page, 'Добавьте фото результата к этапу проекта перед публикацией', True)
            return
        title = ft.TextField(label='Название работы', value=projectItem['projectName'], max_length=100)
        description = ft.TextField(label='Описание для сообщества', multiline=True, min_lines=3, max_length=2000)
        category = ft.Dropdown(label='Категория работы', value=projectItem['categoryName'],
            options=[ft.dropdown.Option(item) for item in POST_CATEGORIES])
        tags = ft.TextField(label='Теги через запятую')
        level = ft.Dropdown(label='Сложность мастер-класса', value=IDEA_LEVELS[0],
                            options=[ft.dropdown.Option(item) for item in IDEA_LEVELS])
        minutes = ft.TextField(label='Время выполнения (минут)', keyboard_type=ft.KeyboardType.NUMBER)
        materials = ft.TextField(label='Материалы — по одному на строку', multiline=True, min_lines=2, max_lines=4,
                                 hint_text='Серый пластилин\nБелый пластилин', max_length=3630)
        tools = ft.TextField(label='Инструменты — по одному на строку', multiline=True, min_lines=2, max_lines=4,
                            hint_text='Стек\nДоска для лепки', max_length=3630)
        result = ft.Dropdown(label='Итоговое фото', value=str(photoSteps[-1]['stepId']),
            options=[ft.dropdown.Option(str(step['stepId']), step['stepDescription']) for step in photoSteps])
        photoChoices = []
        photoControls = []

        @authenticatedAction(page, currentUser)
        def selectionChanged(event):
            page.update()

        for step in steps:
            check = ft.Checkbox(label=step['stepDescription'], value=False, data=step['stepId'],
                                on_change=selectionChanged)
            photoChoices.append(check)
            imageData = getProjectStepPhoto(projectId, step['stepId'], userId)
            photoControls.append(ft.Row(controls=[
                ft.Image(src_base64=base64.b64encode(imageData).decode(), width=64, height=64,
                         fit=ft.ImageFit.CONTAIN) if imageData else ft.Text('Фото не добавлено'),
                ft.Container(content=check, expand=True)]))
        mixtureChoices = [ft.Checkbox(label=item['mixtureName'], value=False, data=item['projectMixtureId'],
                                      on_change=selectionChanged)
                          for item in getProjectMixtures(projectId, userId) if not item.get('recipeError')]

        @authenticatedAction(page, currentUser)
        def publish(event):
            resultId = int(result.value)
            success, message, _ = client.publishProject(projectId, title.value, description.value,
                category.value, tags.value, resultId,
                [check.data for check in photoChoices if check.value and check.data != resultId],
                [check.data for check in mixtureChoices if check.value], workshopInfo={
                    'level': level.value, 'timeMinutes': minutes.value,
                    'materials': [entry.strip() for entry in (materials.value or '').splitlines() if entry.strip()],
                    'tools': [entry.strip() for entry in (tools.value or '').splitlines() if entry.strip()]})
            if success:
                page.close(dialog)
                refreshCallback()
            showMessage(page, message, not success)
            page.update()

        dialog = ft.AlertDialog(modal=True, title=ft.Text('Опубликовать проект'),
            content=ft.Column(width=340, height=450, tight=True, scroll=ft.ScrollMode.AUTO, spacing=10, controls=[
                ft.Text('Выбранные фото, подписи этапов и рецепты будут видны в сообществе. '
                        'Личные заметки и дедлайн останутся в проекте.'),
                title, description, category, level, minutes, materials, tools, tags, result,
                ft.Text('Шаги мастер-класса в порядке проекта. Итоговый этап включается автоматически. '
                        'Можно выбрать текстовые шаги без фото; фотографий всего до 10.'), *photoControls,
                ft.Text('Поделиться рецептами смесей'), *mixtureChoices,
                ft.Text('Мастер-класс будет доступен пользователям сервера' if client.remote else
                        'Сообщество пока общее только в пределах одной локальной базы.', size=12)]),
            actions=[ft.TextButton('Отмена', on_click=lambda event: page.close(dialog)),
                     ft.ElevatedButton('Опубликовать проект', on_click=publish)])
        page.open(dialog)

    controls.extend([ft.OutlinedButton('Добавить смесь из палитры', icon=ft.Icons.PALETTE, on_click=chooseMixture),
                     ft.ElevatedButton('Опубликовать в сообщество', icon=ft.Icons.PUBLISH, on_click=openPublication)])
    return ft.Column(controls=controls, spacing=8)
