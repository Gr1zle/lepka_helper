from localization import tr, term
import base64
import json
import uuid
import flet as ft
import flet_video as fv
from catalog_client import CatalogClient
from learning_catalog import CATEGORIES,LEVELS
from ui_helpers import getCurrentUser,authenticatedAction,showMessage,confirmAction,isWebClient
from api_client import ApiError
from views.admin_permissions import panelAccess
from views.catalog_file_picker import createCatalogFilePicker


def fail(page,error):
    if isinstance(error,ApiError) and error.statusCode==401:raise error
    showMessage(page,str(error),True)


def rootView(page,route,title,controls,back='/home'):
    return ft.View(route,padding=12,appbar=ft.AppBar(title=ft.Text(title),leading=ft.IconButton(icon=ft.Icons.ARROW_BACK,on_click=lambda e:page.go(back))),
        controls=[ft.ListView(expand=True,spacing=12,controls=controls)])


def createCatalogView(page,admin=False):
    user=getCurrentUser(page)
    if not user:return rootView(page,'/catalog','Учебный каталог',[ft.Text(tr(page, 'Войдите в аккаунт для доступа к серверным материалам.'))])
    client=CatalogClient(user)
    if admin and 'catalog.manage' not in panelAccess(page,user)['permissions']:
        return rootView(page,'/catalog-admin','Нет доступа',[ft.Text(tr(page, 'Нужно право управления учебным каталогом'))])
    query=ft.TextField(label=tr(page, 'Название, описание, теги или автор'),max_length=120)
    kind=ft.Dropdown(label=tr(page, 'Тип материала'),value='all',options=[ft.dropdown.Option('all',tr(page, 'Все')),ft.dropdown.Option('lesson',tr(page, 'Уроки')),ft.dropdown.Option('model',tr(page, '3D-модели'))])
    category=ft.Dropdown(label=tr(page, 'Категория каталога'),value='Все',options=[ft.dropdown.Option(key=v, text=term(page, v)) for v in ('Все',*CATEGORIES)])
    level=ft.Dropdown(label=tr(page, 'Сложность материала'),value='Все',options=[ft.dropdown.Option(key=v, text=term(page, v)) for v in ('Все',*LEVELS)])
    video=ft.Checkbox(label=tr(page, 'С видео'),value=False)
    saved=ft.Checkbox(label=tr(page, 'Только сохранённые офлайн'),value=False)
    favorites=ft.Checkbox(label=tr(page, 'Только избранное'),value=False)
    result=ft.Column(spacing=10);message=ft.Text()
    @authenticatedAction(page,user)
    def refresh(event=None):
        try:
            items=client.adminIndex() if admin else client.index()
            downloads={r['contentId']:r for r in client.downloads()}
            from database import openDatabase
            with openDatabase() as connection:personal={r['contentId']:dict(r) for r in connection.execute('SELECT * FROM learningPersonal WHERE userId=? AND apiUrl=?',(user['userId'],client.url))}
            if not admin:
                seen={i['contentId'] for i in items}
                for cid in downloads:
                    if cid not in seen:items.append(client.cached(cid)[0])
            controls=[];words=(query.value or '').casefold().replace('ё','е').split()
            for item in items:
                cid=item['contentId'];cached=downloads.get(cid)
                haystack=json.dumps([item['title'],item['description'],item['tags'],item.get('author','')],ensure_ascii=False).casefold().replace('ё','е')
                if (kind.value!='all' and kind.value!=item['kind'] or category.value!='Все' and category.value!=item['category']
                    or level.value!='Все' and level.value!=item['level'] or video.value and not item['withVideo']
                    or saved.value and not cached or favorites.value and not personal.get(cid,{}).get('favorite') or not all(w in haystack for w in words)):continue
                label=('Черновик' if item['state']=='draft' else 'Архив' if item['state']=='archived' else 'Опубликован') if admin else ('Сохранено · версия '+str(cached['revision']) if cached else 'Нужно скачать')
                if cached and cached['revision']<item['revision']:label+=' · есть обновление'
                actions=[ft.TextButton(tr(page, 'Редактировать') if admin else tr(page, 'Открыть сохранённое'),disabled=not admin and not cached,
                    on_click=lambda e,key=cid:page.go(('/catalog-edit/' if admin else '/catalog/')+key))]
                if not admin:
                    @authenticatedAction(page,user)
                    def download(e,key=cid):
                        try:client.download(key);refresh();showMessage(page,tr(page, 'Материал с файлами сохранён офлайн'))
                        except (ApiError,ValueError,LookupError) as exc:fail(page,exc)
                    actions.append(ft.TextButton(tr(page, 'Обновить копию') if cached else tr(page, 'Скачать для просмотра'),on_click=download))
                    if cached:
                        @authenticatedAction(page,user)
                        def remove(e,key=cid):
                            def confirmed():client.removeDownload(key);refresh()
                            confirmAction(page,'Удалить офлайн-копию?','Прогресс, заметка и избранное сохранятся; файлы понадобится скачать заново.',authenticatedAction(page,user)(confirmed))
                        actions.append(ft.TextButton(tr(page, 'Удалить копию'),on_click=remove))
                controls.append(ft.Card(content=ft.Container(padding=12,content=ft.Column(controls=[ft.Text(item['title'],size=18,weight=ft.FontWeight.BOLD),
                    ft.Text((tr(page, 'Урок') if item['kind']=='lesson' else tr(page, '3D-модель'))+tr(page, ' · {v0} · {v1} · {v2} мин.', v0=term(page,item['category']), v1=term(page,item['level']), v2=item['timeMinutes'])),
                    ft.Text(item['description'],max_lines=3,overflow=ft.TextOverflow.ELLIPSIS),ft.Text(tr(page, 'Автор: ')+item.get('author','Сотрудник')),ft.Text(label),ft.Row(wrap=True,controls=actions)]))))
            result.controls=controls or [ft.Text(tr(page, 'Материалов по этим условиям пока нет. Встроенные уроки и модели доступны в прежних разделах.'))]
            message.value=tr(page, 'Офлайн-копии: {v0}/20 · {v1:.1f}/100 МБ', v0=len(downloads), v1=sum((r['byteCount'] for r in downloads.values())) / 1024 / 1024)
        except (ApiError,ValueError,LookupError) as exc:fail(page,exc)
        page.update()
    for field in (kind,category,level,video,saved,favorites):field.on_change=refresh
    query.on_submit=refresh
    controls=[ft.Text(tr(page, 'Дополнительные материалы сотрудников. Встроенная библиотека сохраняется.')),query,
        ft.Row(wrap=True,controls=[ft.Container(width=160,content=kind),ft.Container(width=170,content=category),ft.Container(width=170,content=level)]),
        ft.Row(wrap=True,controls=[video,saved,favorites]),ft.FilledButton(tr(page, 'Обновить каталог'),on_click=refresh),message]
    if admin:
        controls.extend([ft.Row(wrap=True,controls=[ft.TextButton(tr(page, 'Добавить урок'),on_click=lambda e:page.go('/catalog-edit/new-lesson')),
            ft.TextButton(tr(page, 'Добавить 3D-модель'),on_click=lambda e:page.go('/catalog-edit/new-model'))])])
        @authenticatedAction(page,user)
        def stats(event):
            try:
                data=client.statistics()
                rows=[ft.Text(tr(page, '{v0}: читателей {v1}, завершили {v2}', v0=r['title'], v1=r['readers'], v2=r['completed'])) for r in data['items']]
                dialog=ft.AlertDialog(title=ft.Text(tr(page, 'Использование каталога')),content=ft.Column(tight=True,scroll=ft.ScrollMode.AUTO,controls=[ft.Text(tr(page, 'Файлы: {v0:.1f}/128 МБ', v0=data['assetBytes'] / 1024 / 1024)),*rows]),actions=[ft.TextButton(tr(page, 'Закрыть'),on_click=lambda e:page.close(dialog))])
                page.open(dialog)
            except (ApiError,ValueError) as exc:fail(page,exc)
        @authenticatedAction(page,user)
        def cleanup(event):
            def confirmed():
                try:showMessage(page,'Удалено неиспользуемых файлов: '+str(client.cleanup()))
                except (ApiError,ValueError) as exc:fail(page,exc)
            confirmAction(page,'Очистить неиспользуемые файлы?','Файлы в несохранённых редакторах других сотрудников тоже могут быть удалены. Сначала сохраните все черновики.',authenticatedAction(page,user)(confirmed))
        controls.extend([ft.TextButton(tr(page, 'Статистика использования'),on_click=stats),ft.TextButton(tr(page, 'Очистить неиспользуемые файлы'),on_click=cleanup)])
    else:
        @authenticatedAction(page,user)
        def subscribe(event):
            if category.value=='Все':showMessage(page,tr(page, 'Выберите конкретную категорию'),True);return
            client.subscribe(category.value,True);showMessage(page,tr(page, 'Новые материалы категории появятся в центре уведомлений'))
        @authenticatedAction(page,user)
        def unsubscribe(event):
            if category.value!='Все':client.subscribe(category.value,False);showMessage(page,tr(page, 'Подписка отключена'))
        controls.extend([ft.TextButton(tr(page, 'Подписаться на выбранную категорию'),on_click=subscribe),ft.TextButton(tr(page, 'Отключить подписку категории'),on_click=unsubscribe)])
        if 'catalog.manage' in panelAccess(page,user)['permissions']:controls.append(ft.OutlinedButton(tr(page, 'Управление учебным каталогом'),on_click=lambda e:page.go('/catalog-admin')))
    controls.append(result);refresh()
    return rootView(page,'/catalog-admin' if admin else '/catalog','Управление каталогом' if admin else 'Учебный каталог',controls)


