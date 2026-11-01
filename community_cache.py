"""Ограниченный кеш прочитанных данных, разделённый по аккаунту и серверу."""
import json
import time
from database import openDatabase


def readCache(userId,apiUrl,key):
    if not userId:return None
    with openDatabase() as connection:
        row=connection.execute('SELECT contentJson FROM communityCache WHERE userId=? AND apiUrl=? AND cacheKey=?',(userId,apiUrl,key)).fetchone()
    return json.loads(row[0]) if row else None


def writeCache(userId,apiUrl,key,content):
    if not userId:return
    serialized=json.dumps(content,ensure_ascii=False)
    if len(serialized.encode())>8*1024*1024:return
    with openDatabase() as connection:
        connection.execute('INSERT OR REPLACE INTO communityCache VALUES (?,?,?,?,?)',(userId,apiUrl,key,serialized,time.time()))
        rows=connection.execute('SELECT cacheKey,length(CAST(contentJson AS BLOB)) AS size FROM communityCache WHERE userId=? AND apiUrl=? ORDER BY updatedAt DESC',(userId,apiUrl)).fetchall()
        size=0
        for index,row in enumerate(rows):
            size+=row['size']
            if index>=100 or size>32*1024*1024:connection.execute('DELETE FROM communityCache WHERE userId=? AND apiUrl=? AND cacheKey=?',(userId,apiUrl,row['cacheKey']))
