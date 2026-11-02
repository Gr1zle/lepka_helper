from localization import tr, term, message as translateMessage
"""Календарь дедлайнов и центр локальных напоминаний."""
from datetime import date
import flet as ft
from account_gateway import getUserProfile
from project_planner import monthPlan, syncProjectReminders, markProjectRemindersRead, PLANNER_FILTERS
from ui_helpers import authenticatedAction, getCurrentUser

MONTHS = ('Январь','Февраль','Март','Апрель','Май','Июнь','Июль','Август','Сентябрь','Октябрь','Ноябрь','Декабрь')


def openPlannerProject(page, user, projectId):
    # Получатель повторно проверит владельца и найдёт проект в актуальной базе.
    page.session.set('plannerProject', {'owner': user['sessionToken'], 'projectId': projectId})
    page.session.set('homeTab',3)
    page.go('/home')


def createDeadlineSummary(page, user):
    if user is None: return ft.Container()
    profile = getUserProfile(user['userId'], sessionToken=user.get('sessionToken')) or {}
    enabled = profile.get('notificationsEnabled',True)
    reminders = syncProjectReminders(user['userId'],enabled)
    unread = sum(not item['isRead'] for item in reminders)
    @authenticatedAction(page,user)
    def openCalendar(event): page.go('/planner')
    message = (f'Непрочитанных напоминаний: {unread}' if enabled else 'Напоминания отключены в профиле')
    return ft.Card(content=ft.Container(padding=14,content=ft.Column(controls=[
        ft.Text(tr(page, 'Сроки проектов'),size=18,weight=ft.FontWeight.BOLD),ft.Text(translateMessage(page,message)),
        *[ft.Text(f"{item['projectName']}: {term(page,item['label'])} · {item['deadlineDate']}",size=13)
          for item in reminders if not item['isRead']][:3],
        ft.TextButton(tr(page, 'Календарь и напоминания'),icon=ft.Icons.CALENDAR_MONTH,on_click=openCalendar)])))


