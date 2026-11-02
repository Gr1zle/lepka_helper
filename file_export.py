"""Byte-oriented export: Android documents, browser downloads, atomic desktop files."""
import base64
import json
import os
from pathlib import Path
import tempfile
import flet as ft
from download_service import createDownload
from ui_helpers import isWebClient,showMessage,authenticatedAction,confirmAction


def writeAtomic(path,content,overwrite=False):
    path=Path(path)
    if not isinstance(content,bytes) or not content:raise ValueError('Нет данных для экспорта')
    if str(path).startswith(('content:', 'file:')):raise ValueError('Адрес документа требует системного сохранения Android')
    if path.exists() and path.stat().st_size>0 and not overwrite:raise FileExistsError(str(path))
    temporary=None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent,prefix='.lepka-export-',delete=False) as output:
            temporary=Path(output.name);written=output.write(content)
            output.flush();os.fsync(output.fileno())
        if written!=len(content) or temporary.stat().st_size!=len(content):raise OSError('Неполная запись файла')
        if path.exists() and path.stat().st_size>0 and not overwrite:raise FileExistsError(str(path))
        os.replace(temporary,path);temporary=None
        return len(content)
    finally:
        if temporary is not None:temporary.unlink(missing_ok=True)


def exportBytes(page,user,content,name,mime):
    if not isinstance(content,bytes) or not content:raise ValueError('Нет данных для экспорта')
    from views.project_transfer import androidClient,webAddress
    guard=lambda fn:authenticatedAction(page,user)(fn) if user else fn
    token=(page.session.get('currentUser') or {}).get('sessionToken')
    def active():return (page.session.get('currentUser') or {}).get('sessionToken')==token
    if isWebClient(page):
        ticket=createDownload(content,name,mime,user)
        page.launch_url(webAddress(page)+'/downloads/'+ticket,web_window_name='_self')
        showMessage(page,'Файл передан браузеру для скачивания');return
    if androidClient(page):
        from secure_device import getProtectedSession
        def finished(record):
            if not active():return
            try:
                if not record.get('ok'):raise OSError()
                result=json.loads(record.get('value') or '{}')
                if result.get('cancelled'):return
                if result.get('bytes')!=len(content):raise OSError()
                showMessage(page,'Файл сохранён · '+str(len(content))+' байт')
            except (OSError,ValueError):showMessage(page,'Не удалось записать и проверить файл. Выберите другую папку',True)
        getProtectedSession(page).requestUi('fileSave',json.dumps(dict(name=name,mime=mime,base64=base64.b64encode(content).decode())),finished)
        return
    @guard
    def selected(event):
        if not event.path:return
        path=Path(event.path)
        suffix=Path(name).suffix
        if path.suffix.lower()!=suffix:path=path.with_suffix(suffix)
        def save(overwrite=False):
            try:writeAtomic(path,content,overwrite);showMessage(page,'Файл сохранён')
            except OSError:showMessage(page,'Не удалось сохранить файл в выбранную папку. Исходный файл не изменён',True)
        try:needsConfirmation=path.exists() and path.stat().st_size>0
        except OSError:
            showMessage(page,'Не удалось открыть выбранную папку для сохранения',True);return
        if needsConfirmation:
            confirmAction(page,'Заменить существующий файл?',path.name,guard(lambda:save(True)))
        else:save()
    picker=ft.FilePicker(on_result=selected);page.overlay.append(picker);page.update()
    picker.save_file(file_name=name,file_type=ft.FilePickerFileType.CUSTOM,allowed_extensions=[Path(name).suffix[1:]])
