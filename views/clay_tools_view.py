import asyncio
import flet as ft
from clay_tools import calculateClay, ClayTimer
from ui_helpers import authenticatedAction, showMessage


def createClayTools(page, user):
    @authenticatedAction(page, user)
    def calculator(event):
        shape = ft.Dropdown(label='Форма', value='Объём', options=[ft.dropdown.Option(name) for name in ('Объём', 'Брусок', 'Шар', 'Цилиндр')])
        sizes = ft.Column()
        fields = []
        density = ft.TextField(label='Плотность, г/см³', value='1,6', keyboard_type=ft.KeyboardType.NUMBER)
        reserve = ft.TextField(label='Запас, %', value='10', keyboard_type=ft.KeyboardType.NUMBER)
        result = ft.Text(selectable=True)

        def change(event=None):
            labels = {'Объём': ['Объём, см³'], 'Брусок': ['Длина, см', 'Ширина, см', 'Высота, см'],
                      'Шар': ['Диаметр, см'], 'Цилиндр': ['Диаметр, см', 'Высота, см']}[shape.value]
            fields[:] = [ft.TextField(label=label, keyboard_type=ft.KeyboardType.NUMBER) for label in labels]
            sizes.controls = fields[:]
            result.value = ''
            page.update()

        @authenticatedAction(page, user)
        def compute(event):
            try:
                value = calculateClay(shape.value, [field.value for field in fields], density.value, reserve.value)
                result.value = f"Объём: {value['volume']:.2f} см³\nМасса: {value['mass']:.2f} г\nС запасом: {value['withReserve']:.2f} г"
                result.color = None
            except ValueError as error:
                result.value, result.color = str(error), ft.Colors.RED_400
            page.update()
            body.scroll_to(offset=-1,duration=200)

        shape.on_change = change
        body = ft.Column(scroll=ft.ScrollMode.AUTO, controls=[
                ft.Text('Размеры в сантиметрах. Для сложной фигурки можно ввести известный объём. Плотность уточните на упаковке материала.', size=13),
                shape, sizes, density, reserve, ft.ElevatedButton('Рассчитать массу', on_click=compute), result])
        dialog = ft.AlertDialog(modal=True, title=ft.Text('Количество пластилина'),
            content=ft.Container(width=360, height=430, content=body),
            actions=[ft.TextButton('Закрыть', on_click=lambda event: page.close(dialog))])
        change()
        page.open(dialog)

    @authenticatedAction(page, user)
    def timerDialog(event):
        timer = page.session.get('clayTimer')
        if timer is None or page.session.get('clayTimerOwner') != user.get('sessionToken'):
            timer = ClayTimer()
            page.session.set('clayTimer', timer)
            page.session.set('clayTimerOwner',user.get('sessionToken'))
        minutes = ft.TextField(label='Длительность, минуты', value=f'{timer.duration/60:g}', keyboard_type=ft.KeyboardType.NUMBER)
        display = ft.Text(timer.display(), size=36, text_align=ft.TextAlign.CENTER)
        status = ft.Text()
        started = {'value': timer.deadline is not None or timer.remaining != timer.duration}
        minutes.disabled = started['value']

        @authenticatedAction(page, user)
        def start(event):
            try:
                timer.start(None if started['value'] else minutes.value)
                started['value'] = True
                status.value = 'Идёт отсчёт'
                minutes.disabled = True
            except ValueError as error:
                status.value = str(error)
            page.update()

        @authenticatedAction(page, user)
        def pause(event):
            timer.pause()
            status.value = 'Пауза'
            display.value = timer.display()
            page.update()

        @authenticatedAction(page, user)
        def reset(event):
            timer.reset()
            started['value'] = False
            minutes.disabled = False
            display.value, status.value = timer.display(), 'Таймер сброшен'
            page.update()

        dialog = ft.AlertDialog(modal=True, title=ft.Text('Таймер для сушки / запекания'),
            content=ft.Container(width=340, content=ft.Column(tight=True, controls=[minutes, display, status,
                ft.Row(wrap=True, controls=[ft.ElevatedButton('Старт / продолжить', on_click=start),
                    ft.TextButton('Пауза', on_click=pause), ft.TextButton('Сброс', on_click=reset)]),
                ft.Text('Закрытие этого окна не останавливает отсчёт. После полного закрытия приложения таймер сбрасывается. Фоновое системное уведомление не настроено.', size=12)])),
            actions=[ft.TextButton('Закрыть', on_click=lambda event: page.close(dialog))])

        async def tick():
            while dialog.open and dialog in page.overlay:
                current = page.session.get('currentUser') or {}
                if current.get('sessionToken') != user.get('sessionToken'):
                    return
                display.value = timer.display()
                if started['value'] and timer.seconds() == 0:
                    status.value = 'Время вышло'
                page.update()
                await asyncio.sleep(0.5)

        page.open(dialog)
        page.run_task(tick)

    return ft.Row(wrap=True, controls=[ft.TextButton('Количество пластилина', icon=ft.Icons.SCALE, on_click=calculator),
                                       ft.TextButton('Таймер', icon=ft.Icons.TIMER_OUTLINED, on_click=timerDialog)])
