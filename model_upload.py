"""Одноразовая ограниченная передача личной модели из браузера."""
import secrets
import threading
import time
from starlette.responses import Response
from starlette.concurrency import run_in_threadpool
from account_gateway import getSessionUser
from api_client import ApiError
from model_import import MAX_MODEL_BYTES, decodeModel

_uploads = {}
_lock = threading.Lock()


def createModelUpload(user,filename):
    with _lock:
        for token in list(_uploads):
            if _uploads[token]['expires'] <= time.monotonic(): del _uploads[token]
        if len(_uploads)>=10: raise ValueError('Слишком много ожидающих моделей. Отмените загрузку или повторите через 10 минут')
        token = secrets.token_urlsafe(32)
        _uploads[token] = dict(userId=user['userId'],sessionToken=user['sessionToken'],filename=filename,
                              expires=time.monotonic()+600,state='pending',content=None)
        return token


def cancelModelUpload(token,userId):
    with _lock:
        if token in _uploads and _uploads[token]['userId']==userId: del _uploads[token]


def takeModelUpload(token,userId):
    with _lock:
        record = _uploads.get(token)
        if not record or record['userId']!=userId or record['expires']<=time.monotonic() or record['state']!='ready':
            raise ValueError('Модель ещё не загружена или срок загрузки истёк')
        del _uploads[token]
        return record['filename'],record['content']


async def uploadModel(request):
    token = request.path_params['ticket']
    with _lock:
        record = _uploads.get(token)
        if not record or record['state']!='pending' or record['expires']<=time.monotonic(): return Response(status_code=404)
        record['state']='uploading'
    try:
        user = await run_in_threadpool(getSessionUser,record['sessionToken'])
        if not user or user['userId']!=record['userId']: return Response(status_code=401)
        content = bytearray()
        async for chunk in request.stream():
            if len(content)+len(chunk)>MAX_MODEL_BYTES: return Response('Модель больше 3 МБ',status_code=413)
            content.extend(chunk)
        await run_in_threadpool(decodeModel,record['filename'],bytes(content))
        with _lock:
            if _uploads.get(token) is not record or record['expires']<=time.monotonic(): return Response(status_code=404)
            record.update(state='ready',content=bytes(content))
        return Response(status_code=200)
    except ValueError as error: return Response(str(error),status_code=400)
    except ApiError: return Response(status_code=503)
    finally:
        with _lock:
            if record['state']!='ready' and _uploads.get(token) is record: del _uploads[token]
