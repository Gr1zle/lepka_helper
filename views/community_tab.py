"""Лента, фотографии и комментарии. Личные действия проверяют текущую сессию."""
import base64
from pathlib import Path
from urllib.parse import urlsplit

import flet as ft

from photo_service import MAX_PHOTO_BYTES, PHOTO_EXTENSIONS, preparePhoto
from photo_upload import createPhotoUpload, cancelPhotoUpload, takePhotoUpload
from post_service import POST_CATEGORIES
from ui_helpers import authenticatedAction, isWebClient, showMessage
from views.project_sharing import createPublishedProject
from community_gateway import CommunityClient, ownsItem
from ui_helpers import serverAction
from views.project_planner import createDeadlineSummary

PRIMARY_COLOR = '#FF6B6B'
SECONDARY_COLOR = '#4ECDC4'


def webAddress(page, path):
    address = urlsplit(page.url)
    scheme = {'ws': 'http', 'wss': 'https'}.get(address.scheme, address.scheme)
    if scheme not in ('http', 'https') or not address.netloc:
        raise ValueError('Не удалось определить адрес загрузки')
    return f'{scheme}://{address.netloc}{path}'


def createPhotoViewer(page, photoIds, client=None):
    client = client or CommunityClient(None)
    if not photoIds:
        return ft.Text('Фотография не добавлена в старой версии приложения', size=12)
    position = [0]
    image = ft.Image(height=230, fit=ft.ImageFit.CONTAIN, error_content=ft.Text('Фото недоступно'))
    counter = ft.Text()

    def render():
        photoId = photoIds[position[0]]
        if isWebClient(page) and not client.remote:
            image.src = webAddress(page, f'/post-photos/{photoId}')
        else:
            data = client.getPhoto(photoId)
            image.src_base64 = base64.b64encode(data).decode() if data else ''
        counter.value = f'Фото {position[0] + 1} из {len(photoIds)}'

    def move(delta):
        position[0] = (position[0] + delta) % len(photoIds)
        render()
        page.update()

    render()
    return ft.Column(controls=[image, ft.Row(alignment=ft.MainAxisAlignment.CENTER, controls=[
        ft.IconButton(icon=ft.Icons.CHEVRON_LEFT, tooltip='Предыдущее фото', visible=len(photoIds) > 1,
                      on_click=lambda event: move(-1)), counter,
        ft.IconButton(icon=ft.Icons.CHEVRON_RIGHT, tooltip='Следующее фото', visible=len(photoIds) > 1,
                      on_click=lambda event: move(1))])])


