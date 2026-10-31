"""Статистика по дате последнего завершения; старые даты не выдумываются."""
from datetime import datetime, timezone
from database import openDatabase


def getProjectStatistics(userId, year=None, month=None):
    now = datetime.now(timezone.utc)
    year, month = now.year if year is None else year, now.month if month is None else month
    if type(year) is not int or type(month) is not int or not 1 <= year <= 9999 or not 1 <= month <= 12:
        raise ValueError('Некорректный месяц или год')
    with openDatabase() as connection:
        records = connection.execute('SELECT progressPercent, completedAt FROM projects WHERE userId=?', (userId,)).fetchall()
    complete = [row for row in records if row['progressPercent'] >= 100]
    prefix = f'{year:04d}-{month:02d}'
    return {'total': len(records), 'completed': len(complete), 'active': len(records)-len(complete),
            'month': sum(bool(row['completedAt'] and row['completedAt'].startswith(prefix)) for row in complete),
            'year': sum(bool(row['completedAt'] and row['completedAt'].startswith(f'{year:04d}-')) for row in complete),
            'undated': sum(not row['completedAt'] for row in complete), 'period': f'{month:02d}.{year}'}
