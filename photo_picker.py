"""Одна фотография: общий выбор и загрузка для аватара и этапа проекта."""
from pathlib import Path
from urllib.parse import urlsplit

import flet as ft

from photo_service import MAX_PHOTO_BYTES, PHOTO_EXTENSIONS, preparePhoto
from photo_upload import createPhotoUpload, cancelPhotoUpload, takePhotoUpload
from ui_helpers import authenticatedAction, isWebClient, showMessage


def createPhotoPicker(page, user, onSelected, label='Добавить фото'):
    pending = {'token': None}
    status = ft.Text('JPG, PNG или WebP, до 10 МБ', size=12)

    def reset():
        if pending['token']:
            cancelPhotoUpload(pending['token'], user['userId'])
        pending['token'] = None
        chooseButton.disabled = False
        cancelButton.visible = False
        status.value = 'JPG, PNG или WebP, до 10 МБ'

    def deliver(photo):
        success, message = onSelected(photo)
        status.value = 'Фотография сохранена' if success else 'Фотография не сохранена'
        showMessage(page, message, not success)

    @authenticatedAction(page, user)
    def picked(event):
        if getattr(event, 'control', picker) is not picker:
            return
        if not event.files:
            return
        try:
            if len(event.files) != 1:
                raise ValueError('Выберите одну фотографию')
            if pending['token']:
                raise ValueError('Дождитесь загрузки или отмените её')
            file = event.files[0]
            if file.name.rsplit('.', 1)[-1].lower() not in PHOTO_EXTENSIONS:
                raise ValueError('Разрешены фотографии JPG, PNG или WebP')
            if not 0 < file.size <= MAX_PHOTO_BYTES:
                raise ValueError('Фотография должна быть не больше 10 МБ')
            if isWebClient(page):
                address = urlsplit(page.url)
                scheme = {'ws': 'http', 'wss': 'https'}.get(address.scheme, address.scheme)
                if scheme not in ('http', 'https') or not address.netloc:
                    raise ValueError('Не удалось определить адрес загрузки')
                token = createPhotoUpload(user, file.name)
                pending['token'] = token
                status.value = 'Загрузка фотографии…'
                chooseButton.disabled = True
                cancelButton.visible = True
                picker.upload([ft.FilePickerUploadFile(name=file.name, id=getattr(file, 'id', None),
                    upload_url=f'{scheme}://{address.netloc}/photo-uploads/{token}')])
            else:
                # Веб-запуск помечен сервером: браузер не может передать путь ПК.
                with Path(file.path).open('rb') as source:
                    photo = preparePhoto(file.name, source.read(MAX_PHOTO_BYTES + 1))
                deliver(photo)
        except (ValueError, OSError, TypeError) as error:
            reset()
            showMessage(page, str(error) if isinstance(error, ValueError) else 'Не удалось прочитать фото', True)
        finally:
            page.update()

    @authenticatedAction(page, user)
    def uploaded(event):
        if getattr(event, 'control', picker) is not picker:
            return
        token = pending['token']
        if not token:
            return
        try:
            if event.error:
                raise ValueError('Загрузка не удалась. Проверьте фотографию и выберите её заново')
            if event.progress == 1:
                photo = takePhotoUpload(token, user['userId'])
                reset()
                deliver(photo)
        except ValueError as error:
            reset()
            showMessage(page, str(error), True)
        finally:
            page.update()

    picker = ft.FilePicker(on_result=picked, on_upload=uploaded)
    picker.data = {'singlePhotoPicker': True, 'cancelUpload': reset}

    @authenticatedAction(page, user)
    def choose(event):
        nonlocal picker
        # Один активный одиночный выборщик: смена этапа отменяет старую загрузку.
        for control in list(page.overlay):
            if isinstance(control, ft.FilePicker) and isinstance(control.data, dict) and control.data.get('singlePhotoPicker'):
                control.data['cancelUpload']()
                page.overlay.remove(control)
        picker = ft.FilePicker(on_result=picked, on_upload=uploaded)
        picker.data = {'singlePhotoPicker': True, 'cancelUpload': reset}
        page.overlay.append(picker)
        page.update()
        picker.pick_files(allow_multiple=False, file_type=ft.FilePickerFileType.CUSTOM,
                          allowed_extensions=list(PHOTO_EXTENSIONS), dialog_title=label)

    @authenticatedAction(page, user)
    def cancel(event):
        reset()
        page.update()

    chooseButton = ft.OutlinedButton(label, icon=ft.Icons.ADD_PHOTO_ALTERNATE, on_click=choose,
                                     disabled=user is None)
    cancelButton = ft.TextButton('Отменить загрузку фото', on_click=cancel, visible=False)
    return ft.Column(controls=[chooseButton, status, cancelButton], spacing=4)
