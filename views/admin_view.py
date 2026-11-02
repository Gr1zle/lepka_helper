from localization import tr, term, message as translateMessage
"""Панель показывает только явно разрешённые разделы, сервис повторно проверяет действие."""
import flet as ft
from moderation_gateway import ModerationClient
from ui_helpers import getCurrentUser,authenticatedAction,createLoadError
from views.moderation_actions import reasonDialog
from views.role_editor import openRoleEditor,openRoleAssignment
from views.community_tab import createPhotoViewer
from community_gateway import CommunityClient
from api_client import ApiError
from role_service import PERMISSIONS

STATUS_LABELS={'open':'Открыта','resolved':'Рассмотрена','rejected':'Отклонена'}
ACTION_LABELS={'user.delete':'Удаление аккаунта','role.create':'Создание роли','role.update':'Изменение прав роли','role.delete':'Удаление роли',
 'challenge.auto':'Автоматические итоги конкурса','challenge.create':'Создание задания','challenge.finished':'Итоги задания',
 'challenge.cancelled':'Отмена задания','material.delete':'Удаление материала','user.block':'Блокировка аккаунта',
 'user.unblock':'Разблокировка аккаунта','role.admin':'Назначение администратора','role.user':'Снятие роли администратора',
 'report.resolved':'Жалоба рассмотрена','report.rejected':'Жалоба отклонена'}
SECTIONS={'Жалобы':'reports.manage','Аккаунты':'accounts.view','Журнал':'audit.view','Роли':'roles.manage','Конкурсы':'contests.manage','Материалы':'materials.remove','Учебный каталог':'catalog.manage'}


