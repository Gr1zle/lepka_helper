from fastapi import Depends,HTTPException,Query
from pydantic import BaseModel,ConfigDict,Field
import personal_vault as vault


class SnapshotInput(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    expectedRevision:int=Field(ge=0,lt=2**63-1)
    deviceId:str=Field(pattern=r'^[a-f0-9]{32}$')
    snapshot:dict


def installPersonalRoutes(application,currentUser):
    @application.get('/personal/snapshot-meta')
    def meta(user=Depends(currentUser)):
        return {'data':vault.getSnapshot(user['userId'])}

    @application.get('/personal/snapshot-history')
    def history(user=Depends(currentUser)):
        return {'data':vault.history(user['userId'])}

    @application.get('/personal/snapshot')
    def getSnapshot(revision:int|None=Query(default=None,ge=1,lt=2**63-1),user=Depends(currentUser)):
        result=vault.getSnapshot(user['userId'],True,revision)
        if result is None:raise HTTPException(404,'На сервере нет этой личной копии')
        return {'data':result}

    @application.put('/personal/snapshot')
    def putSnapshot(body:SnapshotInput,user=Depends(currentUser)):
        try:return {'data':vault.saveSnapshot(user['userId'],body.expectedRevision,body.deviceId,body.snapshot)}
        except vault.VaultConflict as error:raise HTTPException(409,str(error)) from None
        except ValueError as error:raise HTTPException(400,str(error)) from None
