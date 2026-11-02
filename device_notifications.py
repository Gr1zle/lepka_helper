"""Build an account-scoped Android alarm plan. No remote token in native data."""
from datetime import datetime, timedelta, timezone
import asyncio
import hashlib
import json
import logging
import time
from database import openDatabase
from delivery_settings import getSettings
from personal_notices import settings as personalSettings
from project_planner import plannerProjects
from lesson_service import getLessonById, normalizeLessonState

MOSCOW = timezone(timedelta(hours=3))


def ownerKey(user):
    return hashlib.sha256(json.dumps([user['userId'], user.get('apiUrl', ''), user.get('serverUserId')], separators=(',', ':')).encode()).hexdigest()


def buildPlan(user, now=None):
    now = now or datetime.now(timezone.utc)
    prefs = getSettings(user['userId']); personal = personalSettings(user['userId'])
    with openDatabase() as c:
        owner = c.execute("SELECT notificationsEnabled FROM users WHERE userId=? AND isBlocked=0 AND roleName!='deleted'", (user['userId'],)).fetchone()
        progress = c.execute('SELECT * FROM lessonProgress WHERE userId=?', (user['userId'],)).fetchall()
    if not owner or not owner[0] or not prefs['deviceEnabled']:
        return dict(owner=ownerKey(user), items=[], enabled=False)
    items = []
    def add(key, title, body, when, route):
        # Skip old reminders rather than generating a storm after a long absence.
        if when < now - timedelta(days=1): return
        items.append(dict(key=key, title=title[:50], body=body[:200], at=int(max(when.timestamp(), now.timestamp()+5)*1000), route=route))
    if prefs['projects'] and personal['projectsEnabled']:
        for project in plannerProjects(user['userId'], today=now.astimezone(MOSCOW).date()):
            if project['complete'] or not project['deadline']: continue
            for days in (2, 1, 0):
                when = datetime.combine(project['deadline']-timedelta(days=days), datetime.min.time(), MOSCOW)+timedelta(hours=10)
                add(f"project:{project['projectId']}:{project['deadlineDate']}:{days}", 'Дедлайн проекта',
                    f"{project['projectName']}: " + ('сегодня' if days == 0 else 'завтра' if days == 1 else 'через 2 дня'), when, '/planner')
    if prefs['learning'] and personal['lessonsEnabled']:
        for row in progress:
            lesson = getLessonById(row['lessonId'])
            if not lesson: continue
            try:
                state = normalizeLessonState(lesson, json.loads(row['stateJson']))
                updated = datetime.fromisoformat(row['updatedAt'])
                if updated.tzinfo is None: updated = updated.replace(tzinfo=timezone.utc)
            except (ValueError, TypeError, KeyError): continue
            if state['isCompleted'] or not (state['completedSteps'] or state['checkedMaterials'] or state['lastStep']): continue
            when = updated + timedelta(days=personal['resumeDays'])
            with openDatabase() as c:
                snoozes = c.execute("SELECT snoozedUntil FROM learningNotices WHERE userId=? AND lessonId=? AND kind='resume' AND snoozedUntil IS NOT NULL", (user['userId'], row['lessonId'])).fetchall()
            for snooze in snoozes:
                try: when = max(when, datetime.fromisoformat(snooze[0]))
                except (ValueError, TypeError): pass
            add(f"lesson:{row['lessonId']}:{row['updatedAt']}:{personal['resumeDays']}:{when.isoformat()}", 'Продолжить обучение', lesson['title'], when, '/learning')
    return dict(owner=ownerKey(user), items=sorted(items, key=lambda i: (i['at'], i['key']))[:100], enabled=True)


def bridge(page):
    from device_session import nativeClient
    if not nativeClient(page): return None
    from secure_device import getProtectedSession
    control = getProtectedSession(page)
    data = page.data if isinstance(page.data, dict) else {}
    page.data = {**data, 'notificationsAttached': True}
    return control


def clear(page):
    if not isinstance(page.data, dict) or not page.data.get('notificationsAttached'): return
    page.data={**page.data,'notificationGeneration':page.data.get('notificationGeneration',0)+1}
    control = bridge(page)
    if control: control.call('notifyClear')


def startNotificationMonitor(page):
    from device_session import nativeClient
    if not nativeClient(page): return
    data = page.data if isinstance(page.data, dict) else {}
    if data.get('notificationMonitor'): return
    page.data = {**data, 'notificationMonitor': True}
    async def monitor():
        previous = None; nextSocial = 0
        while True:
            try:
                user = page.session.get('currentUser')
                generation=page.data.get('notificationGeneration',0)
                def active():
                    return page.session.get('currentUser')==user and page.data.get('notificationGeneration',0)==generation
                valid = user and (not user.get('sessionExpiresAt') or user['sessionExpiresAt'] > time.time())
                control = bridge(page)
                if not control: return
                plan = await asyncio.to_thread(buildPlan, user) if valid else dict(owner='', items=[])
                # Timestamp clamping must not cause identical alarms to be replaced each tick.
                signature = json.dumps([generation, plan['owner'], [(i['key'], i['title'], i['body']) for i in plan['items']]], sort_keys=True)
                if signature != previous:
                    if valid and page.session.get('currentUser') != user: continue
                    response=await asyncio.to_thread(control.call, 'notifySync', json.dumps(plan, ensure_ascii=False), active)
                    if response is None:continue
                    previous = signature
                if valid and time.monotonic() >= nextSocial:
                    nextSocial = time.monotonic()+30
                    prefs = getSettings(user['userId'])
                    if prefs['deviceEnabled'] and plan.get('enabled'):
                        from challenge_gateway import ChallengeClient
                        notices = await asyncio.to_thread(ChallengeClient(user).notices, 0, 'all', True)
                        names = dict(like='likes', comment='comments', reply='replies', award='awards')
                        for item in notices[:20]:
                            if not prefs.get(names.get(item['kind'], ''), False): continue
                            if page.session.get('currentUser') != user: break
                            await asyncio.to_thread(control.call, 'notifyShow', json.dumps(dict(owner=plan['owner'], key='social:'+str(item['noticeId']), title='Событие сообщества', body=(item.get('title') or '')[:200], route='/notices'), ensure_ascii=False), active)
                opened = await asyncio.to_thread(control.call, 'notifyOpen') if valid else None
                if opened and valid:
                    target = json.loads(opened)
                    if target.get('owner') == plan['owner']:
                        route = target.get('route')
                        if route == '/learning': page.session.set('homeTab', 1); page.go('/home')
                        elif route == '/planner': page.go('/planner')
                        elif route == '/notices':
                            page.go('/home')
                            callback=page.session.get('openNoticeCenterCallback')
                            if callable(callback): await asyncio.to_thread(callback, None)
            except Exception:
                logging.getLogger(__name__).warning('Не удалось обновить доставку уведомлений; будет повтор')
            await asyncio.sleep(15)
    page.run_task(monitor)
