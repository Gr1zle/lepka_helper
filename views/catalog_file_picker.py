from pathlib import Path
import flet as ft
from catalog_client import CatalogClient
from catalog_upload import createUpload,takeUpload,cancelUpload
from learning_catalog import MAX_ASSET
from ui_helpers import authenticatedAction,isWebClient,showMessage
from views.project_transfer import webAddress
from api_client import ApiError


def createCatalogFilePicker(page,user,kind,onSelected,label):
    extensions=dict(image=['jpg','jpeg','png','webp'],video=['mp4'],model=['obj','zip'])[kind]
    state={'ticket':None,'picker':None};status=ft.Text(size=12)
    def reset():
        if state['ticket']:cancelUpload(state['ticket'],user['userId'])
        state['ticket']=None;button.disabled=False;cancel.visible=False
    def deliver(result):onSelected(result);status.value='Файл загружен: '+result['name']
    @authenticatedAction(page,user)
    def picked(event):
        if event.control is not state['picker'] or not event.files:return
        try:
            file=event.files[0]
            if len(event.files)!=1 or file.name.rsplit('.',1)[-1].lower() not in extensions or not 0<file.size<=MAX_ASSET:raise ValueError('Выберите один файл подходящего типа, до 12 МБ (модель до 3 МБ)')
            if isWebClient(page):
                state['ticket']=createUpload(user,file.name,kind);button.disabled=True;cancel.visible=True
                status.value='Загрузка…'
                state['picker'].upload([ft.FilePickerUploadFile(name=file.name,id=getattr(file,'id',None),upload_url=webAddress(page)+'/catalog-uploads/'+state['ticket'])])
            else:
                with Path(file.path).open('rb') as stream:raw=stream.read(MAX_ASSET+1)
                deliver(CatalogClient(user).upload(file.name,kind,raw))
        except (ValueError,OSError,ApiError) as error:
            reset();showMessage(page,str(error),True)
        page.update()
    @authenticatedAction(page,user)
    def uploaded(event):
        if event.control is not state['picker'] or not state['ticket']:return
        try:
            if event.error:raise ValueError('Не удалось загрузить файл: проверьте права, связь и формат')
            if event.progress==1:
                result=takeUpload(state['ticket'],user['userId']);reset();deliver(result)
        except ValueError as error:reset();showMessage(page,str(error),True)
        page.update()
    @authenticatedAction(page,user)
    def choose(event):
        old=state['picker']
        if old in page.overlay:page.overlay.remove(old)
        picker=ft.FilePicker(on_result=picked,on_upload=uploaded);state['picker']=picker
        page.overlay.append(picker);page.update()
        picker.pick_files(allow_multiple=False,file_type=ft.FilePickerFileType.CUSTOM,allowed_extensions=extensions)
    button=ft.OutlinedButton(label,on_click=choose)
    cancel=ft.TextButton('Отменить загрузку',visible=False,on_click=lambda e:(reset(),page.update()))
    return ft.Column(spacing=2,controls=[button,status,cancel])
