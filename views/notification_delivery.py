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
    email=ft.Switch(label='Письма на подтверждённый email',value=False)
    status=ft.Text();mailStatus=ft.Text('Почтовая доставка проверяется отдельно на сервере.')
    control=bridge(page)
    def refreshStatus():
        if not control:status.value='Системные уведомления доступны в Android APK. Здесь работает центр уведомлений.';return
        try:
            result=json.loads(control.call('notifyStatus'))
            status.value='Разрешение Android: '+('выдано' if result['granted'] else 'не выдано')+' · канал: '+('включён' if result['channelEnabled'] else 'выключен')
        except (OSError,ValueError):status.value='Не удалось проверить разрешение Android.'
    @authenticatedAction(page,user)
    def permission(event):
        if control:control.call('notifyPermission')
        showMessage(page,'Разрешите уведомления в системном окне; затем нажмите «Проверить разрешение».')
    @authenticatedAction(page,user)
    def test(event):
        if control:control.call('notifyTest')
        refreshStatus();page.update()
    @authenticatedAction(page,user)
    def save(event):
        values={**prefs,**{k:bool(s.value) for k,s in switches.items()}}
        saveSettings(user['userId'],values)
        if control:control.call('notifySync',json.dumps(buildPlan(user),ensure_ascii=False))
        refreshStatus();page.update();showMessage(page,'Настройки устройства сохранены')
    @authenticatedAction(page,user)
    def loadMail(event=None):
        if not user.get('apiUrl'):
            email.value=prefs['emailEnabled'];mailStatus.value='Локальный режим: письма рассылает только отдельно запущенный сервер.';page.update();return
        try:
            result=apiRequest('GET','/account/notification-delivery',sessionToken=user['sessionToken'])['data']
            email.value=result['settings']['emailEnabled']
            mailStatus.value=('Доставка настроена' if result['mail']['configured'] else 'На сервере почтовая доставка выключена или не настроена')+' · очередь: '+str(result['mail']['counts'])
        except ApiError as error:
            if error.statusCode==401:raise
            mailStatus.value='Сервер недоступен или требует обновления. Настройки писем не загружены.'
        page.update()
    @authenticatedAction(page,user)
    def saveMail(event):
        if not user.get('apiUrl'):showMessage(page,'Подключитесь к серверному аккаунту',True);return
        values={**prefs,**{k:bool(s.value) for k,s in switches.items()},'emailEnabled':bool(email.value)}
        try:apiRequest('PUT','/account/notification-delivery',sessionToken=user['sessionToken'],payload=values)
        except ApiError as error:
            if error.statusCode==401:raise
            showMessage(page,'Настройки писем не сохранены: проверьте связь и версию сервера',True);return
        loadMail();showMessage(page,'Настройки писем сохранены на сервере')
    refreshStatus()
    content=ft.Column(width=420,tight=True,scroll=ft.ScrollMode.AUTO,controls=[
        ft.Text('Доставка на устройство',weight=ft.FontWeight.BOLD),status,*switches.values(),
        ft.Text('Дедлайны: за 2 дня, за 1 день и в день срока, в 10:00 по Москве. Android может задерживать неточные будильники. Изменение проектов обновляет расписание при открытом приложении.'),
        ft.Text('Уроки учитывают интервал и «Напомнить завтра». Общий переключатель профиля имеет приоритет. Выход из аккаунта отменяет расписание.'),
        ft.TextButton('Разрешить уведомления Android',on_click=permission,disabled=not control),
        ft.TextButton('Проверить разрешение',on_click=lambda e:(refreshStatus(),page.update())),
        ft.TextButton('Тестовое уведомление',on_click=test,disabled=not control),
        ft.FilledButton('Сохранить на устройстве',on_click=save),ft.Divider(),
        ft.Text('Письма с сервера',weight=ft.FontWeight.BOLD),email,mailStatus,
        ft.Text('Типы выше применятся к письмам при отдельном сохранении на сервере. Для дедлайнов сервер использует последний отправленный личный снимок. Нужны работающий компьютер, интернет и почтовая настройка; Docker не требуется.'),
        ft.Text('События сообщества появляются на телефоне при открытом приложении и связи с сервером. Доставка на закрытый телефон через Wi-Fi не является FCM push.'),
        ft.TextButton('Проверить настройки писем',on_click=loadMail),
        ft.OutlinedButton('Сохранить настройки писем на сервере',on_click=saveMail)])
    dialog=ft.AlertDialog(title=ft.Text('Доставка уведомлений'),content=content,actions=[ft.TextButton('Закрыть',on_click=lambda e:page.close(dialog))])
    page.open(dialog)
