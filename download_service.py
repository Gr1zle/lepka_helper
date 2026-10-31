"""Короткоживущие одноразовые ссылки на PNG, без доступа к файлам пользователя."""
import secrets
import threading
import time

from starlette.responses import Response
from starlette.concurrency import run_in_threadpool
from account_gateway import getSessionUser
from api_client import ApiError

_tickets = {}
_lock = threading.Lock()
DOWNLOAD_SECONDS = 600
MAX_DOWNLOADS = 100
MAX_PENDING_BYTES = 64 * 1024 * 1024


def createDownload(content, filename='lepka-recipe.png', mediaType='image/png', owner=None):
    if (filename, mediaType) not in (('lepka-recipe.png', 'image/png'), ('lepka-project.json', 'application/json')):
        raise ValueError('Неподдерживаемый формат скачивания')
    with _lock:
        now = time.monotonic()
        for token in list(_tickets):
            if _tickets[token][0] <= now:
                del _tickets[token]
        if len(_tickets) >= MAX_DOWNLOADS or sum(len(item[1]) for item in _tickets.values()) + len(content) > MAX_PENDING_BYTES:
            raise ValueError('Слишком много ожидающих загрузок. Повторите через 10 минут')
        token = secrets.token_urlsafe(32)
        _tickets[token] = (now + DOWNLOAD_SECONDS, bytes(content), filename, mediaType, dict(owner) if owner else None)
        return token


async def downloadRecipe(request):
    token = request.path_params['ticket']
    with _lock:
        record = _tickets.get(token) if request.method == 'HEAD' else _tickets.pop(token, None)
    if record is None or record[0] <= time.monotonic():
        return Response('Ссылка недействительна или истекла', status_code=404, media_type='text/plain')
    if record[4]:
        try:
            user = await run_in_threadpool(getSessionUser, record[4]['sessionToken'])
        except ApiError:
            return Response(status_code=503)
        if user is None or user['userId'] != record[4]['userId']:
            return Response(status_code=401)
    return Response(b'' if request.method == 'HEAD' else record[1], media_type=record[3], headers={
        'Content-Length': str(len(record[1])),
        'Content-Disposition': f'attachment; filename="{record[2]}"',
        'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
    })
