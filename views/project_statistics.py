from localization import tr, term
from datetime import datetime, timezone
import flet as ft
from project_statistics import getProjectStatistics
from ui_helpers import authenticatedAction, showMessage


def createProjectStatistics(page, user):
    now = datetime.now(timezone.utc)
    year = ft.TextField(label=tr(page, 'Год'), value=str(now.year), width=110, keyboard_type=ft.KeyboardType.NUMBER)
    month = ft.Dropdown(label=tr(page, 'Месяц'), value=str(now.month), width=110,
        options=[ft.dropdown.Option(str(number), f'{number:02d}') for number in range(1, 13)])
    result = ft.Text()

    def refresh(update=False):
        try:
            stats = getProjectStatistics(user['userId'], int(year.value), int(month.value))
            result.value = (tr(page, 'Всего: {v0} · В работе: {v1} · Завершено: {v2}\nЗа {v3}: {v4} · За {v5} год: {v6}\nЗавершённые без даты: {v7}', v0=stats['total'], v1=stats['active'], v2=stats['completed'], v3=stats['period'], v4=stats['month'], v5=year.value, v6=stats['year'], v7=stats['undated']))
            if update:
                page.update()
        except (ValueError, TypeError):
            showMessage(page, tr(page, 'Укажите год от 1 до 9999 и месяц от 1 до 12'), True)

    @authenticatedAction(page, user)
    def update(event):
        refresh(True)

    refresh()
    card = ft.Card(content=ft.Container(padding=14, content=ft.Column(controls=[
        ft.Text(tr(page, 'Статистика проектов'), size=18, weight=ft.FontWeight.BOLD),
        ft.Row(wrap=True, controls=[year, month, ft.TextButton(tr(page, 'Показать'), on_click=update)]), result,
        ft.Text(tr(page, 'Периоды считаются по UTC. Старые и импортированные завершённые проекты без известной даты показаны отдельно.'), size=12)])))
    card.data = refresh
    return card
