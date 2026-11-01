"""Конкурсное участие в профиле и личные уведомления о призовых местах."""
import flet as ft
from challenge_gateway import ChallengeClient
from ui_helpers import authenticatedAction, createLoadError
from api_client import ApiError


def createChallengeProfile(page,user):
    if not user:return ft.Container()
    client=ChallengeClient(user)
    result=ft.Column(spacing=10)

    @authenticatedAction(page,user)
    def openChallenge(challengeId):
        page.session.set('openChallengeId',challengeId)
        page.go('/challenges')

    @authenticatedAction(page,user)
    def openNotices(event):
        offset={'value':0}
        entries=ft.Column(spacing=12)
        previous=ft.TextButton('Предыдущие')
        following=ft.TextButton('Следующие')
        number=ft.Text()

        def render():
            items=client.notices(offset['value'])
            controls=[]
            for item in items:
                @authenticatedAction(page,user)
                def read(event,nid=item['noticeId']):
                    client.readNotice(nid);render();page.update()
                @authenticatedAction(page,user)
                def openItem(event,cid=item['challengeId']):
                    page.close(dialog);openChallenge(cid)
                controls.append(ft.Card(content=ft.Container(padding=12,content=ft.Column(controls=[
                    ft.Text(f"{item['place']} место: {item['title']}",weight=ft.FontWeight.BOLD),
                    ft.Text('Прочитано' if item['isRead'] else 'Новое уведомление'),
                    ft.Text(item['createdAt']+' UTC',size=12),
                    ft.Row(wrap=True,controls=[ft.TextButton('Открыть итоги',on_click=openItem),
                        ft.TextButton('Прочитано',visible=not item['isRead'],on_click=read)])]))))
            entries.controls=controls or [ft.Text('Уведомлений о призовых местах пока нет.')]
            previous.disabled=offset['value']==0;following.disabled=len(items)<50
            number.value=f"Страница {offset['value']//50+1}"

        @authenticatedAction(page,user)
        def move(delta):
            offset['value']=max(0,offset['value']+delta);render();page.update()
        previous.on_click=lambda e:move(-50)
        following.on_click=lambda e:move(50)
        dialog=ft.AlertDialog(title=ft.Text('Уведомления сообщества'),content=ft.Container(width=440,height=400,
            content=ft.ListView(spacing=12,controls=[ft.Text('Призовые места в конкурсах. Настройка уведомлений находится в профиле.'),entries,
                ft.Row(wrap=True,controls=[previous,number,following])])),
            actions=[ft.TextButton('Закрыть',on_click=lambda e:page.close(dialog))])
        render();page.open(dialog)

    @authenticatedAction(page,user)
    def refresh(event=None,update=True):
        try:
            items=client.profile()
            controls=[ft.Text('Задания и награды',size=18,weight=ft.FontWeight.BOLD)]
            for item in items[:5]:
                label=(f"{item['place']} место" if item['place'] else 'Участвую' if item['state']=='open' else 'Завершено' if item['state']=='finished' else 'Отменено')
                controls.append(ft.Text(label+': '+item['title']))
                controls.append(ft.TextButton('Открыть задание',on_click=lambda e,cid=item['challengeId']:openChallenge(cid)))
            if not items:controls.append(ft.Text('Вы пока не участвуете в заданиях.'))
            controls.extend([ft.OutlinedButton('Уведомления сообщества',icon=ft.Icons.NOTIFICATIONS_OUTLINED,on_click=openNotices),
                ft.TextButton('Все задания',on_click=lambda e:openChallenge(None))])
            result.controls=controls
        except ApiError as error:
            if error.statusCode==401:raise
            result.controls=[createLoadError(page,error,lambda:refresh())]
        if update:page.update()
    refresh(update=False)
    return ft.Card(content=ft.Container(padding=16,content=result))
