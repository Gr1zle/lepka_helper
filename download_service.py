"""Короткоживущие одноразовые ссылки на PNG, без доступа к файлам пользователя."""
import secrets
import threading
import time

from starlette.responses import Response

_tickets = {}
_lock = threading.Lock()
DOWNLOAD_SECONDS = 600
MAX_DOWNLOADS = 100


def createDownload(content):
    with _lock:
        now = time.monotonic()
        for token in list(_tickets):
            if _tickets[token][0] <= now:
                del _tickets[token]
        if len(_tickets) >= MAX_DOWNLOADS:
            raise ValueError('Слишком много ожидающих загрузок. Повторите через 10 минут')
        token = secrets.token_urlsafe(32)
        _tickets[token] = (now + DOWNLOAD_SECONDS, bytes(content))
        return token


async def downloadRecipe(request):
    token = request.path_params['ticket']
    with _lock:
        record = _tickets.get(token) if request.method == 'HEAD' else _tickets.pop(token, None)
    if record is None or record[0] <= time.monotonic():
        return Response('Ссылка недействительна или истекла', status_code=404, media_type='text/plain')
    return Response(b'' if request.method == 'HEAD' else record[1], media_type='image/png', headers={
        'Content-Length': str(len(record[1])),
        'Content-Disposition': 'attachment; filename="lepka-recipe.png"',
        'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
    })
