"""Реальный HTTP, транзакции модерации, bootstrap и смена полномочий."""
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from fastapi.testclient import TestClient
from backend.main import createApp
from scripts.manage_admin import grantAdmin
import database as db
import account_security as security
import moderation_service as service
from password_service import createPasswordHash
from test_community_api import publicationPayload

REASON='Нарушение правил: проверка модерации'


class ModerationTests(unittest.TestCase):
    def setUp(self):
        folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup)
        self.root=Path(folder.name)
        self.client=TestClient(createApp(folder.name));self.client.__enter__()
        self.addCleanup(self.client.__exit__,None,None,None)
        password,salt=createPasswordHash('Student123')
        self.admin=db.createUser('admin@example.com',password,salt,'Администратор')
        self.author=db.createUser('author@example.com',password,salt,'Автор')
        self.reader=db.createUser('reader@example.com',password,salt,'Читатель')
        grantAdmin(db.DATABASE_PATH,'admin@example.com')
        self.adminHeaders=self.login('admin@example.com')
        self.authorHeaders=self.login('author@example.com')
        self.readerHeaders=self.login('reader@example.com')
        response=self.client.post('/community/posts',json=publicationPayload(workshop=True),headers=self.authorHeaders)
        self.assertEqual(response.status_code,200,response.text)
        self.post=response.json()['data']
        response=self.client.post(f'/community/posts/{self.post}/comments',json={'commentText':'Комментарий для проверки жалобы'},headers=self.readerHeaders)
        self.comment=response.json()['data']

    def login(self,email):
        result=self.client.post('/auth/login',json={'email':email,'password':'Student123'})
        self.assertEqual(result.status_code,200,result.text)
        return {'Authorization':'Bearer '+result.json()['data']['sessionToken']}

    def report(self,kind='post',target=None):
        response=self.client.post('/community/reports',headers=self.readerHeaders,
            json=dict(targetType=kind,targetId=target or self.post,reason=REASON))
        self.assertEqual(response.status_code,200,response.text)
        return response.json()['data']

    def test_normal_user_and_guest_cannot_read_or_mutate_admin_endpoints_or_forge_actor(self):
        for path in ('/admin/reports','/admin/users','/admin/audit'):
            self.assertEqual(self.client.get(path).status_code,401)
            result=self.client.get(path,headers=self.readerHeaders)
            self.assertEqual(result.status_code,403)
            self.assertEqual(result.headers['cache-control'],'no-store')
        body=dict(targetType='post',targetId=self.post,reason=REASON)
        self.assertEqual(self.client.post('/admin/remove',headers=self.readerHeaders,json=body).status_code,403)
        self.assertEqual(self.client.put(f'/admin/users/{self.reader}',headers=self.readerHeaders,json=dict(role='admin',reason=REASON)).status_code,403)
        body['actorId']=self.admin
        self.assertEqual(self.client.post('/admin/remove',headers=self.adminHeaders,json=body).status_code,422)
        self.assertEqual(len(self.client.get('/community/posts').json()['data']['items']),1)

    def test_report_is_idempotent_and_daily_limit_does_not_duplicate(self):
        report=self.report()
        self.assertEqual(self.report(),report)
        rows=self.client.get('/admin/reports',headers=self.adminHeaders).json()['data']
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['material']['title'],'Серверный котик')
        for index in range(9):
            comment=db.createPostComment(self.post,self.author,'Ещё один комментарий для жалобы') if index<4 else None
            if comment is None:
                with db.openDatabase() as c:comment=c.execute('INSERT INTO postComments(postId,userId,commentText) VALUES (?,?,?)',(self.post,self.author,'Комментарий')).lastrowid
            self.report('comment',comment)
        result=self.client.post('/community/reports',headers=self.readerHeaders,json=dict(targetType='comment',targetId=self.comment,reason=REASON))
        self.assertEqual(result.status_code,400)
        self.assertEqual(self.report(),report)

    def test_post_removal_erases_photos_comments_likes_workshop_and_resolves_child_reports_atomically(self):
        self.report();self.report('comment',self.comment)
        item=self.client.get('/community/posts').json()['data']['items'][0];photo=item['photoIds'][0]
        self.client.post(f'/community/posts/{self.post}/like',headers=self.readerHeaders)
        result=self.client.post('/admin/remove',headers=self.adminHeaders,json=dict(targetType='post',targetId=self.post,reason=REASON))
        self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(self.client.get('/community/posts').json()['data']['items'],[])
        self.assertEqual(self.client.get(f'/community/photos/{photo}').status_code,404)
        self.assertEqual(self.client.get(f'/community/workshops/{self.post}').status_code,404)
        self.assertEqual(self.client.get(f'/community/posts/{self.post}/comments').status_code,404)
        self.assertEqual(self.client.get('/admin/reports',headers=self.adminHeaders).json()['data'],[])
        self.assertEqual(len(self.client.get('/admin/reports?status=resolved',headers=self.adminHeaders).json()['data']),2)
        audit=service.listAudit(self.admin)
        self.assertEqual(audit[0]['action'],'material.delete');self.assertEqual(audit[0]['reason'],REASON)
        with db.openDatabase() as c:self.assertEqual(c.execute('PRAGMA foreign_key_check').fetchall(),[])

    def test_comment_removal_keeps_post_and_other_comment_and_logs_reason(self):
        self.report('comment',self.comment)
        other=db.createPostComment(self.post,self.author,'Другой нормальный комментарий')
        self.assertTrue(service.removeMaterial(self.admin,'comment',self.comment,REASON))
        self.assertEqual([r['commentId'] for r in db.getCommentsByPostId(self.post)],[other])
        self.assertFalse(service.removeMaterial(self.admin,'comment',self.comment,REASON))
        self.assertEqual(len([r for r in service.listAudit(self.admin) if r['action']=='material.delete']),1)

    def test_rejected_report_keeps_material_and_stale_resolution_is_idempotent(self):
        report=self.report()
        self.assertTrue(service.resolveReport(self.admin,report,'rejected','Нарушение правил не подтверждено'))
        self.assertFalse(service.resolveReport(self.admin,report,'resolved',REASON))
        self.assertIsNotNone(service.listReports(self.admin,'rejected')[0]['material'])
        self.assertEqual(len(self.client.get('/community/posts').json()['data']['items']),1)

    def test_block_unblock_and_role_changes_revoke_sessions_and_recheck_live_role(self):
        old=self.readerHeaders['Authorization'].split()[1]
        self.assertTrue(service.changeUser(self.admin,self.reader,REASON,blocked=True))
        self.assertIsNone(security.getSessionUser(old))
        self.assertEqual(self.client.get('/auth/me',headers=self.readerHeaders).status_code,401)
        self.assertTrue(service.changeUser(self.admin,self.reader,REASON,blocked=False))
        self.assertIsNone(security.getSessionUser(old))
        self.readerHeaders=self.login('reader@example.com')
        self.assertTrue(service.changeUser(self.admin,self.reader,REASON,role='admin'))
        self.assertEqual(self.client.get('/admin/users',headers=self.readerHeaders).status_code,401)
        new=self.login('reader@example.com')
        self.assertEqual(self.client.get('/admin/users',headers=new).status_code,200)
        self.assertTrue(service.changeUser(self.admin,self.reader,REASON,role='user'))
        self.assertEqual(self.client.get('/admin/users',headers=new).status_code,401)
        with self.assertRaises(ValueError):service.changeUser(self.admin,self.admin,REASON,blocked=True)
        with self.assertRaises(ValueError):service.changeUser(self.admin,self.admin,REASON,role='user')

    def test_reason_validation_rollback_and_unicode_user_search(self):
        for reason in ('','коротко',' '*20,'x'*501):
            with self.assertRaises(ValueError):service.removeMaterial(self.admin,'post',self.post,reason)
        self.assertEqual([r['userId'] for r in service.listUsers(self.admin,'аВТОР')],[self.author])
        with patch('moderation_service.audit',side_effect=sqlite3.OperationalError('audit disk full')):
            with self.assertRaises(sqlite3.OperationalError):service.removeMaterial(self.admin,'post',self.post,REASON)
        self.assertEqual(len(self.client.get('/community/posts').json()['data']['items']),1)
        self.assertIsNotNone(db.getPostPhoto(self.client.get('/community/posts').json()['data']['items'][0]['photoIds'][0]))

    def test_report_deletion_retains_decisions_and_audit_without_dangling_owner(self):
        report=self.report();service.resolveReport(self.admin,report,'resolved',REASON)
        self.assertTrue(db.deleteUserDataById(self.reader))
        self.assertIsNone(service.listReports(self.admin,'all')[0]['reporterId'])
        self.assertTrue(db.deleteUserDataById(self.admin))
        with db.openDatabase() as c:
            self.assertTrue(c.execute('SELECT COUNT(*) FROM adminAudit').fetchone()[0])
            self.assertEqual(c.execute('PRAGMA foreign_key_check').fetchall(),[])

    def test_request_body_limit_and_failed_privilege_checks_do_not_log_success(self):
        self.assertEqual(self.client.post('/admin/remove',headers=self.adminHeaders,content=b'x'*8193).status_code,413)
        before=len(service.listAudit(self.admin))
        with self.assertRaises(service.ModerationDenied):service.removeMaterial(self.reader,'post',self.post,REASON)
        self.assertEqual(len(service.listAudit(self.admin)),before)

    def test_concurrent_report_retry_creates_single_report(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            results=list(pool.map(lambda _:service.reportMaterial(self.reader,'post',self.post,REASON),range(8)))
        self.assertEqual(len(set(results)),1)


class BootstrapTests(unittest.TestCase):
    def test_bootstrap_requires_existing_app_database_preserves_password_and_logs_and_is_repeatable(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'test.db'
            with self.assertRaises(ValueError):grantAdmin(path,'owner@example.com')
            self.assertFalse(path.exists())
            with patch.object(db,'DATABASE_PATH',path):
                db.initializeDatabase();owner=db.createUser('owner@example.com','existing hash','salt','owner')
                with patch('mail_service.requests.post') as mail:
                    self.assertTrue(grantAdmin(path,'owner@example.com'));self.assertFalse(grantAdmin(path,'owner@example.com'))
                    mail.assert_not_called()
                user=db.getUserByEmail('owner@example.com')
                self.assertEqual(user['passwordHash'],'existing hash');self.assertEqual(user['roleName'],'admin')
                self.assertEqual(len(service.listAudit(owner)),1)
