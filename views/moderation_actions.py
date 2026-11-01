"""Небольшие действия модерации для карточек и профиля."""
import flet as ft
from moderation_gateway import ModerationClient
from api_client import ApiError
from ui_helpers import authenticatedAction,showMessage
from views.admin_permissions import panelAccess


def reasonDialog(page,user,title,action,callback,onDone=None,successMessage='Изменение сохранено'):
    reason=ft.TextField(label='Причина',multiline=True,min_lines=2,max_lines=5,max_length=500,
                        hint_text='От 10 до 500 символов')
    busy={'value':False}
    @authenticatedAction(page,user)
    def submit(event):
        if busy['value']:return
        if not 10<=len((reason.value or '').strip())<=500:
            reason.error_text='Укажите причину от 10 до 500 символов';page.update();return
        busy['value']=True
        try:
            result=callback(reason.value.strip())
            page.close(dialog)
            if onDone:onDone()
            showMessage(page,successMessage if result is not False else 'Материал уже удалён или действие выполнено ранее')
        except ApiError as error:
            busy['value']=False
            if error.statusCode==401:raise
            reason.error_text=str(error);page.update()
    dialog=ft.AlertDialog(modal=True,title=ft.Text(title),
        content=ft.Column(tight=True,controls=[reason]),
        actions=[ft.TextButton('Отмена',on_click=lambda event:page.close(dialog)),ft.ElevatedButton(action,on_click=submit)])
    page.open(dialog)


def createReportButton(page,user,targetType,targetId):
    @authenticatedAction(page,user)
    def report(event):
        reasonDialog(page,user,'Жалоба на материал','Отправить жалобу',
                     lambda reason:ModerationClient(user).report(targetType,targetId,reason),successMessage='Жалоба отправлена администратору')
    return ft.TextButton('Пожаловаться' if targetType=='post' else 'Жалоба на комментарий',
                         icon=ft.Icons.FLAG_OUTLINED,on_click=report,disabled=user is None)


def createModerationDelete(page,user,targetType,targetId,onDone):
    @authenticatedAction(page,user)
    def remove(event):
        reasonDialog(page,user,'Удалить материал без восстановления?','Удалить как модератор',
            lambda reason:ModerationClient(user).remove(targetType,targetId,reason),onDone)
    return ft.TextButton('Удалить как модератор' if targetType=='post' else 'Удалить комментарий как модератор',
                         icon=ft.Icons.SHIELD_OUTLINED,on_click=remove)


def createAdminButton(page,user):
    @authenticatedAction(page,user)
    def openPanel(event):page.go('/admin')
    return ft.TextButton('Администрирование',icon=ft.Icons.ADMIN_PANEL_SETTINGS_OUTLINED,on_click=openPanel,
                         visible=bool(panelAccess(page,user)['permissions']))
