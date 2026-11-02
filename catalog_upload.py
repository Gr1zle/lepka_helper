"""Single-use bounded web uploads, validated by the current catalogue authority."""
import secrets
import threading
import time
from starlette.responses import Response
from starlette.concurrency import run_in_threadpool
from catalog_client import CatalogClient
from learning_catalog import MAX_ASSET
from api_client import ApiError,getApiUrl

_pending={};_lock=threading.Lock()


def createUpload(user,name,kind):
    with _lock:
        for key in list(_pending):
            if _pending[key]['expires']<=time.monotonic():del _pending[key]
        if len(_pending)>=20:raise ValueError('Слишком много загрузок. Подождите или отмените предыдущую')
        key=secrets.token_urlsafe(32)
        _pending[key]=dict(user=dict(user),name=name,kind=kind,apiUrl=getApiUrl(),state='pending',expires=time.monotonic()+600,result=None)
        return key


def cancelUpload(key,userId):
    with _lock:
        if key in _pending and _pending[key]['user']['userId']==userId:del _pending[key]


def takeUpload(key,userId):
    with _lock:
        row=_pending.get(key)
        if not row or row['user']['userId']!=userId or row['apiUrl']!=getApiUrl() or row['expires']<=time.monotonic() or row['state']!='ready':raise ValueError('Файл ещё не загружен или срок загрузки истёк')
        del _pending[key];return row['result']


async def upload(request):
    key=request.path_params['ticket']
    with _lock:
        row=_pending.get(key)
        if not row or row['state']!='pending' or row['apiUrl']!=getApiUrl() or row['expires']<=time.monotonic():return Response(status_code=404)
        row['state']='uploading'
    try:
        client=CatalogClient(row['user'])
        await run_in_threadpool(client.active)
        content=bytearray()
        async for chunk in request.stream():
            if len(content)+len(chunk)>MAX_ASSET:return Response(status_code=413)
            content.extend(chunk)
        result=await run_in_threadpool(client.upload,row['name'],row['kind'],bytes(content))
        with _lock:
            if _pending.get(key) is not row:return Response(status_code=404)
            row.update(state='ready',result=result)
        return Response(status_code=200)
    except ApiError as error:return Response(str(error),status_code=error.statusCode or 503)
    except ValueError as error:return Response(str(error),status_code=400)
    finally:
        with _lock:
            if row['state']!='ready' and _pending.get(key) is row:del _pending[key]
