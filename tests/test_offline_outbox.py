import json
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import flet as ft
import database as db
import offline_access
import community_outbox as outbox
from api_client import ApiError
from remote_account_cache import cacheRemoteUser
from publication_drafts import saveDraft,listDrafts,deleteDraft


class OfflineFixture(unittest.TestCase):
    def setUp(self):
        folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup);self.folder=Path(folder.name)
        for target,value in [('database.DATABASE_PATH',self.folder/'client.db'),('app_state.STATE_FILE',self.folder/'state.json'),('device_session.SESSION_FILE',self.folder/'device_session.json')]:
            p=patch(target,value);p.start();self.addCleanup(p.stop)
        for target in ('api_client.getApiUrl','account_gateway.getApiUrl','remote_account_cache.getApiUrl','offline_access.getApiUrl','community_outbox.getApiUrl','device_session.getApiUrl'):
            p=patch(target,return_value='https://api.example');p.start();self.addCleanup(p.stop)
        offline_access._verified.clear();offline_access._failed.clear()
        self.addCleanup(offline_access._verified.clear);self.addCleanup(offline_access._failed.clear)
        db.initializeDatabase();self.other=db.createUser('local@example.com','','','local')
        self.token='a'*64
        self.user=cacheRemoteUser(dict(userId=101,email='remote@example.com',nickname='Remote',roleName='user',sessionExpiresAt=time.time()+3600,themeMode='dark'),self.token)
        offline_access.registerVerified(self.user)

    def test_offline_identity_requires_verified_token_scope_and_expiry(self):
        self.assertTrue(offline_access.cachedUser(self.token)['offline'])
        self.assertIsNone(offline_access.cachedUser('unknown'))
        with patch('offline_access.getApiUrl',return_value='https://other.example'):self.assertIsNone(offline_access.cachedUser(self.token))
        with patch('offline_access.time.time',return_value=self.user['sessionExpiresAt']+1):self.assertIsNone(offline_access.cachedUser(self.token))
        from account_gateway import getSessionUser
        with patch('account_gateway.apiRequest',side_effect=ApiError('revoked',401)):
            self.assertIsNone(getSessionUser(self.token))
        self.assertIsNone(offline_access.cachedUser(self.token))

    def test_native_session_restore_uses_protected_record_and_never_plain_json(self):
        import device_session as sessions
        class Store:
            value=None
            def read(self):return self.value
            def write(self,value):self.value=value;return True
            def delete(self):self.value=None;return True
        storage=Store();values={'protectedSession':storage}
        page=SimpleNamespace(platform=ft.PagePlatform.ANDROID,web=False,data=None,session=SimpleNamespace(get=lambda k:values.get(k)))
        self.assertTrue(sessions.saveDeviceSession(page,self.user))
        self.assertFalse((self.folder/'device_session.json').exists())
        self.assertNotIn(self.token,(self.folder/'client.db').read_bytes().decode('latin1'))
        offline_access._verified.clear()
        with patch('account_gateway.apiRequest',side_effect=ApiError('offline')):
            restored=sessions.restoreDeviceSession(page)
        self.assertEqual(restored['userId'],self.user['userId']);self.assertTrue(restored['offline'])
        with patch('device_session.getApiUrl',return_value='https://different.example'):self.assertIsNone(sessions.restoreDeviceSession(page))
        storage.delete=lambda:(_ for _ in ()).throw(OSError('unavailable'))
        sessions.forgetDeviceSession(page)
        self.assertIsNone(sessions.restoreDeviceSession(page))

    def test_protected_storage_failure_has_no_plaintext_fallback(self):
        import device_session as sessions
        storage=SimpleNamespace(write=lambda value:(_ for _ in ()).throw(OSError('failed')))
        page=SimpleNamespace(platform=ft.PagePlatform.ANDROID,web=False,data=None,session=SimpleNamespace(get=lambda k:storage))
        self.assertFalse(sessions.saveDeviceSession(page,self.user))
        self.assertFalse((self.folder/'device_session.json').exists())

    def test_drafts_survive_reopen_and_are_scoped_by_owner_and_api(self):
        payload=dict(titleText='Мой черновик',descriptionText='Текст без фото',categoryName='Животные',tagsText='',photos=[],challengeId=None)
        key=saveDraft(self.user['userId'],'https://api.example',payload)
        self.assertEqual(listDrafts(self.user['userId'],'https://api.example')[0]['payload'],payload)
        self.assertEqual(listDrafts(self.other,'https://api.example'),[])
        self.assertEqual(listDrafts(self.user['userId'],'https://another.example'),[])
        with self.assertRaises(ValueError):saveDraft(self.other,'https://api.example',payload,key)
        deleteDraft(self.other,'https://api.example',key)
        self.assertEqual(len(listDrafts(self.user['userId'],'https://api.example')),1)
        for _ in range(9):saveDraft(self.user['userId'],'https://api.example',payload)
        with self.assertRaises(ValueError):saveDraft(self.user['userId'],'https://api.example',payload)

    def test_queue_owner_lease_cancellation_and_endpoint_change(self):
        payload=dict(postId=1,isLiked=True);key=outbox.enqueue(self.user,'https://api.example','like',payload)
        self.assertEqual(outbox.flush(self.user,'https://api.example',stillActive=lambda:False),0)
        with patch('community_outbox.apiRequest') as request:
            with db.openDatabase() as c:c.execute("UPDATE communityOutbox SET state='sending',leaseUntil=?",(time.time()+60,))
            self.assertEqual(outbox.flush(self.user,'https://api.example',force=True),0);request.assert_not_called()
            with patch('community_outbox.getApiUrl',return_value='https://other.example'),self.assertRaises(ApiError):outbox.flush(self.user,'https://api.example')
        self.assertEqual(outbox.entries({'userId':self.other},'https://api.example'),[])
        self.assertNotIn(self.token,outbox.result(self.user,'https://api.example',key)['payloadJson'])


