"""JSON: одноразовая веб-загрузка, предварительный просмотр и новая копия."""
from pathlib import Path
from urllib.parse import urlsplit
import sqlite3
import flet as ft
from project_archive import MAX_ARCHIVE_BYTES, decodeProject, exportProject, importProject
from project_upload import createProjectUpload, cancelProjectUpload, takeProjectUpload
from download_service import createDownload
from project_backups import saveBackup, listBackups, readBackup, deleteBackup
from ui_helpers import authenticatedAction, isWebClient, showMessage, confirmAction


def androidClient(page):
    try:
        return not isWebClient(page) and page.platform == ft.PagePlatform.ANDROID
    except ValueError:
        return False


def webAddress(page):
    address = urlsplit(page.url)
    scheme = {'ws': 'http', 'wss': 'https'}.get(address.scheme, address.scheme)
    if scheme not in ('http', 'https') or not address.netloc:
        raise ValueError('Не удалось определить адрес приложения')
    return f'{scheme}://{address.netloc}'


def createProjectExport(page, user, projectId):
    @authenticatedAction(page, user)
    def export(event):
        try:
            content = exportProject(projectId, user['userId'])
            if isWebClient(page):
                address = webAddress(page)
                ticket = createDownload(content, 'lepka-project.json', 'application/json', user)
                page.launch_url(f'{address}/downloads/{ticket}', web_window_name='_self')
                showMessage(page, 'JSON проекта передан браузеру для скачивания')
                return
            if androidClient(page):
                saveBackup(user['userId'],content)
                showMessage(page,'JSON-копия сохранена. Для восстановления откройте «Копии в приложении»')
                return

            @authenticatedAction(page, user)
            def picked(event):
                if not event.path:
                    return
                try:
                    path = Path(event.path).with_suffix('.json')
                    with path.open('xb') as stream:
                        stream.write(content)
                    showMessage(page, 'JSON проекта сохранён')
                except FileExistsError:
                    showMessage(page, 'Файл уже существует. Выберите другое имя', True)
                except OSError:
                    showMessage(page, 'Не удалось сохранить JSON в выбранную папку', True)
            picker = ft.FilePicker(on_result=picked)
            page.overlay.append(picker)
            page.update()
            picker.save_file(file_name='lepka-project.json', file_type=ft.FilePickerFileType.CUSTOM, allowed_extensions=['json'])
        except (ValueError, OSError) as error:
            showMessage(page, str(error) if isinstance(error,ValueError) else 'Не удалось сохранить копию проекта', True)
    return ft.TextButton('Экспорт JSON', icon=ft.Icons.DOWNLOAD_OUTLINED, on_click=export)


