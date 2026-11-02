"""HTTP права администратора проверяются заново для каждого действия."""
from fastapi import Depends,HTTPException,Query,Path
from pydantic import BaseModel,ConfigDict,Field
import sqlite3
import moderation_service as service
import role_service as roles


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
    role:str|None=Field(default=None,pattern='^[a-z][a-z0-9_]{2,23}$')


class RoleInput(ReasonInput):
    title:str=Field(min_length=3,max_length=50)
    permissions:list[str]=Field(max_length=8)


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

    @application.get('/community/access')
    def access(user=Depends(currentUser)):
        return invoke(lambda:roles.access(user['userId']))

    @application.get('/community/my-reports')
    def myReports(offset:int=Query(0,ge=0),user=Depends(currentUser)):
        return invoke(lambda:service.myReports(user['userId'],offset))

    @application.get('/admin/roles')
    def listRoles(user=Depends(currentUser)):
        return invoke(lambda:roles.roles(user['userId']))

    @application.post('/admin/roles/{code}')
    def createRole(code:str,body:RoleInput,user=Depends(currentUser)):
        return invoke(lambda:roles.save(user['userId'],code,body.title,body.permissions,body.reason,True))

    @application.put('/admin/roles/{code}')
    def updateRole(code:str,body:RoleInput,user=Depends(currentUser)):
        return invoke(lambda:roles.save(user['userId'],code,body.title,body.permissions,body.reason))

    @application.post('/admin/roles/{code}/delete')
    def deleteRole(code:str,body:ReasonInput,user=Depends(currentUser)):
        return invoke(lambda:roles.remove(user['userId'],code,body.reason))

    @application.post('/admin/users/{userId}/delete')
    def deleteAccount(body:ReasonInput,userId:int=Path(gt=0,le=9223372036854775807),user=Depends(currentUser)):
        return invoke(lambda:service.deleteUser(user['userId'],userId,body.reason))
