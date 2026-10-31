"""Ограниченная одноразовая загрузка JSON с проверкой сессии."""
import secrets
import threading
import time
from starlette.responses import Response
from starlette.concurrency import run_in_threadpool
from account_gateway import getSessionUser
from api_client import ApiError
from project_archive import MAX_ARCHIVE_BYTES, decodeProject

_uploads = {}
_lock = threading.Lock()


def createProjectUpload(user):
    with _lock:
        for key in list(_uploads):
            if _uploads[key]['expires'] <= time.monotonic():
                del _uploads[key]
        if len(_uploads) >= 10:
            raise ValueError('Слишком много ожидающих файлов. Отмените загрузку или повторите через 10 минут')
        token = secrets.token_urlsafe(32)
        _uploads[token] = dict(expires=time.monotonic()+600, userId=user['userId'], sessionToken=user['sessionToken'], state='pending', content=None)
        return token


def cancelProjectUpload(token, userId):
    with _lock:
        record = _uploads.get(token)
        if record and record['userId'] == userId:
            del _uploads[token]


def takeProjectUpload(token, userId):
    with _lock:
        record = _uploads.get(token)
        if not record or record['userId'] != userId or record['expires'] <= time.monotonic() or record['state'] != 'ready':
            raise ValueError('Файл ещё не загружен или срок загрузки истёк')
        del _uploads[token]
        return record['content']


async def uploadProject(request):
    token = request.path_params['ticket']
    with _lock:
        record = _uploads.get(token)
        if not record or record['state'] != 'pending' or record['expires'] <= time.monotonic():
            return Response(status_code=404)
        record['state'] = 'uploading'
    try:
        user = await run_in_threadpool(getSessionUser, record['sessionToken'])
        if not user or user['userId'] != record['userId']:
            return Response(status_code=401)
        content = bytearray()
        async for chunk in request.stream():
            if len(content)+len(chunk) > MAX_ARCHIVE_BYTES:
                return Response('Файл больше 20 МБ', status_code=413)
            content.extend(chunk)
        await run_in_threadpool(decodeProject, bytes(content))
        with _lock:
            if _uploads.get(token) is not record or record['expires'] <= time.monotonic():
                return Response(status_code=404)
            record.update(content=bytes(content), state='ready')
        return Response(status_code=200)
    except ValueError as error:
        return Response(str(error), status_code=400)
    except ApiError:
        return Response(status_code=503)
    finally:
        with _lock:
            if record['state'] != 'ready' and _uploads.get(token) is record:
                del _uploads[token]
