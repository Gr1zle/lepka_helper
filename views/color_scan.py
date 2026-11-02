import base64
import json
import flet as ft
from color_photo import readImage,sampleColor
from photo_picker import createPhotoPicker
from photo_upload import createPhotoUpload,takePhotoUpload,cancelPhotoUpload
from ui_helpers import authenticatedAction,isWebClient,showMessage


def openColorScan(page,user,onColor,onBaseColor):
    state={'image':None,'sample':None,'ticket':None}
    scanWidth=min(280,max(128,(page.width or 390)-64))
    preview=ft.Image(width=scanWidth,height=scanWidth,fit=ft.ImageFit.CONTAIN,visible=False,semantics_label='Фото для выбора цвета')
    sampleBox=ft.Container(height=48,bgcolor='#FFFFFF',border=ft.border.all(1,'#777777'))
    resultText=ft.Text('Сделайте снимок или выберите фото, затем коснитесь нужного участка.')
    def deliver(content):
        image=readImage(content);state['image']=image;state['sample']=None
        from color_photo import pngBytes
        preview.src_base64=base64.b64encode(pngBytes(image)).decode();preview.visible=True
        resultText.value='Коснитесь объекта на фото. Прозрачные области не учитываются.';page.update()
    def selected(photo):
        try:deliver(photo['data']);return True,'Фото готово к выбору цвета'
        except ValueError as error:return False,str(error)
    @authenticatedAction(page,user)
    def tap(event):
        if state['image'] is None:return
        try:
            sample=sampleColor(state['image'],event.local_x,event.local_y,min(scanWidth,max(1,(page.width or 390)-48)),scanWidth)
            if not sample:return
            state['sample']=sample;sampleBox.bgcolor=sample['hex']
            resultText.value=f"{sample['hex']} · RGB {sample['rgb']}\nБлижайший пластилин: {sample['nearest']['name']} ({sample['nearest']['hex']})"
            page.update()
        except ValueError as error:showMessage(page,str(error),True)
    @authenticatedAction(page,user)
    def camera(event):
        from views.project_transfer import androidClient,webAddress
        if androidClient(page):
            from secure_device import getProtectedSession
            def completed(record):
                current=page.session.get('currentUser') or {}
                if current.get('sessionToken')!=user.get('sessionToken'):return
                try:
                    if not record.get('ok'):raise ValueError('Не удалось открыть камеру. Проверьте, что камера установлена и доступна')
                    photo=json.loads(record.get('value') or '{}')
                    if photo.get('cancelled'):return
                    deliver(base64.b64decode(photo['imageBase64'],validate=True))
                except (ValueError,KeyError):showMessage(page,'Не удалось прочитать снимок камеры',True)
            try:getProtectedSession(page).requestUi('cameraCapture',None,completed)
            except OSError as error:showMessage(page,str(error),True)
        elif isWebClient(page):
            if state['ticket']:cancelPhotoUpload(state['ticket'],user['userId'])
            state['ticket']=createPhotoUpload(user,'camera.jpg')
            page.launch_url(webAddress(page)+'/color-camera/'+state['ticket'],web_window_name='_blank')
            takeButton.visible=True;page.update()
        else:showMessage(page,'На ПК выберите фото. Камера доступна в Android APK и веб-версии.')
    @authenticatedAction(page,user)
    def take(event):
        try:
            photo=takePhotoUpload(state['ticket'],user['userId']);state['ticket']=None;takeButton.visible=False;deliver(photo['data'])
        except ValueError as error:showMessage(page,str(error),True)
    @authenticatedAction(page,user)
    def apply(event,base=False):
        sample=state['sample']
        if not sample:showMessage(page,'Сначала коснитесь нужного участка фото',True);return
        page.close(dialog)
        if base:onBaseColor(sample['nearest'])
        else:onColor(sample['hex'])
    def close(event):
        if state['ticket']:cancelPhotoUpload(state['ticket'],user['userId']);state['ticket']=None
        page.close(dialog)
    takeButton=ft.TextButton('Использовать снимок браузера',visible=False,on_click=take)
    dialog=ft.AlertDialog(inset_padding=ft.padding.all(12),content_padding=ft.padding.all(12),title=ft.Text('Цвет с камеры или фото'),content=ft.Column(width=scanWidth,tight=True,scroll=ft.ScrollMode.AUTO,controls=[
        ft.FilledButton('Сделать снимок камерой',on_click=camera),takeButton,createPhotoPicker(page,user,selected,'Выбрать фото для цвета'),
        ft.GestureDetector(content=preview,on_tap_down=tap),sampleBox,resultText,
        ft.Text('Цвет усредняется по небольшому участку. Освещение и баланс белого камеры влияют на результат; пластилин может отличаться.',size=12)]),
        actions=[ft.TextButton('Отмена',on_click=close),ft.TextButton('В целевой HEX',on_click=apply),ft.TextButton('Добавить ближайший цвет',on_click=lambda e:apply(e,base=True))])
    page.open(dialog)
