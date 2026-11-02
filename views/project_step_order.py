"""Drag-only ordering. Flutter owns the optimistic list; Python saves the draft."""
import flet as ft
from project_service import getProjectSteps,saveProjectStepOrder
from ui_helpers import authenticatedAction,showMessage


def createOrderEditor(page,user,projectId,onSaved,onCancel):
    steps=getProjectSteps(projectId,user['userId'])
    expected=[s['stepId'] for s in steps];ordered=list(expected);active={'value':True}
    status=ft.Text('Удерживайте этап на телефоне; на ПК тяните за ручку справа.',size=13)
    labels={step['stepId']:step['stepDescription'] for step in steps}
    generation={'value':0}
    host=ft.Container(height=min(420,max(120,len(steps)*66)))
    def rebuild():
        generation['value']+=1
        current=generation['value']
        @authenticatedAction(page,user)
        def reorder(event):
            if not active['value'] or current!=generation['value']:return
            old,new=event.old_index,event.new_index
            if type(old) is int and type(new) is int and 0<=old<len(ordered) and 0<=new<len(ordered):
                ordered.insert(new,ordered.pop(old))
                status.value='Новый порядок готов. Сохраните изменения или отмените.'
                # Replace the list control, not its children: Flet 0.28 keeps an
                # optimistic child-order cache which otherwise wins over patches.
                rebuild()
                page.update()
        host.content=ft.ReorderableListView(expand=True,show_default_drag_handles=True,on_reorder=reorder,
            controls=[ft.Container(key=str(current)+':'+str(sid),padding=ft.padding.only(left=12,right=48,top=16,bottom=16),
                content=ft.Text(labels[sid],max_lines=2,overflow=ft.TextOverflow.ELLIPSIS)) for sid in ordered])
    rebuild()
    @authenticatedAction(page,user)
    def save(event):
        if not active['value']:return
        success,message=saveProjectStepOrder(projectId,user['userId'],ordered,expected)
        if success:active['value']=False;onSaved()
        showMessage(page,message,not success)
    def cancel(event):active['value']=False;onCancel()
    return ft.Column(spacing=12,controls=[status,host,
        ft.Row(wrap=True,controls=[ft.TextButton('Отмена',on_click=cancel),ft.ElevatedButton('Сохранить порядок',on_click=save)])])


def createStepOrderButton(page,currentUser,projectId,onSaved):
    @authenticatedAction(page,currentUser)
    def openOrder(event):
        if len(getProjectSteps(projectId,currentUser['userId']))<2:
            showMessage(page,'Для изменения порядка нужны хотя бы два этапа');return
        dialog=ft.AlertDialog(modal=True,title=ft.Text('Порядок этапов'))
        def cancel():page.close(dialog)
        def saved():page.close(dialog);onSaved()
        dialog.content=ft.Container(width=min(500,max(240,(page.width or 390)-64)),
            content=createOrderEditor(page,currentUser,projectId,saved,cancel))
        page.open(dialog)
    return ft.TextButton('Порядок этапов',icon=ft.Icons.SWAP_VERT,on_click=openOrder)
