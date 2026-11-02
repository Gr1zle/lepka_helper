from localization import tr, term
import base64
import flet as ft
from color_photo import readImage,pngBytes,cropReference,removeBackground
from reference_service import listReferences,saveReference,deleteReference
from photo_picker import createPhotoPicker
from file_export import exportBytes
from ui_helpers import getCurrentUser,authenticatedAction,showMessage,confirmAction


def createReferenceGallery(page):
    user=getCurrentUser(page)
    if not user:return ft.View('/references',controls=[ft.Text(tr(page, 'Войдите для работы с личными референсами'))])
    state={'original':None,'image':None}
    preview=ft.Image(height=260,fit=ft.ImageFit.CONTAIN,visible=False)
    name=ft.TextField(label=tr(page, 'Название референса'),value='Мой референс',max_length=80)
    margins=[ft.TextField(label=label,value='0',width=130,keyboard_type=ft.KeyboardType.NUMBER) for label in ('Слева, %','Сверху, %','Справа, %','Снизу, %')]
    background=ft.TextField(label=tr(page, 'Цвет фона (HEX)'),value='#FFFFFF')
    tolerance=ft.Slider(min=0,max=150,divisions=30,value=25,label='{value}')
    saved=ft.Column(spacing=12)
    def refreshPreview():
        preview.visible=state['image'] is not None
        if state['image'] is not None:preview.src_base64=base64.b64encode(pngBytes(state['image'])).decode()
        page.update()
    def selected(photo):
        try:
            image=readImage(photo['data']);state.update(original=image.copy(),image=image)
            corner=image.getpixel((0,0));background.value='#'+''.join(f'{v:02X}' for v in corner[:3]);refreshPreview()
            return True,'Фото готово: обрежьте края или удалите однотонный фон'
        except ValueError as error:return False,str(error)
    @authenticatedAction(page,user)
    def crop(event):
        try:
            if state['image'] is None:raise ValueError('Сначала выберите фото')
            state['image']=cropReference(state['image'],*[f.value for f in margins]);refreshPreview()
            for field in margins:field.value='0'
            page.update()
        except ValueError as error:showMessage(page,str(error),True)
    @authenticatedAction(page,user)
    def cutout(event):
        try:
            if state['image'] is None:raise ValueError('Сначала выберите фото')
            state['image']=removeBackground(state['image'],background.value,int(tolerance.value));refreshPreview()
        except ValueError as error:showMessage(page,str(error),True)
    @authenticatedAction(page,user)
    def reset(event):
        if state['original'] is not None:state['image']=state['original'].copy();refreshPreview()
    def renderSaved():
        controls=[]
        for item in listReferences(user['userId']):
            @authenticatedAction(page,user)
            def openItem(event,row=item):state.update(original=readImage(row['image']),image=readImage(row['image']));name.value=row['title'];refreshPreview()
            @authenticatedAction(page,user)
            def remove(event,row=item):
                def confirmed():deleteReference(user['userId'],row['referenceId']);renderSaved();page.update()
                confirmAction(page,'Удалить референс?',row['title'],authenticatedAction(page,user)(confirmed))
            controls.append(ft.Card(content=ft.Container(padding=12,content=ft.Column(controls=[ft.Text(item['title']),
                ft.Image(src_base64=base64.b64encode(item['image']).decode(),height=170,fit=ft.ImageFit.CONTAIN),
                ft.Row(wrap=True,controls=[ft.TextButton(tr(page, 'Открыть референс'),on_click=openItem),ft.TextButton(tr(page, 'Удалить референс'),on_click=remove)])]))))
        saved.controls=controls or [ft.Text(tr(page, 'Сохранённых референсов пока нет.'))]
    @authenticatedAction(page,user)
    def save(event):
        try:
            if state['image'] is None:raise ValueError('Сначала выберите фото')
            saveReference(user['userId'],name.value,pngBytes(state['image']));renderSaved();page.update();showMessage(page,tr(page, 'Референс сохранён на устройстве'))
        except ValueError as error:showMessage(page,str(error),True)
    @authenticatedAction(page,user)
    def export(event):
        try:
            if state['image'] is None:raise ValueError('Сначала выберите фото')
            exportBytes(page,user,pngBytes(state['image']),'lepka-reference.png','image/png')
        except (ValueError,OSError) as error:showMessage(page,str(error),True)
    renderSaved()
    return ft.View('/references',padding=12,appbar=ft.AppBar(title=ft.Text(tr(page, 'Фотореференсы')),leading=ft.IconButton(icon=ft.Icons.ARROW_BACK,on_click=lambda e:page.go('/models'))),
        controls=[ft.ListView(expand=True,spacing=12,controls=[createPhotoPicker(page,user,selected,'Фото для референса'),name,preview,
            ft.Text(tr(page, 'Обрезка краёв в процентах')),ft.Row(wrap=True,controls=margins),ft.OutlinedButton(tr(page, 'Обрезать фото'),on_click=crop),
            background,ft.Text(tr(page, 'Допуск цвета однотонного фона')),tolerance,ft.OutlinedButton(tr(page, 'Удалить однотонный фон'),on_click=cutout),
            ft.Text(tr(page, 'Удаляется только похожий фон, связанный с краями. Для сложного фона используйте обрезку; это не нейросетевое выделение объекта.')),
            ft.TextButton(tr(page, 'Вернуть исходное фото'),on_click=reset),ft.FilledButton(tr(page, 'Сохранить референс'),on_click=save),
            ft.OutlinedButton(tr(page, 'Экспорт референса PNG'),on_click=export),ft.Text(tr(page, 'До 20 референсов и 40 МБ на аккаунт/сервер. Сохраняются на этом устройстве.')),saved])])
