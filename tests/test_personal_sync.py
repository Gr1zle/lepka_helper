import base64
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import database as db
from personal_snapshot import exportSnapshot,decodeSnapshot,encodeSnapshot,applySnapshot
from personal_checkpoints import saveCheckpoint,readCheckpoint,listCheckpoints,restoreCheckpoint
from personal_sync import PersonalSync,fingerprint
import personal_vault as vault
from project_service import saveProject,saveProjectStep,saveProjectStepPhoto,changeProjectStepStatus
from color_service import BASE_COLORS,calculateRecipe,saveColorMixture
from lesson_service import saveUserLessonState
from lesson_library import saveLessonFavorite,saveLessonNote
from model_import import importModel
from image_fixtures import photo


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        p=patch.object(db,'DATABASE_PATH',Path(self.folder.name)/'snapshot.db');p.start();self.addCleanup(p.stop)
        db.initializeDatabase()
        self.owner=db.createUser('one@example.com','','','one')
        self.other=db.createUser('two@example.com','','','two')

    def seed(self):
        uid=self.owner
        project=saveProject(uid,'Личный котик','Животные','05.11.2026','Секретная заметка')[2]
        step=saveProjectStep(project,'Подготовить основу',uid)[2]
        saveProjectStepPhoto(project,step,uid,photo());changeProjectStepStatus(project,step,True,uid)
        selected=[{**color,'proportion':50} for color in BASE_COLORS[:2]]
        saveColorMixture(uid,'Серый котик','#808080',100,calculateRecipe(selected,100))
        saveUserLessonState(uid,1,dict(lastStep=1,completedSteps=[0],checkedMaterials=[0]))
        saveLessonFavorite(uid,1,True);saveLessonNote(uid,1,'Важная учебная заметка')
        model=importModel(uid,'triangle.obj',b'v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n')
        with db.openDatabase() as c:c.execute('INSERT INTO modelFavorites VALUES (?,?)',(uid,model))
        return project

    def test_complete_roundtrip_preserves_photos_dates_models_and_private_identity(self):
        self.seed();content=exportSnapshot(self.owner);original=fingerprint(content)
        with db.openDatabase() as c:
            c.execute('BEGIN IMMEDIATE');applySnapshot(self.other,content,c)
        self.assertEqual(fingerprint(exportSnapshot(self.other)),original)
        self.assertEqual(db.getUserByEmail('two@example.com')['nickname'],'two')
        self.assertEqual(fingerprint(exportSnapshot(self.owner)),original)
        data=json.loads(content)
        self.assertEqual(len(data['models']),1)
        self.assertNotIn('userId',content.decode());self.assertNotIn('password',content.decode())

    def test_restore_requires_fresh_preview_and_creates_safety_copy(self):
        empty=exportSnapshot(self.owner);self.seed();full=exportSnapshot(self.owner)
        restoreCheckpoint(self.owner,empty,fingerprint(full))
        self.assertEqual(exportSnapshot(self.owner),empty)
        self.assertEqual(readCheckpoint(self.owner,listCheckpoints(self.owner)[0]['checkpointId']),full)
        with self.assertRaises(ValueError):restoreCheckpoint(self.owner,full,fingerprint(full))
        self.assertEqual(exportSnapshot(self.owner),empty)

    def test_restore_failure_rolls_back_data_and_safety_copy(self):
        empty=exportSnapshot(self.owner);self.seed();full=exportSnapshot(self.owner)
        def fail(user,content,connection):
            applySnapshot(user,content,connection)
            raise RuntimeError('synthetic rollback')
        with patch('personal_checkpoints.applySnapshot',side_effect=fail),self.assertRaises(RuntimeError):
            restoreCheckpoint(self.owner,empty,fingerprint(full))
        self.assertEqual(exportSnapshot(self.owner),full)
        self.assertEqual(listCheckpoints(self.owner),[])

    def test_copies_owner_scope_retention_and_corruption(self):
        content=exportSnapshot(self.owner)
        keys=[saveCheckpoint(self.owner,content) for _ in range(7)]
        self.assertEqual(len(listCheckpoints(self.owner)),5)
        with self.assertRaises(ValueError):readCheckpoint(self.owner,keys[0])
        with self.assertRaises(ValueError):readCheckpoint(self.other,keys[-1])
        with db.openDatabase() as c:c.execute('UPDATE personalCheckpoints SET content=? WHERE checkpointId=?',(b'bad',keys[-1]))
        with self.assertRaises(ValueError):readCheckpoint(self.owner,keys[-1])

    def test_account_cleanup_removes_private_versions_and_checkpoints(self):
        self.seed();content=exportSnapshot(self.owner)
        saveCheckpoint(self.owner,content)
        vault.saveSnapshot(self.owner,0,'a'*32,json.loads(content))
        with db.openDatabase() as c:c.execute('INSERT INTO personalSyncState(userId,apiUrl,pending) VALUES (?,?,1)',(self.owner,'https://example.invalid'))
        db.deleteUserDataById(self.owner)
        with db.openDatabase() as c:
            for table in ('personalCheckpoints','personalSyncState','personalVault','personalVaultHistory'):
                self.assertEqual(c.execute(f'SELECT COUNT(*) FROM {table} WHERE userId=?',(self.owner,)).fetchone()[0],0)
            self.assertEqual(c.execute('PRAGMA foreign_key_check').fetchall(),[])
        self.assertIsNotNone(db.getUserByEmail('two@example.com'))

    def test_invalid_archive_and_untrusted_owner_fields_are_rejected(self):
        document=json.loads(exportSnapshot(self.owner));document['userId']=self.other
        with self.assertRaises(ValueError):decodeSnapshot(encodeSnapshot(document))
        document.pop('userId');document['lessons']=[dict(lessonId=True,state=None,updatedAt=None,note='',favorite=False)]
        with self.assertRaises(ValueError):decodeSnapshot(encodeSnapshot(document))
        with self.assertRaises(ValueError):decodeSnapshot(b'x'*(20*1024*1024+1))

    def test_server_versions_conflict_idempotence_history_and_owner(self):
        content=json.loads(exportSnapshot(self.owner));device='a'*32
        first=vault.saveSnapshot(self.owner,0,device,content)
        self.assertEqual(first['revision'],1)
        self.assertEqual(vault.saveSnapshot(self.owner,0,device,content)['revision'],1)
        self.assertIsNone(vault.getSnapshot(self.other))
        self.seed();changed=json.loads(exportSnapshot(self.owner))
        with self.assertRaises(vault.VaultConflict):vault.saveSnapshot(self.owner,0,device,changed)
        for revision in range(1,6):
            changed['projects'][0]['archive']['project']['notes']='Редакция '+str(revision)
            vault.saveSnapshot(self.owner,revision,device,changed)
        self.assertEqual([r['revision'] for r in vault.history(self.owner)],[5,4,3])
        self.assertEqual(vault.getSnapshot(self.owner)['revision'],6)
        self.assertEqual(vault.history(self.other),[])
        self.assertIsNone(vault.getSnapshot(self.owner,True,1))