import test_community_api as fixtures


class ReplayApiTests(unittest.TestCase):
    setUp=fixtures.CommunityApiTests.setUp
    publish=fixtures.CommunityApiTests.publish

    def test_like_and_comment_retries_are_idempotent_even_after_removal(self):
        post=self.publish();rid='a'*32
        body=dict(requestId=rid,kind='like',payload=dict(postId=post,isLiked=True))
        for _ in range(3):
            r=self.client.post('/community/actions',headers=self.reader,json=body)
            self.assertEqual(r.json()['data'],{'isLiked':True,'likesCount':1})
        body['payload']['isLiked']=False
        self.assertEqual(self.client.post('/community/actions',headers=self.reader,json=body).status_code,409)
        body['requestId']='b'*32
        self.assertEqual(self.client.post('/community/actions',headers=self.reader,json=body).json()['data']['likesCount'],0)
        comment=dict(requestId='c'*32,kind='comment',payload=dict(postId=post,commentText='Отложенный комментарий',replyToId=None))
        first=self.client.post('/community/actions',headers=self.reader,json=comment).json()['data']['commentId']
        self.assertEqual(self.client.post('/community/actions',headers=self.reader,json=comment).json()['data']['commentId'],first)
        self.client.delete('/community/comments/'+str(first),headers=self.reader)
        self.client.post('/community/actions',headers=self.reader,json=comment)
        with db.openDatabase() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM postComments WHERE postId=?',(post,)).fetchone()[0],0)

    def test_durable_publication_receipt_does_not_resurrect_deleted_work(self):
        body=fixtures.publicationPayload();first=self.publish(body)
        self.client.delete('/community/posts/'+str(first),headers=self.headers)
        self.assertEqual(self.client.post('/community/posts',headers=self.headers,json=body).json()['data'],first)
        with db.openDatabase() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM posts WHERE postId=?',(first,)).fetchone()[0],0)

    def test_outbox_recovers_lost_response_and_releases_heavy_payload(self):
        payload=fixtures.publicationPayload();payload.pop('requestId')
        user=dict(userId=self.owner,serverUserId=self.owner,sessionToken=self.token)
        url='https://api.example';failed={'value':False}
        def send(method,path,body=None,sessionToken=None,**kwargs):
            response=self.client.request(method,path,headers=self.headers,json=body)
            if response.status_code>=400:raise ApiError(response.json().get('detail','error'),response.status_code)
            if not failed['value']:failed['value']=True;raise ApiError('response lost')
            return response.json()
        with patch('community_outbox.getApiUrl',return_value=url),patch('community_outbox.requireCachedUser'),patch('community_outbox.apiRequest',side_effect=send):
            rid=outbox.enqueue(user,url,'publication',payload)
            with self.assertRaises(ApiError):outbox.flush(user,url,force=True)
            self.assertEqual(outbox.result(user,url,rid)['state'],'pending')
            self.assertEqual(outbox.flush(user,url,force=True),1)
            result=outbox.result(user,url,rid)
            self.assertEqual(result['state'],'done');self.assertEqual(result['payloadJson'],'{}')
            self.assertEqual(outbox.enqueue(user,url,'publication',payload,rid),rid)
        with db.openDatabase() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM posts WHERE userId=?',(self.owner,)).fetchone()[0],1)

    def test_comment_rate_limit_is_retryable_and_receipt_bypasses_repeat_rate_check(self):
        post=self.publish();last=None
        for i in range(5):
            body=dict(requestId=f'{i:032x}',kind='comment',payload=dict(postId=post,commentText='Комментарий номер '+str(i),replyToId=None))
            self.assertEqual(self.client.post('/community/actions',headers=self.reader,json=body).status_code,200);last=body
        self.assertEqual(self.client.post('/community/actions',headers=self.reader,json=last).status_code,200)
        last['requestId']='f'*32
        self.assertEqual(self.client.post('/community/actions',headers=self.reader,json=last).status_code,429)


class ConnectionMonitorTests(unittest.IsolatedAsyncioTestCase):
    async def test_monitor_refreshes_feed_and_survives_cleared_session_without_duplicate_loop(self):
        import asyncio
        from unittest.mock import Mock,AsyncMock
        from flet.core.session_storage import SessionStorage
        from connection_monitor import startConnectionMonitor
        user=dict(userId=3,serverUserId=2,apiUrl='https://api.example',sessionToken='token',sessionExpiresAt=time.time()+3600,offline=True)
        session=SessionStorage(None);session.set('currentUser',user);session.set('homeTab',0)
        refresh=Mock();session.set('refreshCommunityFeed',refresh)
        page=SimpleNamespace(data=None,session=session,route='/home',run_task=Mock())
        with patch('connection_monitor.getApiUrl',return_value=user['apiUrl']),patch('connection_monitor.apiRequest',return_value={'data':{}}),patch('connection_monitor.cacheRemoteUser',return_value={**user,'offline':False}),patch('connection_monitor.registerVerified'),patch('connection_monitor.flush',return_value=1):
            startConnectionMonitor(page)
            monitor=page.run_task.call_args.args[0]
            with patch('connection_monitor.asyncio.sleep',new=AsyncMock(side_effect=[None,asyncio.CancelledError])):
                with self.assertRaises(asyncio.CancelledError):await monitor()
            refresh.assert_called_once();self.assertEqual(session.get('connectionState'),'online')
            startConnectionMonitor(page);count=page.run_task.call_count
            session.clear();startConnectionMonitor(page)
            self.assertEqual(page.run_task.call_count,count)
