"""Жалобы и панель: текущая локальная база или API, без обхода прав при сбое."""
from urllib.parse import urlencode
import sqlite3
import account_gateway as accounts
from api_client import ApiError,apiRequest
from remote_account_cache import requireCachedUser
import moderation_service as service


class ModerationClient:
    def __init__(self,user):
        self.user=user
        self.apiUrl=accounts.getApiUrl()
        self.remote=bool(self.apiUrl)

    def call(self,method,path,payload=None,local=None):
        if accounts.getApiUrl()!=self.apiUrl:raise ApiError('Адрес API изменился. Откройте приложение заново')
        if not self.user:raise ApiError('Выполните вход',401)
        if self.remote:
            requireCachedUser(self.user['userId'],self.user.get('sessionToken'))
            return apiRequest(method,path,payload,self.user.get('sessionToken'))['data']
        current=accounts.getSessionUser(self.user.get('sessionToken'))
        if not current or current['userId']!=self.user['userId']:raise ApiError('Сессия завершена. Выполните вход снова',401)
        try:return local(current['userId'])
        except service.ModerationDenied as error:raise ApiError(str(error),403) from error
        except ValueError as error:raise ApiError(str(error),400) from error
        except sqlite3.Error as error:raise ApiError('Не удалось выполнить действие. Повторите позже',503) from error

    def report(self,targetType,targetId,reason):
        return self.call('POST','/community/reports',dict(targetType=targetType,targetId=targetId,reason=reason),
                         lambda actor:service.reportMaterial(actor,targetType,targetId,reason))

    def reports(self,status='open',offset=0):
        return self.call('GET','/admin/reports?'+urlencode(dict(status=status,offset=offset)),local=lambda actor:service.listReports(actor,status,offset))

    def resolve(self,reportId,status,reason):
        return self.call('PUT',f'/admin/reports/{reportId}',dict(status=status,reason=reason),
                         lambda actor:service.resolveReport(actor,reportId,status,reason))

    def remove(self,targetType,targetId,reason):
        return self.call('POST','/admin/remove',dict(targetType=targetType,targetId=targetId,reason=reason),
                         lambda actor:service.removeMaterial(actor,targetType,targetId,reason))

    def users(self,query='',offset=0):
        return self.call('GET','/admin/users?'+urlencode(dict(query=query,offset=offset)),local=lambda actor:service.listUsers(actor,query,offset))

    def changeUser(self,userId,reason,blocked=None,role=None):
        payload=dict(reason=reason)
        if blocked is not None:payload['blocked']=blocked
        if role is not None:payload['role']=role
        return self.call('PUT',f'/admin/users/{userId}',payload,lambda actor:service.changeUser(actor,userId,reason,blocked,role))

    def audit(self,offset=0):
        return self.call('GET','/admin/audit?'+urlencode(dict(offset=offset)),local=lambda actor:service.listAudit(actor,offset))
