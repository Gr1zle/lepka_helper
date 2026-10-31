from pathlib import Path
import threading
import flet as ft
import flet.canvas as cv
from model_service import getModel,loadModel,modelBundle
from model_import import deleteImportedModel
from mesh_renderer import projectMesh
from views.model_gallery import modelUser,createModelFavorite
from ui_helpers import isWebClient,showMessage,authenticatedAction,confirmAction
from download_service import createDownload
from views.project_transfer import webAddress,androidClient


def createModelView(page,modelId):
    user=modelUser(page)
    owner=user['userId'] if user else None
    item=getModel(modelId,owner)
    if item is None:
        return ft.View('/models/missing',controls=[ft.Text('Модель не найдена или недоступна'),
            ft.TextButton('К галерее',on_click=lambda event:page.go('/models'))])
    try:mesh=loadModel(modelId,owner)
    except (OSError,ValueError):
        return ft.View('/models/'+modelId,controls=[ft.Text('Не удалось прочитать встроенную модель'),
            ft.TextButton('К галерее',on_click=lambda event:page.go('/models'))])
    state={'yaw':-25,'pitch':45 if modelId=='pizza' else 15,'zoom':1.0,'light':-45,'brightness':1.0,
           'width':min(520,max(200,(page.width or 390)-24)),'height':320}
    full={'value':False}
    view=ft.View('/models/'+modelId,padding=12)
    def active():return bool(page.views and page.views[-1] is view)
    wire=ft.Checkbox(label='Показать рёбра',value=False)
    canvas=cv.Canvas(expand=True,resize_interval=150)
    pool=[]
    drawLock=threading.Lock()
    def draw(update=True):
        if update and not active():return
        with drawLock:
            faces=projectMesh(mesh,**state)
            index=0
            def shape(elements,paint):
                nonlocal index
                if index==len(pool):pool.append(cv.Path())
                pool[index].elements=elements;pool[index].paint=paint;index+=1
            for face in faces:
                a,b,c=face['points']
                elements=[cv.Path.MoveTo(*a),cv.Path.LineTo(*b),cv.Path.LineTo(*c),cv.Path.Close()]
                shape(elements,ft.Paint(color=face['color'],style=ft.PaintingStyle.FILL))
                if wire.value:shape(elements,ft.Paint(color='#425266',stroke_width=.55,style=ft.PaintingStyle.STROKE))
            canvas.shapes=pool[:index]
            if update:canvas.update()
    def resize(event):
        if 0<event.width<=8192 and 0<event.height<=8192 and (state['width']!=event.width or state['height']!=event.height):
            state.update(width=event.width,height=event.height);draw()
    canvas.on_resize=resize
    def rotate(event):
        state['yaw']=(state['yaw']+event.delta_x*.6)%360
        state['pitch']=max(-80,min(80,state['pitch']+event.delta_y*.5))
        draw()
    def angle(yaw,pitch):
        state.update(yaw=yaw,pitch=pitch);draw()
    def zoom(delta):
        state['zoom']=max(.5,min(2.5,round(state['zoom']+delta,2)));draw()
    def scroll(event):zoom(-event.scroll_delta_y/1000)
    def reset(event):
        state.update(yaw=-25,pitch=45 if modelId=='pizza' else 15,zoom=1.0,light=-45,brightness=1.0)
        light.value=-45;brightness.value=1;wire.value=False;draw();page.update()
    def lighting(event):
        state.update(light=light.value,brightness=brightness.value);draw()
    light=ft.Slider(min=-180,max=180,value=-45,divisions=24,label='{value}°',on_change=lighting)
    brightness=ft.Slider(min=.4,max=1.6,value=1,divisions=12,label='{value}',on_change=lighting)
    wire.on_change=lambda event:draw()
    def linkedLesson(event):
        page.session.set('openBuiltinLesson',item['lessonId']);page.session.set('homeTab',1)
        page.session.set('modelReturnLesson',None);page.go('/home')
    def export(event):
        content=modelBundle(modelId,owner)
        if isWebClient(page):
            ticket=createDownload(content,'lepka-model.zip','application/zip',user if item.get('imported') else None)
            page.launch_url(webAddress(page)+'/downloads/'+ticket,web_window_name='_self')
        else:
            def selected(event):
                if not event.path:return
                try:
                    with Path(event.path).with_suffix('.zip').open('xb') as stream:stream.write(content)
                    showMessage(page,'OBJ и материалы сохранены в ZIP')
                except OSError:showMessage(page,'Не удалось сохранить ZIP. Выберите новое имя файла',True)
            handler=authenticatedAction(page,user)(selected) if item.get('imported') else selected
            picker=ft.FilePicker(on_result=handler);page.overlay.append(picker);page.update()
            picker.save_file(file_name='lepka-model.zip')
    back=page.views[-1].route if page.views and page.views[-1].route=='/models' else '/home'
    @authenticatedAction(page,user)
    def remove(event):
        @authenticatedAction(page,user)
        def confirmed():
            deleteImportedModel(owner,modelId);page.go('/models')
        confirmAction(page,'Удалить личную модель?','Модель будет удалена с этого устройства.',confirmed)
    def leave(event):
        if full['value']:toggleFull()
        else:page.go(back)
    appbar=ft.AppBar(title=ft.Text(item['title']),leading=ft.IconButton(icon=ft.Icons.ARROW_BACK,on_click=leave))
    fullButton=ft.TextButton('Во весь экран',icon=ft.Icons.FULLSCREEN,on_click=lambda event:toggleFull())
    scene=ft.Container(left=0,right=0,top=0,height=320,clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        bgcolor='#edf1f5',border_radius=16,
        content=ft.GestureDetector(expand=True,content=canvas,drag_interval=60,on_pan_update=rotate,on_scroll=scroll,
                                  mouse_cursor=ft.MouseCursor.MOVE))
    exportHandler=authenticatedAction(page,user)(export) if item.get('imported') else export
    tools=ft.Container(left=0,right=0,top=330,bottom=0,content=ft.ListView(expand=True,spacing=10,controls=[
            fullButton,ft.Text(item['title'],size=17,weight=ft.FontWeight.BOLD),
            ft.Text('Тяните фигурку пальцем или мышью. Масштаб — кнопками или колёсиком.',size=12),
            ft.Row(wrap=True,controls=[ft.TextButton('Уменьшить',on_click=lambda event:zoom(-.2)),
                ft.TextButton('Увеличить',on_click=lambda event:zoom(.2)),ft.TextButton('Сбросить вид',on_click=reset)]),
            ft.Row(wrap=True,controls=[ft.TextButton('Спереди',on_click=lambda event:angle(0,0)),
                ft.TextButton('Слева',on_click=lambda event:angle(-90,0)),ft.TextButton('Сзади',on_click=lambda event:angle(180,0)),
                ft.TextButton('Сверху',on_click=lambda event:angle(0,75))]),
            ft.ExpansionTile(title=ft.Text('Освещение и рёбра'),initially_expanded=False,
                controls=[ft.Text('Направление света'),light,ft.Text('Яркость'),brightness,wire]),
            createModelFavorite(page,user,modelId),
            *([] if item.get('imported') else [ft.TextButton('Урок для этой фигурки',icon=ft.Icons.SCHOOL_OUTLINED,on_click=linkedLesson)]),
            ft.TextButton('Скачать OBJ и материалы',icon=ft.Icons.DOWNLOAD_OUTLINED,on_click=exportHandler,visible=not androidClient(page)),
            *([ft.TextButton('Удалить модель',icon=ft.Icons.DELETE_OUTLINED,on_click=remove)] if item.get('imported') else []),
            ft.Text('Личная модель на этом устройстве' if item.get('imported') else 'Формы упрощены для изучения объёма и деталей. Это не 3D-скан готовой работы.',size=12)
        ]))
    def layout(update=True):
        if update and not active():return
        width,height=page.width or 390,page.height or 844
        view.appbar=None if full['value'] else appbar
        fullButton.text='Выйти из полного экрана' if full['value'] else 'Во весь экран'
        fullButton.icon=ft.Icons.FULLSCREEN_EXIT if full['value'] else ft.Icons.FULLSCREEN
        scene.height=None;scene.bottom=0;scene.right=0
        tools.left=0;tools.right=0;tools.top=None;tools.bottom=0;tools.width=None;tools.height=None
        available=max(160,height-(24 if full['value'] else 80))
        if full['value'] and width>=760:
            scene.right=312;tools.left=None;tools.top=0;tools.width=300
        elif full['value']:
            panel=min(200,max(120,int(available*.3)))
            scene.bottom=panel+10;tools.height=panel
        else:
            scene.height=min(320,max(100,int(available*.5)));scene.bottom=None
            tools.top=scene.height+10
        if update:page.update()
    def toggleFull():full['value']=not full['value'];layout()
    def exitFull():
        if active() and full['value']:toggleFull();return True
        return False
    page.session.set('resizeModelView',lambda event:layout())
    page.session.set('exitModelFullscreen',exitFull)
    view.controls=[ft.Stack(expand=True,controls=[scene,tools])]
    view.data={'camera':state,'fullscreen':full}
    draw(False);layout(False)
    return view
