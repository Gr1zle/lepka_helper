"""API сообщества. Личные действия используют только пользователя из Bearer-сессии."""
import base64
import binascii
import hashlib
import json

from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from starlette.responses import JSONResponse

import database as db
import post_service as posts
import workshop_service as workshops

MAX_COMMUNITY_BODY = 48 * 1024 * 1024


class CommunityBodyLimit:
    """Проверяем фактический поток до разбора JSON, включая запросы без Content-Length."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if (scope['type'] != 'http' or not scope['path'].startswith('/community/')
                or scope['method'] not in ('POST', 'PUT')):
            return await self.app(scope, receive, send)
        body = bytearray()
        while True:
            event = await receive()
            if event['type'] == 'http.disconnect':
                return
            if len(body) + len(event.get('body', b'')) > MAX_COMMUNITY_BODY:
                return await JSONResponse({'detail': 'Публикация слишком большая (до 48 МБ)'}, status_code=413)(scope, receive, send)
            body.extend(event.get('body', b''))
            if not event.get('more_body', False):
                break
        delivered = False

        async def replay():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {'type': 'http.request', 'body': bytes(body), 'more_body': False}
            return await receive()
        return await self.app(scope, replay, send)


class CommunityInput(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class PhotoInput(CommunityInput):
    name: str = Field(min_length=1, max_length=160)
    imageBase64: str = Field(max_length=14 * 1024 * 1024)


class PostInput(CommunityInput):
    titleText: str = Field(max_length=100)
    descriptionText: str = Field(max_length=2000)
    categoryName: str = Field(max_length=40)
    tagsText: str = Field(max_length=320)
    photos: list[PhotoInput] = Field(min_length=1, max_length=10)
    projectDetailsJson: str = Field(default='', max_length=131072)
    requestId: str = Field(min_length=16, max_length=80, pattern=r'^[a-zA-Z0-9-]+$')


class CommentInput(CommunityInput):
    commentText: str = Field(max_length=1000)


class ProgressInput(CommunityInput):
    lastStep: int
    completedSteps: list[int] = Field(max_length=100)
    checkedMaterials: list[int] = Field(max_length=60)
    isCompleted: bool = False


def requirePost(postId):
    with db.openDatabase() as connection:
        if connection.execute('SELECT postId FROM posts WHERE postId = ?', (postId,)).fetchone() is None:
            raise HTTPException(404, 'Работа не найдена')


def installCommunityRoutes(application, currentUser, optionalUser):
    application.add_middleware(CommunityBodyLimit)

    @application.get('/community/posts')
    def feed(user=Depends(optionalUser), mine: bool = False, searchMode: bool = False, offset: int = Query(0, ge=0),
             limit: int = Query(50, ge=1, le=100), searchText: str = Query('', max_length=120),
             categoryName: str = 'Все', levelName: str = 'Все', maxTime: int | None = Query(None, ge=1),
             onlyVideo: bool = False):
        if mine and user is None:
            raise HTTPException(401, 'Выполните вход')
        if searchMode or searchText or categoryName != 'Все' or levelName != 'Все' or maxTime is not None or onlyVideo:
            items = workshops.searchCommunityWorks(searchText, categoryName, levelName, maxTime, onlyVideo)
        else:
            items = posts.getUserPosts(user['userId']) if mine else posts.getCommunityPosts()
        if mine:
            items = [item for item in items if item['userId'] == user['userId']]
        total = len(items)
        items = items[offset:offset + limit]
        for item in items:
            item['isOwn'] = bool(user and item['userId'] == user['userId'])
            item['isLiked'] = bool(user and posts.checkPostLikedByUser(item['postId'], user['userId']))
        return {'data': {'items': items, 'hasMore': offset + len(items) < total}}

    @application.post('/community/posts')
    def publish(body: PostInput, user=Depends(currentUser)):
        payload = body.model_dump(exclude={'requestId'})
        payloadHash = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        with db.openDatabase() as connection:
            connection.execute('BEGIN IMMEDIATE')
            existing = connection.execute('SELECT payloadHash, postId FROM communityRequests WHERE userId = ? AND requestId = ?',
                                           (user['userId'], body.requestId)).fetchone()
            if existing:
                if existing['payloadHash'] != payloadHash:
                    raise HTTPException(409, 'Идентификатор отправки уже использован для другой работы')
                return {'message': 'Работа уже опубликована', 'data': existing['postId']}
            photos = []
            try:
                for item in body.photos:
                    image = base64.b64decode(item.imageBase64, validate=True)
                    if not 0 < len(image) <= 10 * 1024 * 1024:
                        raise ValueError('Фото должно быть не больше 10 МБ')
                    photos.append({'name': item.name, 'data': image})
            except (ValueError, binascii.Error):
                raise HTTPException(400, 'Некорректные данные фотографии') from None
            success, message, postId = posts.savePost(user['userId'], body.titleText, body.descriptionText,
                body.categoryName, body.tagsText, photos, body.projectDetailsJson, existingConnection=connection)
            if not success:
                raise HTTPException(400, message)
            connection.execute('INSERT INTO communityRequests VALUES (?, ?, ?, ?)',
                               (user['userId'], body.requestId, payloadHash, postId))
        return {'message': message, 'data': postId}

    @application.get('/community/photos/{photoId}')
    def photo(photoId: int):
        image = db.getPostPhoto(photoId)
        if image is None:
            raise HTTPException(404, 'Фото не найдено')
        return {'data': {'imageBase64': base64.b64encode(image).decode()}}

    @application.delete('/community/posts/{postId}')
    def deletePost(postId: int, user=Depends(currentUser)):
        if not posts.removePost(postId, user['userId']):
            raise HTTPException(404, 'Работа не найдена или недоступна')
        return {'data': True}

    @application.post('/community/posts/{postId}/like')
    def like(postId: int, user=Depends(currentUser)):
        liked, count = posts.togglePostLike(postId, user['userId'])
        if count is None:
            raise HTTPException(404, 'Работа недоступна')
        return {'data': {'isLiked': liked, 'likesCount': count}}

    @application.get('/community/posts/{postId}/comments')
    def comments(postId: int, user=Depends(optionalUser)):
        requirePost(postId)
        items = posts.getPostComments(postId)
        for item in items:
            item['isOwn'] = bool(user and item['userId'] == user['userId'])
        return {'data': items}

    @application.post('/community/posts/{postId}/comments')
    def comment(postId: int, body: CommentInput, user=Depends(currentUser)):
        success, message, commentId = posts.savePostComment(postId, user['userId'], body.commentText)
        if not success:
            raise HTTPException(400, message)
        return {'message': message, 'data': commentId}

    @application.put('/community/comments/{commentId}')
    def editComment(commentId: int, body: CommentInput, user=Depends(currentUser)):
        success, message = posts.editPostComment(commentId, user['userId'], body.commentText)
        if not success:
            raise HTTPException(400, message)
        return {'message': message, 'data': True}

    @application.delete('/community/comments/{commentId}')
    def deleteComment(commentId: int, user=Depends(currentUser)):
        if not posts.removePostComment(commentId, user['userId']):
            raise HTTPException(404, 'Комментарий недоступен')
        return {'data': True}

    @application.get('/community/workshops/{postId}')
    def workshop(postId: int, user=Depends(optionalUser)):
        item = workshops.getWorkshop(postId)
        if item is None:
            raise HTTPException(404, 'Мастер-класс недоступен')
        return {'data': item}

    @application.get('/community/workshops/{postId}/progress')
    def progress(postId: int, user=Depends(currentUser)):
        try:
            return {'data': workshops.getUserWorkshopState(user['userId'], postId)}
        except ValueError as error:
            raise HTTPException(404, str(error)) from None

    @application.put('/community/workshops/{postId}/progress')
    def saveProgress(postId: int, body: ProgressInput, user=Depends(currentUser)):
        try:
            return {'data': workshops.saveUserWorkshopState(user['userId'], postId, body.model_dump())}
        except ValueError as error:
            raise HTTPException(400, str(error)) from None
