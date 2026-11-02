from localization import tr, term
"""One project workspace. Editors share the page, avoiding nested modal routes."""
import base64
import flet as ft
from database import getProjectById,projectFinalPhoto
from project_service import (getProjectSteps,saveStep,changeProjectStepStatus,saveProjectStepPhoto,
    removeProjectStepPhoto,removeProjectStep,saveFinalPhoto,removeFinalPhoto,finishProject,editProject,removeProject)
from photo_picker import createPhotoPicker
from ui_helpers import authenticatedAction,showMessage,confirmAction
from design_system import polish,disclosure


def createProjectEditor(page,user,projectId,onChanged=None):
    uid=user['userId'];action=authenticatedAction(page,user)
    body=ft.Column(spacing=14)
    root=ft.ListView(expand=True,padding=16,controls=[body],build_controls_on_demand=False)
    def mount(controls):body.controls=controls;polish(root);page.update()
    def changed():
        if onChanged:onChanged()
        render()
    def message(result):
        ok,text=result[:2]
        if ok:changed()
        showMessage(page,text,not ok)
    def backButton():return ft.TextButton(tr(page, 'К проекту'),icon=ft.Icons.ARROW_BACK,on_click=lambda e:render())
    def image(data,height=180):return ft.Image(src_base64=base64.b64encode(data).decode(),height=height,fit=ft.ImageFit.CONTAIN)
    @action
    def confirm(title,callback):
        mount([ft.Text(title,size=22,weight=ft.FontWeight.W_600),ft.Text(tr(page, 'Это действие нельзя отменить.')),
            ft.Row(wrap=True,controls=[ft.TextButton(tr(page, 'Отмена'),on_click=lambda e:render()),
                ft.FilledButton(tr(page, 'Подтвердить удаление'),on_click=action(lambda e:callback()),style=ft.ButtonStyle(bgcolor=ft.Colors.ERROR,color=ft.Colors.ON_ERROR))])])
    @action
    def editStep(event,step=None):
        title=ft.TextField(label=tr(page, 'Название этапа'),value=step['title'] if step else '',max_length=80)
        details=ft.TextField(label=tr(page, 'Описание этапа (необязательно)'),value=step['details'] if step else '',multiline=True,min_lines=3,max_lines=6,max_length=900)
        @action
        def save(event):message(saveStep(projectId,uid,title.value,details.value,step['stepId'] if step else None))
        controls=[backButton(),ft.Text(tr(page, 'Редактировать этап') if step else tr(page, 'Новый этап'),size=22),title,details,
            ft.FilledButton(tr(page, 'Сохранить этап'),icon=ft.Icons.SAVE_OUTLINED,on_click=save)]
        if step:controls.append(ft.TextButton(tr(page, 'Удалить этап'),icon=ft.Icons.DELETE_OUTLINE,on_click=lambda e:confirm('Удалить этап «'+step['title']+'»?',lambda:(removeProjectStep(projectId,step['stepId'],uid),changed()))))
        mount(controls)
    @action
    def photoEditor(event,step=None):
        data=(__import__('database').getProjectStepPhoto(projectId,step['stepId'],uid) if step else projectFinalPhoto(projectId,uid))
        def selected(photo):
            result=saveProjectStepPhoto(projectId,step['stepId'],uid,photo) if step else saveFinalPhoto(projectId,uid,photo)
            if result[0]:changed()
            return result
        def remove(event):message(removeProjectStepPhoto(projectId,step['stepId'],uid) if step else removeFinalPhoto(projectId,uid))
        mount([backButton(),ft.Text(tr(page, 'Фото этапа') if step else tr(page, 'Финальный результат'),size=22),
            *([image(data,260)] if data else []),createPhotoPicker(page,user,selected,'Заменить фото' if data else 'Выбрать фото'),
            ft.Text(tr(page, 'JPG, PNG или WebP, до 10 МБ. Фото личного этапа необязательно; для выбранных этапов публикации нужно фото.'),size=12),
            *([ft.TextButton(tr(page, 'Убрать фото'),icon=ft.Icons.DELETE_OUTLINE,on_click=action(remove))] if data else [])])
    @action
    def projectForm(event):
        project=getProjectById(projectId,uid)
        if not project:return render()
        from date_field import createDeadlineField
        name=ft.TextField(label=tr(page, 'Название проекта'),value=project['projectName'],max_length=80)
        category=ft.Dropdown(label=tr(page, 'Категория'),value=project['categoryName'],options=[ft.dropdown.Option(key=c, text=term(page, c)) for c in __import__('project_service').PROJECT_CATEGORIES])
        deadline=createDeadlineField(page);deadline.value=project['deadlineDate'] or ''
        notes=ft.TextField(label=tr(page, 'Описание / заметки'),value=project['descriptionText'] or '',multiline=True,max_length=1500)
        @action
        def save(event):message(editProject(projectId,uid,name.value,category.value,deadline.value,notes.value))
        mount([backButton(),ft.Text(tr(page, 'Редактировать проект'),size=22),name,category,deadline,notes,ft.FilledButton(tr(page, 'Сохранить изменения'),on_click=save),
            ft.TextButton(tr(page, 'Удалить проект'),on_click=lambda e:confirm('Удалить проект?',lambda:(removeProject(projectId,uid),changed())))])
    @action
    def order(event):
        from views.project_step_order import createOrderEditor
        mount([ft.Text(tr(page, 'Порядок этапов'),size=22),createOrderEditor(page,user,projectId,changed,render)])
    @action
    def recipes(event):
        from project_sharing import getProjectMixtures,addProjectMixture,removeProjectMixture
        from color_service import getUserColorMixtures
        saved=[m for m in getUserColorMixtures(uid) if not m['recipeError']]
        choice=ft.Dropdown(label=tr(page, 'Смесь из моей палитры'),options=[ft.dropdown.Option(str(m['mixtureId']),m['mixtureName']) for m in saved])
        def refreshRecipes():recipes(None)
        @action
        def add(event):
            if choice.value is None:showMessage(page,tr(page, 'Выберите смесь'),True);return
            result=addProjectMixture(projectId,uid,int(choice.value));refreshRecipes();showMessage(page,result[1],not result[0])
        controls=[backButton(),ft.Text(tr(page, 'Смеси проекта'),size=22),choice,ft.FilledButton(tr(page, 'Добавить смесь'),disabled=not saved,on_click=add)]
        for item in getProjectMixtures(projectId,uid):
            mid=item['projectMixtureId']
            controls.append(ft.Card(content=ft.Container(padding=12,content=ft.Column(controls=[
                ft.Text(item['mixtureName'],weight=ft.FontWeight.W_600),ft.Text(str(item.get('totalWeight',''))+tr(page, ' г')),
                *([ft.Text(tr(page, 'Рецепт повреждён'),color=ft.Colors.ERROR)] if item.get('recipeError') else [disclosure(tr(page, 'Рецепт'),[ft.Row([ft.Container(width=20,height=20,bgcolor=c['hex'],border_radius=10),
                    ft.Text(str(term(page,c['name']))+' · '+str(c['percent'])+'% · '+str(c['grams'])+tr(page, ' г'),expand=True)]) for c in item['recipeItems']])]),
                ft.TextButton(tr(page, 'Убрать из проекта'),on_click=action(lambda e,key=mid:(removeProjectMixture(projectId,uid,key),refreshRecipes())))]))))
        mount(controls)
    @action
    def publication(event):
        from community_gateway import CommunityClient
        from post_service import POST_CATEGORIES
        from views.contest_picker import createContestPicker,selectedContest
        project=getProjectById(projectId,uid);steps=getProjectSteps(projectId,uid)
        if not project or not project['finalPhotoImage']:
            showMessage(page,tr(page, 'Перед публикацией добавьте финальное фото'),True);photoEditor(None);return
        title=ft.TextField(label=tr(page, 'Название работы'),value=project['projectName'],max_length=100)
        description=ft.TextField(label=tr(page, 'Описание для сообщества'),value='',multiline=True,min_lines=3,max_length=2000)
        category=ft.Dropdown(label=tr(page, 'Категория работы'),value=project['categoryName'],options=[ft.dropdown.Option(key=c, text=term(page, c)) for c in POST_CATEGORIES])
        tags=ft.TextField(label=tr(page, 'Теги через запятую'))
        contest,contestControls=createContestPicker(page,user)
        choices=[ft.Checkbox(label=s['title']+(tr(page, ' — добавьте фото') if not s['hasPhoto'] else ''),disabled=not s['hasPhoto'],data=s['stepId']) for s in steps]
        from project_sharing import getProjectMixtures
        mixes=[ft.Checkbox(label=m['mixtureName'],data=m['projectMixtureId']) for m in getProjectMixtures(projectId,uid) if not m.get('recipeError')]
        from lesson_service import IDEA_LEVELS
        enableInfo=ft.Switch(label=tr(page, 'Добавить параметры мастер-класса'),value=False)
        level=ft.Dropdown(label=tr(page, 'Сложность'),value=IDEA_LEVELS[0],options=[ft.dropdown.Option(key=v, text=term(page, v)) for v in IDEA_LEVELS])
        minutes=ft.TextField(label=tr(page, 'Время выполнения (минут)'),keyboard_type=ft.KeyboardType.NUMBER)
        materials=ft.TextField(label=tr(page, 'Материалы — по одному на строку'),multiline=True)
        tools=ft.TextField(label=tr(page, 'Инструменты — по одному на строку'),multiline=True)
        client=CommunityClient(user)
        busy={'value':False}
        @action
        def publish(event):
            if busy['value']:return
            busy['value']=True
            try:
                result=client.publishProject(projectId,title.value,description.value,category.value,tags.value,None,
                    [c.data for c in choices if c.value],[c.data for c in mixes if c.value],
                    workshopInfo=({'level':level.value,'timeMinutes':minutes.value,'materials':(materials.value or '').splitlines(),'tools':(tools.value or '').splitlines()} if enableInfo.value else None),
                    challengeId=selectedContest(contest))
                if result[0]:render()
                else:busy['value']=False
                showMessage(page,result[1],not result[0])
            except Exception:
                busy['value']=False
                raise
        mount([backButton(),ft.Text(tr(page, 'Публикация проекта'),size=22),image(bytes(project['finalPhotoImage'])),title,description,category,tags,contestControls,
            ft.Text(tr(page, 'Финальное фото станет обложкой. Выберите до 9 этапов с фотографиями; личные заметки и дедлайн не публикуются.')),
            *choices,disclosure(tr(page, 'Параметры мастер-класса'),[enableInfo,level,minutes,materials,tools]),disclosure(tr(page, 'Поделиться рецептами'),mixes),ft.FilledButton(tr(page, 'Опубликовать проект'),on_click=publish)])
    @action
    def render(event=None):
        project=getProjectById(projectId,uid)
        if not project:mount([ft.Text(tr(page, 'Проект удалён или недоступен'))]);return
        steps=getProjectSteps(projectId,uid)
        finished=bool(project['isFinished'])
        controls=[ft.Row([ft.Text(project['projectName'],size=24,weight=ft.FontWeight.W_600,expand=True),
            ft.IconButton(ft.Icons.EDIT_OUTLINED,tooltip=tr(page, 'Редактировать проект'),on_click=projectForm)]),
            ft.Text(term(page,project['categoryName'])+' · '+(project['deadlineDate'] or tr(page,'Без дедлайна'))),
            ft.Text(tr(page, 'Проект завершён') if finished else tr(page, 'В работе · этапы: ')+str(project['progressPercent'])+'%')]
        if project['descriptionText']:controls.append(ft.Text(project['descriptionText']))
        controls.extend([ft.Row(wrap=True,controls=[ft.FilledButton(tr(page, 'Вернуть в работу') if finished else tr(page, 'Завершить проект'),
            icon=ft.Icons.CHECK_CIRCLE_OUTLINE,on_click=action(lambda e:message(finishProject(projectId,uid,not finished)))),
            ft.TextButton(tr(page, 'Финальное фото'),icon=ft.Icons.PHOTO_OUTLINED,on_click=lambda e:photoEditor(e))]),
            *([image(bytes(project['finalPhotoImage']),140)] if project['finalPhotoImage'] else []),
            ft.Row([ft.Text(tr(page, 'Этапы'),size=18,weight=ft.FontWeight.W_600,expand=True),ft.TextButton(tr(page, 'Порядок этапов'),disabled=len(steps)<2,on_click=order)])])
        for step in steps:
            @action
            def toggle(event,sid=step['stepId']):
                changeProjectStepStatus(projectId,sid,event.control.value,uid);changed()
            controls.append(ft.Card(content=ft.Container(padding=10,content=ft.Column(spacing=4,controls=[
                ft.Row(spacing=0,controls=[ft.Checkbox(value=step['isCompleted'],on_change=toggle),
                    ft.Text(step['title'],expand=True,weight=ft.FontWeight.W_600),
                    ft.IconButton(ft.Icons.PHOTO if step['hasPhoto'] else ft.Icons.ADD_PHOTO_ALTERNATE_OUTLINED,tooltip=tr(page, 'Фото этапа'),on_click=lambda e,s=step:photoEditor(e,s)),
                    ft.IconButton(ft.Icons.EDIT_OUTLINED,tooltip=tr(page, 'Редактировать этап'),on_click=lambda e,s=step:editStep(e,s))]),
                *([ft.Text(step['details'],size=13,color=ft.Colors.ON_SURFACE_VARIANT)] if step['details'] else [])]))))
        controls.extend([ft.OutlinedButton(tr(page, 'Добавить этап'),icon=ft.Icons.ADD,on_click=editStep),
            ft.Row(wrap=True,controls=[ft.TextButton(tr(page, 'Смеси проекта'),icon=ft.Icons.PALETTE_OUTLINED,on_click=recipes),
                ft.TextButton(tr(page, 'Опубликовать в сообщество'),icon=ft.Icons.PUBLISH_OUTLINED,on_click=publication)])])
        from views.project_transfer import createProjectExport
        controls.append(createProjectExport(page,user,projectId))
        mount(controls)
    render()
    return root
