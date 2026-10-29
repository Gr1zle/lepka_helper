"""Дедлайн можно ввести вручную или выбрать календарём."""
from datetime import datetime
import flet as ft


def createDeadlineField(page, value=''):
    field = ft.TextField(label='Дедлайн', value=value or '',
                         hint_text='ДД.ММ.ГГГГ, можно оставить пустым', border_radius=12)

    def changed(event):
        if event.control.value:
            field.value = event.control.value.strftime('%d.%m.%Y')
            field.error_text = None
            page.close(picker)
            page.update()

    picker = ft.DatePicker(first_date=datetime(1900, 1, 1), last_date=datetime(2100, 12, 31), on_change=changed)

    def openCalendar(event):
        try:
            selected = datetime.strptime(field.value or '', '%d.%m.%Y')
            picker.value = selected if 1900 <= selected.year <= 2100 else None
        except ValueError:
            picker.value = None
        page.open(picker)

    field.suffix = ft.IconButton(icon=ft.Icons.CALENDAR_MONTH, tooltip='Выбрать дату', on_click=openCalendar)
    return field
