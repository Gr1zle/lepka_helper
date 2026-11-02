import asyncio
import json
from datetime import datetime
import flet as ft
from api_client import getApiUrl,ApiError
from community_outbox import entries,flush,remove
from publication_drafts import saveDraft,listDrafts,deleteDraft
from views.personal_data import localAction
from ui_helpers import showMessage


def createConnectionBanner(page,user):
    if not user or not user.get('apiUrl'):return ft.Container()
    text=ft.Text(size=12)
    def refresh():
        current=page.session.get('currentUser') or {}
        if current.get('userId')!=user['userId']:return
        state=page.session.get('connectionState') or ('offline' if current.get('offline') else 'online')
        count=len(entries(user,user['apiUrl']))
        text.value={'online':'Сервер доступен','offline':'Оффлайн: личные данные на устройстве','sending':'Отправка очереди…','error':'Ошибка локального кеша или очереди'}[state]+f' · в очереди: {count}'
        try:
            if text.page:page.update()
        except AssertionError:pass
    page.session.set('updateConnectionBanner',refresh)
    # До монтирования Control.page ещё недоступен.
    state='offline' if user.get('offline') else 'online'
    text.value=('Оффлайн: личные данные на устройстве' if state=='offline' else 'Сервер доступен')+f" · в очереди: {len(entries(user,user['apiUrl']))}"
    return ft.Container(padding=ft.padding.symmetric(horizontal=16,vertical=4),
        content=ft.Row([ft.Icon(ft.Icons.CLOUD_OUTLINED,size=18,color=ft.Colors.PRIMARY),
            ft.Container(content=text,expand=True),createOutboxButton(page,user)],spacing=8))


def createOutboxButton(page,user):
    if not user or not user.get('apiUrl'):return ft.Container()
    action=localAction(page,user);apiUrl=user['apiUrl']
    @action
    def openQueue(event):
        items=ft.Column(spacing=8);busy={'value':False}
        def render():
            controls=[]
            for row in entries(user,apiUrl):
                payload=json.loads(row['payloadJson'])
                label={'publication':'Публикация','like':'Лайк','comment':'Комментарий'}[row['kind']]
                parts=[ft.Text(label+' · '+{'pending':'ожидает','sending':'отправляется','blocked':'нужно исправление'}[row['state']]),
                    ft.Text(payload.get('titleText',payload.get('commentText',''))[:100]),ft.Text(row['lastError'],size=12)]
                @action
                def discard(event,rid=row['requestId']):remove(user,apiUrl,rid);render();page.update()
                parts.append(ft.TextButton('Убрать из очереди',disabled=row['state']=='sending',on_click=discard))
                if row['kind']=='publication' and row['state']=='blocked' and not payload.get('projectDetailsJson'):
                    @action
                    def toDraft(event,item=row):
                        saveDraft(user['userId'],apiUrl,json.loads(item['payloadJson']));remove(user,apiUrl,item['requestId']);render();page.update()
                        showMessage(page,'Работа возвращена в черновики. Откройте её на главной вкладке.')
                    parts.append(ft.TextButton('Вернуть в черновики',on_click=toDraft))
                controls.append(ft.Card(content=ft.Container(padding=10,content=ft.Column(parts))))
            items.controls=controls or [ft.Text('Очередь пуста.')]
        @action
        def retry(event):
            if busy['value']:return
            busy['value']=True
            try:
                def active():
                    current=page.session.get('currentUser') or {}
                    return current.get('sessionToken')==user.get('sessionToken') and getApiUrl()==apiUrl
                flush(user,apiUrl,active,force=True);render();page.update()
            finally:busy['value']=False
        dialog=ft.AlertDialog(title=ft.Text('Очередь отправки'),content=ft.Container(width=440,height=420,content=ft.ListView(controls=[
            ft.Text('Отправка продолжается при доступном сервере и открытом приложении. Удаление заявки не отменяет действие, которое сервер уже успел принять.'),
            ft.TextButton('Отправить сейчас',on_click=retry),items])),actions=[ft.TextButton('Закрыть',on_click=lambda e:page.close(dialog))])
        def refreshIfOpen():
            current=page.session.get('currentUser') or {}
            if dialog.open and current.get('sessionToken')==user.get('sessionToken'):render()
        page.session.set('refreshOutboxDialog',refreshIfOpen)
        render();page.open(dialog)
    return ft.IconButton(icon=ft.Icons.CLOUD_UPLOAD_OUTLINED,tooltip='Очередь отправки',on_click=openQueue)