def createPostCard(page, postItem, currentUser, refreshCallback):
    client = CommunityClient(currentUser)
    postId = postItem['postId']
    deleted = postItem['isDeleted']
    comments = ft.Column(spacing=8)
    commentField = ft.TextField(label='Комментарий', multiline=True, max_lines=3, max_length=1000)

    def refreshComments():
        comments.controls.clear()
        for item in client.getComments(postId):
            actions = []
            if ownsItem(item, currentUser):
                @authenticatedAction(page, currentUser)
                def delete(event, commentId=item['commentId']):
                    success = client.deleteComment(commentId)
                    refreshComments()
                    showMessage(page, 'Комментарий удалён' if success else 'Комментарий недоступен', not success)
                    page.update()

                @authenticatedAction(page, currentUser)
                def edit(event, comment=dict(item)):
                    field = ft.TextField(label='Текст комментария', value=comment['commentText'], multiline=True,
                                         max_length=1000)

                    @authenticatedAction(page, currentUser)
                    def save(event):
                        success, message = client.editComment(comment['commentId'], field.value)
                        if success:
                            page.close(dialog)
                            refreshComments()
                        showMessage(page, message, not success)
                        page.update()

                    dialog = ft.AlertDialog(title=ft.Text('Изменить комментарий'), content=field, actions=[
                        ft.TextButton('Отмена', on_click=lambda event: page.close(dialog)),
                        ft.ElevatedButton('Сохранить комментарий', on_click=save)])
                    page.open(dialog)

                if not deleted:
                    actions.append(ft.IconButton(icon=ft.Icons.EDIT, tooltip='Изменить комментарий (до 30 минут)', on_click=edit))
                actions.append(ft.IconButton(icon=ft.Icons.DELETE, tooltip='Удалить свой комментарий', on_click=delete))
            comments.controls.append(ft.Column(controls=[
                ft.Text(item['nickname'], weight=ft.FontWeight.BOLD, size=12),
                ft.Text(item['commentText']), ft.Row(controls=actions, wrap=True)]))
        if not comments.controls:
            comments.controls.append(ft.Text('Комментариев пока нет.', size=12))

    @authenticatedAction(page, currentUser)
    def like(event):
        _, count = client.toggleLike(postId)
        if count is None:
            showMessage(page, 'Публикация недоступна', True)
            return
        refreshCallback()
        page.update()

    @authenticatedAction(page, currentUser)
    def deletePost(event):
        @authenticatedAction(page, currentUser)
        def confirm(event):
            success = client.deletePost(postId)
            page.close(dialog)
            refreshCallback()
            showMessage(page, 'Публикация удалена' if success else 'Публикация недоступна', not success)
            page.update()
        dialog = ft.AlertDialog(modal=True, title=ft.Text('Удалить публикацию?'),
            content=ft.Text('Фотографии, лайки и комментарии этой работы будут удалены.'), actions=[
                ft.TextButton('Отмена', on_click=lambda event: page.close(dialog)),
                ft.ElevatedButton('Удалить работу', on_click=confirm)])
        page.open(dialog)

    @authenticatedAction(page, currentUser)
    def addComment(event):
        success, message, _ = client.saveComment(postId, commentField.value)
        if success:
            commentField.value = ''
            refreshComments()
        showMessage(page, message, not success)
        page.update()

    controls = [ft.Text(postItem['titleText'], size=18, weight=ft.FontWeight.BOLD),
                ft.Text(f"Автор: {postItem['nickname']} · {postItem['categoryName']}", size=12),
                createPhotoViewer(page, postItem.get('photoIds', []), client) if not deleted else ft.Text('Работа удалена пользователем'),
                ft.Text(postItem['descriptionText'])]
    if postItem['tagsText']:
        controls.append(ft.Text('Теги: ' + postItem['tagsText'], size=12))
    if not deleted:
        controls.append(createPublishedProject(page, postId, currentUser))
    if not deleted:
        liked = client.isLiked(postItem)
        actions = [ft.TextButton(f"{'❤️' if liked else '🤍'} {postItem['likesCount']}",
                    tooltip='Поставить или снять лайк', disabled=currentUser is None, on_click=like)]
        if ownsItem(postItem, currentUser):
            actions.append(ft.TextButton('Удалить', on_click=deletePost))
        controls.append(ft.Row(controls=actions, wrap=True))
    refreshComments()
    controls.extend([ft.Divider(), ft.Text('Комментарии', weight=ft.FontWeight.BOLD), comments])
    if currentUser and not deleted:
        controls.extend([commentField, ft.ElevatedButton('Отправить комментарий', on_click=addComment)])
    elif not deleted:
        controls.append(ft.Text('Войдите, чтобы поставить лайк или оставить комментарий', size=12))
    return ft.Card(content=ft.Container(padding=14, content=ft.Column(controls=controls, spacing=10)))


