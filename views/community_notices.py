"""Участие в профиле и центр личных уведомлений сообщества."""
import flet as ft
from challenge_gateway import ChallengeClient
from community_gateway import CommunityClient
from ui_helpers import authenticatedAction,createLoadError,showMessage
from api_client import ApiError

KIND_LABELS={'all':'Все события','award':'Призовые места','like':'Лайки','comment':'Комментарии','reply':'Ответы'}


def createNoticeButton(page,user):
    if not user:return ft.Container()
    client=ChallengeClient(user)
    counter=ft.Text(size=12)

    def summary():
        try:counter.value='Непрочитанных: '+str(client.noticeSummary()['unread'])
        except ApiError as error:
            if error.statusCode==401:raise
            counter.value='Счётчик временно недоступен'

    @authenticatedAction(page,user)
    def openNotices(event):
        offset={'value':0}
        entries=ft.Column(spacing=12)
        kind=ft.Dropdown(label='Тип уведомлений',value='all',options=[ft.dropdown.Option(k,v) for k,v in KIND_LABELS.items()])
        unread=ft.Checkbox(label='Только непрочитанные',value=False)
        previous=ft.TextButton('Предыдущие');following=ft.TextButton('Следующие');number=ft.Text()

        @authenticatedAction(page,user)
        def openItem(item):
            page.close(dialog)
            if item['kind']=='award':
                page.session.set('openChallengeId',item['challengeId']);page.go('/challenges');return
            community=CommunityClient(user)
            post=community.getPost(item['postId'])
            if not post:
                showMessage(page,'Материал уже недоступен',True);return
            from views.community_tab import createPostCard
            postDialog=ft.AlertDialog(title=ft.Text('Публикация из уведомления'),content=ft.Container(width=500,height=440,
                content=ft.ListView(controls=[createPostCard(page,post,user,lambda:page.close(postDialog))])),
                actions=[ft.TextButton('Закрыть',on_click=lambda e:page.close(postDialog))])
            page.open(postDialog)

        def render():
            try:
                items=client.notices(offset['value'],kind.value,bool(unread.value))
                controls=[]
                for item in items:
                    @authenticatedAction(page,user)
                    def read(event,nid=item['noticeId']):
                        client.readNotice(nid);render();summary();page.update()
                    if item['kind']=='award':title=f"{item['place']} место: {item['title']}"
                    else:
                        verb={'like':'понравилась ваша работа','comment':'комментирует вашу работу','reply':'отвечает на ваш комментарий'}[item['kind']]
                        title=f"{item['actor']}: {verb}"
                    parts=[ft.Text(title,weight=ft.FontWeight.BOLD)]
                    if item['kind']!='award':parts.append(ft.Text(item['title']))
                    if item.get('preview'):parts.append(ft.Text(item['preview'][:200]))
                    parts.extend([ft.Text('Прочитано' if item['isRead'] else 'Новое уведомление'),ft.Text(item['createdAt']+' UTC',size=12),
                        ft.Row(wrap=True,controls=[ft.TextButton('Открыть итоги' if item['kind']=='award' else 'Открыть публикацию',
                            on_click=lambda e,i=item:openItem(i)),ft.TextButton('Прочитано',visible=not item['isRead'],on_click=read)])])
                    controls.append(ft.Card(content=ft.Container(padding=12,content=ft.Column(controls=parts))))
                entries.controls=controls or [ft.Text('Уведомлений по этому фильтру нет.')]
                previous.disabled=offset['value']==0;following.disabled=len(items)<50
                number.value=f"Страница {offset['value']//50+1}"
            except ApiError as error:
                if error.statusCode==401:raise
                entries.controls=[createLoadError(page,error,lambda:(render(),page.update()))]

        @authenticatedAction(page,user)
        def move(delta):
            offset['value']=max(0,offset['value']+delta);render();page.update()
        @authenticatedAction(page,user)
        def reset(event):offset['value']=0;render();summary();page.update()
        @authenticatedAction(page,user)
        def readAll(event):client.readAllNotices();render();summary();page.update()
        previous.on_click=lambda e:move(-50);following.on_click=lambda e:move(50)
        kind.on_change=reset;unread.on_change=reset
        dialog=ft.AlertDialog(title=ft.Text('Уведомления сообщества'),content=ft.Container(width=440,height=430,
            content=ft.ListView(spacing=12,controls=[ft.Container(content=kind,padding=6),unread,
                ft.Row(wrap=True,controls=[ft.TextButton('Прочитать все уведомления',on_click=readAll),ft.TextButton('Обновить уведомления',on_click=reset)]),
                entries,ft.Row(wrap=True,controls=[previous,number,following])])),
            actions=[ft.TextButton('Закрыть',on_click=lambda e:page.close(dialog))])
        render();summary();page.open(dialog)
    summary()
    return ft.Column(spacing=4,controls=[ft.OutlinedButton('Уведомления сообщества',icon=ft.Icons.NOTIFICATIONS_OUTLINED,on_click=openNotices),counter])


def createChallengeProfile(page,user):
    if not user:return ft.Container()
    client=ChallengeClient(user);result=ft.Column(spacing=10)

    @authenticatedAction(page,user)
    def openChallenge(challengeId):
        page.session.set('openChallengeId',challengeId);page.go('/challenges')

    @authenticatedAction(page,user)
    def refresh(event=None,update=True):
        try:
            items=client.profile()
            controls=[ft.Text('Задания и награды',size=18,weight=ft.FontWeight.BOLD)]
            for item in items[:5]:
                label=(f"{item['place']} место" if item['place'] else 'Участвую' if item['state']=='open' else 'Завершено' if item['state']=='finished' else 'Отменено')
                controls.extend([ft.Text(label+': '+item['title']),ft.TextButton('Открыть задание',on_click=lambda e,cid=item['challengeId']:openChallenge(cid))])
            if not items:controls.append(ft.Text('Вы пока не участвуете в заданиях.'))
            controls.extend([createNoticeButton(page,user),ft.TextButton('Все задания',on_click=lambda e:openChallenge(None))])
            result.controls=controls
        except ApiError as error:
            if error.statusCode==401:raise
            result.controls=[createLoadError(page,error,lambda:refresh())]
        if update:page.update()
    refresh(update=False)
    return ft.Card(content=ft.Container(padding=16,content=result))
