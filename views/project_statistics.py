from datetime import datetime, timezone
import flet as ft
from project_statistics import getProjectStatistics
from ui_helpers import authenticatedAction, showMessage


def createProjectStatistics(page, user):
    now = datetime.now(timezone.utc)
    year = ft.TextField(label='Год', value=str(now.year), width=110, keyboard_type=ft.KeyboardType.NUMBER)
    month = ft.Dropdown(label='Месяц', value=str(now.month), width=110,
        options=[ft.dropdown.Option(str(number), f'{number:02d}') for number in range(1, 13)])
    result = ft.Text()

    def refresh(update=False):
        try:
            stats = getProjectStatistics(user['userId'], int(year.value), int(month.value))
            result.value = (f"Всего: {stats['total']} · В работе: {stats['active']} · Завершено: {stats['completed']}\n"
                f"За {stats['period']}: {stats['month']} · За {year.value} год: {stats['year']}\n"
                f"Завершённые без даты: {stats['undated']}")
            if update:
                page.update()
        except (ValueError, TypeError):
            showMessage(page, 'Укажите год от 1 до 9999 и месяц от 1 до 12', True)

    @authenticatedAction(page, user)
    def update(event):
        refresh(True)

    refresh()
    card = ft.Card(content=ft.Container(padding=14, content=ft.Column(controls=[
        ft.Text('Статистика проектов', size=18, weight=ft.FontWeight.BOLD),
        ft.Row(wrap=True, controls=[year, month, ft.TextButton('Показать', on_click=update)]), result,
        ft.Text('Периоды считаются по UTC. Старые и импортированные завершённые проекты без известной даты показаны отдельно.', size=12)])))
    card.data = refresh
    return card
