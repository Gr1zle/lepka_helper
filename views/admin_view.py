"""Жалобы, аккаунты и журнал. Права подтверждает сервис при каждом запросе."""
import flet as ft
from moderation_gateway import ModerationClient
from ui_helpers import getCurrentUser,authenticatedAction,createLoadError
from views.moderation_actions import reasonDialog
from views.community_tab import createPhotoViewer
from community_gateway import CommunityClient
from api_client import ApiError

STATUS_LABELS={'open':'Открыта','resolved':'Рассмотрена','rejected':'Отклонена'}
ACTION_LABELS={'challenge.auto':'Автоматические итоги конкурса','challenge.create':'Создание задания','challenge.finished':'Итоги задания','challenge.cancelled':'Отмена задания','material.delete':'Удаление материала','user.block':'Блокировка аккаунта','user.unblock':'Разблокировка аккаунта',
               'role.admin':'Назначение администратора','role.user':'Снятие роли администратора',
               'report.resolved':'Жалоба рассмотрена','report.rejected':'Жалоба отклонена'}


def createAdminView(page):
    user=getCurrentUser(page)
    if user is None or user.get('roleName')!='admin':
        return ft.View('/admin',controls=[ft.Text('Этот раздел доступен только администратору'),
            ft.TextButton('На главную',on_click=lambda event:page.go('/home'))])
    client=ModerationClient(user)
    section=ft.Dropdown(label='Раздел панели',value='Жалобы',options=[ft.dropdown.Option(v) for v in ('Жалобы','Аккаунты','Журнал')])
    status=ft.Dropdown(label='Статус жалоб',value='open',options=[ft.dropdown.Option(k,v) for k,v in [*STATUS_LABELS.items(),('all','Все')]])
    query=ft.TextField(label='Никнейм или email',max_length=100,visible=False)
    result=ft.Column(spacing=10)
    offset={'value':0};pageNumber=ft.Text()
    previous=ft.TextButton('Предыдущие',disabled=True)
    following=ft.TextButton('Следующие')

    def ask(title,action,callback):
        reasonDialog(page,user,title,action,callback,lambda:render())

    def reportCard(item):
        content=[ft.Text(f"Жалоба №{item['reportId']} · {STATUS_LABELS[item['status']]}",size=18,weight=ft.FontWeight.BOLD),
                 ft.Text(f"От: {item['reporter']} · {item['createdAt']} UTC",size=12),ft.Text('Причина: '+item['reason'])]
        material=item['material']
        if material:
            content.extend([ft.Text(('Публикация' if item['targetType']=='post' else 'Комментарий')+f" №{item['targetId']} · {material['nickname']}"),
                            ft.Text(material['title'],weight=ft.FontWeight.BOLD),ft.Text(material['text'])])
            if item['targetType']=='post' and material['photoIds']:
                content.append(createPhotoViewer(page,material['photoIds'],CommunityClient(user)))
        else:content.append(ft.Text('Материал уже недоступен. Можно закрыть жалобу.'))
        if item['resolution']:content.append(ft.Text('Решение: '+item['resolution']))
        if item['status']=='open':
            @authenticatedAction(page,user)
            def reject(event):ask('Отклонить жалобу','Отклонить жалобу',lambda reason:client.resolve(item['reportId'],'rejected',reason))
            @authenticatedAction(page,user)
            def resolve(event):ask('Закрыть рассмотренную жалобу','Закрыть жалобу',lambda reason:client.resolve(item['reportId'],'resolved',reason))
            actions=[ft.TextButton('Отклонить жалобу',on_click=reject),ft.TextButton('Закрыть жалобу',on_click=resolve)]
            if material:
                @authenticatedAction(page,user)
                def remove(event):ask('Удалить материал без восстановления?','Удалить материал',lambda reason:client.remove(item['targetType'],item['targetId'],reason))
                actions.append(ft.TextButton('Удалить материал',on_click=remove))
            content.append(ft.Row(wrap=True,controls=actions))
        return ft.Card(content=ft.Container(padding=14,content=ft.Column(controls=content)))

    def userCard(item):
        content=[ft.Text(f"{item['nickname']} · №{item['userId']}",size=18,weight=ft.FontWeight.BOLD),ft.Text(item['email']),
                 ft.Text(('Администратор' if item['roleName']=='admin' else 'Пользователь')+' · '+('Заблокирован' if item['isBlocked'] else 'Активен'))]
        if item['userId']==user.get('serverUserId',user['userId']):content.append(ft.Text('Ваш аккаунт',size=12))
        else:
            @authenticatedAction(page,user)
            def block(event):
                label='Разблокировать аккаунт' if item['isBlocked'] else 'Заблокировать аккаунт'
                ask(label,label,lambda reason:client.changeUser(item['userId'],reason,blocked=not bool(item['isBlocked'])))
            @authenticatedAction(page,user)
            def role(event):
                value='user' if item['roleName']=='admin' else 'admin'
                label='Снять роль администратора' if value=='user' else 'Назначить администратором'
                ask(label,label,lambda reason:client.changeUser(item['userId'],reason,role=value))
            content.append(ft.Row(wrap=True,controls=[ft.TextButton('Разблокировать' if item['isBlocked'] else 'Заблокировать',on_click=block),
                ft.TextButton('Снять роль администратора' if item['roleName']=='admin' else 'Назначить администратором',on_click=role)]))
        return ft.Card(content=ft.Container(padding=14,content=ft.Column(controls=content)))

    def auditCard(item):
        return ft.Card(content=ft.Container(padding=14,content=ft.Column(controls=[
            ft.Text(ACTION_LABELS.get(item['action'],item['action']),size=17,weight=ft.FontWeight.BOLD),
            ft.Text(f"{item['actorNickname']} · {item['createdAt']} UTC",size=12),
            ft.Text(f"Объект: {item['targetType']} №{item['targetId']}"),ft.Text('Причина: '+item['reason'])])))

    def render(update=True):
        try:
            status.visible=section.value=='Жалобы';query.visible=section.value=='Аккаунты'
            if section.value=='Жалобы':items=client.reports(status.value,offset['value']);factory=reportCard
            elif section.value=='Аккаунты':items=client.users(query.value or '',offset['value']);factory=userCard
            else:items=client.audit(offset['value']);factory=auditCard
            result.controls=[factory(item) for item in items] or [ft.Text('Записей пока нет.')]
            previous.disabled=offset['value']==0;following.disabled=len(items)<50
            pageNumber.value=f"Страница {offset['value']//50+1}"
        except ApiError as error:
            if error.statusCode==401:raise
            result.controls=([ft.Text(str(error)),ft.TextButton('На главную',on_click=lambda event:page.go('/home'))]
                             if error.statusCode==403 else [createLoadError(page,error,lambda:render())])
        if update:page.update()
    @authenticatedAction(page,user)
    def reset(event):offset['value']=0;render()
    @authenticatedAction(page,user)
    def before(event):offset['value']=max(0,offset['value']-50);render()
    @authenticatedAction(page,user)
    def after(event):offset['value']+=50;render()
    @authenticatedAction(page,user)
    def refresh(event):render()
    section.on_change=reset;status.on_change=reset;query.on_submit=reset
    previous.on_click=before;following.on_click=after
    render(False)
    return ft.View('/admin',padding=12,appbar=ft.AppBar(title=ft.Text('Администрирование'),
        leading=ft.IconButton(icon=ft.Icons.ARROW_BACK,on_click=lambda event:page.go('/home'))),
        controls=[ft.ListView(expand=True,build_controls_on_demand=False,spacing=12,controls=[
            ft.Text('Серверное сообщество' if client.remote else 'Локальное сообщество на этом устройстве'),
            ft.Container(content=section,padding=ft.padding.symmetric(vertical=6)),
            ft.Container(content=status,padding=ft.padding.symmetric(vertical=6)),query,
            ft.Row(wrap=True,controls=[ft.TextButton('Найти',on_click=reset),ft.TextButton('Обновить панель',on_click=refresh)]),
            result,ft.Row(wrap=True,controls=[previous,pageNumber,following])])])
