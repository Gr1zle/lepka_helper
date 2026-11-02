import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import database as db
from delivery_settings import DEFAULTS, getSettings, saveSettings
from device_notifications import buildPlan, ownerKey
from mail_service import MailDeliveryError, sendNotification
from notification_mail import collect, deliver
from project_service import saveProject


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        directory=tempfile.TemporaryDirectory();self.addCleanup(directory.cleanup)
        p=patch.object(db,'DATABASE_PATH',Path(directory.name)/'delivery.db');p.start();self.addCleanup(p.stop)
        db.initializeDatabase()
        self.uid=db.createUser('delivery@example.com','','','reader')
        self.other=db.createUser('other@example.com','','','other')
        self.user=dict(userId=self.uid)
        self.now=datetime(2026,11,2,6,tzinfo=timezone.utc)

    def enable(self,**values):return saveSettings(self.uid,{**DEFAULTS,'deviceEnabled':True,**values})

    def project(self,date='04.11.2026',name='Фигура'):
        return saveProject(self.uid,name,'Другое',date,'')

    def test_plan_has_three_moscow_deadlines_and_no_other_owner(self):
        self.enable();self.project()
        saveProject(self.other,'Чужой','Другое','04.11.2026','')
        items=buildPlan(self.user,self.now)['items']
        self.assertEqual(len(items),3)
        self.assertEqual([datetime.fromtimestamp(i['at']/1000,timezone.utc).hour for i in items],[7,7,7])
        self.assertTrue(all('Фигура' in i['body'] for i in items))
        self.assertNotEqual(ownerKey(self.user),ownerKey(dict(userId=self.uid,apiUrl='http://192.168.1.2:8000',serverUserId=10)))

    def test_global_disable_project_change_and_completion_remove_alarms(self):
        self.enable();self.project()
        with db.openDatabase() as c:pid=c.execute('SELECT projectId FROM projects WHERE userId=?',(self.uid,)).fetchone()[0]
        before=buildPlan(self.user,self.now)['items']
        with db.openDatabase() as c:c.execute("UPDATE projects SET deadlineDate='05.11.2026' WHERE projectId=?",(pid,))
        after=buildPlan(self.user,self.now)['items']
        self.assertTrue(set(i['key'] for i in before).isdisjoint(i['key'] for i in after))
        with db.openDatabase() as c:c.execute('UPDATE projects SET progressPercent=100 WHERE projectId=?',(pid,))
        self.assertEqual(buildPlan(self.user,self.now)['items'],[])
        self.project()
        with db.openDatabase() as c:c.execute('UPDATE users SET notificationsEnabled=0 WHERE userId=?',(self.uid,))
        self.assertEqual(buildPlan(self.user,self.now)['items'],[])

    def test_settings_are_opt_in_validated_and_owner_scoped(self):
        self.assertFalse(getSettings(self.uid)['deviceEnabled'])
        self.assertFalse(getSettings(self.uid)['emailEnabled'])
        self.enable(projects=False)
        self.assertTrue(getSettings(self.other)['projects'])
        with self.assertRaises(ValueError):saveSettings(self.uid,{**DEFAULTS,'likes':1})
        db.deleteUserDataById(self.uid)
        with db.openDatabase() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM deliverySettings WHERE userId=?',(self.uid,)).fetchone()[0],0)
            self.assertEqual(c.execute('PRAGMA foreign_key_check').fetchall(),[])

    def event(self):
        with db.openDatabase() as c:
            pid=c.execute("INSERT INTO posts(userId,titleText,descriptionText,categoryName) VALUES (?,'Работа','Описание','Другое')",(self.uid,)).lastrowid
            c.execute("INSERT INTO activityNotices(userId,actorId,kind,postId,eventKey,createdAt) VALUES (?,?,'like',?,'event',?)",(self.uid,self.other,pid,self.now.isoformat()))
            c.execute('UPDATE notificationMailState SET since=? WHERE userId=?',((self.now-timedelta(seconds=1)).isoformat(),self.uid))

    def test_mail_disabled_does_not_collect_or_contact_provider(self):
        self.enable(emailEnabled=True);self.event()
        with patch.dict(os.environ,{'LEPKA_NOTIFICATION_MAIL_ENABLED':'0'}):
            self.assertEqual(deliver(send=lambda *a:self.fail('unexpected mail')),0)
        with db.openDatabase() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM notificationMailQueue').fetchone()[0],0)

    def test_mail_receipt_retry_same_key_and_opt_out(self):
        self.enable(emailEnabled=True);self.event();collect(self.now)
        calls=[]
        def fail(*args):calls.append(args);raise MailDeliveryError('temporary')
        with patch.dict(os.environ,{'LEPKA_NOTIFICATION_MAIL_ENABLED':'1'}),patch('notification_mail.collect'):
            self.assertEqual(deliver(send=fail,clock=lambda:self.now.timestamp()),0)
            self.assertEqual(deliver(send=lambda *args:calls.append(args),clock=lambda:self.now.timestamp()+31),1)
            self.assertEqual(deliver(send=lambda *a:self.fail('duplicate'),clock=lambda:self.now.timestamp()+62),0)
        self.assertEqual(calls[0][-1],calls[1][-1])
        collect(self.now)
        with db.openDatabase() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM notificationMailQueue').fetchone()[0],1)

    def test_pending_mail_cancelled_after_disable_or_address_change(self):
        self.enable(emailEnabled=True);self.event();collect(self.now)
        self.enable(emailEnabled=False)
        with patch.dict(os.environ,{'LEPKA_NOTIFICATION_MAIL_ENABLED':'1'}),patch('notification_mail.collect'):
            self.assertEqual(deliver(send=lambda *a:self.fail('opted out'),clock=lambda:self.now.timestamp()),0)
        with db.openDatabase() as c:self.assertEqual(c.execute('SELECT state FROM notificationMailQueue').fetchone()[0],'cancelled')

    def test_mail_escapes_html_and_passes_idempotency_key(self):
        with patch.dict(os.environ,{'LEPKA_MAIL_API_KEY':'test','LEPKA_MAIL_FROM':'test@example.com'}),patch('mail_service.requests.post') as post:
            sendNotification('one@example.com','<script>','<img src=x>','a'*64)
        kwargs=post.call_args.kwargs
        self.assertIn('&lt;img',kwargs['json']['html'])
        self.assertNotIn('<script>',kwargs['json']['html'])
        self.assertEqual(kwargs['headers']['Idempotency-Key'],'lepka-notice-'+'a'*64)

    def test_learning_alarm_moves_after_snooze_and_disappears_on_completion(self):
        from lesson_service import saveUserLessonState, getLessonById
        from personal_notices import personalItems, snoozeLesson
        self.enable()
        state=dict(lastStep=1,completedSteps=[0],checkedMaterials=[])
        saveUserLessonState(self.uid,1,state)
        with db.openDatabase() as c:c.execute('UPDATE lessonProgress SET updatedAt=? WHERE userId=?',((self.now-timedelta(days=3)).isoformat(),self.uid))
        initial=buildPlan(self.user,self.now)['items']
        self.assertEqual(len(initial),1)
        item=next(i for i in personalItems(self.uid,now=self.now) if i['source']=='learning')
        snoozeLesson(self.uid,item['noticeId'],1,now=self.now)
        changed=buildPlan(self.user,self.now)['items']
        self.assertGreater(changed[0]['at'],initial[0]['at'])
        state['completedSteps']=list(range(len(getLessonById(1)['steps'])))
        saveUserLessonState(self.uid,1,state)
        self.assertEqual(buildPlan(self.user,self.now)['items'],[])

    def test_deadline_email_uses_only_uploaded_snapshot_and_excludes_completed(self):
        from personal_snapshot import exportSnapshot
        from personal_vault import saveSnapshot
        self.enable(emailEnabled=True);self.project('04.11.2026')
        collect(self.now)
        with db.openDatabase() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM notificationMailQueue').fetchone()[0],0)
        document=json.loads(exportSnapshot(self.uid))
        saveSnapshot(self.uid,0,'a'*32,document)
        collect(self.now)
        with db.openDatabase() as c:
            row=c.execute('SELECT * FROM notificationMailQueue').fetchone()
            self.assertTrue(row['eventKey'].startswith('project:'))
            self.assertIn('Фигура',row['body'])
        document['projects'][0]['completedAt']=self.now.isoformat()
        saveSnapshot(self.uid,1,'a'*32,document)
        with patch.dict(os.environ,{'LEPKA_NOTIFICATION_MAIL_ENABLED':'1'}),patch('notification_mail.collect'):
            self.assertEqual(deliver(send=lambda *a:self.fail('completed project'),clock=lambda:self.now.timestamp()),0)
        with db.openDatabase() as c:self.assertEqual(c.execute('SELECT state FROM notificationMailQueue').fetchone()[0],'cancelled')

    def test_ambiguous_delivery_is_not_retried_after_provider_dedup_window(self):
        self.enable(emailEnabled=True);self.event();collect(self.now)
        with db.openDatabase() as c:c.execute('UPDATE notificationMailQueue SET attempts=1')
        with patch.dict(os.environ,{'LEPKA_NOTIFICATION_MAIL_ENABLED':'1'}),patch('notification_mail.collect'):
            deliver(send=lambda *a:self.fail('unsafe late retry'),clock=lambda:self.now.timestamp()+24*3600)
        with db.openDatabase() as c:self.assertEqual(c.execute('SELECT state FROM notificationMailQueue').fetchone()[0],'review')


