"""Preferences for device notifications and optional server email delivery."""
from database import openDatabase
from lesson_library import requireOwner

DEFAULTS = dict(deviceEnabled=False, likes=True, comments=True, replies=True,
                awards=True, projects=True, learning=True, emailEnabled=False)


def getSettings(userId):
    with openDatabase() as c:
        requireOwner(c, userId)
        row = c.execute('SELECT * FROM deliverySettings WHERE userId=?', (userId,)).fetchone()
    return {key: bool(row[key]) if row else value for key, value in DEFAULTS.items()}


def saveSettings(userId, values):
    if not isinstance(values, dict) or set(values) != set(DEFAULTS) or any(type(v) is not bool for v in values.values()):
        raise ValueError('Некорректные настройки доставки')
    with openDatabase() as c:
        requireOwner(c, userId)
        old = c.execute('SELECT emailEnabled FROM deliverySettings WHERE userId=?', (userId,)).fetchone()
        if values['emailEnabled'] and (old is None or not old[0]):
            from datetime import datetime, timezone
            c.execute('INSERT OR REPLACE INTO notificationMailState VALUES (?,?)', (userId, datetime.now(timezone.utc).isoformat()))
        keys = list(DEFAULTS)
        c.execute('INSERT OR REPLACE INTO deliverySettings (userId,' + ','.join(keys) + ') VALUES (' + ','.join('?' for _ in range(len(keys)+1)) + ')',
                  (userId, *(int(values[k]) for k in keys)))
    return getSettings(userId)
