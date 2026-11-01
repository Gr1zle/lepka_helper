"""Личные копии и ручная синхронизация с явным сравнением версий."""
import json
from pathlib import Path
from functools import wraps
import sqlite3
from urllib.parse import urlsplit
import flet as ft
from api_client import ApiError
from personal_snapshot import MAX_SNAPSHOT_BYTES,exportSnapshot,decodeSnapshot,snapshotSummary
from personal_checkpoints import saveCheckpoint,listCheckpoints,readCheckpoint,deleteCheckpoint,restoreCheckpoint
from personal_sync import PersonalSync,fingerprint
from ui_helpers import serverAction,showMessage,isWebClient


def localAction(page,user):
    def decorate(callback):
        @serverAction(page)
        @wraps(callback)
        def guarded(*args,**kwargs):
            current=page.session.get('currentUser')
            if not current or current.get('sessionToken')!=user.get('sessionToken') or current.get('userId')!=user['userId']:
                raise ApiError('Сессия изменилась. Выполните вход снова',401)
            try:return callback(*args,**kwargs)
            except (ValueError,OSError,sqlite3.Error) as error:
                showMessage(page,str(error) if isinstance(error,ValueError) else 'Не удалось выполнить операцию с личными данными',True)
        return guarded
    return decorate


def summaryText(summary):
    return f"Проекты: {summary['projects']} · смеси: {summary['mixtures']} · уроки: {summary['lessons']} · модели: {summary['models']}"


