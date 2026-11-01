"""Версии личного снимка на сервере. Владельца задаёт проверенный Bearer-токен."""
import hashlib
import json
import re
from database import openDatabase
from personal_snapshot import decodeSnapshot,encodeSnapshot,requireOwner,snapshotSummary


class VaultConflict(ValueError):pass


def checksum(content):return hashlib.sha256(content).hexdigest()


def metadata(row):
    return dict(revision=row['revision'],checksum=row['checksum'],deviceId=row['deviceId'],updatedAt=row['updatedAt'],summary=snapshotSummary(json.loads(row['snapshotJson'])))


def getSnapshot(userId,includeContent=False,revision=None):
    with openDatabase() as connection:
        requireOwner(connection,userId)
        if revision is None:row=connection.execute('SELECT * FROM personalVault WHERE userId=?',(userId,)).fetchone()
        else:row=connection.execute('SELECT * FROM personalVaultHistory WHERE userId=? AND revision=?',(userId,revision)).fetchone()
    if row is None:return None
    result=metadata(row)
    if includeContent:result['snapshot']=json.loads(row['snapshotJson'])
    return result


def saveSnapshot(userId,expectedRevision,deviceId,document):
    if type(expectedRevision) is not int or not 0<=expectedRevision<2**63-1 or not isinstance(deviceId,str) or not re.fullmatch(r'[a-f0-9]{32}',deviceId):
        raise ValueError('Некорректная версия или устройство')
    content=encodeSnapshot(document);decodeSnapshot(content);digest=checksum(content)
    with openDatabase() as connection:
        connection.execute('BEGIN IMMEDIATE');requireOwner(connection,userId)
        row=connection.execute('SELECT * FROM personalVault WHERE userId=?',(userId,)).fetchone()
        current=row['revision'] if row else 0
        if row and row['checksum']==digest:return metadata(row)
        if current!=expectedRevision:raise VaultConflict('Данные на сервере изменились. Обновите сравнение перед отправкой')
        if row:
            connection.execute('INSERT INTO personalVaultHistory SELECT * FROM personalVault WHERE userId=?',(userId,))
        connection.execute('''INSERT INTO personalVault(userId,revision,checksum,snapshotJson,deviceId) VALUES (?,?,?,?,?)
            ON CONFLICT(userId) DO UPDATE SET revision=excluded.revision,checksum=excluded.checksum,
            snapshotJson=excluded.snapshotJson,deviceId=excluded.deviceId,updatedAt=CURRENT_TIMESTAMP''',
            (userId,current+1,digest,content.decode(),deviceId))
        connection.execute('DELETE FROM personalVaultHistory WHERE userId=? AND revision NOT IN (SELECT revision FROM personalVaultHistory WHERE userId=? ORDER BY revision DESC LIMIT 3)',(userId,userId))
        return metadata(connection.execute('SELECT * FROM personalVault WHERE userId=?',(userId,)).fetchone())


def history(userId):
    with openDatabase() as connection:
        requireOwner(connection,userId)
        return [metadata(row) for row in connection.execute('SELECT * FROM personalVaultHistory WHERE userId=? ORDER BY revision DESC',(userId,))]
