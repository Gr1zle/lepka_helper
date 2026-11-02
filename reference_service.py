import time
import uuid
from database import openDatabase
from lesson_library import requireOwner
from api_client import getApiUrl
from color_photo import readImage,pngBytes


def saveReference(userId,title,content):
    if not isinstance(title,str) or not 1<=len(title.strip())<=80:raise ValueError('Название референса: 1–80 символов')
    content=pngBytes(readImage(content));rid=uuid.uuid4().hex
    with openDatabase() as c:
        c.execute('BEGIN IMMEDIATE');requireOwner(c,userId)
        count,size=c.execute('SELECT COUNT(*),COALESCE(SUM(LENGTH(image)),0) FROM referenceImages WHERE userId=? AND apiUrl=?',(userId,getApiUrl())).fetchone()
        if count>=20 or size+len(content)>40*1024*1024:raise ValueError('Референсы: максимум 20 изображений и 40 МБ на аккаунт/сервер')
        c.execute('INSERT INTO referenceImages VALUES (?,?,?,?,?,?)',(rid,userId,getApiUrl(),title.strip(),content,time.time()))
    return rid


def listReferences(userId):
    with openDatabase() as c:
        requireOwner(c,userId)
        return [dict(r) for r in c.execute('SELECT * FROM referenceImages WHERE userId=? AND apiUrl=? ORDER BY createdAt DESC',(userId,getApiUrl()))]


def deleteReference(userId,rid):
    with openDatabase() as c:
        requireOwner(c,userId);return bool(c.execute('DELETE FROM referenceImages WHERE userId=? AND apiUrl=? AND referenceId=?',(userId,getApiUrl(),rid)).rowcount)