def createPersonalDataButton(page,user):
    if not user:return ft.Container()
    action=localAction(page,user)
    @action
    def openData(event):
        client=PersonalSync(user);comparison={'value':None};busy={'value':False}
        status=ft.Text('Сравнение показывает различия устройства и сервера. Замена данных требует подтверждения.')
        serverInfo=ft.Text();copies=ft.Column(spacing=8);history=ft.Column(spacing=8)
        push=ft.TextButton('Отправить данные устройства',disabled=True)
        pull=ft.TextButton('Загрузить данные сервера',disabled=True)
        sync=ft.ElevatedButton('Сравнить и синхронизировать',disabled=not bool(client.apiUrl))
        pending=ft.Text()

        def openChild(child):
            page.close(dialog)
            page.open(child)

        def returnToMain(child):
            page.close(child)
            page.open(dialog)

        def refreshCopies():
            entries=[]
            for item in listCheckpoints(user['userId']):
                @action
                def restore(event,key=item['checkpointId']):preview(readCheckpoint(user['userId'],key),'Восстановление личной копии')
                @action
                def remove(event,key=item['checkpointId']):
                    deleteCheckpoint(user['userId'],key);refreshCopies();page.update()
                entries.append(ft.Card(content=ft.Container(padding=10,content=ft.Column([
                    ft.Text(item['title']),ft.Text(item['createdAt']+' UTC',size=12),
                    ft.Row(wrap=True,controls=[ft.TextButton('Восстановить копию',on_click=restore),ft.TextButton('Удалить копию',on_click=remove)])]))))
            copies.controls=entries or [ft.Text('Полных личных копий пока нет.')]
            base=client.base();pending.value='Есть отложенный запрос синхронизации. Повторите сравнение при доступном сервере.' if base and base['pending'] else ''

        def invalidate():
            comparison['value']=None;push.disabled=True;pull.disabled=True
            refreshCopies();page.update()

        def preview(content,title):
            document=decodeSnapshot(content)[0];expected=fingerprint(exportSnapshot(user['userId']))
            @action
            def confirm(event):
                if busy['value']:return
                busy['value']=True
                try:
                    restoreCheckpoint(user['userId'],content,expected)
                    returnToMain(confirmDialog);status.value='Личные данные восстановлены. Страховочная копия сохранена.'
                    invalidate();showMessage(page,'Данные восстановлены. Заново откройте нужную вкладку.')
                finally:busy['value']=False
            confirmDialog=ft.AlertDialog(modal=True,title=ft.Text(title),content=ft.Column(tight=True,controls=[
                ft.Text(summaryText(snapshotSummary(document))),ft.Text('Будут заменены ваши личные проекты, смеси, учебные данные и импортированные модели на этом устройстве. Перед заменой автоматически сохранится полная копия. Аккаунт и публикации сохраняются.')]),
                actions=[ft.TextButton('Отмена',on_click=lambda e:returnToMain(confirmDialog)),ft.TextButton('Заменить личные данные',on_click=confirm)])
            openChild(confirmDialog)

        @action
        def manualCopy(event):
            saveCheckpoint(user['userId'],exportSnapshot(user['userId']))
            refreshCopies();page.update();showMessage(page,'Полная личная копия сохранена на устройстве')

        @action
        def exportFile(event):
            content=exportSnapshot(user['userId'])
            if isWebClient(page):
                from download_service import createDownload
                address=urlsplit(page.url);scheme={'ws':'http','wss':'https'}.get(address.scheme,address.scheme)
                ticket=createDownload(content,'lepka-personal.json','application/json',user)
                page.launch_url(f'{scheme}://{address.netloc}/downloads/{ticket}',web_window_name='_self');return
            if page.platform==ft.PagePlatform.ANDROID:
                saveCheckpoint(user['userId'],content);refreshCopies();page.update()
                showMessage(page,'На Android копия сохранена внутри приложения. Для другого устройства используйте Wi-Fi-синхронизацию.');return
            @action
            def save(event):
                if event.path:
                    with Path(event.path).with_suffix('.json').open('xb') as stream:stream.write(content)
                    showMessage(page,'Полный JSON-архив сохранён')
            picker=ft.FilePicker(on_result=save);page.overlay.append(picker);page.update()
            picker.save_file(file_name='lepka-personal.json',file_type=ft.FilePickerFileType.CUSTOM,allowed_extensions=['json'])

        def networkError(error):
            if error.statusCode==401:raise error
            if error.statusCode==0 or error.statusCode>=500:
                client.queue();status.value='Сервер недоступен. Запрос отложен; данные остались на устройстве. Повторите сравнение после подключения к Wi-Fi.'
            else:status.value=str(error)
            invalidate()

        @action
        def compare(event=None):
            if busy['value']:return
            busy['value']=True;sync.disabled=True;status.value='Сравниваю личные данные…';page.update()
            try:
                plan=client.compare();comparison['value']=plan
                state=plan['state']
                status.value={'clean':'Устройство и сервер содержат одинаковые данные.','upload':'Изменения есть только на устройстве. Можно отправить их на сервер.',
                    'download':'На сервере есть другая версия. Загрузите её после просмотра и подтверждения.',
                    'conflict':'КОНФЛИКТ ВЕРСИЙ: изменения есть с обеих сторон либо это первое объединение двух непустых наборов. Выберите, какую версию использовать.'}[state]
                serverInfo.value='Устройство: '+summaryText(plan['localSummary'])+'\nСервер: '+(f"версия {plan['remote']['revision']} · "+summaryText(plan['remote']['summary']) if plan['remote'] else 'копии пока нет')
                push.disabled=state=='clean';pull.disabled=state=='clean' or not bool(plan['remote'])
                refreshCopies()
            except ApiError as error:networkError(error)
            finally:busy['value']=False;sync.disabled=not bool(client.apiUrl);page.update()

        @action
        def upload(event):
            plan=comparison['value']
            if not plan:raise ValueError('Сначала сравните версии')
            @action
            def confirm(event):
                if busy['value']:return
                busy['value']=True;returnToMain(confirmDialog);status.value='Отправляю личные данные…';page.update()
                try:
                    result=client.upload(plan);status.value=f"На сервере сохранена версия {result['revision']}.";invalidate()
                except ApiError as error:networkError(error)
                finally:busy['value']=False;page.update()
            confirmDialog=ft.AlertDialog(modal=True,title=ft.Text('Сохранить версию устройства на сервере?'),
                content=ft.Text('Она станет общей личной версией этого аккаунта. До трёх предыдущих серверных версий сохраняются в истории. Конфликт при новом изменении сервера остановит отправку.'),
                actions=[ft.TextButton('Отмена',on_click=lambda e:returnToMain(confirmDialog)),ft.TextButton('Подтвердить отправку',on_click=confirm)])
            openChild(confirmDialog)

        def download(revision=None):
            plan=comparison['value']
            if not plan:raise ValueError('Сначала сравните версии')
            @action
            def confirm(event):
                if busy['value']:return
                busy['value']=True;returnToMain(confirmDialog);status.value='Загружаю личные данные…';page.update()
                try:
                    client.download(plan,revision);status.value='Личные данные загружены. Страховочная копия сохранена.';invalidate()
                    showMessage(page,'Заново откройте нужную вкладку для просмотра загруженных данных')
                except ApiError as error:networkError(error)
                finally:busy['value']=False;page.update()
            confirmDialog=ft.AlertDialog(modal=True,title=ft.Text('Заменить данные устройства?'),content=ft.Text(
                'Будут заменены личные проекты, смеси, прогресс, заметки, избранное и импортированные модели. Сначала автоматически сохранится полная копия текущих данных. Аккаунт и публикации сохраняются.'),
                actions=[ft.TextButton('Отмена',on_click=lambda e:returnToMain(confirmDialog)),ft.TextButton('Подтвердить загрузку',on_click=confirm)])
            openChild(confirmDialog)

        @action
        def serverHistory(event):
            try:
                items=client.history()
                history.controls=[ft.Column([ft.Text(f"Версия {item['revision']} · {item['updatedAt']} UTC"),ft.Text(summaryText(item['summary'])),
                    ft.TextButton('Загрузить историческую версию',on_click=action(lambda e,revision=item['revision']:download(revision)))]) for item in items] or [ft.Text('Предыдущих серверных версий пока нет.')]
                page.update()
            except ApiError as error:networkError(error)

        @action
        def cancelQueue(event):client.cancelPending();refreshCopies();page.update()
        push.on_click=upload;pull.on_click=action(lambda e:download());sync.on_click=compare
        importer=createPersonalImport(page,user,lambda content:preview(content,'Импорт полного личного архива'))
        dialog=ft.AlertDialog(title=ft.Text('Личные данные и синхронизация'),content=ft.Container(width=480,height=480,content=ft.ListView(spacing=12,build_controls_on_demand=False,controls=[
            ft.Text('Сеть: '+(client.apiUrl or 'локальный режим; сервер подключается на экране входа')),
            ft.Text('Передаются личные данные этого аккаунта. Храним 5 последних локальных копий и 3 предыдущие версии на сервере. JSON до 20 МБ; копии внутри приложения удалятся при его удалении.'),
            sync,status,serverInfo,pending,ft.TextButton('Отменить отложенный запрос',on_click=cancelQueue),push,pull,
            ft.TextButton('История версий на сервере',disabled=not bool(client.apiUrl),on_click=serverHistory),history,
            ft.Divider(),ft.TextButton('Создать полную личную копию',on_click=manualCopy),ft.TextButton('Экспорт полного JSON',on_click=exportFile),importer,copies])),
            actions=[ft.TextButton('Закрыть',on_click=lambda e:page.close(dialog))])
        refreshCopies();page.open(dialog)
    return ft.TextButton('Личные данные и синхронизация',icon=ft.Icons.SYNC,on_click=openData)


