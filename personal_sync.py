"""Ручная двусторонняя синхронизация снимка с проверкой версий и локальных изменений."""
from functools import wraps
import hashlib
import json
import re
import secrets
from urllib.parse import urlencode
from api_client import ApiError,apiRequest,getApiUrl
from database import openDatabase
from remote_account_cache import requireCachedUser
from personal_snapshot import exportSnapshot,encodeSnapshot,decodeSnapshot,snapshotSummary
from personal_checkpoints import saveCheckpoint,restoreCheckpoint
from app_state import getAppState,setAppState


def fingerprint(content):return hashlib.sha256(content).hexdigest()


def getDeviceId():
    deviceId=getAppState('syncDeviceId')
    if not isinstance(deviceId,str) or not re.fullmatch(r'[a-f0-9]{32}',deviceId):
        deviceId=secrets.token_hex(16);setAppState('syncDeviceId',deviceId)
    return deviceId


class PersonalSync:
    def __init__(self,user):
        self.user=user;self.apiUrl=getApiUrl()

    def request(self,method,path,payload=None):
        if not self.apiUrl:raise ValueError('Подключите сервер через Wi-Fi на экране входа')
        if getApiUrl()!=self.apiUrl:raise ApiError('Адрес сервера изменился. Откройте раздел заново')
        requireCachedUser(self.user['userId'],self.user.get('sessionToken'))
        try:
            result=apiRequest(method,'/personal/'+path,sessionToken=self.user.get('sessionToken'),
                jsonContent=encodeSnapshot(payload) if payload is not None else None)['data']
        except ApiError as error:
            if error.statusCode==404:raise ApiError('Обновите сервер до версии с личной синхронизацией',404) from None
            raise
        return result

    def base(self):
        with openDatabase() as connection:
            row=connection.execute('SELECT * FROM personalSyncState WHERE userId=? AND apiUrl=?',(self.user['userId'],self.apiUrl)).fetchone()
        return dict(row) if row else None

    def remember(self,metadata,connection=None):
        from contextlib import nullcontext
        with (nullcontext(connection) if connection is not None else openDatabase()) as current:
            current.execute('''INSERT INTO personalSyncState(userId,apiUrl,revision,checksum,pending) VALUES (?,?,?,?,0)
                ON CONFLICT(userId,apiUrl) DO UPDATE SET revision=excluded.revision,checksum=excluded.checksum,pending=0''',
                (self.user['userId'],self.apiUrl,metadata['revision'],metadata['checksum']))

    def queue(self):
        if not self.apiUrl:raise ValueError('Для отложенной синхронизации сначала подключите сервер')
        with openDatabase() as connection:
            connection.execute('''INSERT INTO personalSyncState(userId,apiUrl,pending) VALUES (?,?,1)
                ON CONFLICT(userId,apiUrl) DO UPDATE SET pending=1''',(self.user['userId'],self.apiUrl))

    def cancelPending(self):
        with openDatabase() as connection:connection.execute('UPDATE personalSyncState SET pending=0 WHERE userId=? AND apiUrl=?',(self.user['userId'],self.apiUrl))

    def compare(self):
        local=exportSnapshot(self.user['userId']);digest=fingerprint(local)
        remote=self.request('GET','snapshot-meta');base=self.base()
        if remote is not None and (not isinstance(remote,dict) or type(remote.get('revision')) is not int or remote['revision']<1 or not re.fullmatch('[a-f0-9]{64}',str(remote.get('checksum','')))):
            raise ApiError('Сервер вернул некорректную версию личных данных')
        if remote and remote['checksum']==digest:
            state='clean';self.remember(remote)
        elif remote is None:state='conflict' if base and base['revision'] else 'upload'
        elif not base or not base['checksum']:
            document=json.loads(local)
            empty=not any(document[key] for key in ('projects','mixtures','lessons','models','modelFavorites'))
            state='download' if empty else 'conflict'
        else:
            localChanged=digest!=base['checksum'];remoteChanged=remote['checksum']!=base['checksum']
            state='conflict' if localChanged and remoteChanged else 'upload' if localChanged else 'download' if remoteChanged else 'clean'
        return dict(state=state,localChecksum=digest,localSummary=snapshotSummary(json.loads(local)),remote=remote,pending=bool(base and base['pending']))

    def upload(self,comparison):
        local=exportSnapshot(self.user['userId'])
        if fingerprint(local)!=comparison['localChecksum']:raise ValueError('Данные устройства изменились. Сравните версии ещё раз')
        expected=comparison['remote']['revision'] if comparison['remote'] else 0
        payload=dict(expectedRevision=expected,deviceId=getDeviceId(),snapshot=json.loads(local))
        # Лимит снимка отдельно от небольшого конверта версии.
        content=json.dumps(payload,ensure_ascii=False,separators=(',',':')).encode()
        if getApiUrl()!=self.apiUrl:raise ApiError('Адрес сервера изменился')
        requireCachedUser(self.user['userId'],self.user.get('sessionToken'))
        result=apiRequest('PUT','/personal/snapshot',sessionToken=self.user.get('sessionToken'),jsonContent=content)['data']
        if result.get('checksum')!=fingerprint(local):raise ApiError('Не совпала контрольная сумма отправленных данных')
        self.remember(result)
        return result

    def download(self,comparison,revision=None):
        path='snapshot'+('?' + urlencode({'revision':revision}) if revision is not None else '')
        response=self.request('GET',path);content=encodeSnapshot(response['snapshot']);decodeSnapshot(content)
        expected=comparison['remote']
        if fingerprint(content)!=response['checksum'] or (revision is None and (not expected or response['revision']!=expected['revision'] or response['checksum']!=expected['checksum'])):
            raise ValueError('Серверная копия изменилась. Сравните версии ещё раз')
        with openDatabase() as connection:
            connection.execute('BEGIN IMMEDIATE')
            local=exportSnapshot(self.user['userId'],connection)
            if fingerprint(local)!=comparison['localChecksum']:raise ValueError('Данные устройства изменились. Сравните версии ещё раз')
            saveCheckpoint(self.user['userId'],local,'Перед загрузкой с сервера',connection)
            from personal_snapshot import applySnapshot
            result=applySnapshot(self.user['userId'],content,connection)
            # Исторический снимок становится локальным изменением относительно текущей версии сервера.
            self.remember(expected if revision is not None and expected else response,connection)
        return result

    def history(self):return self.request('GET','snapshot-history')
