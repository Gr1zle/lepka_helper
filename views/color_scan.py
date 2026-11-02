from localization import tr, term
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
    preview=ft.Image(width=scanWidth,height=scanWidth,fit=ft.ImageFit.CONTAIN,visible=False,semantics_label=tr(page, 'Фото для выбора цвета'))
    sampleBox=ft.Container(height=48,bgcolor='#FFFFFF',border=ft.border.all(1,'#777777'))
    resultText=ft.Text(tr(page, 'Сделайте снимок или выберите фото, затем коснитесь нужного участка.'))
    def deliver(content):
        image=readImage(content);state['image']=image;state['sample']=None
        from color_photo import pngBytes
        preview.src_base64=base64.b64encode(pngBytes(image)).decode();preview.visible=True;fullButton.visible=True
        resultText.value=tr(page, 'Коснитесь объекта на фото. Прозрачные области не учитываются.');page.update()
    def selected(photo):
        try:deliver(photo['data']);return True,'Фото готово к выбору цвета'
        except ValueError as error:return False,str(error)
    def choosePoint(x,y,width,height):
        if state['image'] is None:return
        sample=sampleColor(state['image'],x,y,width,height)
        if not sample:return
        state['sample']=sample;sampleBox.bgcolor=sample['hex']
        resultText.value=tr(page, '{v0} · RGB {v1}\nБлижайший пластилин: {v2} ({v3})', v0=sample['hex'], v1=sample['rgb'], v2=term(page,sample['nearest']['name']), v3=sample['nearest']['hex'])
        page.update()
    @authenticatedAction(page,user)
    def tap(event):
        try:choosePoint(event.local_x,event.local_y,min(scanWidth,max(1,(page.width or 390)-48)),scanWidth)
        except ValueError as error:showMessage(page,str(error),True)
    @authenticatedAction(page,user)
    def fullPhoto(event):
        if state['image'] is None:return
        from views.discovery import openPage
        width=max(240,(page.width or 390)-24);height=max(220,(page.height or 780)-240)
        fullResult=ft.Text(resultText.value)
        def choose(event):
            try:
                choosePoint(event.local_x,event.local_y,width,height)
                fullResult.value=resultText.value;page.update()
            except ValueError as error:showMessage(page,str(error),True)
        image=ft.Image(src_base64=preview.src_base64,width=width,height=height,fit=ft.ImageFit.CONTAIN,
            semantics_label=tr(page, 'Увеличенное фото для выбора цвета'))
        viewer=ft.InteractiveViewer(content=ft.GestureDetector(on_tap_up=choose,
            content=ft.Container(content=image,width=width,height=height)),constrained=False,min_scale=1,max_scale=10,
            expand=True,trackpad_scroll_causes_scale=True)
        def done(event):
            page.views.pop();page.open(dialog);page.update()
        body=ft.Column(expand=True,controls=[viewer,fullResult,
            ft.Text(tr(page, 'Разведите пальцы для увеличения, перемещайте фото и коснитесь нужного оттенка.'),size=12),
            ft.Row(wrap=True,controls=[ft.TextButton(tr(page, 'Сбросить масштаб'),on_click=lambda e:viewer.reset()),
                ft.FilledButton(tr(page, 'Готово'),on_click=done)])])
        @authenticatedAction(page,user)
        def dismissed(event):
            dialog.on_dismiss=None
            fullButton.disabled=False
            view=openPage(page,tr(page, 'Выбрать цвет'),ft.SafeArea(expand=True,content=body),'/discovery/color-photo')
            view.appbar.leading.on_click=done
            page.session.set('restoreColorScan',lambda:page.open(dialog))
        # Wait for Flutter's modal-dismiss acknowledgement before changing pages.
        # Otherwise Flet 0.28 can pop the newly added page while closing the modal.
        fullButton.disabled=True
        dialog.on_dismiss=dismissed
        page.close(dialog)
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
                except (ValueError,KeyError):showMessage(page,tr(page, 'Не удалось прочитать снимок камеры'),True)
            try:getProtectedSession(page).requestUi('cameraCapture',None,completed)
            except OSError as error:showMessage(page,str(error),True)
        elif isWebClient(page):
            if state['ticket']:cancelPhotoUpload(state['ticket'],user['userId'])
            state['ticket']=createPhotoUpload(user,'camera.jpg')
            page.launch_url(webAddress(page)+'/color-camera/'+state['ticket'],web_window_name='_blank')
            takeButton.visible=True;page.update()
        else:showMessage(page,tr(page, 'На ПК выберите фото. Камера доступна в Android APK и веб-версии.'))
    @authenticatedAction(page,user)
    def take(event):
        try:
            photo=takePhotoUpload(state['ticket'],user['userId']);state['ticket']=None;takeButton.visible=False;deliver(photo['data'])
        except ValueError as error:showMessage(page,str(error),True)
    @authenticatedAction(page,user)
    def apply(event,base=False):
        sample=state['sample']
        if not sample:showMessage(page,tr(page, 'Сначала коснитесь нужного участка фото'),True);return
        page.close(dialog)
        if base:onBaseColor(sample['nearest'])
        else:onColor(sample['hex'])
    def close(event):
        if state['ticket']:cancelPhotoUpload(state['ticket'],user['userId']);state['ticket']=None
        page.close(dialog)
    fullButton=ft.TextButton(tr(page, 'Открыть фото во весь экран'),icon=ft.Icons.FULLSCREEN,visible=False,on_click=fullPhoto)
    takeButton=ft.TextButton(tr(page, 'Использовать снимок браузера'),visible=False,on_click=take)
    dialog=ft.AlertDialog(inset_padding=ft.padding.all(12),content_padding=ft.padding.all(12),title=ft.Text(tr(page, 'Цвет с камеры или фото')),content=ft.Column(width=scanWidth,tight=True,scroll=ft.ScrollMode.AUTO,controls=[
        ft.FilledButton(tr(page, 'Сделать снимок камерой'),on_click=camera),takeButton,createPhotoPicker(page,user,selected,'Выбрать фото для цвета',False),
        ft.GestureDetector(content=preview,on_tap_down=tap),fullButton,sampleBox,resultText,
        ft.Text(tr(page, 'Цвет усредняется по небольшому участку. Освещение и баланс белого камеры влияют на результат; пластилин может отличаться.'),size=12)]),
        actions=[ft.TextButton(tr(page, 'Отмена'),on_click=close),ft.TextButton(tr(page, 'В целевой HEX'),on_click=apply),ft.TextButton(tr(page, 'Добавить ближайший цвет'),on_click=lambda e:apply(e,base=True))])
    page.open(dialog)