def createPersonalImport(page,user,onContent):
    from project_upload import createProjectUpload,cancelProjectUpload,takeProjectUpload
    action=localAction(page,user);pending={'token':None};status=ft.Text('Полный личный JSON до 20 МБ.')
    @action
    def cancel(event=None):
        if pending['token']:cancelProjectUpload(pending['token'],user['userId'])
        pending['token']=None;choose.disabled=False;status.value='Полный личный JSON до 20 МБ.';page.update()
    @action
    def selected(event):
        if not event.files:return
        file=event.files[0]
        if len(event.files)!=1 or not file.name.lower().endswith('.json') or not 0<file.size<=MAX_SNAPSHOT_BYTES:raise ValueError('Выберите один JSON не больше 20 МБ')
        if isWebClient(page):
            if pending['token']:raise ValueError('Дождитесь загрузки или отмените её')
            address=urlsplit(page.url);scheme={'ws':'http','wss':'https'}.get(address.scheme,address.scheme)
            pending['token']=createProjectUpload(user,'personal');choose.disabled=True;status.value='Загрузка личного JSON…';page.update()
            picker.upload([ft.FilePickerUploadFile(name=file.name,id=getattr(file,'id',None),upload_url=f'{scheme}://{address.netloc}/project-uploads/{pending["token"]}')])
        elif file.path:
            with Path(file.path).open('rb') as stream:content=stream.read(MAX_SNAPSHOT_BYTES+1)
            decodeSnapshot(content);onContent(content)
    @action
    def uploaded(event):
        if not pending['token']:return
        if event.error:cancel();raise ValueError('Не удалось загрузить личный JSON')
        if event.progress==1:
            token=pending['token'];pending['token']=None;choose.disabled=False
            content=takeProjectUpload(token,user['userId']);status.value='Архив проверен. Подтвердите восстановление.';page.update();onContent(content)
    picker=ft.FilePicker(on_result=selected,on_upload=uploaded);page.overlay.append(picker)
    choose=ft.TextButton('Импорт полного JSON',on_click=action(lambda e:picker.pick_files(allow_multiple=False,file_type=ft.FilePickerFileType.CUSTOM,allowed_extensions=['json'])))
    return ft.Column([choose,ft.TextButton('Отменить загрузку JSON',on_click=cancel),status])
