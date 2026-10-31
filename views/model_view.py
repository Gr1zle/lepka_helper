from pathlib import Path
import threading
import flet as ft
import flet.canvas as cv
from model_service import getModel,loadModel,modelBundle
from mesh_renderer import projectMesh
from views.model_gallery import modelUser,createModelFavorite
from ui_helpers import isWebClient,showMessage
from download_service import createDownload
from views.project_transfer import webAddress,androidClient


def createModelView(page,modelId):
    item=getModel(modelId)
    if item is None:
        return ft.View('/models/missing',controls=[ft.Text('Модель не найдена'),
            ft.TextButton('К галерее',on_click=lambda event:page.go('/models'))])
    user=modelUser(page)
    try:mesh=loadModel(modelId)
    except (OSError,ValueError):
        return ft.View('/models/'+modelId,controls=[ft.Text('Не удалось прочитать встроенную модель'),
            ft.TextButton('К галерее',on_click=lambda event:page.go('/models'))])
    state={'yaw':-25,'pitch':45 if modelId=='pizza' else 15,'zoom':1.0,'light':-45,'brightness':1.0,
           'width':min(520,max(200,(page.width or 390)-24)),'height':320}
    wire=ft.Checkbox(label='Показать рёбра',value=False)
    canvas=cv.Canvas(width=state['width'],height=320,resize_interval=150)
    pool=[]
    drawLock=threading.Lock()
    def draw(update=True):
        if update and not any(view.route=='/models/'+modelId for view in page.views):return
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
        if event.width>0 and event.height>0 and (state['width']!=event.width or state['height']!=event.height):
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
        content=modelBundle(modelId)
        if isWebClient(page):
            ticket=createDownload(content,'lepka-model.zip','application/zip')
            page.launch_url(webAddress(page)+'/downloads/'+ticket,web_window_name='_self')
        else:
            def selected(event):
                if not event.path:return
                try:
                    with Path(event.path).with_suffix('.zip').open('xb') as stream:stream.write(content)
                    showMessage(page,'OBJ и материалы сохранены в ZIP')
                except OSError:showMessage(page,'Не удалось сохранить ZIP. Выберите новое имя файла',True)
            picker=ft.FilePicker(on_result=selected);page.overlay.append(picker);page.update()
            picker.save_file(file_name='lepka-model.zip')
    draw(False)
    back=page.views[-1].route if page.views and page.views[-1].route=='/models' else '/home'
    return ft.View('/models/'+modelId,padding=12,
        appbar=ft.AppBar(title=ft.Text(item['title']),leading=ft.IconButton(icon=ft.Icons.ARROW_BACK,on_click=lambda event:page.go(back))),
        controls=[ft.ListView(expand=True,spacing=10,controls=[
            ft.Text('Учебная геометрическая модель',size=13),
            ft.Container(alignment=ft.alignment.center,bgcolor='#edf1f5',border_radius=16,
                content=ft.GestureDetector(content=canvas,drag_interval=60,on_pan_update=rotate,on_scroll=scroll,
                    mouse_cursor=ft.MouseCursor.MOVE)),
            ft.Text('Тяните фигурку пальцем или мышью. Масштаб — кнопками или колёсиком.',size=12),
            ft.Row(wrap=True,controls=[ft.TextButton('Уменьшить',on_click=lambda event:zoom(-.2)),
                ft.TextButton('Увеличить',on_click=lambda event:zoom(.2)),ft.TextButton('Сбросить вид',on_click=reset)]),
            ft.Row(wrap=True,controls=[ft.TextButton('Спереди',on_click=lambda event:angle(0,0)),
                ft.TextButton('Слева',on_click=lambda event:angle(-90,0)),ft.TextButton('Сзади',on_click=lambda event:angle(180,0)),
                ft.TextButton('Сверху',on_click=lambda event:angle(0,75))]),
            ft.ExpansionTile(title=ft.Text('Освещение и рёбра'),initially_expanded=False,
                controls=[ft.Text('Направление света'),light,ft.Text('Яркость'),brightness,wire]),
            createModelFavorite(page,user,modelId),
            ft.TextButton('Урок для этой фигурки',icon=ft.Icons.SCHOOL_OUTLINED,on_click=linkedLesson),
            ft.TextButton('Скачать OBJ и материалы',icon=ft.Icons.DOWNLOAD_OUTLINED,on_click=export,visible=not androidClient(page)),
            ft.Text('Формы упрощены для изучения объёма и деталей. Это не 3D-скан готовой работы.',size=12)
        ])])