class CoordinatorTests(unittest.TestCase):
    setUp=SnapshotTests.setUp
    seed=SnapshotTests.seed

    def clients(self):
        from api_client import ApiError
        from urllib.parse import urlsplit,parse_qs
        def request(method,path,payload=None,sessionToken=None,jsonContent=None,**kwargs):
            if method=='PUT':
                data=json.loads(jsonContent)
                try:return {'data':vault.saveSnapshot(self.owner,data['expectedRevision'],data['deviceId'],data['snapshot'])}
                except vault.VaultConflict as error:raise ApiError(str(error),409)
            if path.endswith('snapshot-meta'):return {'data':vault.getSnapshot(self.owner)}
            if path.endswith('snapshot-history'):return {'data':vault.history(self.owner)}
            query=parse_qs(urlsplit(path).query)
            revision=int(query['revision'][0]) if 'revision' in query else None
            return {'data':vault.getSnapshot(self.owner,True,revision)}
        for target,value in [('personal_sync.getApiUrl','https://local.example'),('personal_sync.getDeviceId','b'*32),('personal_sync.requireCachedUser',None)]:
            p=patch(target,return_value=value);p.start();self.addCleanup(p.stop)
        p=patch('personal_sync.apiRequest',side_effect=request);p.start();self.addCleanup(p.stop)
        self.request=request
        return PersonalSync({'userId':self.owner,'sessionToken':'one'}),PersonalSync({'userId':self.other,'sessionToken':'two'})

    def test_two_devices_upload_download_and_both_changed_conflict(self):
        self.seed();first,second=self.clients()
        first.upload(first.compare())
        plan=second.compare();self.assertEqual(plan['state'],'download')
        second.download(plan)
        self.assertEqual(exportSnapshot(self.owner),exportSnapshot(self.other))
        self.assertEqual(second.compare()['state'],'clean')
        with db.openDatabase() as c:
            c.execute("UPDATE projects SET descriptionText='Первое устройство' WHERE userId=?",(self.owner,))
            c.execute("UPDATE projects SET descriptionText='Второе устройство' WHERE userId=?",(self.other,))
        stale=second.compare();self.assertEqual(stale['state'],'upload')
        first.upload(first.compare())
        from api_client import ApiError
        with self.assertRaises(ApiError) as error:second.upload(stale)
        self.assertEqual(error.exception.statusCode,409)
        self.assertEqual(second.compare()['state'],'conflict')
        previous=exportSnapshot(self.other)
        second.download(second.compare())
        self.assertEqual(exportSnapshot(self.owner),exportSnapshot(self.other))
        self.assertEqual(readCheckpoint(self.other,listCheckpoints(self.other)[0]['checkpointId']),previous)

    def test_lost_upload_response_is_reconciled_and_pending_survives_client_restart(self):
        from api_client import ApiError
        self.seed();first,_=self.clients();plan=first.compare()
        def lost(*args,**kwargs):self.request(*args,**kwargs);raise ApiError('Сеть прервана')
        with patch('personal_sync.apiRequest',side_effect=lost),self.assertRaises(ApiError):first.upload(plan)
        first.queue()
        restarted=PersonalSync(first.user)
        self.assertTrue(restarted.base()['pending'])
        self.assertEqual(restarted.compare()['state'],'clean')
        self.assertFalse(restarted.base()['pending'])
        self.assertEqual(vault.getSnapshot(self.owner)['revision'],1)

    def test_download_rechecks_local_and_remote_changes_before_replace(self):
        self.seed();first,second=self.clients();first.upload(first.compare());plan=second.compare()
        saveProject(self.other,'Новая локальная работа','Другое','','')
        with self.assertRaises(ValueError):second.download(plan)
        self.assertEqual(len(json.loads(exportSnapshot(self.other))['projects']),1)
        self.assertEqual(listCheckpoints(self.other),[])
        plan=second.compare()
        with db.openDatabase() as c:c.execute("UPDATE projects SET descriptionText='Следующая редакция' WHERE userId=?",(self.owner,))
        first.upload(first.compare())
        with self.assertRaises(ValueError):second.download(plan)
        self.assertEqual(listCheckpoints(self.other),[])

    def test_historical_version_is_local_change_and_next_upload_creates_new_revision(self):
        self.seed();first,_=self.clients();first.upload(first.compare());original=exportSnapshot(self.owner)
        with db.openDatabase() as c:c.execute("UPDATE projects SET descriptionText='Новая редакция' WHERE userId=?",(self.owner,))
        first.upload(first.compare());plan=first.compare()
        first.download(plan,1)
        self.assertEqual(exportSnapshot(self.owner),original)
        self.assertEqual(first.compare()['state'],'upload')
        self.assertEqual(first.upload(first.compare())['revision'],3)


