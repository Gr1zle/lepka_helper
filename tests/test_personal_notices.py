import json
from datetime import datetime,timedelta,timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch,Mock
import database as db
import personal_notices as notices
from lesson_service import getLessonById,saveUserLessonState
from notification_center import NoticeCenter
from project_service import saveProject


class PersonalNoticeTests(unittest.TestCase):
    def setUp(self):
        folder=tempfile.TemporaryDirectory(dir='/workspace/work' if Path('/workspace/work').exists() else None)
        self.addCleanup(folder.cleanup)
        p=patch.object(db,'DATABASE_PATH',Path(folder.name)/'notices.db');p.start();self.addCleanup(p.stop)
        db.initializeDatabase()
        self.user=db.createUser('one@example.com','','','one')
        self.other=db.createUser('two@example.com','','','two')
        self.now=datetime(2026,11,1,12,tzinfo=timezone.utc)

    def progress(self,complete=False,ago=4):
        lesson=getLessonById(1)
        state=dict(lastStep=1,completedSteps=list(range(len(lesson['steps']))) if complete else [0],checkedMaterials=[])
        saveUserLessonState(self.user,1,state)
        with db.openDatabase() as c:c.execute('UPDATE lessonProgress SET updatedAt=? WHERE userId=?',((self.now-timedelta(days=ago)).isoformat(),self.user))

    def test_resume_boundary_read_snooze_and_new_activity(self):
        self.progress(ago=2)
        self.assertEqual(notices.personalItems(self.user,now=self.now),[])
        self.progress(ago=3)
        item=notices.personalItems(self.user,now=self.now)[0]
        notices.snoozeLesson(self.other,item['noticeId'],1,now=self.now)
        self.assertEqual(len(notices.personalItems(self.user,now=self.now)),1)
        notices.snoozeLesson(self.user,item['noticeId'],1,now=self.now)
        self.assertEqual(notices.personalItems(self.user,now=self.now),[])
        self.assertEqual(notices.personalItems(self.user,now=self.now+timedelta(days=1))[0]['noticeId'],item['noticeId'])
        notices.readPersonal(self.other,item['noticeId'])
        self.assertFalse(notices.personalItems(self.user,now=self.now+timedelta(days=1))[0]['isRead'])
        notices.readPersonal(self.user,item['noticeId'])
        self.assertTrue(notices.personalItems(self.user,now=self.now+timedelta(days=1))[0]['isRead'])
        self.progress(ago=0)
        self.assertEqual(notices.personalItems(self.user,now=self.now),[])

    def test_completion_once_and_bad_legacy_progress_is_ignored(self):
        self.progress(complete=True)
        items=notices.personalItems(self.user,now=self.now)
        self.assertEqual([i['kind'] for i in items],['complete'])
        self.progress(complete=True,ago=0)
        self.assertEqual(len(notices.personalItems(self.user,now=self.now)),1)
        with db.openDatabase() as c:c.execute('UPDATE lessonProgress SET stateJson=? WHERE userId=?',('broken',self.user))
        self.assertEqual(len(notices.personalItems(self.user,now=self.now)),1)
        self.assertEqual(notices.personalItems(self.other,now=self.now),[])

    def test_settings_and_global_switch_do_not_reset_read_state(self):
        self.progress()
        saveProject(self.user,'Фигурка','Другое','01.11.2026','')
        items=notices.personalItems(self.user,now=self.now)
        self.assertEqual({i['source'] for i in items},{'projects','learning'})
        notices.readPersonal(self.user)
        notices.saveSettings(self.user,False,False,7)
        self.assertEqual(notices.personalItems(self.user,now=self.now),[])
        notices.saveSettings(self.user,True,True,3)
        self.assertTrue(all(i['isRead'] for i in notices.personalItems(self.user,now=self.now)))
        with db.openDatabase() as c:c.execute('UPDATE users SET notificationsEnabled=0 WHERE userId=?',(self.user,))
        self.assertEqual(notices.personalItems(self.user,now=self.now),[])
        for days in (0,31,True):
            with self.assertRaises(ValueError):notices.saveSettings(self.user,True,True,days)

    def test_deadline_date_uses_moscow_even_when_host_day_is_previous(self):
        saveProject(self.user,'Ночной проект','Другое','02.11.2026','')
        now=datetime(2026,11,1,22,tzinfo=timezone.utc)
        item=notices.personalItems(self.user,now=now)[0]
        self.assertEqual(item['createdAt'],'2026-11-02')
        self.assertIn('сегодня',item['preview'])

    def test_account_delete_cleans_personal_tables(self):
        self.progress();notices.personalItems(self.user,now=self.now);notices.saveSettings(self.user,True,True,3)
        db.deleteUserDataById(self.user)
        with db.openDatabase() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM learningNotices WHERE userId=?',(self.user,)).fetchone()[0],0)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM personalNoticeSettings WHERE userId=?',(self.user,)).fetchone()[0],0)
            self.assertEqual(c.execute('PRAGMA foreign_key_check').fetchall(),[])


class MergeNoticeTests(unittest.TestCase):
    def test_merged_pages_have_no_gaps_even_with_equal_timestamps(self):
        user={'userId':1,'sessionToken':'token'}
        remote=[dict(noticeId=-i,kind='like',createdAt='2026-11-01 12:00:00',isRead=False) for i in range(1,401)]
        local=[dict(noticeId='lesson:'+str(i),source='learning',kind='resume',createdAt='2026-11-01 12:00:00',isRead=False) for i in range(100)]
        with patch('notification_center.ChallengeClient') as cls:
            client=cls.return_value;client.notices.side_effect=lambda offset,kind,unread:remote[offset:offset+50]
            center=NoticeCenter(user)
            with patch.object(center,'local',return_value=local):
                allItems=[item for offset in range(0,500,50) for item in center.notices(offset)]
            ids=[i['noticeId'] for i in allItems]
            self.assertEqual(len(ids),500);self.assertEqual(len(set(ids)),500)
            self.assertEqual(ids[:400],['community:'+str(-i) for i in range(1,401)])

    def test_namespaced_reads_and_source_filters(self):
        with patch('notification_center.ChallengeClient') as cls,patch('notification_center.readPersonal') as read:
            center=NoticeCenter({'userId':5})
            center.readNotice('community:-12');cls.return_value.readNotice.assert_called_once_with(-12)
            center.readNotice('lesson:12');read.assert_called_once_with(5,'lesson:12')
            with patch.object(center,'local',return_value=[]):self.assertEqual(center.notices(source='learning'),[])
            cls.return_value.notices.assert_not_called()


class ColorWheelTests(unittest.TestCase):
    def test_coordinates_and_cached_image(self):
        from color_wheel import createColorWheelBase64,getColorWheelHexAtPoint
        self.assertEqual(getColorWheelHexAtPoint(110,110,220),'#FFFFFF')
        self.assertEqual(getColorWheelHexAtPoint(220,110,220),'#FF0000')
        self.assertIsNone(getColorWheelHexAtPoint(0,0,220))
        createColorWheelBase64.cache_clear()
        first=createColorWheelBase64(220)
        self.assertEqual(createColorWheelBase64(220),first)
        self.assertEqual(createColorWheelBase64.cache_info().hits,1)
