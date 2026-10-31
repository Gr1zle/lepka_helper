"""Импорт модели на Android/ПК и через одноразовую веб-загрузку."""
from pathlib import Path
import sqlite3
import flet as ft
from model_import import MAX_MODEL_BYTES,decodeModel,importModel
from model_upload import createModelUpload,cancelModelUpload,takeModelUpload
from ui_helpers import authenticatedAction,isWebClient,showMessage
from views.project_transfer import webAddress


def createModelImport(page,user,onImported):
    pending = {'token':None}
    status = ft.Text('OBJ или ZIP с одним OBJ и MTL, до 3 МБ. Текстуры пока не поддерживаются.',size=12)
    def reset():
        if pending['token']: cancelModelUpload(pending['token'],user['userId'])
        pending['token']=None;choose.disabled=user is None;cancel.visible=False
    def preview(filename,content):
        decoded=decodeModel(filename,content)
        name=ft.TextField(label='Название модели',value=decoded['title'],max_length=80)
        done={'value':False}
        @authenticatedAction(page,user)
        def save(event):
            if done['value']:return
            done['value']=True
            try:
                modelId=importModel(user['userId'],filename,content,name.value)
                done['value']=True;page.close(dialog);onImported(modelId)
                showMessage(page,'Модель сохранена в личной библиотеке')
            except (ValueError,sqlite3.Error) as error:
                done['value']=False
                showMessage(page,str(error) if isinstance(error,ValueError) else 'Не удалось сохранить модель',True)
        dialog=ft.AlertDialog(modal=True,title=ft.Text('Импорт 3D-модели'),
            content=ft.Column(tight=True,controls=[name,ft.Text(f"Треугольников: {len(decoded['mesh'].faces)}"),
                ft.Text('Сохранится на этом устройстве. Цвета MTL поддерживаются, текстуры — пока нет.')]),
            actions=[ft.TextButton('Отмена',on_click=lambda event:page.close(dialog)),ft.ElevatedButton('Сохранить модель',on_click=save)])
        page.open(dialog)
    @authenticatedAction(page,user)
    def selected(event):
        if getattr(event,'control',picker) is not picker or not event.files:return
        try:
            if pending['token']:raise ValueError('Дождитесь загрузки или отмените её')
            if len(event.files)!=1:raise ValueError('Выберите один OBJ или ZIP')
            file=event.files[0]
            if not file.name.lower().endswith(('.obj','.zip')) or not 0<file.size<=MAX_MODEL_BYTES:
                raise ValueError('Выберите OBJ или ZIP не больше 3 МБ')
            if isWebClient(page):
                address=webAddress(page);pending['token']=createModelUpload(user,file.name)
                choose.disabled=True;cancel.visible=True;status.value='Загрузка модели…'
                picker.upload([ft.FilePickerUploadFile(name=file.name,id=getattr(file,'id',None),
                    upload_url=f"{address}/model-uploads/{pending['token']}")])
            else:
                with Path(file.path).open('rb') as stream:preview(file.name,stream.read(MAX_MODEL_BYTES+1))
        except (ValueError,OSError,TypeError) as error:
            reset();showMessage(page,str(error) if isinstance(error,ValueError) else 'Не удалось прочитать модель',True)
        page.update()
    @authenticatedAction(page,user)
    def uploaded(event):
        if getattr(event,'control',picker) is not picker or not pending['token']:return
        try:
            if event.error:raise ValueError('Не удалось загрузить модель. Проверьте файл и повторите')
            if event.progress==1:
                filename,content=takeModelUpload(pending['token'],user['userId']);reset();status.value='Модель загружена'
                preview(filename,content)
        except ValueError as error:reset();status.value=str(error);showMessage(page,str(error),True)
        page.update()
    picker=ft.FilePicker(on_result=selected,on_upload=uploaded)
    @authenticatedAction(page,user)
    def select(event):
        # Не копим выборщики при повторных открытиях галереи.
        for old in list(page.overlay):
            if isinstance(old,ft.FilePicker) and isinstance(old.data,dict) and old.data.get('modelImport'):
                old.data['cancel']();page.overlay.remove(old)
        picker.data={'modelImport':True,'cancel':reset};page.overlay.append(picker);page.update()
        picker.pick_files(allow_multiple=False,file_type=ft.FilePickerFileType.CUSTOM,allowed_extensions=['obj','zip'])
    @authenticatedAction(page,user)
    def cancelUpload(event):reset();status.value='Загрузка отменена';page.update()
    choose=ft.ElevatedButton('Импорт 3D-модели',icon=ft.Icons.UPLOAD_FILE_OUTLINED,on_click=select,disabled=user is None)
    cancel=ft.TextButton('Отменить загрузку модели',on_click=cancelUpload,visible=False)
    return ft.Column(controls=[choose,status,cancel])