def createHomeTab(page, currentUser, nickname):
    client = CommunityClient(currentUser)
    posts = ft.Column(spacing=12)
    title = ft.TextField(label='Название работы', max_length=100)
    description = ft.TextField(label='Описание', multiline=True, min_lines=3, max_lines=5, max_length=2000)
    category = ft.Dropdown(label='Категория', value=POST_CATEGORIES[0],
                           options=[ft.dropdown.Option(value) for value in POST_CATEGORIES])
    tags = ft.TextField(label='Теги через запятую', hint_text='До 10 тегов, каждый 2–30 символов')
    photos = []
    pending = {}
    previews = ft.Column()
    status = ft.Text('Добавьте от 1 до 10 фотографий: JPG, PNG или WebP, до 10 МБ каждая', size=12)
    onlyMine = ft.Checkbox(label='Только мои работы', visible=currentUser is not None, value=False)

    def feedAction(callback):
        return authenticatedAction(page, currentUser)(callback) if currentUser else serverAction(page)(callback)

    @feedAction
    def refreshPosts(event=None):
        items = client.getPosts(mine=bool(onlyMine.value and currentUser))
        posts.controls = [createPostCard(page, item, currentUser, refreshPosts) for item in items]
        if not items:
            posts.controls = [ft.Text('Публикаций пока нет.')]

    def refreshPhotos():
        previews.controls.clear()
        for photo in photos:
            @authenticatedAction(page, currentUser)
            def remove(event, selected=photo):
                photos.remove(selected)
                refreshPhotos()
                page.update()
            previews.controls.append(ft.Row(wrap=True, controls=[
                ft.Image(src_base64=base64.b64encode(photo['data']).decode(), width=100, height=90,
                         fit=ft.ImageFit.CONTAIN), ft.Text(photo['name'], width=130),
                ft.IconButton(icon=ft.Icons.CLOSE, tooltip='Убрать фото из публикации', on_click=remove)]))
        status.value = f'Готово фото: {len(photos)} из 10. Загружается: {len(pending)}'
        publish.disabled = bool(pending)
        pick.disabled = bool(pending)

    @authenticatedAction(page, currentUser)
    def cancel(event):
        for token in pending.values():
            cancelPhotoUpload(token, currentUser['userId'])
        pending.clear()
        refreshPhotos()
        page.update()

    @authenticatedAction(page, currentUser)
    def uploaded(event):
        token = pending.get(event.file_name)
        if not token:
            return
        if event.error:
            cancelPhotoUpload(token, currentUser['userId'])
            pending.pop(event.file_name)
            showMessage(page, 'Не удалось загрузить фото. Проверьте формат/размер и добавьте его снова', True)
        elif event.progress == 1:
            pending.pop(event.file_name)
            try:
                photos.append(takePhotoUpload(token, currentUser['userId']))
            except ValueError as error:
                cancelPhotoUpload(token, currentUser['userId'])
                showMessage(page, str(error), True)
        refreshPhotos()
        page.update()

    @authenticatedAction(page, currentUser)
    def picked(event):
        if not event.files:
            return
        try:
            if pending:
                raise ValueError('Дождитесь загрузки или отмените её')
            if len(photos) + len(event.files) > 10:
                raise ValueError('Допускается не больше 10 фотографий')
            names = [file.name for file in event.files]
            if len(set(names)) != len(names):
                raise ValueError('Выберите файлы с разными именами')
            for file in event.files:
                if file.name.rsplit('.', 1)[-1].lower() not in PHOTO_EXTENSIONS:
                    raise ValueError('Разрешены фотографии JPG, PNG или WebP')
                if not 0 < file.size <= MAX_PHOTO_BYTES:
                    raise ValueError('Каждая фотография должна быть не больше 10 МБ')
            if isWebClient(page):
                uploads = []
                for file in event.files:
                    token = createPhotoUpload(currentUser, file.name)
                    pending[file.name] = token
                    uploads.append(ft.FilePickerUploadFile(name=file.name, id=getattr(file, 'id', None),
                                    upload_url=webAddress(page, '/photo-uploads/' + token)))
                picker.upload(uploads)
            else:
                prepared = []
                for file in event.files:
                    # Путь получен от системного FilePicker, не из поля формы.
                    with Path(file.path).open('rb') as source:
                        prepared.append(preparePhoto(file.name, source.read(MAX_PHOTO_BYTES + 1)))
                photos.extend(prepared)
            refreshPhotos()
        except (ValueError, OSError, TypeError) as error:
            for token in pending.values():
                cancelPhotoUpload(token, currentUser['userId'])
            pending.clear()
            refreshPhotos()
            showMessage(page, str(error) if isinstance(error, ValueError) else 'Не удалось прочитать фото', True)
        page.update()

    picker = ft.FilePicker(on_result=picked, on_upload=uploaded, data='post-photo-picker')

    @authenticatedAction(page, currentUser)
    def choose(event):
        page.overlay[:] = [control for control in page.overlay if not (
            isinstance(control, ft.FilePicker) and control.data == 'post-photo-picker')]
        page.overlay.append(picker)
        page.update()
        picker.pick_files(allow_multiple=True, file_type=ft.FilePickerFileType.CUSTOM,
                          allowed_extensions=list(PHOTO_EXTENSIONS))

    @authenticatedAction(page, currentUser)
    def publishPost(event):
        if pending:
            showMessage(page, 'Дождитесь загрузки всех фотографий', True)
            return
        success, message, _ = client.publishPost(title.value, description.value,
                                       category.value, tags.value, photos)
        if success:
            title.value, description.value, tags.value = '', '', ''
            photos.clear()
            refreshPhotos()
            refreshPosts()
        showMessage(page, message, not success)
        page.update()

    pick = ft.OutlinedButton('Добавить фото', icon=ft.Icons.ADD_PHOTO_ALTERNATE, on_click=choose)
    publish = ft.ElevatedButton('Опубликовать', icon=ft.Icons.PUBLISH, on_click=publishPost, height=48)
    onlyMine.on_change = lambda event: (refreshPosts(), page.update())
    refreshPosts()
    return ft.ListView(expand=True, padding=16, spacing=12, controls=[
        ft.Text(f'Привет, {nickname}!', size=22, weight=ft.FontWeight.BOLD),
        createDeadlineSummary(page,currentUser),
        ft.Text('Работы пользователей сервера' if client.remote else
                'Работы на этом устройстве. Для общего сообщества подключите сервер.', size=12),
        ft.Container(padding=18, border_radius=18, bgcolor=PRIMARY_COLOR, content=ft.Column(controls=[
            ft.Text('Идея для практики', color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD),
            ft.Text('Слепи милого котика', size=22, color=ft.Colors.WHITE),
            ft.Text('Начните с простого урока котика на вкладке «Поиск» или создайте свою идею.',
                    color=ft.Colors.WHITE)])),
        ft.Card(visible=currentUser is not None, content=ft.Container(padding=16, content=ft.Column(controls=[
            ft.Text('Опубликовать работу', size=18, weight=ft.FontWeight.BOLD), title, description, category,
            tags, pick, status, previews, ft.TextButton('Отменить загрузку', on_click=cancel), publish]))),
        ft.Text('Лента сообщества', size=18, weight=ft.FontWeight.BOLD), onlyMine,
        ft.OutlinedButton('Обновить ленту', on_click=lambda event: (refreshPosts(), page.update())), posts])


