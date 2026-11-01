"""Незавершённые публикации: фото и текст сохраняются отдельно для владельца/API."""
import json
import secrets
import time
from database import openDatabase
from api_client import getApiUrl


def saveDraft(userId,apiUrl,payload,draftId=None):
    allowed={'titleText','descriptionText','categoryName','tagsText','photos','challengeId','projectDetailsJson'}
    if not isinstance(payload,dict) or set(payload)-allowed:raise ValueError('Некорректные поля черновика')
    for key,limit in [('titleText',100),('descriptionText',2000),('tagsText',500),('projectDetailsJson',131072)]:
        if not isinstance(payload.get(key,''),str) or len(payload.get(key,''))>limit:raise ValueError('Слишком большой текст черновика')
    photos=payload.get('photos',[])
    if not isinstance(photos,list) or len(photos)>10:raise ValueError('В черновике допускается до 10 фото')
    encoded=json.dumps(payload,ensure_ascii=False,separators=(',',':'),allow_nan=False)
    if len(encoded.encode())>32*1024*1024:raise ValueError('Черновик больше 32 МБ')
    draftId=draftId or secrets.token_hex(16)
    with openDatabase() as connection:
        connection.execute('BEGIN IMMEDIATE')
        old=connection.execute('SELECT userId,apiUrl FROM publicationDrafts WHERE draftId=?',(draftId,)).fetchone()
        if old and (old['userId']!=userId or old['apiUrl']!=apiUrl):raise ValueError('Черновик другого аккаунта недоступен')
        rows=connection.execute('SELECT draftId,length(CAST(payloadJson AS BLOB)) AS size FROM publicationDrafts WHERE userId=? AND draftId!=?',(userId,draftId)).fetchall()
        if len(rows)>=10 or sum(row['size'] for row in rows)+len(encoded.encode())>64*1024*1024:raise ValueError('Можно хранить до 10 черновиков и 64 МБ')
        connection.execute('INSERT OR REPLACE INTO publicationDrafts VALUES (?,?,?,?,?)',(draftId,userId,apiUrl,encoded,time.time()))
    return draftId


def listDrafts(userId,apiUrl):
    with openDatabase() as connection:rows=connection.execute('SELECT draftId,payloadJson,updatedAt FROM publicationDrafts WHERE userId=? AND apiUrl=? ORDER BY updatedAt DESC',(userId,apiUrl)).fetchall()
    return [dict(draftId=row['draftId'],payload=json.loads(row['payloadJson']),updatedAt=row['updatedAt']) for row in rows]


def getDraft(userId,apiUrl,draftId):
    return next((item for item in listDrafts(userId,apiUrl) if item['draftId']==draftId),None)


def deleteDraft(userId,apiUrl,draftId):
    with openDatabase() as connection:connection.execute('DELETE FROM publicationDrafts WHERE userId=? AND apiUrl=? AND draftId=?',(userId,apiUrl,draftId))
