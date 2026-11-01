"""Задания сообщества: список, заявки, публикации и подведение итогов."""
from datetime import datetime
import flet as ft
from challenge_gateway import ChallengeClient
from community_gateway import CommunityClient
from date_field import createDeadlineField
from ui_helpers import getCurrentUser, authenticatedAction, createLoadError, showMessage
from views.moderation_actions import reasonDialog
from api_client import ApiError

LABELS = {'scheduled':'Скоро начнётся','open': 'Приём работ', 'judging': 'Ожидает итогов', 'finished': 'Завершено', 'cancelled': 'Отменено'}


def createChallengeView(page):
    user = getCurrentUser(page)
    if not user:
        return ft.View('/challenges', controls=[ft.Text('Для участия войдите в аккаунт'),
                       ft.TextButton('Войти', on_click=lambda e: page.go('/auth'))])
    client = ChallengeClient(user)
    community = CommunityClient(user)
    selected = {'id': page.session.get('openChallengeId'), 'offset': 0, 'listOffset': 0}
    page.session.set('openChallengeId',None)
    mode = ft.Dropdown(label='Показать задания', value='active', options=[
        ft.dropdown.Option('active', 'Активные и без итогов'),
        ft.dropdown.Option('mine', 'Мои заявки'), ft.dropdown.Option('finished', 'Завершённые и отменённые')])
    sort = ft.Dropdown(label='Сортировка участников', value='new', options=[ft.dropdown.Option('new','Сначала новые'), ft.dropdown.Option('votes','По голосам')])
    content = ft.Column(spacing=12)

    def action(callback):
        return authenticatedAction(page, user)(callback)

    def button(text, callback):
        return ft.OutlinedButton(text, on_click=action(callback))

    def openDetail(challengeId):
        selected.update(id=challengeId, offset=0)
        render()

    def openList(event=None):
        selected.update(id=None, offset=0)
        render()

    def openPost(postId):
        # Не загружаем всю ленту ради одной заявки.
        item = community.getPost(postId)
        if not item:
            showMessage(page, 'Публикация уже недоступна', True)
            render()
            return
        from views.community_tab import createPostCard
        dialog = ft.AlertDialog(title=ft.Text('Работа участника'), content=ft.Container(width=500, height=440,
            content=ft.ListView(controls=[createPostCard(page, item, user, lambda: (page.close(dialog), render()))])),
            actions=[ft.TextButton('Закрыть', on_click=lambda e: page.close(dialog))])
        page.open(dialog)

    def submitDialog(challengeId):
        works = community.getPosts(mine=True)
        if not works:
            showMessage(page, 'Сначала опубликуйте работу в ленте сообщества', True)
            return
        picker = ft.Dropdown(label='Моя опубликованная работа', options=[
            ft.dropdown.Option(str(p['postId']), p['titleText']) for p in works if not p['isDeleted']])
        error = ft.Text(color=ft.Colors.RED)

        @action
        def send(event):
            if not picker.value:
                error.value = 'Выберите работу'; page.update(); return
            try:
                client.submit(challengeId, int(picker.value))
                page.close(dialog); render()
                showMessage(page, 'Работа принята')
            except ApiError as exc:
                if exc.statusCode == 401: raise
                error.value = str(exc); page.update()
        dialog = ft.AlertDialog(title=ft.Text('Отправить работу'), content=ft.Column(tight=True, controls=[
            ft.Text('Одна работа на участника. До срока заявку можно отозвать и отправить другую.'), picker, error]),
            actions=[ft.TextButton('Отмена', on_click=lambda e: page.close(dialog)), ft.ElevatedButton('Отправить заявку', on_click=send)])
        page.open(dialog)

    def createDialog(event):
        title = ft.TextField(label='Название задания', max_length=100)
        rules = ft.TextField(label='Правила и критерии выбора победителя', multiline=True, min_lines=3, max_length=2000)
        starts = createDeadlineField(page)
        starts.label = 'Начало конкурса'
        starts.hint_text = 'ДД.ММ.ГГГГ, пусто — сегодня'
        theme = ft.TextField(label='Тематика',max_length=80)
        resultMode = ft.Dropdown(label='Подведение итогов',value='votes',options=[ft.dropdown.Option('votes','Автоматически: топ-3 по голосам'),ft.dropdown.Option('manual','Выбирает администратор')])
        deadline = createDeadlineField(page)
        deadline.hint_text = 'ДД.ММ.ГГГГ, обязательное поле'
        error = ft.Text(color=ft.Colors.RED)
        busy = {'value': False}

        @action
        def save(event):
            if busy['value']: return
            try:
                day = datetime.strptime(deadline.value or '', '%d.%m.%Y').date().isoformat()
                startDay = datetime.strptime(starts.value,'%d.%m.%Y').date().isoformat() if starts.value else None
            except ValueError:
                error.value = 'Укажите дату в формате ДД.ММ.ГГГГ'; page.update(); return
            busy['value'] = True
            try:
                challengeId = client.create(title.value or '', rules.value or '', day, startDay, theme.value or '', resultMode.value)
                page.close(dialog); openDetail(challengeId)
            except ApiError as exc:
                if exc.statusCode == 401: raise
                error.value = str(exc); page.update()
            finally:
                busy['value'] = False
        dialog = ft.AlertDialog(title=ft.Text('Новое задание'), content=ft.Container(width=460, height=380,
            content=ft.ListView(spacing=14,controls=[title, theme, rules, starts, deadline, ft.Container(content=resultMode,padding=6), ft.Text('Приём до конца указанного дня по Москве.'), error])),
            actions=[ft.TextButton('Отмена', on_click=lambda e: page.close(dialog)), ft.ElevatedButton('Создать задание', on_click=save)])
        page.open(dialog)

    def decide(challengeId, state, postId=None):
        title = 'Отменить задание?' if state == 'cancelled' else 'Опубликовать окончательные итоги?'
        reasonDialog(page, user, title, 'Подтвердить решение',
                     lambda reason: client.finish(challengeId, state, reason, postId), lambda: render())

    def paginate(delta, detail=False):
        key = 'offset' if detail else 'listOffset'
        selected[key] = max(0, selected[key] + delta)
        render()

    def pagination(count, detail=False):
        offset = selected['offset' if detail else 'listOffset']
        return ft.Row(wrap=True, controls=[
            ft.TextButton('Предыдущие', disabled=offset == 0, on_click=action(lambda e: paginate(-50, detail))),
            ft.Text(f'Страница {offset // 50 + 1}'),
            ft.TextButton('Следующие', disabled=count < 50, on_click=action(lambda e: paginate(50, detail)))])

    def render(update=True):
        controls = []
        try:
            if selected['id'] is None:
                items = client.listing(mode.value, selected['listOffset'])
                controls.append(ft.Container(content=mode, padding=ft.padding.symmetric(vertical=6)))
                if user.get('roleName') == 'admin':
                    controls.append(button('Создать задание', createDialog))
                for item in items:
                    controls.append(ft.Card(content=ft.Container(padding=14, content=ft.Column(controls=[
                        ft.Text(item['title'], size=20, weight=ft.FontWeight.BOLD),
                        ft.Text(f"{LABELS[item['status']]} · заявок: {item['entriesCount']}"),
                        ft.Text(('Начало: '+item['startsOn']+' · ' if item['startsOn'] else '')+'Срок: ' + item['deadline'] + ' включительно (Москва)'),
                        button('Открыть задание', lambda e, i=item['challengeId']: openDetail(i))]))))
                if not items: controls.append(ft.Text('Заданий пока нет.'))
                controls.append(pagination(len(items)))
            else:
                item = client.detail(selected['id'], selected['offset'], sort.value)
                cid = item['challengeId']
                controls.extend([button('К списку заданий', openList), ft.Text(item['title'], size=24, weight=ft.FontWeight.BOLD),
                    ft.Text(LABELS[item['status']]), ft.Text('Приём до ' + item['deadline'] + ' включительно, Москва (UTC+3)'),
                    ft.Text('Тематика: '+(item['theme'] or 'Свободная')), ft.Text('Начало: '+(item['startsOn'] or 'С момента создания')),
                    ft.Text('Итоги: автоматический топ-3' if item['resultMode']=='votes' else 'Итоги выбирает администратор'),
                    ft.Text(item['rules']), ft.Text(f"Участников: {item['entriesCount']}")])
                if item['state'] != 'open':
                    controls.append(ft.Text('Решение: ' + item['result']))
                    winner = item['winner']
                    controls.append(ft.Text('Победитель: ' + winner['nickname'] + ' — ' + winner['titleText'] if winner else
                                            'Победитель не выбран или его публикация удалена.'))
                for award in item['awards']:
                    controls.append(ft.Text(f"{award['place']} место · {award['nickname'] or 'Участник недоступен'} · {award['titleText'] or 'Работа удалена'} · голосов на момент итогов: {award['votes']}",weight=ft.FontWeight.BOLD))
                if item['myPostId']:
                    controls.append(ft.Text('Ваша работа участвует в задании'))
                    if item['status'] == 'open':
                        controls.append(button('Отозвать мою заявку', lambda e: (client.withdraw(cid), render())))
                elif item['status'] == 'open':
                    controls.append(button('Участвовать: отправить свою работу', lambda e: submitDialog(cid)))
                if user.get('roleName') == 'admin' and item['state'] == 'open':
                    controls.append(button('Отменить задание', lambda e: decide(cid, 'cancelled')))
                    if item['status'] == 'judging':
                        controls.append(button('Завершить без победителя', lambda e: decide(cid, 'finished')))
                controls.extend([ft.Text('Работы участников', size=20), ft.Container(content=sort, padding=ft.padding.symmetric(vertical=6))])
                for entry in item['entries']:
                    entryControls = [ft.Text(entry['titleText'], weight=ft.FontWeight.BOLD), ft.Text(entry['nickname']),
                        button('Посмотреть работу', lambda e, pid=entry['postId']: openPost(pid))]
                    entryControls.append(ft.Text(f"Голосов в задании: {entry['votes']}"))
                    if item['status']=='open' and not entry['isOwn']:
                        entryControls.append(button('Убрать голос' if entry['isVoted'] else 'Голосовать за работу',
                            lambda e, pid=entry['postId'], liked=not bool(entry['isVoted']): (client.vote(cid,pid,liked),render())))
                    if user.get('roleName') == 'admin' and item['status'] == 'judging':
                        entryControls.append(button('Выбрать победителем', lambda e, pid=entry['postId']: decide(cid, 'finished', pid)))
                    controls.append(ft.Card(content=ft.Container(padding=12, content=ft.Column(controls=entryControls))))
                if not item['entries']: controls.append(ft.Text('Работ пока нет.'))
                controls.append(pagination(len(item['entries']), True))
            content.controls = controls
        except ApiError as exc:
            if exc.statusCode == 401: raise
            content.controls = [createLoadError(page, exc, lambda: render()), button('К списку заданий', openList)]
        if update: page.update()

    @action
    def changeMode(event):
        selected['listOffset'] = 0; render()
    @action
    def changeSort(event):
        selected['offset'] = 0; render()
    sort.on_change = changeSort
    mode.on_change = changeMode
    render(False)
    return ft.View('/challenges', padding=12, appbar=ft.AppBar(title=ft.Text('Задания сообщества'),
        leading=ft.IconButton(icon=ft.Icons.ARROW_BACK, on_click=lambda e: page.go('/home'))),
        controls=[ft.ListView(expand=True, build_controls_on_demand=False, spacing=12, controls=[
            ft.Text('Серверные задания' if client.remote else 'Локальные задания на этом устройстве'),
            button('Обновить задания', lambda e: render()), content])])
