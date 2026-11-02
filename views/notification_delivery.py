from localization import tr, term
"""Device permission, type preferences and explicit server-mail opt-in."""
import json
import flet as ft
from api_client import apiRequest, ApiError, getApiUrl
from delivery_settings import getSettings, saveSettings
from device_notifications import bridge, buildPlan
from ui_helpers import authenticatedAction, showMessage


def openDeliverySettings(page,user):
    prefs=getSettings(user['userId'])
    labels=dict(deviceEnabled='Уведомления Android',likes='Лайки',comments='Комментарии',replies='Ответы на комментарии',
                awards='Призовые места',projects='Дедлайны проектов',learning='Продолжение обучения')
    switches={key:ft.Switch(label=label,value=prefs[key]) for key,label in labels.items()}
    email=ft.Switch(label=tr(page, 'Письма на подтверждённый email'),value=False)
    status=ft.Text();mailStatus=ft.Text(tr(page, 'Почтовая доставка проверяется отдельно на сервере.'))
    control=bridge(page)
    def refreshStatus():
        if not control:status.value=tr(page, 'Системные уведомления доступны в Android APK. Здесь работает центр уведомлений.');return
        try:
            result=json.loads(control.call('notifyStatus'))
            status.value=tr(page, 'Разрешение Android: ')+(tr(page, 'выдано') if result['granted'] else tr(page, 'не выдано'))+tr(page, ' · канал: ')+(tr(page, 'включён') if result['channelEnabled'] else tr(page, 'выключен'))
        except (OSError,ValueError):status.value=tr(page, 'Не удалось проверить разрешение Android.')
    @authenticatedAction(page,user)
    def permission(event):
        if control:control.call('notifyPermission')
        showMessage(page,tr(page, 'Разрешите уведомления в системном окне; затем нажмите «Проверить разрешение».'))
    @authenticatedAction(page,user)
    def test(event):
        if control:control.call('notifyTest')
        refreshStatus();page.update()
    @authenticatedAction(page,user)
    def save(event):
        values={**prefs,**{k:bool(s.value) for k,s in switches.items()}}
        saveSettings(user['userId'],values)
        if control:control.call('notifySync',json.dumps(buildPlan(user),ensure_ascii=False))
        refreshStatus();page.update();showMessage(page,tr(page, 'Настройки устройства сохранены'))
    @authenticatedAction(page,user)
    def loadMail(event=None):
        if not user.get('apiUrl'):
            email.value=prefs['emailEnabled'];mailStatus.value=tr(page, 'Локальный режим: письма рассылает только отдельно запущенный сервер.');page.update();return
        try:
            result=apiRequest('GET','/account/notification-delivery',sessionToken=user['sessionToken'])['data']
            email.value=result['settings']['emailEnabled']
            mailStatus.value=(tr(page, 'Доставка настроена') if result['mail']['configured'] else tr(page, 'На сервере почтовая доставка выключена или не настроена'))+tr(page, ' · очередь: ')+str(result['mail']['counts'])
        except ApiError as error:
            if error.statusCode==401:raise
            mailStatus.value=tr(page, 'Сервер недоступен или требует обновления. Настройки писем не загружены.')
        page.update()
    @authenticatedAction(page,user)
    def saveMail(event):
        if not user.get('apiUrl'):showMessage(page,tr(page, 'Подключитесь к серверному аккаунту'),True);return
        values={**prefs,**{k:bool(s.value) for k,s in switches.items()},'emailEnabled':bool(email.value)}
        try:apiRequest('PUT','/account/notification-delivery',sessionToken=user['sessionToken'],payload=values)
        except ApiError as error:
            if error.statusCode==401:raise
            showMessage(page,tr(page, 'Настройки писем не сохранены: проверьте связь и версию сервера'),True);return
        loadMail();showMessage(page,tr(page, 'Настройки писем сохранены на сервере'))
    refreshStatus()
    content=ft.Column(width=420,tight=True,scroll=ft.ScrollMode.AUTO,controls=[
        ft.Text(tr(page, 'Доставка на устройство'),weight=ft.FontWeight.BOLD),status,*switches.values(),
        ft.Text(tr(page, 'Дедлайны: за 2 дня, за 1 день и в день срока, в 10:00 по Москве. Android может задерживать неточные будильники. Изменение проектов обновляет расписание при открытом приложении.')),
        ft.Text(tr(page, 'Уроки учитывают интервал и «Напомнить завтра». Общий переключатель профиля имеет приоритет. Выход из аккаунта отменяет расписание.')),
        ft.TextButton(tr(page, 'Разрешить уведомления Android'),on_click=permission,disabled=not control),
        ft.TextButton(tr(page, 'Проверить разрешение'),on_click=lambda e:(refreshStatus(),page.update())),
        ft.TextButton(tr(page, 'Тестовое уведомление'),on_click=test,disabled=not control),
        ft.FilledButton(tr(page, 'Сохранить на устройстве'),on_click=save),ft.Divider(),
        ft.Text(tr(page, 'Письма с сервера'),weight=ft.FontWeight.BOLD),email,mailStatus,
        ft.Text(tr(page, 'Типы выше применятся к письмам при отдельном сохранении на сервере. Для дедлайнов сервер использует последний отправленный личный снимок. Нужны работающий компьютер, интернет и почтовая настройка; Docker не требуется.')),
        ft.Text(tr(page, 'События сообщества появляются на телефоне при открытом приложении и связи с сервером. Доставка на закрытый телефон через Wi-Fi не является FCM push.')),
        ft.TextButton(tr(page, 'Проверить настройки писем'),on_click=loadMail),
        ft.OutlinedButton(tr(page, 'Сохранить настройки писем на сервере'),on_click=saveMail)])
    dialog=ft.AlertDialog(title=ft.Text(tr(page, 'Доставка уведомлений')),content=content,actions=[ft.TextButton(tr(page, 'Закрыть'),on_click=lambda e:page.close(dialog))])
    page.open(dialog)
