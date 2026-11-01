"""Ограниченный доступ к личным данным по ранее подтверждённой серверной сессии."""
import json
import time
from account_security import hashToken
from api_client import ApiError,getApiUrl
from remote_account_cache import requireCachedUser
from database import openDatabase

_verified={}
_failed={}


def registerVerified(user):
    if not isinstance(user,dict) or type(user.get('userId')) is not int or not isinstance(user.get('sessionToken'),str) or not 0<len(user['sessionToken'])<=256:return False
    expires=user.get('sessionExpiresAt')
    if type(expires) not in (int,float) or not time.time()<expires<=time.time()+13*3600:return False
    requireCachedUser(user['userId'],user.get('sessionToken'))
    _verified[hashToken(user['sessionToken'])]=dict(user,apiUrl=getApiUrl(),offline=False)
    _failed.pop(getApiUrl(),None)
    return True


def cachedUser(token):
    if not isinstance(token,str):return None
    record=_verified.get(hashToken(token))
    if not record or record['apiUrl']!=getApiUrl() or record['sessionExpiresAt']<=time.time():return None
    try:requireCachedUser(record['userId'],token)
    except ApiError:return None
    return dict(record,offline=True)


def forgetVerified(token):
    if isinstance(token,str):_verified.pop(hashToken(token),None)


def noteUnavailable():_failed[getApiUrl()]=time.monotonic()
def coolingDown():return time.monotonic()-_failed.get(getApiUrl(),-100)<5


def cachedProfile(userId,token):
    user=cachedUser(token)
    if not user or user['userId']!=userId:return None
    with openDatabase() as connection:
        row=connection.execute('SELECT profileJson FROM remoteProfileCache WHERE userId=? AND apiUrl=?',(userId,getApiUrl())).fetchone()
    profile=dict(bioText='',ageCategory='Взрослый 18+',favoriteColors=[],themeMode='light',languageCode='ru',notificationsEnabled=True,avatarPath='',avatarImage='')
    if row:profile.update(json.loads(row[0]))
    return {**profile,**user}
