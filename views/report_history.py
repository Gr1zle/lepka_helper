from localization import tr, term
"""Пользователь видит только свои жалобы и опубликованные решения."""
import flet as ft
from moderation_gateway import ModerationClient
from ui_helpers import authenticatedAction,createLoadError
from api_client import ApiError


def createReportHistoryButton(page,user):
    @authenticatedAction(page,user)
    def openHistory(event):
        client=ModerationClient(user);offset={'value':0};result=ft.Column(spacing=12)
        previous=ft.TextButton(tr(page, 'Предыдущие'));following=ft.TextButton(tr(page, 'Следующие'));number=ft.Text()
        def render():
            try:
                rows=client.myReports(offset['value']);controls=[]
                for item in rows:
                    label={'open':'Ожидает рассмотрения','resolved':'Рассмотрена','rejected':'Отклонена'}[item['status']]
                    controls.append(ft.Card(content=ft.Container(padding=12,content=ft.Column(controls=[
                        ft.Text(tr(page, 'Жалоба №{v0} · {v1}', v0=item['reportId'], v1=label),weight=ft.FontWeight.BOLD),
                        ft.Text((tr(page, 'Публикация') if item['targetType']=='post' else tr(page, 'Комментарий'))+f" №{item['targetId']}"),
                        ft.Text(tr(page, 'Ваша причина: ')+item['reason']),ft.Text(tr(page, 'Решение: ')+(item['resolution'] or 'Ещё не опубликовано')),
                        ft.Text(item['createdAt']+' UTC',size=12)]))))
                result.controls=controls or [ft.Text(tr(page, 'Вы пока не отправляли жалобы.'))]
                previous.disabled=offset['value']==0;following.disabled=len(rows)<50;number.value=tr(page, 'Страница {v0}', v0=offset['value'] // 50 + 1)
            except ApiError as error:
                if error.statusCode==401:raise
                result.controls=[createLoadError(page,error,lambda:(render(),page.update()))]
        @authenticatedAction(page,user)
        def move(delta):offset['value']=max(0,offset['value']+delta);render();page.update()
        @authenticatedAction(page,user)
        def refresh(event):render();page.update()
        previous.on_click=lambda e:move(-50);following.on_click=lambda e:move(50)
        dialog=ft.AlertDialog(title=ft.Text(tr(page, 'Мои жалобы и решения')),content=ft.Container(width=440,height=400,
            content=ft.ListView(spacing=12,controls=[ft.TextButton(tr(page, 'Обновить решения'),on_click=refresh),result,ft.Row(wrap=True,controls=[previous,number,following])])),
            actions=[ft.TextButton(tr(page, 'Закрыть'),on_click=lambda e:page.close(dialog))])
        render();page.open(dialog)
    return ft.TextButton(tr(page, 'Мои жалобы и решения'),icon=ft.Icons.FLAG_OUTLINED,on_click=openHistory,visible=user is not None)
