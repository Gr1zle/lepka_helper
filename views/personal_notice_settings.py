import flet as ft
from personal_notices import settings,saveSettings
from ui_helpers import authenticatedAction,showMessage


def openPersonalNoticeSettings(page,user,onSaved):
    prefs=settings(user['userId'])
    projects=ft.Switch(data='projects',value=bool(prefs['projectsEnabled']))
    lessons=ft.Switch(data='lessons',value=bool(prefs['lessonsEnabled']))
    days=ft.Dropdown(label='Перерыв, дней',value=str(prefs['resumeDays']),
        options=[ft.dropdown.Option(str(i),f'{i} дн.') for i in range(1,31)])
    error=ft.Text(color=ft.Colors.RED_400)
    @authenticatedAction(page,user)
    def save(event):
        try:saveSettings(user['userId'],bool(projects.value),bool(lessons.value),int(days.value))
        except ValueError as exc:error.value=str(exc);page.update();return
        page.close(dialog);onSaved();showMessage(page,'Настройки личных уведомлений сохранены')
    dialog=ft.AlertDialog(title=ft.Text('Личные уведомления'),content=ft.Column(tight=True,controls=[ft.Row([projects,ft.Text('Напоминания о дедлайнах',expand=True)]),
        ft.Row([lessons,ft.Text('Уроки и учебные достижения',expand=True)]),days,
        ft.Text('Общий переключатель уведомлений находится в профиле. Настройки действуют на этом устройстве. Android-напоминания и письма настраиваются отдельно в «Доставке уведомлений».'),error]),
        actions=[ft.TextButton('Отмена',on_click=lambda e:page.close(dialog)),ft.TextButton('Сохранить настройки уведомлений',on_click=save)])
    page.open(dialog)