def createAdminView(page):
    user=getCurrentUser(page);client=ModerationClient(user)
    permissions=set(client.access()['permissions']) if user else set()
    sections=[label for label,cap in SECTIONS.items() if cap in permissions]
    if not sections:
        return ft.View('/admin',controls=[ft.Text(tr(page, 'Нет прав для доступа к панели')),ft.TextButton(tr(page, 'На главную'),on_click=lambda e:page.go('/home'))])
    section=ft.Dropdown(label=tr(page, 'Раздел панели'),value=sections[0],options=[ft.dropdown.Option(key=v, text=term(page, v)) for v in sections])
    status=ft.Dropdown(label=tr(page, 'Статус жалоб'),value='open',options=[ft.dropdown.Option(k,v) for k,v in [*STATUS_LABELS.items(),('all','Все')]])
    query=ft.TextField(label=tr(page, 'Никнейм или email'),max_length=100,visible=False)
    result=ft.Column(spacing=10);offset={'value':0};pageNumber=ft.Text()
    previous=ft.TextButton(tr(page, 'Предыдущие'),disabled=True);following=ft.TextButton(tr(page, 'Следующие'))

    def ask(title,action,callback):reasonDialog(page,user,title,action,callback,lambda:render())

    def reportCard(item):
        content=[ft.Text(tr(page, 'Жалоба №{v0} · {v1}', v0=item['reportId'], v1=STATUS_LABELS[item['status']]),size=18,weight=ft.FontWeight.BOLD),
                 ft.Text(tr(page, 'От: {v0} · {v1} UTC', v0=item['reporter'], v1=item['createdAt']),size=12),ft.Text(tr(page, 'Причина: ')+item['reason'])]
        material=item['material']
        if material:
            content.extend([ft.Text((tr(page, 'Публикация') if item['targetType']=='post' else tr(page, 'Комментарий'))+f" №{item['targetId']} · {material['nickname']}"),ft.Text(material['title'],weight=ft.FontWeight.BOLD),ft.Text(material['text'])])
            if item['targetType']=='post' and material['photoIds']:content.append(createPhotoViewer(page,material['photoIds'],CommunityClient(user)))
        else:content.append(ft.Text(tr(page, 'Материал уже недоступен. Можно закрыть жалобу.')))
        if item['resolution']:content.append(ft.Text(tr(page, 'Решение: ')+item['resolution']))
        if item['status']=='open':
            @authenticatedAction(page,user)
            def reject(e):ask('Отклонить жалобу','Отклонить жалобу',lambda reason:client.resolve(item['reportId'],'rejected',reason))
            @authenticatedAction(page,user)
            def resolve(e):ask('Закрыть рассмотренную жалобу','Закрыть жалобу',lambda reason:client.resolve(item['reportId'],'resolved',reason))
            actions=[ft.TextButton(tr(page, 'Отклонить жалобу'),on_click=reject),ft.TextButton(tr(page, 'Закрыть жалобу'),on_click=resolve)]
            if material and 'materials.remove' in permissions:
                @authenticatedAction(page,user)
                def remove(e):ask('Удалить материал без восстановления?','Удалить материал',lambda reason:client.remove(item['targetType'],item['targetId'],reason))
                actions.append(ft.TextButton(tr(page, 'Удалить материал'),on_click=remove))
            content.append(ft.Row(wrap=True,controls=actions))
        return card(content)

    def card(content):return ft.Card(content=ft.Container(padding=14,content=ft.Column(controls=content)))

    def userCard(item):
        label={'admin':'Администратор','user':'Пользователь'}.get(item['roleName'],item['roleName'])
        content=[ft.Text(f"{item['nickname']} · №{item['userId']}",size=18,weight=ft.FontWeight.BOLD),ft.Text(item['email']),
                 ft.Text(label+' · '+(tr(page, 'Заблокирован') if item['isBlocked'] else tr(page, 'Активен')))]
        if item['userId']==user.get('serverUserId',user['userId']):content.append(ft.Text(tr(page, 'Ваш аккаунт'),size=12))
        else:
            actions=[];canTarget='roles.manage' in permissions or item['roleName']=='user'
            if 'accounts.block' in permissions and canTarget:
                @authenticatedAction(page,user)
                def block(e):
                    label='Разблокировать аккаунт' if item['isBlocked'] else 'Заблокировать аккаунт'
                    ask(label,label,lambda reason:client.changeUser(item['userId'],reason,blocked=not bool(item['isBlocked'])))
                actions.append(ft.TextButton(tr(page, 'Разблокировать') if item['isBlocked'] else tr(page, 'Заблокировать'),on_click=block))
            if 'roles.manage' in permissions:
                @authenticatedAction(page,user)
                def role(e):
                    value='user' if item['roleName']=='admin' else 'admin'
                    label='Снять роль администратора' if value=='user' else 'Назначить администратором'
                    ask(label,label,lambda reason:client.changeUser(item['userId'],reason,role=value))
                @authenticatedAction(page,user)
                def assign(e):openRoleAssignment(page,user,client,item,lambda:render())
                actions.extend([ft.TextButton(tr(page, 'Снять роль администратора') if item['roleName']=='admin' else tr(page, 'Назначить администратором'),on_click=role),
                                ft.TextButton(tr(page, 'Назначить другую роль'),on_click=assign)])
            if 'accounts.delete' in permissions and canTarget:
                @authenticatedAction(page,user)
                def remove(e):ask('Удалить аккаунт '+item['email']+' и личные данные без восстановления?',
                                 'Удалить аккаунт и данные',lambda reason:client.deleteUser(item['userId'],reason))
                actions.append(ft.TextButton(tr(page, 'Удалить аккаунт'),on_click=remove))
            content.append(ft.Row(wrap=True,controls=actions))
        return card(content)

    def auditCard(item):return card([ft.Text(ACTION_LABELS.get(item['action'],item['action']),size=17,weight=ft.FontWeight.BOLD),
        ft.Text(f"{item['actorNickname']} · {item['createdAt']} UTC",size=12),ft.Text(tr(page, 'Объект: {v0} №{v1}', v0=item['targetType'], v1=item['targetId'])),ft.Text(tr(page, 'Причина: ')+item['reason'])])

    def roleCard(item):
        @authenticatedAction(page,user)
        def edit(e):openRoleEditor(page,user,client,item,lambda:render())
        @authenticatedAction(page,user)
        def remove(e):ask('Удалить роль '+item['title']+'?','Удалить роль',lambda reason:client.deleteRole(item['roleCode'],reason))
        return card([ft.Text(item['title'],size=18,weight=ft.FontWeight.BOLD),ft.Text(item['roleCode']),
            ft.Text(tr(page, 'Права: ')+(', '.join(PERMISSIONS.get(v,v) for v in item['permissions']) or 'Нет полномочий администрирования')),ft.Text(tr(page, 'Назначено аккаунтов: ')+str(item['assignedCount'])),
            ft.Row(wrap=True,controls=[ft.TextButton(tr(page, 'Изменить права'),on_click=edit),ft.TextButton(tr(page, 'Удалить роль'),disabled=item['assignedCount']>0,on_click=remove)])])

    @authenticatedAction(page,user)
    def createRole(e):openRoleEditor(page,user,client,onDone=lambda:render())
    newRole=ft.OutlinedButton(tr(page, 'Создать роль'),visible=False,on_click=createRole)

    def render(update=True):
        try:
            current=client.access();permissions.clear();permissions.update(current['permissions'])
            if SECTIONS[section.value] not in permissions:raise ApiError('Недостаточно прав для этого действия',403)
            status.visible=section.value=='Жалобы';query.visible=section.value=='Аккаунты';newRole.visible=section.value=='Роли'
            if section.value=='Жалобы':items=client.reports(status.value,offset['value']);factory=reportCard
            elif section.value=='Аккаунты':items=client.users(query.value or '',offset['value']);factory=userCard
            elif section.value=='Журнал':items=client.audit(offset['value']);factory=auditCard
            elif section.value=='Роли':items=client.roles()['items'];factory=roleCard
            else:items=[];factory=None
            result.controls=([ft.OutlinedButton(tr(page, 'Перейти к конкурсам') if section.value=='Конкурсы' else tr(page, 'К ленте для модерации'),
                                on_click=authenticatedAction(page,user)(lambda e:page.go('/challenges' if section.value=='Конкурсы' else '/home')))]
                             if section.value in ('Конкурсы','Материалы') else [factory(item) for item in items] or [ft.Text(tr(page, 'Записей пока нет.'))])
            previous.disabled=offset['value']==0;following.disabled=len(items)<50;pageNumber.value=tr(page, 'Страница {v0}', v0=offset['value'] // 50 + 1)
            if section.value=='Учебный каталог':result.controls=[ft.OutlinedButton(tr(page, 'Управление учебным каталогом'),on_click=authenticatedAction(page,user)(lambda e:page.go('/catalog-admin')))]
        except ApiError as error:
            if error.statusCode==401:raise
            result.controls=[ft.Text(translateMessage(page,str(error)))] if error.statusCode==403 else [createLoadError(page,error,lambda:render())]
        if update:page.update()
    @authenticatedAction(page,user)
    def reset(e):offset['value']=0;render()
    @authenticatedAction(page,user)
    def before(e):offset['value']=max(0,offset['value']-50);render()
    @authenticatedAction(page,user)
    def after(e):offset['value']+=50;render()
    @authenticatedAction(page,user)
    def refresh(e):render()
    section.on_change=reset;status.on_change=reset;query.on_submit=reset;previous.on_click=before;following.on_click=after
    render(False)
    return ft.View('/admin',padding=12,appbar=ft.AppBar(title=ft.Text(tr(page, 'Администрирование')),leading=ft.IconButton(icon=ft.Icons.ARROW_BACK,on_click=lambda e:page.go('/home'))),
        controls=[ft.ListView(expand=True,build_controls_on_demand=False,spacing=12,controls=[
            ft.Text(tr(page, 'Серверное сообщество') if client.remote else tr(page, 'Локальное сообщество на этом устройстве')),
            ft.Container(content=section,padding=ft.padding.symmetric(vertical=6)),newRole,status,query,
            ft.TextButton(tr(page, 'Обновить панель'),on_click=refresh),result,ft.Row(wrap=True,controls=[previous,pageNumber,following])])])
