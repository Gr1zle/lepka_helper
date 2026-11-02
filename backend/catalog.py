import base64
import json
import sqlite3
from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from backend.moderation import invoke
from role_service import PermissionDenied
import learning_catalog as catalog


class SaveInput(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    expectedRevision:int=Field(ge=0)
    state:str
    document:dict
    reason:str=Field(min_length=10,max_length=500)


class AssetInput(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    name:str=Field(max_length=120)
    kind:str
    contentBase64:str=Field(max_length=17*1024*1024)


class UsageInput(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    revision:int=Field(gt=0)
    completed:bool=False


def call(callback):
    try:return {'data':callback()}
    except catalog.CatalogConflict as error:raise HTTPException(409,str(error)) from error
    except PermissionDenied as error:raise HTTPException(403,str(error)) from error
    except LookupError as error:raise HTTPException(404,str(error)) from error
    except ValueError as error:raise HTTPException(400,str(error)) from error
    except sqlite3.Error as error:raise HTTPException(503,'Не удалось сохранить учебные данные') from error


async def bounded(request,limit):
    body=bytearray()
    async for chunk in request.stream():
        if len(body)+len(chunk)>limit:raise HTTPException(413,'Учебный файл или документ слишком большой')
        body.extend(chunk)
    return bytes(body)


def installCatalogRoutes(app,currentUser):
    @app.get('/learning/catalog')
    def listing(user=Depends(currentUser)):return call(lambda:catalog.listing(user['userId']))

    @app.get('/learning/catalog/{contentId}')
    def detail(contentId:str,user=Depends(currentUser)):return call(lambda:catalog.detail(user['userId'],contentId))

    @app.get('/learning/assets/{assetId}')
    def asset(assetId:str,user=Depends(currentUser)):return call(lambda:catalog.asset(user['userId'],assetId))

    @app.post('/learning/catalog/{contentId}/usage')
    def usage(contentId:str,body:UsageInput,user=Depends(currentUser)):
        return call(lambda:catalog.usage(user['userId'],contentId,body.revision,body.completed))

    @app.get('/admin/catalog')
    def admin(user=Depends(currentUser)):return call(lambda:catalog.listing(user['userId'],True))

    @app.get('/admin/catalog-statistics')
    def stats(user=Depends(currentUser)):return call(lambda:catalog.statistics(user['userId']))

    @app.post('/admin/catalog-cleanup')
    def cleanup(user=Depends(currentUser)):return call(lambda:catalog.cleanUnused(user['userId']))

    @app.get('/admin/catalog/{contentId}')
    def adminDetail(contentId:str,user=Depends(currentUser)):return call(lambda:catalog.detail(user['userId'],contentId,True))

    @app.put('/admin/catalog/{contentId}')
    async def save(contentId:str,request:Request,user=Depends(currentUser)):
        from starlette.concurrency import run_in_threadpool
        raw=await bounded(request,100*1024)
        def action():
            body=SaveInput.model_validate_json(raw)
            return catalog.save(user['userId'],contentId,body.expectedRevision,body.state,body.document,body.reason)
        return await run_in_threadpool(call,action)

    @app.post('/admin/catalog-assets')
    async def upload(request:Request,user=Depends(currentUser)):
        from starlette.concurrency import run_in_threadpool
        # Check permission before reading a potentially large request body.
        from database import openDatabase
        with openDatabase() as connection:
            try:catalog.require(connection,user['userId'],'catalog.manage')
            except PermissionDenied as error:raise HTTPException(403,str(error)) from error
        raw=await bounded(request,18*1024*1024)
        def action():
            body=AssetInput.model_validate_json(raw)
            return catalog.upload(user['userId'],body.name,body.kind,base64.b64decode(body.contentBase64,validate=True))
        return await run_in_threadpool(call,action)
