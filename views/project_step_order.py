"""Редактирование порядка этапов с отдельными сохранением и отменой."""
import flet as ft
from project_service import getProjectSteps, saveProjectStepOrder
from ui_helpers import authenticatedAction, showMessage


def createStepOrderButton(page, currentUser, projectId, onSaved):
    @authenticatedAction(page, currentUser)
    def openOrder(event):
        steps = getProjectSteps(projectId, currentUser['userId'])
        if len(steps) < 2:
            showMessage(page, 'Для изменения порядка нужны хотя бы два этапа')
            return
        expectedIds = [step['stepId'] for step in steps]
        ordered = list(steps)
        listing = ft.ReorderableListView(show_default_drag_handles=True)

        def render():
            controls = []
            for index, step in enumerate(ordered):
                @authenticatedAction(page, currentUser)
                def up(event, stepId=step['stepId']):
                    move(stepId, -1)

                @authenticatedAction(page, currentUser)
                def down(event, stepId=step['stepId']):
                    move(stepId, 1)

                # Справа зарезервировано место для штатной ручки перетаскивания.
                controls.append(ft.Container(key=str(step['stepId']), padding=ft.padding.only(left=4, top=4, bottom=4, right=40),
                    content=ft.Column(tight=True, spacing=0, controls=[
                        ft.Text(f"{index + 1}. {step['stepDescription']}", max_lines=2,
                                overflow=ft.TextOverflow.ELLIPSIS),
                        ft.Row(spacing=4, controls=[
                        ft.IconButton(icon=ft.Icons.ARROW_UPWARD, width=32, height=36, icon_size=18, tooltip='Этап выше', disabled=index == 0, on_click=up),
                        ft.IconButton(icon=ft.Icons.ARROW_DOWNWARD, width=32, height=36, icon_size=18, tooltip='Этап ниже', disabled=index == len(ordered)-1, on_click=down),
                        ]),
                    ])))
            listing.controls = controls
            page.update()

        def move(stepId, shift):
            index = next(i for i, step in enumerate(ordered) if step['stepId'] == stepId)
            target = index + shift
            if 0 <= target < len(ordered):
                ordered.insert(target, ordered.pop(index))
                render()

        @authenticatedAction(page, currentUser)
        def reorder(event):
            # Flet 0.28.3 уже передаёт скорректированный конечный индекс.
            if (type(event.old_index) is int and type(event.new_index) is int
                    and 0 <= event.old_index < len(ordered) and 0 <= event.new_index < len(ordered)):
                ordered.insert(event.new_index, ordered.pop(event.old_index))
                render()

        @authenticatedAction(page, currentUser)
        def save(event):
            success, message = saveProjectStepOrder(projectId, currentUser['userId'],
                                                   [step['stepId'] for step in ordered], expectedIds)
            if success:
                page.close(dialog)
                onSaved()
            showMessage(page, message, not success)
            page.update()

        listing.on_reorder = reorder
        dialog = ft.AlertDialog(modal=True, title=ft.Text('Порядок этапов'),
            content=ft.Container(width=420, height=360, content=ft.Column(controls=[
                ft.Text('Перетащите этап или используйте стрелки. Изменения применятся после сохранения.', size=13),
                ft.Container(content=listing, expand=True),
            ])), actions=[ft.TextButton('Отмена', on_click=lambda event: page.close(dialog)),
                          ft.ElevatedButton('Сохранить порядок', on_click=save)])
        render()
        page.open(dialog)

    return ft.TextButton('Порядок этапов', icon=ft.Icons.SWAP_VERT, on_click=openOrder)