def createMyWorksButton(page, currentUser, onChanged=None):
    client = CommunityClient(currentUser)
    @authenticatedAction(page, currentUser)
    def openWorks(event):
        items = ft.Column(scroll=ft.ScrollMode.AUTO, width=340, height=420)

        @authenticatedAction(page, currentUser)
        def refresh():
            postItems = client.getPosts(mine=True)
            items.controls = [createPostCard(page, item, currentUser, refresh)
                              for item in postItems] or [ft.Text('Пока нет ваших работ.')]
            if onChanged:
                onChanged(postItems)
        refresh()
        dialog = ft.AlertDialog(title=ft.Text('Мои работы'), content=items,
                               actions=[ft.TextButton('Закрыть', on_click=lambda event: page.close(dialog))])
        page.open(dialog)
    return ft.OutlinedButton('Мои работы', icon=ft.Icons.PHOTO_LIBRARY, on_click=openWorks,
                              disabled=currentUser is None)


def createLocalWorksButton(page, currentUser):
    client = CommunityClient(currentUser)

    @authenticatedAction(page, currentUser)
    def openLocal(event):
        items = ft.Column(scroll=ft.ScrollMode.AUTO, width=340, height=420)
        for item in client.getLocalPosts():
            @authenticatedAction(page, currentUser)
            def export(event, localId=item['postId']):
                success, message, _ = client.exportLocalPost(localId)
                showMessage(page, message, not success)
            items.controls.append(ft.Card(content=ft.Container(padding=12, content=ft.Column(controls=[
                ft.Text(item['titleText'], weight=ft.FontWeight.BOLD), ft.Text(item['descriptionText']),
                ft.Text(f"Фотографий: {len(item['photoIds'])}"),
                ft.OutlinedButton('Отправить эту работу на сервер', on_click=export)]))))
        if not items.controls:
            items.controls.append(ft.Text('Сохранённых местных публикаций этого аккаунта нет.'))
        dialog = ft.AlertDialog(title=ft.Text('Публикации на этом устройстве'), content=items,
            actions=[ft.TextButton('Закрыть', on_click=lambda event: page.close(dialog))])
        page.open(dialog)
    return ft.OutlinedButton('Публикации на этом устройстве', visible=client.remote and currentUser is not None,
                              icon=ft.Icons.PHONE_ANDROID, on_click=openLocal)
