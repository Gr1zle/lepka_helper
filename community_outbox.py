"""Долговечная очередь без токенов; повторяется только под владельцем и его API."""
import json
import hashlib
import secrets
import threading
import time
from api_client import ApiError,apiRequest,getApiUrl
from database import openDatabase
from remote_account_cache import requireCachedUser

MAX_QUEUE_BYTES=64*1024*1024
_flushLock=threading.Lock()


def requireIdentity(user,apiUrl):
    if not user or not apiUrl or getApiUrl()!=apiUrl or type(user.get('serverUserId')) is not int:raise ApiError('Неверный аккаунт или адрес очереди',401)
    requireCachedUser(user['userId'],user.get('sessionToken'))


def serialize(payload):return json.dumps(payload,ensure_ascii=False,separators=(',',':'),allow_nan=False)


def enqueue(user,apiUrl,kind,payload,requestId=None):
    requireIdentity(user,apiUrl)
    if kind not in ('publication','like','comment'):raise ValueError('Неизвестный тип отправки')
    encoded=serialize(payload)
    digest=hashlib.sha256(encoded.encode()).hexdigest()
    requestId=requestId or secrets.token_hex(16)
    with openDatabase() as connection:
        connection.execute('BEGIN IMMEDIATE')
        existing=connection.execute('SELECT * FROM communityOutbox WHERE requestId=?',(requestId,)).fetchone()
        if existing:
            if existing['userId']!=user['userId'] or existing['apiUrl']!=apiUrl or existing['kind']!=kind or existing['payloadHash']!=digest:raise ValueError('Отправка уже существует с другими данными')
            return requestId
        count,size=connection.execute("SELECT COUNT(*),COALESCE(SUM(length(CAST(payloadJson AS BLOB))),0) FROM communityOutbox WHERE userId=? AND state!='done'",(user['userId'],)).fetchone()
        if count>=100 or size+len(encoded.encode())>MAX_QUEUE_BYTES:raise ValueError('Очередь заполнена: до 100 действий и 64 МБ. Отправьте или уберите старые действия')
        connection.execute('INSERT INTO communityOutbox(requestId,userId,apiUrl,serverUserId,kind,payloadJson,payloadHash,createdAt) VALUES (?,?,?,?,?,?,?,?)',
            (requestId,user['userId'],apiUrl,user['serverUserId'],kind,encoded,digest,time.time()))
        connection.execute("DELETE FROM communityOutbox WHERE userId=? AND state='done' AND requestId NOT IN (SELECT requestId FROM communityOutbox WHERE userId=? AND state='done' ORDER BY createdAt DESC LIMIT 100)",(user['userId'],user['userId']))
    return requestId


def entries(user,apiUrl,includeDone=False):
    with openDatabase() as connection:
        rows=connection.execute("SELECT * FROM communityOutbox WHERE userId=? AND apiUrl=? AND (? OR state!='done') ORDER BY createdAt,requestId",(user['userId'],apiUrl,int(includeDone))).fetchall()
    return [dict(row) for row in rows]


def result(user,apiUrl,requestId):
    with openDatabase() as connection:
        row=connection.execute('SELECT * FROM communityOutbox WHERE requestId=? AND userId=? AND apiUrl=?',(requestId,user['userId'],apiUrl)).fetchone()
    return dict(row) if row else None


def remove(user,apiUrl,requestId):
    with openDatabase() as connection:
        connection.execute("DELETE FROM communityOutbox WHERE requestId=? AND userId=? AND apiUrl=? AND state!='sending'",(requestId,user['userId'],apiUrl))


def lastLike(user,apiUrl,postId):
    for row in reversed(entries(user,apiUrl)):
        if row['kind']=='like' and row['state'] in ('pending','sending'):
            payload=json.loads(row['payloadJson'])
            if payload['postId']==postId:return payload['isLiked']
    return None


def flush(user,apiUrl,stillActive=lambda:True,force=False,limit=10):
    requireIdentity(user,apiUrl)
    if not _flushLock.acquire(blocking=False):return 0
    sent=0
    try:
        for _ in range(limit):
            if not stillActive():break
            requireIdentity(user,apiUrl)
            now=time.time();lease=secrets.token_hex(16)
            with openDatabase() as connection:
                connection.execute('BEGIN IMMEDIATE')
                connection.execute("UPDATE communityOutbox SET state='pending' WHERE userId=? AND apiUrl=? AND state='sending' AND leaseUntil<?",(user['userId'],apiUrl,now))
                row=connection.execute("SELECT * FROM communityOutbox WHERE userId=? AND apiUrl=? AND state IN ('pending','sending') ORDER BY createdAt,requestId LIMIT 1",(user['userId'],apiUrl)).fetchone()
                if not row or row['state']=='sending' or (not force and row['nextAttemptAt']>now):break
                if row['serverUserId']!=user['serverUserId']:raise ApiError('Владелец очереди изменился',401)
                connection.execute("UPDATE communityOutbox SET state='sending',leaseUntil=?,leaseToken=?,attempts=attempts+1 WHERE requestId=?",(now+60,lease,row['requestId']))
            payload=json.loads(row['payloadJson']);error=None
            try:
                if not stillActive():raise ApiError('Отправка остановлена после смены сессии')
                if row['kind']=='publication':response=apiRequest('POST','/community/posts',{**payload,'requestId':row['requestId']},user['sessionToken'])['data']
                else:response=apiRequest('POST','/community/actions',dict(requestId=row['requestId'],kind=row['kind'],payload=payload),user['sessionToken'])['data']
            except ApiError as failure:error=failure
            with openDatabase() as connection:
                if error:
                    temporary=error.statusCode==0 or error.statusCode>=500 or error.statusCode in (401,429)
                    message='Обновите сервер для отложенных действий' if error.statusCode==404 and row['kind']!='publication' else str(error)
                    connection.execute('UPDATE communityOutbox SET state=?,lastError=?,nextAttemptAt=?,leaseUntil=0 WHERE requestId=? AND leaseToken=?',
                        ('pending' if temporary else 'blocked',message[:500],now+min(60,2**min(row['attempts']+1,6)),row['requestId'],lease))
                else:
                    connection.execute("UPDATE communityOutbox SET state='done',payloadJson='{}',resultJson=?,lastError='',leaseUntil=0 WHERE requestId=? AND leaseToken=?",(serialize(response),row['requestId'],lease));sent+=1
            if error:
                if error.statusCode==401:raise error
                if error.statusCode==0 or error.statusCode>=500:raise error
                if error.statusCode==429:break
        return sent
    finally:_flushLock.release()