class DeliveryApiTests(unittest.TestCase):
    def test_auth_strict_settings_and_separate_owners(self):
        from fastapi.testclient import TestClient
        from backend.main import createApp
        from account_security import createSession
        with tempfile.TemporaryDirectory() as folder,TestClient(createApp(folder)) as client:
            one=db.createUser('one@example.com','','','one');two=db.createUser('two@example.com','','','two')
            with db.openDatabase() as c:
                first={'Authorization':'Bearer '+createSession(c,c.execute('SELECT * FROM users WHERE userId=?',(one,)).fetchone())['sessionToken']}
                second={'Authorization':'Bearer '+createSession(c,c.execute('SELECT * FROM users WHERE userId=?',(two,)).fetchone())['sessionToken']}
            self.assertEqual(client.get('/account/notification-delivery').status_code,401)
            values={**DEFAULTS,'emailEnabled':True}
            self.assertEqual(client.put('/account/notification-delivery',json=values,headers=first).status_code,200)
            self.assertFalse(client.get('/account/notification-delivery',headers=second).json()['data']['settings']['emailEnabled'])
            self.assertEqual(client.put('/account/notification-delivery',json={**values,'userId':two},headers=first).status_code,422)


class DeliveryUiTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        import test_startup
        test_startup.StartupTests.setUp(self)
    def tearDown(self):
        import test_startup
        test_startup.StartupTests.tearDown(self)

    async def test_device_preferences_save_without_network_and_mail_is_explicit(self):
        import flet as ft
        from test_startup import find
        from views.notification_delivery import openDeliverySettings
        with patch('views.notification_delivery.apiRequest') as request:
            openDeliverySettings(self.page,self.user)
            dialog=next(c for c in self.page.overlay if isinstance(c,ft.AlertDialog))
            find(dialog,ft.Switch,label='Уведомления Android').value=True
            find(dialog,ft.Switch,label='Лайки').value=False
            find(dialog,ft.FilledButton,text='Сохранить на устройстве').on_click(None)
            self.assertTrue(getSettings(self.user['userId'])['deviceEnabled'])
            self.assertFalse(getSettings(self.user['userId'])['likes'])
            self.assertFalse(getSettings(self.user['userId'])['emailEnabled'])
            request.assert_not_called()
