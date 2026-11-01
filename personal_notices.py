"""Личные события устройства: дедлайны и обучение. Доставка при открытии приложения."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import hashlib
import json
from database import openDatabase
from lesson_library import requireOwner
from lesson_service import getLessonById, normalizeLessonState
from project_planner import syncProjectReminders, markProjectRemindersRead


def nowUtc():
    return datetime.now(timezone.utc)


def instant(value):
    parsed = datetime.fromisoformat(value)
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def settings(userId):
    with openDatabase() as c:
        requireOwner(c,userId)
        row=c.execute('SELECT * FROM personalNoticeSettings WHERE userId=?',(userId,)).fetchone()
    return dict(row) if row else dict(userId=userId,projectsEnabled=1,lessonsEnabled=1,resumeDays=3)


def saveSettings(userId,projects,lessons,days):
    if type(projects) is not bool or type(lessons) is not bool or type(days) is not int or not 1<=days<=30:
        raise ValueError('Выберите типы событий и интервал от 1 до 30 дней')
    with openDatabase() as c:
        requireOwner(c,userId)
        c.execute('INSERT OR REPLACE INTO personalNoticeSettings VALUES (?,?,?,?)',(userId,int(projects),int(lessons),days))


def syncLearning(userId,enabled=True,now=None):
    now=now or nowUtc(); prefs=settings(userId)
    with openDatabase() as c:
        c.execute('BEGIN IMMEDIATE');requireOwner(c,userId)
        rows=c.execute('SELECT * FROM lessonProgress WHERE userId=?',(userId,)).fetchall()
        validResume=set();eligibleResume=set()
        for row in rows:
            lesson=getLessonById(row['lessonId'])
            if not lesson:continue
            try:
                state=normalizeLessonState(lesson,json.loads(row['stateJson']))
                updated=instant(row['updatedAt'])
            except (ValueError,TypeError,KeyError):continue
            key=hashlib.sha256((str(row['lessonId'])+row['updatedAt']+row['stateJson']).encode()).hexdigest()
            started=state['completedSteps'] or state['checkedMaterials'] or state['lastStep']>0
            kind='complete' if state['isCompleted'] else 'resume'
            if kind=='complete':key='completed:'+str(row['lessonId'])
            eligible=state['isCompleted'] or (started and now-updated>=timedelta(days=prefs['resumeDays']))
            if kind=='resume' and started:
                validResume.add(key)
                if eligible:eligibleResume.add(key)
            if enabled and prefs['lessonsEnabled'] and eligible:
                c.execute('INSERT OR IGNORE INTO learningNotices(userId,lessonId,kind,eventKey,createdAt) VALUES (?,?,?,?,?)',
                          (userId,row['lessonId'],kind,key,now.isoformat()))
        for row in c.execute("SELECT noticeId,eventKey FROM learningNotices WHERE userId=? AND kind='resume'",(userId,)).fetchall():
            if row['eventKey'] not in validResume:c.execute('DELETE FROM learningNotices WHERE noticeId=?',(row['noticeId'],))
        c.execute('DELETE FROM learningNotices WHERE userId=? AND noticeId NOT IN (SELECT noticeId FROM learningNotices WHERE userId=? ORDER BY noticeId DESC LIMIT 100)',(userId,userId))
        rows=c.execute('SELECT * FROM learningNotices WHERE userId=? ORDER BY noticeId DESC',(userId,)).fetchall()
    if not enabled or not prefs['lessonsEnabled']:return []
    return [dict(row) for row in rows if (row['kind']!='resume' or row['eventKey'] in eligibleResume)
            and (not row['snoozedUntil'] or instant(row['snoozedUntil'])<=now)]


def personalItems(userId,enabled=None,now=None):
    if enabled is None:
        with openDatabase() as c:
            requireOwner(c,userId)
            enabled=bool(c.execute('SELECT notificationsEnabled FROM users WHERE userId=?',(userId,)).fetchone()[0])
    now=now or nowUtc();prefs=settings(userId)
    projects=syncProjectReminders(userId,enabled and bool(prefs['projectsEnabled']),today=now.astimezone(ZoneInfo('Europe/Moscow')).date())
    result=[dict(noticeId='project:'+str(r['reminderId']),source='projects',kind='deadline',title=r['projectName'],
                 preview=r['label']+' · '+r['deadlineDate'],createdAt=r['generatedDate'],isRead=r['isRead'],projectId=r['projectId']) for r in projects]
    for row in syncLearning(userId,enabled,now):
        lesson=getLessonById(row['lessonId'])
        if lesson:
            result.append(dict(noticeId='lesson:'+str(row['noticeId']),source='learning',kind=row['kind'],title=lesson['title'],
                preview='Урок завершён. Можно выбрать следующий.' if row['kind']=='complete' else 'Продолжите урок с сохранённого этапа.',
                createdAt=row['createdAt'],isRead=row['isRead'],lessonId=row['lessonId']))
    return result


def readPersonal(userId,noticeId=None):
    with openDatabase() as c:
        requireOwner(c,userId)
        if noticeId is None:
            c.execute('UPDATE learningNotices SET isRead=1 WHERE userId=?',(userId,))
        elif noticeId.startswith('lesson:'):
            c.execute('UPDATE learningNotices SET isRead=1 WHERE userId=? AND noticeId=?',(userId,int(noticeId.split(':')[1])))
    if noticeId is None or noticeId.startswith('project:'):
        markProjectRemindersRead(userId,None if noticeId is None else int(noticeId.split(':')[1]))


def snoozeLesson(userId,noticeId,days,now=None):
    if type(days) is not int or days not in (1,7) or not noticeId.startswith('lesson:'):
        raise ValueError('Отложить можно учебное напоминание на 1 или 7 дней')
    until=((now or nowUtc())+timedelta(days=days)).isoformat()
    with openDatabase() as c:
        requireOwner(c,userId)
        c.execute("UPDATE learningNotices SET snoozedUntil=? WHERE userId=? AND noticeId=? AND kind='resume'",(until,userId,int(noticeId.split(':')[1])))