def createProjectPlanner(page):
    user = getCurrentUser(page)
    if user is None:
        return ft.View('/planner',controls=[ft.Text(tr(page, 'Войдите, чтобы открыть личный календарь')),
            ft.TextButton(tr(page, 'Войти'),on_click=lambda event:page.go('/auth'))])
    today = date.today()
    state = {'year':today.year,'month':today.month,'day':None}
    title = ft.Text(size=20,weight=ft.FontWeight.BOLD)
    summary = ft.Text()
    days = ft.Column(spacing=2)
    results = ft.Column(spacing=8)
    inbox = ft.Column(spacing=8)
    filterField = ft.Dropdown(label=tr(page, 'Показать проекты'),value='Месяц',options=[ft.dropdown.Option(key=v, text=term(page, v)) for v in PLANNER_FILTERS])

    def projectRow(item):
        @authenticatedAction(page,user)
        def openProject(event): openPlannerProject(page,user,item['projectId'])
        return ft.Card(content=ft.Container(padding=12,content=ft.Column(spacing=6,controls=[
            ft.Text(item['projectName'],size=17,weight=ft.FontWeight.BOLD),
            ft.Text(f"{item['deadlineDate'] or tr(page,'Без срока')} · {term(page,item['status'])} · {round(item['progressPercent'])}%"),
            ft.TextButton(tr(page, 'К проекту'),on_click=openProject)])))

    def refresh():
        plan = monthPlan(user['userId'],state['year'],state['month'],filterField.value,state['day'])
        title.value = f"{term(page,MONTHS[state['month']-1])} {state['year']}"
        summary.value = tr(page, 'В работе: {v0} · Просрочены: {v1} · Без срока: {v2}', v0=plan['active'], v1=plan['overdue'], v2=plan['undated'])
        days.controls = [ft.Row(spacing=0,controls=[ft.Container(expand=1,alignment=ft.alignment.center,content=ft.Text(term(page,day),size=12))
                                                 for day in ('Пн','Вт','Ср','Чт','Пт','Сб','Вс')])]
        for week in plan['weeks']:
            cells = []
            for day in week:
                @authenticatedAction(page,user)
                def select(event, value=day):
                    state['day'] = value; filterField.value = 'Месяц'; refresh()
                count = plan['counts'].get(day,0)
                selected = day and state['day']==day
                button = ft.TextButton(f'{day}' + (f'\n•{count}' if count else ''),expand=1,height=46,
                    tooltip=tr(page, '{v0:02d}.{v1:02d}.{v2:04d}: проектов {v3}', v0=day, v1=state['month'], v2=state['year'], v3=count),on_click=select,
                    style=ft.ButtonStyle(padding=0,bgcolor=ft.Colors.SECONDARY_CONTAINER if selected else None))
                cells.append(button if day else ft.Container(expand=1,height=46))
            days.controls.append(ft.Row(spacing=0,controls=cells))
        results.controls = [projectRow(item) for item in plan['items']] or [ft.Text(tr(page, 'На выбранный период проектов нет.'))]
        renderReminders()
        page.update()

    def renderReminders():
        profile = getUserProfile(user['userId'],sessionToken=user.get('sessionToken')) or {}
        enabled = profile.get('notificationsEnabled',True)
        reminders = syncProjectReminders(user['userId'],enabled)
        unread = sum(not item['isRead'] for item in reminders)
        inbox.controls = [ft.Text(tr(page, 'Напоминания · непрочитано: {v0}', v0=unread),size=18,weight=ft.FontWeight.BOLD)]
        if not enabled:
            inbox.controls.append(ft.Text(tr(page, 'Напоминания отключены. Включить их можно в настройках профиля.')));return
        if not reminders:
            inbox.controls.append(ft.Text(tr(page, 'Напоминаний пока нет. Они появляются за 2 дня, за день, в день срока и после просрочки.')));return
        @authenticatedAction(page,user)
        def readAll(event): markProjectRemindersRead(user['userId']);refresh()
        inbox.controls.append(ft.TextButton(tr(page, 'Прочитать все напоминания'),on_click=readAll))
        for item in reminders:
            @authenticatedAction(page,user)
            def openReminder(event, value=item):
                markProjectRemindersRead(user['userId'],value['reminderId'])
                openPlannerProject(page,user,value['projectId'])
            inbox.controls.append(ft.Card(content=ft.Container(padding=12,content=ft.Column(controls=[
                ft.Text(('' if item['isRead'] else tr(page, 'Новое · '))+item['label'],weight=ft.FontWeight.BOLD),
                ft.Text(f"{item['projectName']} · {item['deadlineDate']}"),
                ft.Text(tr(page, 'Создано: {v0}', v0=date.fromisoformat(item['generatedDate']).strftime('%d.%m.%Y')),size=12),
                ft.TextButton(tr(page, 'Открыть проект'),on_click=openReminder)]))))

    def changeMonth(delta):
        index = (state['year']-1)*12+state['month']-1+delta
        if not 0 <= index < 9999*12: return
        state.update(year=index//12+1,month=index%12+1,day=None);refresh()
    @authenticatedAction(page,user)
    def previous(event): changeMonth(-1)
    @authenticatedAction(page,user)
    def following(event): changeMonth(1)
    @authenticatedAction(page,user)
    def reset(event):
        now = date.today();state.update(year=now.year,month=now.month,day=None);filterField.value='Месяц';refresh()
    @authenticatedAction(page,user)
    def clearDay(event): state['day']=None;refresh()
    @authenticatedAction(page,user)
    def filtered(event): state['day']=None;refresh()
    @authenticatedAction(page,user)
    def update(event): refresh()
    filterField.on_change = filtered
    refresh()
    return ft.View('/planner',padding=12,
        appbar=ft.AppBar(title=ft.Text(tr(page, 'Планировщик проектов')),leading=ft.IconButton(icon=ft.Icons.ARROW_BACK,on_click=lambda event:page.go('/home'))),
        controls=[ft.ListView(expand=True,spacing=12,controls=[
            summary,title,ft.Row(wrap=True,controls=[ft.TextButton(tr(page, 'Раньше'),on_click=previous),
                ft.TextButton(tr(page, 'Текущий месяц'),on_click=reset),ft.TextButton(tr(page, 'Позже'),on_click=following)]),days,
            ft.Text(tr(page, 'Точка с числом — активные проекты с дедлайном в этот день. Нажмите день для отбора.'),size=12),
            ft.TextButton(tr(page, 'Все дни месяца'),on_click=clearDay),filterField,results,
            ft.Divider(),inbox,ft.TextButton(tr(page, 'Обновить сроки'),on_click=update),
            ft.Text(tr(page, 'Используется местная дата запуска приложения. Напоминания проверяются при открытии главной, проектов и календаря. При закрытом приложении уведомления не отправляются.'),size=12)])])
