"""Полный экран мастер-класса: одинаковые элементы Flet для ПК и телефона."""
import base64

import flet as ft

from database import getPostPhoto
from project_sharing import copyPublishedMixture
from workshop_service import (getWorkshop, getUserWorkshopState, saveUserWorkshopState, addWorkshopAsProject)
from ui_helpers import authenticatedAction, showMessage


def createWorkshopView(page, postId, currentUser, onBack):
    # Импорт здесь позволяет использовать тот же вывод рецепта, что и в проекте.
    from views.project_sharing import createMixtureRecipe

    workshop = getWorkshop(postId)
    body = ft.Column(spacing=14)
    state = [getUserWorkshopState(currentUser['userId'], postId) if currentUser and workshop else
             {'lastStep': 0, 'completedSteps': [], 'checkedMaterials': [], 'isCompleted': False}]

    def action(callback):
        return authenticatedAction(page, currentUser)(callback) if currentUser else callback

    def persist():
        if currentUser:
            state[0] = saveUserWorkshopState(currentUser['userId'], postId, state[0])

    def updateContent():
        if getWorkshop(postId) is None:
            body.controls = [ft.TextButton('← Назад', on_click=onBack), ft.Text('Мастер-класс удалён или недоступен')]
            return
        currentIndex = state[0]['lastStep']
        step = workshop['steps'][currentIndex]

        @action
        def move(event, delta):
            if delta > 0 and currentUser and currentIndex not in state[0]['completedSteps']:
                state[0]['completedSteps'].append(currentIndex)
            state[0]['lastStep'] = min(len(workshop['steps']) - 1, max(0, currentIndex + delta))
            saveAndRefresh()

        def saveAndRefresh():
            try:
                persist()
            except ValueError as error:
                showMessage(page, str(error), True)
            updateContent()
            page.update()

        @action
        def complete(event):
            checked = state[0]['completedSteps']
            if event.control.value and currentIndex not in checked:
                checked.append(currentIndex)
            elif not event.control.value and currentIndex in checked:
                checked.remove(currentIndex)
            saveAndRefresh()

        def checklist(index, label):
            @action
            def change(event):
                checked = state[0]['checkedMaterials']
                if event.control.value and index not in checked:
                    checked.append(index)
                elif not event.control.value and index in checked:
                    checked.remove(index)
                saveAndRefresh()
            return ft.Checkbox(label=label, value=index in state[0]['checkedMaterials'],
                               disabled=currentUser is None, on_change=change)

        materialControls = [ft.Text('Материалы и инструменты', size=18, weight=ft.FontWeight.BOLD)]
        materialControls.extend(checklist(index, item) for index, item in enumerate(workshop['materials']))
        if workshop['tools']:
            materialControls.append(ft.Text('Инструменты', weight=ft.FontWeight.BOLD))
            materialControls.extend(checklist(len(workshop['materials']) + index, item)
                                    for index, item in enumerate(workshop['tools']))
        if not workshop['materials'] and not workshop['tools']:
            materialControls.append(ft.Text('Автор не указал материалы и инструменты.'))
        materialControls.append(ft.Text('Отметки сохраняются автоматически' if currentUser else
                                       'Войдите, чтобы сохранять отметки и прогресс', size=12))

        photoPosition = step['photoPosition']
        imageData = getPostPhoto(workshop['photoIds'][photoPosition]) if photoPosition is not None else None
        image = (ft.Image(src_base64=base64.b64encode(imageData).decode(), height=220, fit=ft.ImageFit.CONTAIN)
                 if imageData else ft.Text('Автор не добавил фотографию этого шага.', size=12))
        completedCount = len(state[0]['completedSteps'])
        progress = completedCount / len(workshop['steps'])
        meta = (f"{workshop['level']} · {workshop['timeMinutes']} мин" if workshop['level'] else
                'Сложность и время не указаны автором')
        body.controls = [
            ft.TextButton('← Назад', on_click=onBack),
            ft.Container(padding=18, border_radius=18, bgcolor='#FF6B6B', content=ft.Column(spacing=8, controls=[
                ft.Text(workshop['title'], size=24, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
                ft.Text(f"{workshop['category']} · {meta}", color=ft.Colors.WHITE),
                ft.Text(f"Автор: {workshop['nickname']}", color=ft.Colors.WHITE),
                ft.Text(workshop['description'], color=ft.Colors.WHITE)])),
            ft.Card(content=ft.Container(padding=16, content=ft.Column(controls=materialControls))),
            ft.Card(content=ft.Container(padding=16, content=ft.Column(spacing=12, controls=[
                ft.Text(f"Шаг {currentIndex + 1} из {len(workshop['steps'])}", size=18, weight=ft.FontWeight.BOLD),
                ft.ProgressBar(value=progress, color='#4ECDC4'), image,
                ft.Text(step['description'], size=16),
                ft.Checkbox(label='Шаг выполнен', value=currentIndex in state[0]['completedSteps'],
                            disabled=currentUser is None, on_change=complete),
                ft.Text('Мастер-класс завершён' if progress == 1 else
                        f"Выполнено шагов: {completedCount} из {len(workshop['steps'])}"),
                ft.Row(wrap=True, alignment=ft.MainAxisAlignment.SPACE_BETWEEN, controls=[
                    ft.OutlinedButton('Предыдущий', icon=ft.Icons.ARROW_BACK, height=48, disabled=currentIndex == 0,
                                      on_click=lambda event: move(event, -1)),
                    ft.ElevatedButton('Следующий' if currentIndex < len(workshop['steps']) - 1 else 'Завершить',
                        icon=ft.Icons.ARROW_FORWARD, height=48, on_click=lambda event: move(event, 1))])])))]
        if workshop['mixtures']:
            body.controls.append(ft.Text('Смеси для этой работы', size=18, weight=ft.FontWeight.BOLD))
        for index, mixture in enumerate(workshop['mixtures']):
            @authenticatedAction(page, currentUser)
            def saveRecipe(event, mixtureIndex=index):
                success, message, _ = copyPublishedMixture(postId, mixtureIndex, currentUser['userId'])
                showMessage(page, message, not success)
            body.controls.extend([createMixtureRecipe(mixture), ft.OutlinedButton('Сохранить рецепт в мою палитру',
                disabled=currentUser is None, on_click=saveRecipe)])

        @authenticatedAction(page, currentUser)
        def addProject(event):
            success, message, _ = addWorkshopAsProject(postId, currentUser['userId'])
            showMessage(page, message, not success)
        body.controls.append(ft.ElevatedButton('Добавить как проект', icon=ft.Icons.ADD, height=48,
                                              disabled=currentUser is None, on_click=addProject))

    updateContent()
    return ft.View(f'/workshop/{postId}', padding=0, controls=[
        ft.SafeArea(expand=True, content=ft.Container(expand=True, alignment=ft.alignment.top_center,
            content=ft.Container(width=900, content=ft.ListView(expand=True, padding=16, controls=[body]))))])


def openWorkshop(page, postId, currentUser):
    if getWorkshop(postId) is None:
        showMessage(page, 'Мастер-класс удалён или недоступен', True)
        return

    def back(event):
        if page.views and page.views[-1] is view:
            page.views.pop()
            page.update()

    view = createWorkshopView(page, postId, currentUser, back)
    page.views.append(view)
    page.update()