def createCatalogDetail(page,cid):
    user=getCurrentUser(page);client=CatalogClient(user)
    try:info,assets=client.cached(cid)
    except (ApiError,ValueError) as exc:return rootView(page,'/catalog/'+cid,'Учебный материал',[ft.Text(str(exc))],'/catalog')
    document=info['document'];personal=client.personal(cid)
    checked=set(json.loads(personal['checkedJson'])) if personal['revision']==info['revision'] else set()
    favorite=ft.Checkbox(label=tr(page, 'В избранном'),value=bool(personal['favorite']))
    note=ft.TextField(label=tr(page, 'Личная заметка к материалу'),value=personal['note'],multiline=True,max_length=2000)
    boxes=[];progress=ft.Text()
    @authenticatedAction(page,user)
    def save(event=None):
        try:
            values=[i for i,box in enumerate(boxes) if box.value]
            complete=client.savePersonal(cid,info['revision'],values,bool(favorite.value),note.value or '')
            progress.value=tr(page, 'Этапы: {v0}/{v1}', v0=len(values), v1=len(boxes))+(tr(page, ' · Урок завершён') if complete else '')
            page.update()
            if not user.get('offline'):
                try:client.flushUsage()
                except (ApiError,ValueError,LookupError):pass
        except (ApiError,ValueError) as exc:fail(page,exc)
    controls=[ft.Text(document['title'],size=23,weight=ft.FontWeight.BOLD),ft.Text(tr(page, 'Версия {v0} · сохранённая офлайн-копия', v0=info['revision'])),
        ft.Text(document['description']),favorite,ft.Text(tr(page, 'Материалы: ')+', '.join(document['materials'])),progress]
    if personal['revision'] not in (0,info['revision']):controls.append(ft.Text(tr(page, 'Версия изменилась: этапы новой версии отмечаются заново. Заметка и избранное сохранены.')))
    def image(aid):return ft.Image(src_base64=assets[aid]['contentBase64'],height=220,fit=ft.ImageFit.CONTAIN)
    if document['coverAsset']:controls.append(image(document['coverAsset']))
    if document['modelAsset']:controls.append(ft.FilledButton(tr(page, 'Открыть 3D-модель'),on_click=lambda e:page.go('/models/catalog-'+cid)))
    for index,step in enumerate(document['steps']):
        box=ft.Checkbox(label=tr(page, 'Этап выполнен'),value=index in checked,on_change=save);boxes.append(box)
        content=[ft.Text(f"{index+1}. {step['text']}"),box]
        if step['imageAsset']:content.append(image(step['imageAsset']))
        if step['videoAsset']:
            @authenticatedAction(page,user)
            def play(event,aid=step['videoAsset'],container=content):
                try:
                    from catalog_media import videoTicket,nativeVideo
                    from views.project_transfer import webAddress
                    resource=webAddress(page)+'/catalog-media/'+videoTicket(user,assets[aid]) if isWebClient(page) else nativeVideo(user,assets[aid])
                    if isWebClient(page):
                        page.launch_url(resource,web_window_name='_blank');return
                    from views.project_transfer import androidClient
                    if not androidClient(page):
                        from pathlib import Path
                        page.launch_url(Path(resource).as_uri());return
                    player=fv.Video(playlist=[fv.VideoMedia(resource)],autoplay=False,show_controls=True,height=220,on_error=lambda e:showMessage(page,tr(page, 'Видео не воспроизводится: используйте MP4 H.264/AAC и проверьте поддержку устройства'),True))
                    dialog=ft.AlertDialog(title=ft.Text(tr(page, 'Видео этапа')),content=ft.Container(width=480,content=player),actions=[ft.TextButton(tr(page, 'Закрыть'),on_click=lambda e:page.close(dialog))])
                    page.open(dialog)
                except (ApiError,ValueError,OSError) as exc:fail(page,exc)
            content.append(ft.TextButton(tr(page, 'Смотреть видео этапа'),on_click=play))
        controls.append(ft.Card(content=ft.Container(padding=12,content=ft.Column(controls=content))))
    favorite.on_change=save
    controls.extend([note,ft.FilledButton(tr(page, 'Сохранить заметку и прогресс'),on_click=save)])
    save()
    return rootView(page,'/catalog/'+cid,'Учебный материал',controls,'/catalog')