def createDraftTools(page,user,fields,photos,onPhotos):
    if not user:return ft.Container()
    apiUrl=getApiUrl();action=localAction(page,user)
    active={'id':None,'generation':0};notice=ft.Text(size=12)
    def payload():
        import base64
        return dict(titleText=fields['title'].value or '',descriptionText=fields['description'].value or '',categoryName=fields['category'].value,
            tagsText=fields['tags'].value or '',challengeId=int(fields['contest'].value) if fields['contest'].value else None,
            photos=[dict(name=photo['name'],imageBase64=base64.b64encode(photo['data']).decode()) for photo in photos])
    def write(event=None):
        data=payload()
        if not data['titleText'] and not data['descriptionText'] and not data['tagsText'] and not photos:return
        active['id']=saveDraft(user['userId'],apiUrl,data,active['id']);notice.value='Черновик сохранён на устройстве'
    def changed(event=None):
        active['generation']+=1;generation=active['generation']
        async def later():
            await asyncio.sleep(.7)
            current=page.session.get('currentUser') or {}
            if active['generation']!=generation or current.get('sessionToken')!=user.get('sessionToken') or getApiUrl()!=apiUrl:return
            try:write();page.update()
            except (ValueError,OSError):notice.value='Не удалось сохранить черновик';page.update()
        page.run_task(later)
    for name in ('title','description','category','tags','contest'):fields[name].on_change=changed
    def clearAfterSend():
        active['generation']+=1
        if active['id']:deleteDraft(user['userId'],apiUrl,active['id'])
        active['id']=None;notice.value=''
    @action
    def new(event):
        write();active['generation']+=1;active['id']=None
        for key in ('title','description','tags'):fields[key].value=''
        fields['contest'].value='';photos.clear();onPhotos();page.update()
    @action
    def choose(event):
        write()
        controls=[]
        for row in listDrafts(user['userId'],apiUrl):
            @action
            def openDraft(event,item=row):
                import base64
                active['generation']+=1;active['id']=item['draftId'];data=item['payload']
                for key,target in [('titleText','title'),('descriptionText','description'),('categoryName','category'),('tagsText','tags')]:fields[target].value=data.get(key,'')
                value=str(data.get('challengeId') or '')
                if value not in [option.key for option in fields['contest'].options]:
                    fields['contest'].options.append(ft.dropdown.Option(value,'Сохранённое задание: '+value))
                fields['contest'].value=value
                photos[:]=[dict(name=p['name'],data=base64.b64decode(p['imageBase64'])) for p in data.get('photos',[])]
                page.close(dialog);onPhotos();page.update()
            @action
            def removeDraft(event,key=row['draftId']):deleteDraft(user['userId'],apiUrl,key);page.close(dialog);choose(None)
            controls.append(ft.Card(content=ft.Container(padding=10,content=ft.Column([ft.Text(row['payload'].get('titleText') or 'Без названия'),
                ft.Row(wrap=True,controls=[ft.TextButton('Открыть черновик',on_click=openDraft),ft.TextButton('Удалить черновик',on_click=removeDraft)])]))))
        dialog=ft.AlertDialog(title=ft.Text('Мои черновики'),content=ft.Container(width=400,height=350,content=ft.ListView(controls=controls or [ft.Text('Черновиков пока нет.')])),
            actions=[ft.TextButton('Закрыть',on_click=lambda e:page.close(dialog))])
        page.open(dialog)
    fields['saveDraft']=action(write);fields['draftChanged']=changed;fields['clearDraft']=clearAfterSend
    return ft.Column([ft.Row(wrap=True,controls=[ft.TextButton('Сохранить черновик',on_click=action(lambda e:(write(),page.update()))),
        ft.TextButton('Мои черновики',on_click=choose),ft.TextButton('Новый черновик',on_click=new)]),notice])
