"""Пять последних полных копий в личной SQLite, атомарное восстановление."""
import hashlib
import secrets
import zlib
from database import openDatabase
from personal_snapshot import MAX_SNAPSHOT_BYTES,exportSnapshot,decodeSnapshot,applySnapshot,requireOwner


def saveCheckpoint(userId,content,title='Ручная копия',connection=None):
    from contextlib import nullcontext
    decodeSnapshot(content)
    checkpointId=secrets.token_hex(16)
    with (nullcontext(connection) if connection is not None else openDatabase()) as current:
        if not current.in_transaction:current.execute('BEGIN IMMEDIATE')
        requireOwner(current,userId)
        current.execute('INSERT INTO personalCheckpoints(checkpointId,userId,title,content,checksum) VALUES (?,?,?,?,?)',
            (checkpointId,userId,title[:100],zlib.compress(content),hashlib.sha256(content).hexdigest()))
        current.execute('DELETE FROM personalCheckpoints WHERE userId=? AND checkpointId NOT IN (SELECT checkpointId FROM personalCheckpoints WHERE userId=? ORDER BY rowid DESC LIMIT 5)',(userId,userId))
    return checkpointId


def listCheckpoints(userId):
    with openDatabase() as connection:
        requireOwner(connection,userId)
        return [dict(row) for row in connection.execute('SELECT checkpointId,title,createdAt,length(content) AS size FROM personalCheckpoints WHERE userId=? ORDER BY rowid DESC',(userId,))]


def readCheckpoint(userId,checkpointId):
    with openDatabase() as connection:
        requireOwner(connection,userId)
        row=connection.execute('SELECT content,checksum FROM personalCheckpoints WHERE userId=? AND checkpointId=?',(userId,checkpointId)).fetchone()
    if row is None:raise ValueError('Личная копия не найдена')
    try:
        decoder=zlib.decompressobj();content=decoder.decompress(row['content'],MAX_SNAPSHOT_BYTES+1)
        if len(content)>MAX_SNAPSHOT_BYTES or not decoder.eof or decoder.unused_data or hashlib.sha256(content).hexdigest()!=row['checksum']:
            raise ValueError('Личная копия повреждена')
        decodeSnapshot(content);return content
    except zlib.error as error:raise ValueError('Личная копия повреждена') from error


def deleteCheckpoint(userId,checkpointId):
    with openDatabase() as connection:
        requireOwner(connection,userId)
        connection.execute('DELETE FROM personalCheckpoints WHERE userId=? AND checkpointId=?',(userId,checkpointId))


def restoreCheckpoint(userId,content,expectedChecksum):
    decodeSnapshot(content)
    with openDatabase() as connection:
        connection.execute('BEGIN IMMEDIATE')
        previous=exportSnapshot(userId,connection)
        if hashlib.sha256(previous).hexdigest()!=expectedChecksum:raise ValueError('Личные данные уже изменились. Обновите предварительный просмотр')
        saveCheckpoint(userId,previous,'Перед восстановлением',connection)
        return applySnapshot(userId,content,connection)
