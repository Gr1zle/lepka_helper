"""Личный календарь и локальные напоминания. Фоновой push-доставки нет."""
import calendar
from datetime import date, datetime
from database import openDatabase

PLANNER_FILTERS = ('Месяц', 'Просрочены', 'Ближайшие 7 дней', 'Без срока', 'Все активные', 'Завершённые')
REMINDER_LABELS = {'2': 'Дедлайн через 2 дня', '1': 'Дедлайн завтра',
                   '0': 'Дедлайн сегодня', 'overdue': 'Дедлайн прошёл'}


def parseDeadline(value):
    try:
        return datetime.strptime(value, '%d.%m.%Y').date() if value else None
    except (ValueError, TypeError):
        return None  # Историческая некорректная дата не ломает календарь.


def plannerProjects(userId, today=None):
    today = today or date.today()
    with openDatabase() as connection:
        records = connection.execute('''SELECT p.projectId,p.projectName,p.categoryName,
            p.deadlineDate,p.progressPercent FROM projects p JOIN users u ON u.userId=p.userId
            WHERE p.userId=? AND u.isBlocked=0 AND u.roleName!='deleted' ''', (userId,)).fetchall()
    result = []
    for record in records:
        item = dict(record)
        deadline = parseDeadline(item['deadlineDate'])
        days = (deadline-today).days if deadline else None
        complete = item['progressPercent'] >= 100
        status = ('Завершён' if complete else 'Проверьте дату' if item['deadlineDate'] and not deadline
                  else 'Без срока' if deadline is None else 'Просрочен' if days < 0
                  else 'Сегодня' if days == 0 else 'Завтра' if days == 1 else f'Через {days} дн.')
        result.append({**item, 'deadline': deadline, 'daysLeft': days, 'complete': complete, 'status': status})
    return sorted(result, key=lambda item: (item['deadline'] or date.max, item['projectId']))


def monthPlan(userId, year, month, filterName='Месяц', selectedDay=None, today=None):
    if type(year) is not int or type(month) is not int or not 1 <= year <= 9999 or not 1 <= month <= 12:
        raise ValueError('Укажите существующий месяц и год')
    if filterName not in PLANNER_FILTERS:
        raise ValueError('Выберите фильтр сроков')
    if selectedDay is not None and (type(selectedDay) is not int or not 1 <= selectedDay <= calendar.monthrange(year, month)[1]):
        raise ValueError('Такого дня нет в выбранном месяце')
    items = plannerProjects(userId, today)
    active = [item for item in items if not item['complete']]
    inMonth = [item for item in active if item['deadline'] and (item['deadline'].year,item['deadline'].month)==(year,month)]
    counts = {}
    for item in inMonth:
        day = item['deadline'].day
        counts[day] = counts.get(day,0)+1
    if filterName == 'Месяц':
        filtered = [item for item in inMonth if selectedDay is None or item['deadline'].day == selectedDay]
    elif filterName == 'Просрочены': filtered = [item for item in active if item['daysLeft'] is not None and item['daysLeft'] < 0]
    elif filterName == 'Ближайшие 7 дней': filtered = [item for item in active if item['daysLeft'] is not None and 0 <= item['daysLeft'] <= 7]
    elif filterName == 'Без срока': filtered = [item for item in active if item['deadline'] is None]
    elif filterName == 'Завершённые': filtered = [item for item in items if item['complete']]
    else: filtered = active
    return {'items': filtered, 'counts': counts, 'weeks': calendar.Calendar(firstweekday=0).monthdayscalendar(year,month),
            'active': len(active), 'overdue': sum(item['daysLeft'] is not None and item['daysLeft'] < 0 for item in active),
            'undated': sum(item['deadline'] is None for item in active)}


def syncProjectReminders(userId, enabled=True, today=None):
    if type(enabled) is not bool: raise ValueError('Некорректная настройка напоминаний')
    today = today or date.today()
    with openDatabase() as connection:
        connection.execute('BEGIN IMMEDIATE')
        owner = connection.execute("SELECT userId FROM users WHERE userId=? AND isBlocked=0 AND roleName!='deleted'", (userId,)).fetchone()
        if owner is None: return []
        # Удалённый, завершённый проект или изменённый дедлайн больше не должен напоминать о старом сроке.
        connection.execute('''DELETE FROM projectReminders WHERE userId=? AND NOT EXISTS (
            SELECT 1 FROM projects p WHERE p.projectId=projectReminders.projectId AND p.userId=projectReminders.userId
            AND p.progressPercent<100 AND p.deadlineDate=projectReminders.deadlineDate)''', (userId,))
        if not enabled: return []
        projects = connection.execute('SELECT projectId,deadlineDate FROM projects WHERE userId=? AND progressPercent<100', (userId,)).fetchall()
        candidates = []
        for item in projects:
            deadline = parseDeadline(item['deadlineDate'])
            if deadline is None: continue
            days = (deadline-today).days
            if days > 2: continue
            kind = str(days) if days >= 0 else 'overdue'
            candidates.append((days if days >= 0 else 100000+abs(days),item['projectId'],item,kind))
        # Стабильный набор: вытеснённые при большом числе проектов записи не создаются заново при каждом открытии.
        for _, _, item, kind in sorted(candidates,key=lambda row:row[:2])[:100]:
            connection.execute('''INSERT OR IGNORE INTO projectReminders
                (userId,projectId,deadlineDate,kind,generatedDate) VALUES (?,?,?,?,?)''',
                (userId,item['projectId'],item['deadlineDate'],kind,today.isoformat()))
        connection.execute('''DELETE FROM projectReminders WHERE userId=? AND reminderId NOT IN (
            SELECT reminderId FROM projectReminders WHERE userId=? ORDER BY generatedDate DESC,reminderId DESC LIMIT 100)''', (userId,userId))
        rows = connection.execute('''SELECT r.*,p.projectName FROM projectReminders r
            JOIN projects p ON p.projectId=r.projectId AND p.userId=r.userId WHERE r.userId=?
            ORDER BY r.generatedDate DESC,r.reminderId DESC''', (userId,)).fetchall()
    return [{**dict(row), 'label': REMINDER_LABELS[row['kind']]} for row in rows]


def markProjectRemindersRead(userId, reminderId=None):
    with openDatabase() as connection:
        cursor = connection.execute('''UPDATE projectReminders SET isRead=1 WHERE userId=?
            AND (? IS NULL OR reminderId=?) AND EXISTS (
                SELECT 1 FROM users WHERE userId=? AND isBlocked=0 AND roleName!='deleted')''',
                (userId,reminderId,reminderId,userId))
        return cursor.rowcount
