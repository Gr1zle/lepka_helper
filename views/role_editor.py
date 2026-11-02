from localization import tr, term
"""Редактор явных прав пользовательской роли; встроенные роли неизменяемы."""
import flet as ft
from api_client import ApiError
from ui_helpers import authenticatedAction,showMessage


def openRoleEditor(page,user,client,role=None,onDone=None):
    data=client.roles()
    code=ft.TextField(label=tr(page, 'Код роли'),value=role['roleCode'] if role else '',read_only=bool(role),max_length=24,hint_text=tr(page, 'Например: moderator'))
    title=ft.TextField(label=tr(page, 'Название роли'),value=role['title'] if role else '',max_length=50)
    checks=[ft.Checkbox(label=label,value=key in (role['permissions'] if role else []),data=key) for key,label in data['catalog'].items()]
    reason=ft.TextField(label=tr(page, 'Причина'),multiline=True,min_lines=2,max_length=500,hint_text=tr(page, 'От 10 до 500 символов'))
    error=ft.Text(color=ft.Colors.RED)
    busy={'value':False}
    @authenticatedAction(page,user)
    def save(event):
        if busy['value']:return
        busy['value']=True
        try:
            client.saveRole(code.value or '',title.value or '',[c.data for c in checks if c.value],reason.value or '',create=role is None)
            page.close(dialog)
            if onDone:onDone()
            showMessage(page,tr(page, 'Роль сохранена. Затронутым пользователям потребуется войти заново.'))
        except ApiError as exc:
            if exc.statusCode==401:raise
            error.value=str(exc);page.update()
        finally:busy['value']=False
    dialog=ft.AlertDialog(modal=True,title=ft.Text(tr(page, 'Изменить роль') if role else tr(page, 'Создать роль')),
        content=ft.Container(width=460,height=430,content=ft.ListView(spacing=12,controls=[code,title,
            ft.Text(tr(page, 'Полномочия выдаются только явно. Управление ролями остаётся у администратора.')),*checks,reason,error])),
        actions=[ft.TextButton(tr(page, 'Отмена'),on_click=lambda e:page.close(dialog)),ft.ElevatedButton(tr(page, 'Сохранить роль'),on_click=save)])
    page.open(dialog)


def openRoleAssignment(page,user,client,target,onDone):
    roles=client.roles()['items']
    choice=ft.Dropdown(label=tr(page, 'Новая роль'),value=target['roleName'],options=[ft.dropdown.Option('user',tr(page, 'Пользователь')),
        ft.dropdown.Option('admin',tr(page, 'Администратор')),*[ft.dropdown.Option(r['roleCode'],r['title']) for r in roles]])
    reason=ft.TextField(label=tr(page, 'Причина'),multiline=True,max_length=500,hint_text=tr(page, 'От 10 до 500 символов'))
    error=ft.Text(color=ft.Colors.RED)
    busy={'value':False}
    @authenticatedAction(page,user)
    def save(event):
        if busy['value']:return
        busy['value']=True
        try:
            client.changeUser(target['userId'],reason.value or '',role=choice.value)
            page.close(dialog);onDone();showMessage(page,tr(page, 'Роль назначена, прежние сессии отозваны.'))
        except ApiError as exc:
            if exc.statusCode==401:raise
            error.value=str(exc);page.update()
        finally:busy['value']=False
    dialog=ft.AlertDialog(modal=True,title=ft.Text(tr(page, 'Назначить роль: ')+target['nickname']),
        content=ft.Column(tight=True,controls=[ft.Container(content=choice,padding=6),reason,error]),
        actions=[ft.TextButton(tr(page, 'Отмена'),on_click=lambda e:page.close(dialog)),ft.ElevatedButton(tr(page, 'Назначить роль'),on_click=save)])
    page.open(dialog)