def createProjectImport(page, user, onImported):
    pending = {'token': None}
    status = ft.Text('JSON до 20 МБ. Импорт создаст новый личный проект.', size=12)

    def reset(event=None):
        if pending['token']:
            cancelProjectUpload(pending['token'], user['userId'])
        pending['token'] = None
        choose.disabled, cancel.visible = False, False
        status.value = 'JSON до 20 МБ. Импорт создаст новый личный проект.'
        page.update()

    def preview(content):
        data = decodeProject(content)
        state = {'done':False}
        @authenticatedAction(page, user)
        def confirm(event):
            if state['done']:
                return
            state['done'] = True
            try:
                importProject(user['userId'], content)
                page.close(dialog)
                onImported()
                showMessage(page, 'Создан новый проект из JSON')
                page.update()
            except (ValueError,sqlite3.Error) as error:
                state['done'] = False
                showMessage(page, str(error) if isinstance(error,ValueError) else 'Не удалось сохранить импортированный проект', True)
        dialog = ft.AlertDialog(modal=True, title=ft.Text('Импорт проекта'),
            content=ft.Column(tight=True, controls=[ft.Text(data['project']['projectName']),
                ft.Text(f"Этапов: {len(data['steps'])}; фотографий: {sum(step['image'] is not None for step in data['steps'])}; рецептов: {len(data['mixtures'])}"),
                ft.Text('Будет создана новая копия. Существующие проекты сохранятся.')]),
            actions=[ft.TextButton('Отмена', on_click=lambda event: page.close(dialog)),
                     ft.ElevatedButton('Импортировать проект', on_click=confirm)])
        page.open(dialog)

    @authenticatedAction(page, user)
    def selected(event):
        if getattr(event, 'control', picker) is not picker or not event.files:
            return
        try:
            if pending['token']:
                raise ValueError('Дождитесь загрузки или отмените её')
            if len(event.files) != 1:
                raise ValueError('Выберите один JSON-файл')
            file = event.files[0]
            if not file.name.lower().endswith('.json') or not 0 < file.size <= MAX_ARCHIVE_BYTES:
                raise ValueError('Выберите JSON-файл не больше 20 МБ')
            if isWebClient(page):
                address = webAddress(page)
                pending['token'] = createProjectUpload(user)
                choose.disabled, cancel.visible = True, True
                status.value = 'Загрузка JSON…'
                picker.upload([ft.FilePickerUploadFile(name=file.name, id=getattr(file, 'id', None),
                    upload_url=f"{address}/project-uploads/{pending['token']}")])
            else:
                with Path(file.path).open('rb') as stream:
                    preview(stream.read(MAX_ARCHIVE_BYTES+1))
        except (ValueError, OSError, TypeError) as error:
            reset()
            showMessage(page, str(error) if isinstance(error, ValueError) else 'Не удалось прочитать файл', True)
        page.update()

    @authenticatedAction(page, user)
    def uploaded(event):
        if getattr(event, 'control', picker) is not picker or not pending['token']:
            return
        try:
            if event.error:
                raise ValueError('Не удалось загрузить JSON. Проверьте файл и повторите')
            if event.progress == 1:
                content = takeProjectUpload(pending['token'], user['userId'])
                reset()
                preview(content)
        except ValueError as error:
            reset()
            showMessage(page, str(error), True)

    picker = ft.FilePicker(on_result=selected, on_upload=uploaded)

    @authenticatedAction(page, user)
    def select(event):
        if picker not in page.overlay:
            page.overlay.append(picker)
            page.update()
        picker.pick_files(allow_multiple=False, file_type=ft.FilePickerFileType.CUSTOM, allowed_extensions=['json'])

    choose = ft.ElevatedButton('Импорт JSON', icon=ft.Icons.UPLOAD_FILE_OUTLINED, on_click=select)
    cancel = ft.TextButton('Отменить загрузку', visible=False, on_click=reset)

    @authenticatedAction(page,user)
    def openBackups(event=None):
        entries = []
        for name in listBackups(user['userId']):
            @authenticatedAction(page,user)
            def restore(event,name=name):
                try:
                    content = readBackup(user['userId'],name)
                    page.close(dialog)
                    preview(content)
                except (OSError,ValueError):
                    showMessage(page,'Не удалось прочитать копию',True)

            @authenticatedAction(page,user)
            def remove(event,name=name):
                page.close(dialog)
                @authenticatedAction(page,user)
                def confirmed():
                    try:
                        deleteBackup(user['userId'],name)
                        openBackups()
                    except (OSError,ValueError):
                        showMessage(page,'Не удалось удалить копию',True)
                confirmAction(page,'Удалить JSON-копию?','Личный проект останется в приложении.',confirmed)
            entries.append(ft.Row(controls=[ft.TextButton(name,on_click=restore,expand=True),
                ft.IconButton(icon=ft.Icons.DELETE_OUTLINE,tooltip='Удалить копию',on_click=remove)]))
        dialog = ft.AlertDialog(modal=True,title=ft.Text('Копии в приложении'),
            content=ft.Container(width=360,height=320,content=ft.ListView(controls=entries or [ft.Text('Сохранённых копий пока нет')])),
            actions=[ft.TextButton('Закрыть',on_click=lambda event:page.close(dialog))])
        page.open(dialog)

    return ft.Column(controls=[ft.Row(wrap=True, controls=[choose, cancel,
        ft.TextButton('Копии в приложении',on_click=openBackups,visible=androidClient(page))]), status])
