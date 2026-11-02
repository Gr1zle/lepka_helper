from localization import tr, term
"""Одинаковый выбор конкурса для публикации фото и проекта."""
import flet as ft
from challenge_gateway import ChallengeClient
from api_client import ApiError
from ui_helpers import authenticatedAction


NO_CONTEST='none'

def selectedContest(picker):
    value=picker.value
    if value in (None,'',NO_CONTEST):return None
    if isinstance(value,str) and value.isdecimal() and int(value)>0 and value in [o.key for o in picker.options]:return int(value)
    raise ValueError('Выберите конкурс из списка или вариант «Без конкурса»')


def createContestPicker(page,user):
    picker=ft.Dropdown(label=tr(page, 'Участие в конкурсе'),value=NO_CONTEST,options=[ft.dropdown.Option(NO_CONTEST,tr(page, 'Без конкурса'))])
    hint=ft.Text(tr(page, 'Выбранному конкурсу автоматически добавится тег. Публикация и заявка сохранятся вместе.'),size=12)
    def refresh(event=None):
        if not user:return
        try:
            items=ChallengeClient(user).listing()
            picker.options=[ft.dropdown.Option(NO_CONTEST,tr(page, 'Без конкурса'))]+[ft.dropdown.Option(str(i['challengeId']),i['title'])
                for i in items if i['status']=='open']
            if picker.value not in [item.key for item in picker.options]:picker.value=NO_CONTEST
            hint.value=tr(page, 'Одна работа на участника. Конкурсный тег занимает одно из 10 мест для тегов.')
        except ApiError as error:
            if error.statusCode==401:raise
            hint.value=tr(page, 'Не удалось загрузить конкурсы: ')+str(error)
        if event:page.update()
    refresh()
    draft=page.session.get('publicationChallenge')
    if user and draft and draft.get('userId')==user['userId'] and draft.get('sessionToken')==user.get('sessionToken'):
        if str(draft.get('challengeId')) in [o.key for o in picker.options]:picker.value=str(draft['challengeId'])
        page.session.set('publicationChallenge',None)
    return picker,ft.Column(spacing=8,controls=[ft.Container(content=picker,padding=ft.padding.symmetric(vertical=6)),hint,
        ft.TextButton(tr(page, 'Обновить список конкурсов'),on_click=authenticatedAction(page,user)(refresh),disabled=user is None)])
