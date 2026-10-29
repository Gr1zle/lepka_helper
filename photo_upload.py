"""Одноразовая загрузка фото из браузера. Черновики живут только в памяти."""
import secrets
import threading
import time

from starlette.concurrency import run_in_threadpool
from starlette.responses import Response

from account_gateway import getSessionUser
from api_client import ApiError
from database import getPostPhoto
from photo_service import MAX_PHOTO_BYTES, preparePhoto

_uploads = {}
_lock = threading.Lock()
UPLOAD_SECONDS = 600


def createPhotoUpload(user, name):
    with _lock:
        now = time.monotonic()
        for token in list(_uploads):
            if _uploads[token]['expires'] <= now:
                del _uploads[token]
        if len(_uploads) >= 100:
            raise ValueError('Слишком много загрузок. Повторите через 10 минут')
        token = secrets.token_urlsafe(32)
        _uploads[token] = {'expires': now + UPLOAD_SECONDS, 'userId': user['userId'],
                           'sessionToken': user['sessionToken'], 'name': name,
                           'state': 'pending', 'photo': None}
        return token


def cancelPhotoUpload(token, userId):
    with _lock:
        item = _uploads.get(token)
        if item and item['userId'] == userId:
            del _uploads[token]


def takePhotoUpload(token, userId):
    with _lock:
        item = _uploads.get(token)
        if not item or item['userId'] != userId or item['expires'] <= time.monotonic():
            raise ValueError('Загрузка недоступна или истекли 10 минут')
        if item['state'] != 'ready':
            raise ValueError('Дождитесь завершения загрузки фотографии')
        del _uploads[token]
        return item['photo']


async def uploadPhoto(request):
    token = request.path_params['ticket']
    with _lock:
        item = _uploads.get(token)
        if not item or item['expires'] <= time.monotonic() or item['state'] != 'pending':
            return Response(status_code=404)
        item['state'] = 'uploading'
    try:
        user = await run_in_threadpool(getSessionUser, item['sessionToken'])
        if user is None or user['userId'] != item['userId']:
            return Response(status_code=401)
        body = bytearray()
        async for chunk in request.stream():
            if len(body) + len(chunk) > MAX_PHOTO_BYTES:
                return Response('Фотография больше 10 МБ', status_code=413)
            body.extend(chunk)
        photo = await run_in_threadpool(preparePhoto, item['name'], bytes(body))
        with _lock:
            # Пользователь мог отменить загрузку во время чтения.
            if _uploads.get(token) is not item or item['expires'] <= time.monotonic():
                return Response(status_code=404)
            item['photo'] = photo
            item['state'] = 'ready'
        return Response(status_code=200)
    except ValueError as error:
        return Response(str(error), status_code=400)
    except ApiError:
        return Response('Сервер аккаунтов недоступен', status_code=503)
    finally:
        with _lock:
            if item['state'] != 'ready' and _uploads.get(token) is item:
                del _uploads[token]


async def publishedPhoto(request):
    data = await run_in_threadpool(getPostPhoto, request.path_params['photoId'])
    if data is None:
        return Response(status_code=404)
    return Response(data, media_type='image/jpeg', headers={
        'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
    })
