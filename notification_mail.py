"""Opt-in mail spool. Disabled unless the server operator explicitly enables it."""
from datetime import datetime, timezone, timedelta
import hashlib
import json
import os
import time
from database import openDatabase
from delivery_settings import getSettings
from project_planner import parseDeadline
from mail_service import sendNotification, MailDeliveryError
import social_feed


def enabled():
    return os.environ.get('LEPKA_NOTIFICATION_MAIL_ENABLED') == '1'


def deadlineEvents(c,userId,now):
    events=[]
    vault=c.execute('SELECT snapshotJson FROM personalVault WHERE userId=?',(userId,)).fetchone()
    if not vault:return events
    for item in json.loads(vault[0])['projects']:
        archive=item['archive'];project=archive['project']
        if item.get('completedAt') or (archive['steps'] and all(s['completed'] for s in archive['steps'])):continue
        deadline=parseDeadline(project['deadline'])
        days=(deadline-now.astimezone(timezone(timedelta(hours=3))).date()).days if deadline else None
        if days not in (0,1,2):continue
        key=hashlib.sha256(json.dumps([project['name'],project['deadline'],item['createdAt']],ensure_ascii=False).encode()).hexdigest()
        events.append((f'project:{key}:{days}','Дедлайн проекта',project['name']+': '+project['deadline']))
    return events


def collect(now=None):
    now = now or datetime.now(timezone.utc)
    with openDatabase() as c:
        c.execute('BEGIN IMMEDIATE')
        owners = c.execute("""SELECT u.userId,u.email,s.since FROM users u JOIN deliverySettings d ON d.userId=u.userId
            JOIN notificationMailState s ON s.userId=u.userId WHERE d.emailEnabled=1 AND u.notificationsEnabled=1
            AND u.isBlocked=0 AND u.roleName!='deleted' AND u.emailVerified=1""").fetchall()
        for owner in owners:
            prefs = dict(c.execute('SELECT * FROM deliverySettings WHERE userId=?', (owner['userId'],)).fetchone())
            since = datetime.fromisoformat(owner['since'])
            events = []
            kinds = dict(like='likes', comment='comments', reply='replies', award='awards')
            # The bounded current in-app stream is the source, not cached client data.
            for offset in (0, 50):
                for row in social_feed.listing(c, owner['userId'], offset):
                    created = datetime.fromisoformat(row['createdAt'])
                    if created.tzinfo is None: created = created.replace(tzinfo=timezone.utc)
                    if created < since or not prefs[kinds[row['kind']]]: continue
                    labels = dict(like='Вашу работу оценили', comment='Новый комментарий', reply='Ответ на комментарий', award='Призовое место в конкурсе')
                    events.append(('social:'+str(row['noticeId']), labels[row['kind']], row['title']))
            if prefs['projects']: events.extend(deadlineEvents(c, owner['userId'], now))
            for key, subject, body in events:
                mailId=hashlib.sha256(json.dumps([owner['userId'],owner['email'],key]).encode()).hexdigest()
                c.execute('''INSERT OR IGNORE INTO notificationMailQueue(mailId,userId,email,eventKey,subject,body,createdAt)
                    VALUES (?,?,?,?,?,?,?)''',(mailId,owner['userId'],owner['email'],key,subject[:100],body[:500],now.timestamp()))
        # Sent receipts must survive future collection to prevent redelivery.
        # Old events are outside the delivery horizon; advance the scan floor before pruning receipts.
        floor=(now-timedelta(days=7)).isoformat()
        c.execute('UPDATE notificationMailState SET since=? WHERE since<?',(floor,floor))
        c.execute("DELETE FROM notificationMailQueue WHERE createdAt<? AND state IN ('sent','cancelled')",((now-timedelta(days=7)).timestamp(),))


def deliver(send=sendNotification, clock=time.time):
    if not enabled(): return 0
    collect(); delivered=0
    for _ in range(25):
        now=clock()
        with openDatabase() as c:
            c.execute('BEGIN IMMEDIATE')
            row=c.execute("SELECT * FROM notificationMailQueue WHERE state='pending' AND nextAttempt<=? AND leaseUntil<=? ORDER BY createdAt,mailId LIMIT 1",(now,now)).fetchone()
            if row is None: break
            row=dict(row)
            owner=c.execute("SELECT email,notificationsEnabled,isBlocked,roleName FROM users WHERE userId=?",(row['userId'],)).fetchone()
            prefs=c.execute('SELECT * FROM deliverySettings WHERE userId=?',(row['userId'],)).fetchone()
            kind=row['eventKey'].split(':')[0]
            allowed=owner and prefs and prefs['emailEnabled'] and owner['notificationsEnabled'] and not owner['isBlocked'] and owner['roleName']!='deleted' and owner['email']==row['email']
            if allowed and kind=='project':
                allowed=bool(prefs['projects']) and any(key==row['eventKey'] for key,_,_ in deadlineEvents(c,row['userId'],datetime.fromtimestamp(now,timezone.utc)))
            if allowed and kind=='social':
                candidates=social_feed.listing(c,row['userId'],0)+social_feed.listing(c,row['userId'],50)
                event=next((e for e in candidates if 'social:'+str(e['noticeId'])==row['eventKey']),None)
                allowed=bool(event and prefs[dict(like='likes',comment='comments',reply='replies',award='awards')[event['kind']]])
            if not allowed:
                c.execute("UPDATE notificationMailQueue SET state='cancelled' WHERE mailId=?",(row['mailId'],));continue
            # Resend idempotency keys expire after 24h: never blindly retry beyond that window.
            if row['attempts'] and now-row['createdAt']>=23*3600:
                c.execute("UPDATE notificationMailQueue SET state='review',lastError='Требуется проверка доставки' WHERE mailId=?",(row['mailId'],));continue
            c.execute('UPDATE notificationMailQueue SET leaseUntil=?,attempts=attempts+1 WHERE mailId=?',(now+60,row['mailId']))
        try:
            send(row['email'],row['subject'],row['body'],row['mailId'])
        except MailDeliveryError:
            with openDatabase() as c:
                c.execute("UPDATE notificationMailQueue SET leaseUntil=0,nextAttempt=?,lastError='Не удалось отправить письмо' WHERE mailId=?",(now+min(3600,30*2**min(row['attempts'],7)),row['mailId']))
        else:
            with openDatabase() as c:
                c.execute("UPDATE notificationMailQueue SET state='sent',leaseUntil=0,lastError='' WHERE mailId=?",(row['mailId'],))
            delivered+=1
    return delivered


def status(userId):
    with openDatabase() as c:
        counts={r['state']:r['n'] for r in c.execute('SELECT state,COUNT(*) AS n FROM notificationMailQueue WHERE userId=? GROUP BY state',(userId,))}
    return dict(configured=enabled() and bool(os.environ.get('LEPKA_MAIL_API_KEY') and os.environ.get('LEPKA_MAIL_FROM')), counts=counts)