def createCatalogEditor(page,cid):
    user=getCurrentUser(page);client=CatalogClient(user)
    if 'catalog.manage' not in panelAccess(page,user)['permissions']:return rootView(page,'/catalog-admin','Нет доступа',[ft.Text(tr(page, 'Нужно право управления учебным каталогом'))])
    new=cid.startswith('new-');kindName=cid[4:] if new else None
    try:info=client.detail(cid,True) if not new else dict(contentId=uuid.uuid4().hex,revision=0,state='draft',document=dict(kind=kindName,title='',category='Другое',level='Начинающий',timeMinutes=30,description='',tags=[],materials=[],steps=[],coverAsset=None,modelAsset=None))
    except (ApiError,ValueError,LookupError) as exc:return rootView(page,'/catalog-admin','Редактор',[ft.Text(str(exc))])
    document=info['document'];steps=[];stepList=ft.Column(spacing=10);message=ft.Text()
    title=ft.TextField(label=tr(page, 'Название материала'),value=document['title'],max_length=100)
    description=ft.TextField(label=tr(page, 'Описание материала'),value=document['description'],multiline=True,min_lines=2,max_length=3000)
    category=ft.Dropdown(label=tr(page, 'Категория материала'),value=document['category'],options=[ft.dropdown.Option(key=v, text=term(page, v)) for v in CATEGORIES])
    level=ft.Dropdown(label=tr(page, 'Сложность'),value=document['level'],options=[ft.dropdown.Option(key=v, text=term(page, v)) for v in LEVELS])
    minutes=ft.TextField(label=tr(page, 'Время, минут'),value=str(document['timeMinutes']),keyboard_type=ft.KeyboardType.NUMBER)
    tags=ft.TextField(label=tr(page, 'Теги через запятую'),value=', '.join(document['tags']))
    materials=ft.TextField(label=tr(page, 'Материалы и инструменты — по одному на строку'),value='\n'.join(document['materials']),multiline=True,min_lines=2)
    state=ft.Dropdown(label=tr(page, 'Состояние материала'),value=info['state'],options=[ft.dropdown.Option('draft',tr(page, 'Черновик')),ft.dropdown.Option('published',tr(page, 'Опубликован')),ft.dropdown.Option('archived',tr(page, 'Архив'))])
    reason=ft.TextField(label=tr(page, 'Причина изменения'),value='Добавление учебного материала' if new else '',max_length=500)
    coverStatus=ft.Text(tr(page, 'Обложка прикреплена') if document['coverAsset'] else tr(page, 'Без обложки'))
    modelStatus=ft.Text(tr(page, 'Модель прикреплена') if document['modelAsset'] else tr(page, 'Без 3D-модели'))
    def assetSelected(result,field,status):document[field]=result['assetId'];status.value='Файл прикреплён';page.update()
    def renderSteps():
        cards=[]
        for index,step in enumerate(steps):
            def attach(result,field,obj=step):obj[field]=result['assetId'];renderSteps();page.update()
            @authenticatedAction(page,user)
            def remove(event,obj=step):steps.remove(obj);renderSteps();page.update()
            @authenticatedAction(page,user)
            def move(event,obj=step,delta=-1):
                old=steps.index(obj);target=old+delta
                if 0<=target<len(steps):steps[old],steps[target]=steps[target],steps[old]
                renderSteps();page.update()
            def clear(field,obj=step):obj[field]=None;renderSteps();page.update()
            cards.append(ft.Card(content=ft.Container(padding=10,content=ft.Column(controls=[ft.Text(tr(page, 'Этап ')+str(index+1)),step['field'],
                ft.Row(wrap=True,controls=[ft.TextButton(tr(page, 'Выше'),disabled=index==0,on_click=move),ft.TextButton(tr(page, 'Ниже'),disabled=index==len(steps)-1,on_click=lambda e,fn=move:fn(e,delta=1)),ft.TextButton(tr(page, 'Удалить этап'),on_click=remove)]),
                ft.Text(tr(page, 'Фото прикреплено') if step['imageAsset'] else tr(page, 'Без фото')),createCatalogFilePicker(page,user,'image',lambda result,fn=attach:fn(result,'imageAsset'),'Фото этапа'),
                ft.TextButton(tr(page, 'Убрать фото'),on_click=lambda e,fn=clear:fn('imageAsset')),
                ft.Text(tr(page, 'Видео прикреплено') if step['videoAsset'] else tr(page, 'Без видео')),createCatalogFilePicker(page,user,'video',lambda result,fn=attach:fn(result,'videoAsset'),'Видео MP4'),
                ft.TextButton(tr(page, 'Убрать видео'),on_click=lambda e,fn=clear:fn('videoAsset'))]))))
        stepList.controls=cards
    @authenticatedAction(page,user)
    def add(event=None):
        if len(steps)>=20:showMessage(page,tr(page, 'Можно добавить до 20 этапов'),True);return
        steps.append(dict(field=ft.TextField(label=tr(page, 'Текст этапа'),multiline=True,min_lines=2,max_length=2000),imageAsset=None,videoAsset=None));renderSteps();page.update()
    for step in document['steps']:steps.append(dict(field=ft.TextField(label=tr(page, 'Текст этапа'),value=step['text'],multiline=True,min_lines=2,max_length=2000),imageAsset=step['imageAsset'],videoAsset=step['videoAsset']))
    renderSteps()
    @authenticatedAction(page,user)
    def save(event):
        try:
            payload={**document,'title':title.value or '', 'description':description.value or '',
                'category':category.value,'level':level.value,'timeMinutes':int(minutes.value),
                'tags':[v.strip() for v in (tags.value or '').split(',') if v.strip()],
                'materials':[v.strip() for v in (materials.value or '').splitlines() if v.strip()],
                'steps':[dict(text=s['field'].value or '',imageAsset=s['imageAsset'],videoAsset=s['videoAsset']) for s in steps]}
            saved=client.save(info['contentId'],info['revision'],state.value,payload,reason.value or '')
            info['revision']=saved['revision'];message.value=tr(page, 'Сохранено · версия ')+str(saved['revision']);reason.value='';page.update()
        except (ApiError,ValueError,LookupError) as exc:fail(page,exc)
    controls=[ft.Text(tr(page, 'Урок') if document['kind']=='lesson' else tr(page, '3D-материал'),size=20),title,description,category,level,minutes,tags,materials,
        coverStatus,createCatalogFilePicker(page,user,'image',lambda result:assetSelected(result,'coverAsset',coverStatus),'Обложка материала'),
        ft.TextButton(tr(page, 'Убрать обложку'),on_click=lambda e:(document.update(coverAsset=None),setattr(coverStatus,'value','Без обложки'),page.update())),
        modelStatus,createCatalogFilePicker(page,user,'model',lambda result:assetSelected(result,'modelAsset',modelStatus),'OBJ или ZIP с OBJ/MTL'),stepList,
        ft.TextButton(tr(page, 'Добавить этап'),on_click=add),state,reason,message,ft.FilledButton(tr(page, 'Сохранить материал'),on_click=save)]
    return rootView(page,'/catalog-edit/'+cid,'Редактор учебного материала',controls,'/catalog-admin')
