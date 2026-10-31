"""HTTP права администратора проверяются заново для каждого действия."""
from fastapi import Depends,HTTPException,Query
from pydantic import BaseModel,ConfigDict,Field
import sqlite3
import moderation_service as service


class ReasonInput(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    reason:str=Field(min_length=10,max_length=500)


class MaterialInput(ReasonInput):
    targetType:str=Field(pattern='^(post|comment)$')
    targetId:int=Field(gt=0)


class ResolveInput(ReasonInput):
    status:str=Field(pattern='^(resolved|rejected)$')


class UserChangeInput(ReasonInput):
    blocked:bool|None=None
    role:str|None=Field(default=None,pattern='^(user|admin)$')


def invoke(callback):
    try:return {'data':callback()}
    except service.ModerationDenied as error:raise HTTPException(403,str(error)) from error
    except ValueError as error:raise HTTPException(400,str(error)) from error
    except sqlite3.Error as error:raise HTTPException(503,'Не удалось выполнить действие. Повторите позже') from error


def installModerationRoutes(application,currentUser):
    @application.post('/community/reports')
    def report(body:MaterialInput,user=Depends(currentUser)):
        return invoke(lambda:service.reportMaterial(user['userId'],body.targetType,body.targetId,body.reason))

    @application.get('/admin/reports')
    def reports(status:str=Query(default='open',pattern='^(open|resolved|rejected|all)$'),offset:int=Query(default=0,ge=0),user=Depends(currentUser)):
        return invoke(lambda:service.listReports(user['userId'],status,offset))

    @application.put('/admin/reports/{reportId}')
    def resolve(reportId:int,body:ResolveInput,user=Depends(currentUser)):
        return invoke(lambda:service.resolveReport(user['userId'],reportId,body.status,body.reason))

    @application.post('/admin/remove')
    def remove(body:MaterialInput,user=Depends(currentUser)):
        return invoke(lambda:service.removeMaterial(user['userId'],body.targetType,body.targetId,body.reason))

    @application.get('/admin/users')
    def users(query:str=Query(default='',max_length=100),offset:int=Query(default=0,ge=0),user=Depends(currentUser)):
        return invoke(lambda:service.listUsers(user['userId'],query,offset))

    @application.put('/admin/users/{userId}')
    def change(userId:int,body:UserChangeInput,user=Depends(currentUser)):
        return invoke(lambda:service.changeUser(user['userId'],userId,body.reason,body.blocked,body.role))

    @application.get('/admin/audit')
    def journal(offset:int=Query(default=0,ge=0),user=Depends(currentUser)):
        return invoke(lambda:service.listAudit(user['userId'],offset))