class PrivateApiTests(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        from backend.main import createApp
        from account_security import createSession
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        self.client=TestClient(createApp(self.folder.name));self.client.__enter__();self.addCleanup(self.client.__exit__,None,None,None)
        self.user=db.createUser('owner@example.com','','','owner')
        self.other=db.createUser('other@example.com','','','other')
        with db.openDatabase() as c:
            self.headers={'Authorization':'Bearer '+createSession(c,db.getUserByEmail('owner@example.com'))['sessionToken']}
            self.otherHeaders={'Authorization':'Bearer '+createSession(c,db.getUserByEmail('other@example.com'))['sessionToken']}
        self.document=json.loads(exportSnapshot(self.user))

    def test_private_routes_owner_auth_and_concurrency(self):
        body=dict(expectedRevision=0,deviceId='c'*32,snapshot=self.document)
        self.assertEqual(self.client.get('/personal/snapshot-meta').status_code,401)
        response=self.client.put('/personal/snapshot',headers=self.headers,json=body)
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['data']['revision'],1)
        self.assertIsNone(self.client.get('/personal/snapshot-meta',headers=self.otherHeaders).json()['data'])
        self.assertEqual(self.client.get('/personal/snapshot',headers=self.otherHeaders).status_code,404)
        body['snapshot']['lessons']=[dict(lessonId=1,state=None,updatedAt=None,note='Заметка владельца',favorite=False)]
        self.assertEqual(self.client.put('/personal/snapshot',headers=self.headers,json=body).status_code,409)
        body['expectedRevision']=1
        self.assertEqual(self.client.put('/personal/snapshot',headers=self.headers,json=body).status_code,200)
        self.assertEqual(self.client.get('/personal/snapshot-history',headers=self.headers).json()['data'][0]['revision'],1)
        body['userId']=self.other
        self.assertEqual(self.client.put('/personal/snapshot',headers=self.headers,json=body).status_code,422)

    def test_private_body_limit_checks_actual_bytes_and_account_deletion_cleans_vault(self):
        body=dict(expectedRevision=0,deviceId='c'*32,snapshot=self.document)
        self.client.put('/personal/snapshot',headers=self.headers,json=body)
        response=self.client.put('/personal/snapshot',headers={**self.headers,'Content-Length':'1'},content=b'x'*(20*1024*1024+32769))
        self.assertEqual(response.status_code,413)
        db.deleteUserDataById(self.user)
        self.assertEqual(self.client.get('/personal/snapshot',headers=self.headers).status_code,401)
        with db.openDatabase() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM personalVault WHERE userId=?',(self.user,)).fetchone()[0],0)
            self.assertEqual(c.execute('PRAGMA foreign_key_check').fetchall(),[])
