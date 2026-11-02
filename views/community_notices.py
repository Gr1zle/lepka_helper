"""Участие в профиле и центр личных уведомлений сообщества."""
import flet as ft
from challenge_gateway import ChallengeClient
from community_gateway import CommunityClient
from ui_helpers import authenticatedAction,createLoadError,showMessage
from api_client import ApiError
from notification_center import NoticeCenter,SOURCES
from personal_notices import snoozeLesson
from views.personal_notice_settings import openPersonalNoticeSettings
from views.notification_delivery import openDeliverySettings

KIND_LABELS={'all':'Все события','award':'Призовые места','like':'Лайки','comment':'Комментарии','reply':'Ответы'}


def createNoticeButton(page,user):
    if not user:return ft.Container()
    client=NoticeCenter(user)
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
        source=ft.Dropdown(label='Источник уведомлений',value='all',options=[ft.dropdown.Option(k,v) for k,v in SOURCES.items()])
        kind=ft.Dropdown(label='Тип уведомлений',value='all',options=[ft.dropdown.Option(k,v) for k,v in KIND_LABELS.items()])
        unread=ft.Checkbox(label='Только непрочитанные',value=False)
        previous=ft.TextButton('Предыдущие');following=ft.TextButton('Следующие');number=ft.Text()

        @authenticatedAction(page,user)
        def openItem(item):
            page.close(dialog)
            if item['source']=='projects':
                from views.project_planner import openPlannerProject
                openPlannerProject(page,user,item['projectId']);return
            if item['source']=='learning':
                if item.get('contentId'):page.go('/catalog/'+item['contentId']);return
                page.session.set('openBuiltinLesson',item['lessonId'])
                page.session.set('homeTab',1)
                navigate=page.session.get('navigateHomeTab')
                if callable(navigate):navigate(1)
                else:page.go('/home')
                return
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
                items=client.notices(offset['value'],kind.value,bool(unread.value),source.value)
                controls=[]
                for item in items:
                    @authenticatedAction(page,user)
                    def read(event,nid=item['noticeId']):
                        client.readNotice(nid);render();summary();page.update()
                    if item['source']!='community':title=item['title']
                    elif item['kind']=='award':title=f"{item['place']} место: {item['title']}"
                    else:
                        verb={'like':'понравилась ваша работа','comment':'комментирует вашу работу','reply':'отвечает на ваш комментарий'}[item['kind']]
                        title=f"{item['actor']}: {verb}"
                    parts=[ft.Text(title,weight=ft.FontWeight.BOLD)]
                    if item['source']=='community' and item['kind']!='award':parts.append(ft.Text(item['title']))
                    if item.get('preview'):parts.append(ft.Text(item['preview'][:200]))
                    parts.extend([ft.Text('Прочитано' if item['isRead'] else 'Новое уведомление'),ft.Text(item['createdAt']+(' · дата' if item['source']=='projects' else ' UTC'),size=12),
                        ft.Row(wrap=True,controls=[ft.TextButton('Открыть проект' if item['source']=='projects' else 'Открыть урок' if item['source']=='learning' else 'Открыть итоги' if item['kind']=='award' else 'Открыть публикацию',
                            on_click=lambda e,i=item:openItem(i)),ft.TextButton('Прочитано',visible=not item['isRead'],on_click=read)])])
                    if item['source']=='learning' and item['kind']=='resume':
                        @authenticatedAction(page,user)
                        def snooze(event,nid=item['noticeId']):
                            snoozeLesson(user['userId'],nid,1);render();summary();page.update()
                        parts.append(ft.TextButton('Напомнить завтра',on_click=snooze))
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
        def changeSource(event):
            if source.value in ('projects','learning'):kind.value='all'
            kind.disabled=source.value in ('projects','learning')
            reset(event)
        source.on_change=changeSource
        dialog=ft.AlertDialog(title=ft.Text('Центр уведомлений'),content=ft.Container(width=440,height=430,
            content=ft.ListView(spacing=12,controls=[source,ft.Container(content=kind,padding=6),unread,
                ft.TextButton('Настроить личные уведомления',on_click=lambda e:openPersonalNoticeSettings(page,user,lambda:(render(),summary(),page.update()))),
                ft.Row(wrap=True,controls=[ft.TextButton('Прочитать все уведомления',on_click=readAll),ft.TextButton('Обновить уведомления',on_click=reset)]),
                entries,ft.Row(wrap=True,controls=[previous,number,following])])),
            actions=[ft.TextButton('Закрыть',on_click=lambda e:page.close(dialog))])
        render();summary();page.open(dialog)
    summary()
    page.session.set('openNoticeCenterCallback',openNotices)
    return ft.Column(spacing=4,controls=[ft.OutlinedButton('Центр уведомлений',icon=ft.Icons.NOTIFICATIONS_OUTLINED,on_click=openNotices),counter,
        ft.TextButton('Доставка уведомлений',on_click=lambda e:openDeliverySettings(page,user))])


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
