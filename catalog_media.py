"""Private cached video: short-lived web tickets with byte ranges, native files."""
import base64
import hashlib
from pathlib import Path
import re
import secrets
import threading
import time
from starlette.responses import Response
from starlette.concurrency import run_in_threadpool
from account_gateway import getSessionUser
from api_client import ApiError,getApiUrl
from app_paths import DATA_DIRECTORY

_tickets={};_lock=threading.Lock()


def videoTicket(user,asset):
    content=base64.b64decode(asset['contentBase64'],validate=True)
    with _lock:
        for key in list(_tickets):
            if _tickets[key]['expires']<time.monotonic():del _tickets[key]
        if sum(len(r['content']) for r in _tickets.values())+len(content)>32*1024*1024:raise ValueError('Закройте лишние видео и повторите через 10 минут')
        key=secrets.token_urlsafe(32)
        _tickets[key]=dict(user=dict(user),url=getApiUrl(),content=content,expires=time.monotonic()+600)
        return key


def nativeVideo(user,asset):
    scope=hashlib.sha256(f"{user['userId']}:{getApiUrl()}".encode()).hexdigest()
    folder=DATA_DIRECTORY/'catalog_media'/scope;folder.mkdir(parents=True,exist_ok=True)
    path=folder/(asset['assetId']+'.mp4')
    content=base64.b64decode(asset['contentBase64'],validate=True)
    # Only the active video needs a second filesystem copy beside the SQLite package.
    for old in folder.glob('*.mp4'):
        if old!=path:
            try:old.unlink()
            except OSError:pass
    if not path.exists() or path.read_bytes()!=content:path.write_bytes(content)
    return str(path)


async def media(request):
    with _lock:row=_tickets.get(request.path_params['ticket'])
    if not row or row['expires']<time.monotonic() or row['url']!=getApiUrl():return Response(status_code=404)
    try:user=await run_in_threadpool(getSessionUser,row['user']['sessionToken'])
    except ApiError:return Response(status_code=401)
    if not user or user['userId']!=row['user']['userId']:return Response(status_code=401)
    content=row['content'];length=len(content);start=0;end=length-1;status=200
    headers={'Accept-Ranges':'bytes','Cache-Control':'no-store'}
    value=request.headers.get('range')
    if value:
        match=re.fullmatch(r'bytes=(\d*)-(\d*)',value)
        if not match or not any(match.groups()):return Response(status_code=416,headers={'Content-Range':f'bytes */{length}'})
        first,last=match.groups()
        if first:start=int(first);end=min(int(last),length-1) if last else length-1
        else:start=max(0,length-int(last))
        if start>end or start>=length:return Response(status_code=416,headers={'Content-Range':f'bytes */{length}'})
        status=206;headers['Content-Range']=f'bytes {start}-{end}/{length}'
    headers['Content-Length']=str(end-start+1)
    return Response(b'' if request.method=='HEAD' else content[start:end+1],status_code=status,media_type='video/mp4',headers=headers)
