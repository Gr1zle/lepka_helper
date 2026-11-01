"""Короткий снимок для видимости кнопок. Разрешение действия всегда проверяет сервис."""
from time import monotonic
from moderation_gateway import ModerationClient
from account_gateway import getApiUrl


def panelAccess(page,user):
    if not user or user.get('offline'):return {'permissions':[]}
    key=(user.get('sessionToken'),getApiUrl())
    cached=page.session.get('adminAccess')
    if cached and cached['key']==key and monotonic()-cached['at']<10:return cached['access']
    access=ModerationClient(user).access()
    page.session.set('adminAccess',dict(key=key,at=monotonic(),access=access))
    return access
