import base64
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import uuid
from fastapi.testclient import TestClient
import database as db
from backend.main import createApp
from account_security import createSession
from catalog_client import CatalogClient,catalogNotices
import learning_catalog as service
from api_client import ApiError
from image_fixtures import photo


def document(kind='lesson',asset=None):
    return dict(kind=kind,title='Учебная фигурка',category='Животные',level='Начинающий',timeMinutes=20,
        description='Новый подробный урок лепки фигурки',tags=['котик','лепка'],materials=['Пластилин','Стек'],
        steps=[dict(text='Скатайте шарик и сделайте основу',imageAsset=asset,videoAsset=None)],coverAsset=asset,modelAsset=None)


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        client=TestClient(createApp(self.folder.name));client.__enter__();self.addCleanup(client.__exit__,None,None,None);self.http=client
        self.admin=db.createUser('teacher@example.com','','','teacher')
        self.reader=db.createUser('reader@example.com','','','reader')
        self.other=db.createUser('other@example.com','','','other')
        with db.openDatabase() as c:
            c.execute("UPDATE users SET roleName='admin' WHERE userId=?",(self.admin,))
            self.adminToken=createSession(c,c.execute('SELECT * FROM users WHERE userId=?',(self.admin,)).fetchone())['sessionToken']
            self.readerToken=createSession(c,c.execute('SELECT * FROM users WHERE userId=?',(self.reader,)).fetchone())['sessionToken']
        self.headers={'Authorization':'Bearer '+self.adminToken};self.readerHeaders={'Authorization':'Bearer '+self.readerToken}
        self.cid=uuid.uuid4().hex
    def save(self,doc=None,state='published',revision=0):
        return service.save(self.admin,self.cid,revision,state,doc or document(),'Публикация учебного материала')
    def remoteClient(self):
        # Client owner deliberately differs from the Bearer owner at the real API.
        user=dict(userId=self.other,serverUserId=self.reader,sessionToken=self.readerToken,apiUrl='https://api.example')
        def request(method,path,payload=None,sessionToken=None,**kwargs):
            response=self.http.request(method,path,headers={'Authorization':'Bearer '+sessionToken},json=payload)
            if response.status_code>=300:raise ApiError(response.json().get('detail','Ошибка'),response.status_code)
            return response.json()
        for target,value in [('catalog_client.getApiUrl',lambda:'https://api.example'),('catalog_client.getSessionUser',lambda token:user),('catalog_client.apiRequest',request)]:
            p=patch(target,side_effect=value);p.start();self.addCleanup(p.stop)
        return CatalogClient(user)

    def test_drafts_assets_and_publication_are_permission_checked(self):
        asset=service.upload(self.admin,'photo.png','image',photo()['data'])
        self.save(document(asset=asset['assetId']),'draft')
        self.assertEqual(service.listing(self.reader),[])
        self.assertEqual(self.http.get('/learning/catalog').status_code,401)
        self.assertEqual(self.http.get('/learning/assets/'+asset['assetId'],headers=self.readerHeaders).status_code,404)
        self.assertEqual(self.http.get('/admin/catalog',headers=self.readerHeaders).status_code,403)
        self.assertEqual(self.http.post('/admin/catalog-assets',headers=self.readerHeaders,json={}).status_code,403)
        self.save(document(asset=asset['assetId']),'published',1)
        self.assertEqual(len(service.listing(self.reader)),1)
        self.assertEqual(self.http.get('/learning/assets/'+asset['assetId'],headers=self.readerHeaders).status_code,200)
        self.save(document(asset=asset['assetId']),'archived',2)
        self.assertEqual(self.http.get('/learning/catalog/'+self.cid,headers=self.readerHeaders).status_code,404)

    def test_real_http_upload_and_revoked_actor_session(self):
        payload=dict(name='upload.png',kind='image',contentBase64=base64.b64encode(photo()['data']).decode())
        result=self.http.post('/admin/catalog-assets',headers=self.headers,json=payload)
        self.assertEqual(result.status_code,200)
        aid=result.json()['data']['assetId']
        self.save(document(asset=aid))
        result=self.http.get('/learning/assets/'+aid,headers=self.readerHeaders)
        self.assertEqual(result.status_code,200)
        self.assertEqual(result.json()['data']['mime'],'image/jpeg')
        with db.openDatabase() as c:c.execute('DELETE FROM accountSessions WHERE userId=?',(self.admin,))
        self.assertEqual(self.http.post('/admin/catalog-assets',headers=self.headers,json=payload).status_code,401)

    def test_revision_conflict_returns_409_without_overwriting(self):
        self.save()
        response=self.http.put('/admin/catalog/'+self.cid,headers=self.headers,json=dict(expectedRevision=0,state='published',document=document(),reason='Повтор старой версии'))
        self.assertEqual(response.status_code,409)
        self.assertEqual(service.detail(self.reader,self.cid)['revision'],1)

    def test_catalog_only_staff_has_no_account_or_role_authority(self):
        import role_service
        role_service.save(self.admin,'teacher_role','Преподаватель',['catalog.manage'],'Выдать права преподавателя',True)
        with db.openDatabase() as c:c.execute("UPDATE users SET roleName='teacher_role' WHERE userId=?",(self.reader,))
        service.save(self.reader,self.cid,0,'published',document(),'Создание учебного материала')
        self.assertEqual(service.statistics(self.reader)['items'][0]['title'],document()['title'])
        self.assertEqual(self.http.get('/admin/users',headers=self.readerHeaders).status_code,403)

    def test_validation_rejects_wrong_types_asset_reference_and_traversal(self):
        for field,value in [('timeMinutes',True),('category','неизвестно'),('steps',[]),('coverAsset','../file')]:
            bad=document();bad[field]=value
            with self.assertRaises(ValueError):self.save(bad)
        with self.assertRaises(ValueError):self.save(document(asset='a'*64))
        with self.assertRaises(ValueError):service.upload(self.admin,'../a.mp4','video',b'bad')
        with self.assertRaises(ValueError):service.upload(self.admin,'a.mp4','video',b'\0'*100)
        with self.assertRaises(ValueError):service.upload(self.admin,'a.zip','model',b'bad')
        self.assertEqual(service.listing(self.reader),[])

    def test_audit_failure_rolls_back_publication(self):
        with patch('learning_catalog.audit',side_effect=ValueError('journal failed')):
            with self.assertRaises(ValueError):self.save()
        self.assertEqual(service.listing(self.admin,True),[])

    def test_cleanup_preserves_draft_and_published_references(self):
        first=service.upload(self.admin,'one.png','image',photo()['data'])
        unused=service.upload(self.admin,'extra.obj','model',b'v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n')
        self.save(document(asset=first['assetId']),'draft')
        self.assertEqual(service.cleanUnused(self.admin),1)
        self.assertEqual(service.asset(self.admin,first['assetId'])['assetId'],first['assetId'])
        with self.assertRaises(LookupError):service.asset(self.admin,unused['assetId'])

    def test_complete_cache_owner_scope_offline_progress_and_idempotent_statistics(self):
        image=service.upload(self.admin,'one.png','image',photo()['data']);self.save(document(asset=image['assetId']))
        client=self.remoteClient();client.download(self.cid)
        self.assertEqual(client.cached(self.cid)[0]['revision'],1)
        with db.openDatabase() as c:
            self.assertEqual(c.execute('SELECT userId FROM learningCache').fetchone()[0],self.other)
        client.savePersonal(self.cid,1,[0],True,'Моя заметка');client.flushUsage();client.flushUsage()
        stats=service.statistics(self.admin)['items'][0]
        self.assertEqual((stats['readers'],stats['completed']),(1,1))
        with db.openDatabase() as c:self.assertEqual(c.execute('SELECT userId FROM learningUsage').fetchone()[0],self.reader)
        with patch('catalog_client.apiRequest',side_effect=ApiError('offline')):
            self.assertEqual(client.cached(self.cid)[1][image['assetId']]['kind'],'image')
            client.savePersonal(self.cid,1,[0],False,'Сохранилось без API')
        self.assertEqual(client.personal(self.cid)['note'],'Сохранилось без API')
        with patch('catalog_client.getApiUrl',return_value='https://other.example'):
            with self.assertRaises(ApiError):client.cached(self.cid)

    def test_failed_download_and_changed_version_leave_previous_package_intact(self):
        self.save();client=self.remoteClient();client.download(self.cid)
        image=service.upload(self.admin,'one.png','image',photo()['data']);self.save(document(asset=image['assetId']),revision=1)
        original=client.request
        def broken(method,path,*args,**kwargs):
            if '/assets/' in path:raise ApiError('lost connection')
            return original(method,path,*args,**kwargs)
        with patch.object(client,'request',side_effect=broken):
            with self.assertRaises(ApiError):client.download(self.cid)
        self.assertEqual(client.cached(self.cid)[0]['revision'],1)
        with patch.object(client,'detail',side_effect=[service.detail(self.reader,self.cid),{**service.detail(self.reader,self.cid),'revision':3}]):
            with self.assertRaises(ValueError):client.download(self.cid)
        self.assertEqual(client.cached(self.cid)[0]['revision'],1)

    def test_cache_limit_is_atomic_and_never_evicts_existing_copy(self):
        self.save();client=self.remoteClient();client.download(self.cid)
        self.save(revision=1)
        with patch('catalog_client.MAX_CACHE_BYTES',1):
            with self.assertRaises(ValueError):client.download(self.cid)
        self.assertEqual(client.cached(self.cid)[0]['revision'],1)

    def test_updates_subscriptions_notifications_and_revision_progress(self):
        self.save();client=self.remoteClient();client.index();client.subscribe('Животные',True)
        client.download(self.cid);client.savePersonal(self.cid,1,[0],True,'Заметка')
        self.save(revision=1);client.index();client.index()
        with patch('catalog_client.getApiUrl',return_value=client.url):items=catalogNotices(client.user)
        self.assertEqual(len(items),1)
        client.download(self.cid)
        self.assertEqual(client.cached(self.cid)[0]['revision'],2)
        self.assertEqual(client.personal(self.cid)['revision'],1)
        self.assertTrue(client.personal(self.cid)['favorite'])

    def test_model_cache_loads_in_existing_renderer_without_personal_import(self):
        from model_service import loadModel,getModel
        model=service.upload(self.admin,'triangle.obj','model',b'v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n')
        doc=document('model');doc['modelAsset']=model['assetId'];self.save(doc)
        client=self.remoteClient();client.download(self.cid)
        with patch('api_client.getApiUrl',return_value=client.url):
            self.assertTrue(getModel('catalog-'+self.cid,self.other)['catalog'])
            self.assertEqual(len(loadModel('catalog-'+self.cid,self.other).faces),1)
        with db.openDatabase() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM importedModels').fetchone()[0],0)

    def test_http_rejects_large_document_and_wrong_media_hash(self):
        response=self.http.put('/admin/catalog/'+self.cid,headers={**self.headers,'Content-Type':'application/json'},content=b' '*102401)
        self.assertEqual(response.status_code,413)
        image=service.upload(self.admin,'one.png','image',photo()['data']);self.save(document(asset=image['assetId']))
        client=self.remoteClient();original=client.request
        def corrupt(method,path,*args,**kwargs):
            data=original(method,path,*args,**kwargs)
            if '/assets/' in path:data['contentBase64']=base64.b64encode(b'corrupted').decode()
            return data
        with patch.object(client,'request',side_effect=corrupt):
            with self.assertRaises(ValueError):client.download(self.cid)
        self.assertEqual(client.downloads(),[])

    def test_known_offline_index_does_not_repeat_network_timeout(self):
        self.save();client=self.remoteClient();client.index()
        with patch('catalog_client.getSessionUser',return_value={**client.user,'offline':True}),patch('catalog_client.apiRequest') as network:
            self.assertEqual(client.index()[0]['contentId'],self.cid)
            self.assertEqual(client.index()[0]['contentId'],self.cid)
            network.assert_not_called()

    def test_video_ticket_ranges_and_owner_revocation(self):
        from catalog_media import videoTicket,media
        from starlette.applications import Starlette
        from starlette.routing import Route
        # Container structure validation is separate from codec decoding on the device.
        clip=b'\0\0\0\x10ftypisom\0\0\0\0'+b'\0\0\0\x08moov'+b'\0\0\0\x0cmdatdata'
        video=service.upload(self.admin,'clip.mp4','video',clip)
        asset=service.asset(self.admin,video['assetId'])
        user=dict(userId=self.reader,sessionToken=self.readerToken)
        with patch('catalog_media.getApiUrl',return_value=''),patch('catalog_media.getSessionUser',return_value=user):
            token=videoTicket(user,asset)
            with TestClient(Starlette(routes=[Route('/media/{ticket}',media,methods=['GET','HEAD'])])) as browser:
                result=browser.get('/media/'+token,headers={'Range':'bytes=4-7'})
                self.assertEqual(result.status_code,206);self.assertEqual(result.content,b'ftyp')
                self.assertEqual(browser.get('/media/'+token,headers={'Range':'bytes=999-'}).status_code,416)
                self.assertEqual(browser.head('/media/'+token).headers['content-length'],str(len(clip)))
                with patch('catalog_media.getSessionUser',return_value=None):self.assertEqual(browser.get('/media/'+token).status_code,401)


class CatalogUiTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        import test_startup
        test_startup.StartupTests.setUp(self)
        with db.openDatabase() as c:c.execute("UPDATE users SET roleName='admin' WHERE userId=?",(self.user['userId'],))
        self.user['roleName']='admin';self.page.session.set('currentUser',self.user)
        for target in ['catalog_client.getApiUrl','api_client.getApiUrl']:
            p=patch(target,return_value='');p.start();self.addCleanup(p.stop)
    def tearDown(self):
        import test_startup
        test_startup.StartupTests.tearDown(self)
    async def test_editor_saves_structured_lesson_detail_restores_checklist(self):
        import flet as ft
        from views.learning_catalog import createCatalogEditor,createCatalogDetail,createCatalogView
        from test_startup import find,walk
        view=createCatalogEditor(self.page,'new-lesson');self.page.views[:]=[view];self.page.update()
        find(view,ft.TextField,label='Название материала').value='Мой новый урок'
        find(view,ft.TextField,label='Описание материала').value='Подробное описание нового урока лепки'
        find(view,ft.TextField,label='Материалы и инструменты — по одному на строку').value='Пластилин\nСтек'
        find(view,ft.TextButton,text='Добавить этап').on_click(None)
        find(view,ft.TextField,label='Текст этапа').value='Скатайте шарик для головы'
        find(view,ft.Dropdown,label='Состояние материала').value='published'
        find(view,ft.FilledButton,text='Сохранить материал').on_click(None)
        cid=service.listing(self.user['userId'])[0]['contentId']
        client=CatalogClient(self.user);client.download(cid)
        view=createCatalogDetail(self.page,cid);self.page.views[:]=[view];self.page.update()
        box=find(view,ft.Checkbox,label='Этап выполнен');box.value=True;box.on_change(None)
        self.assertEqual(json.loads(client.personal(cid)['checkedJson']),[0])
        self.assertEqual(service.statistics(self.user['userId'])['items'][0]['completed'],1)
        view=createCatalogView(self.page)
        self.assertTrue(any(isinstance(c,ft.Text) and c.value=='Мой новый урок' for c in walk(view)))
