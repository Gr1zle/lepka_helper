"""Сроки, границы календаря и устойчивые личные напоминания."""
from datetime import date, timedelta
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import database as db
from project_service import saveProject, editProject, saveProjectStep, changeProjectStepStatus, removeProject, saveProjectStepPhoto
from image_fixtures import photo
from project_planner import monthPlan, plannerProjects, syncProjectReminders, markProjectRemindersRead


class PlannerTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory(); self.addCleanup(folder.cleanup)
        patched = patch.object(db,'DATABASE_PATH',Path(folder.name)/'test.db')
        patched.start(); self.addCleanup(patched.stop)
        db.initializeDatabase()
        self.owner = db.createUser('one@example.com','hash','salt','one')
        self.other = db.createUser('two@example.com','hash','salt','two')
        self.today = date(2028,2,28)

    def project(self, delta=None, owner=None):
        deadline = (self.today+timedelta(days=delta)).strftime('%d.%m.%Y') if delta is not None else ''
        return saveProject(self.owner if owner is None else owner,'Фигурка','Другое',deadline,'')[2]

    def test_calendar_is_monday_first_counts_active_deadlines_and_handles_leap_year(self):
        self.project(1); self.project(1); self.project(2)
        completed = self.project(0)
        step = saveProjectStep(completed,'Подготовить основу',self.owner)[2]
        saveProjectStepPhoto(completed,step,self.owner,photo())
        changeProjectStepStatus(completed,step,True,self.owner)
        self.project(1,self.other)
        plan = monthPlan(self.owner,2028,2,today=self.today)
        self.assertEqual(plan['weeks'][0],[0,1,2,3,4,5,6])
        self.assertEqual(plan['counts'],{29:2})
        self.assertEqual(len(plan['items']),2)
        self.assertEqual(len(monthPlan(self.owner,2028,2,selectedDay=28,today=self.today)['items']),0)
        self.assertEqual(len(monthPlan(self.owner,2028,3,today=self.today)['items']),1)

    def test_filters_include_boundaries_and_old_invalid_dates_without_crashing(self):
        overdue = self.project(-1); today = self.project(0); week = self.project(7)
        far = self.project(8); undated = self.project()
        with db.openDatabase() as c:
            c.execute("UPDATE projects SET deadlineDate='31.02.2028' WHERE projectId=?",(undated,))
        def ids(filterName):
            return [p['projectId'] for p in monthPlan(self.owner,2028,2,filterName,today=self.today)['items']]
        self.assertEqual(ids('Просрочены'),[overdue])
        self.assertEqual(ids('Ближайшие 7 дней'),[today,week])
        self.assertEqual(ids('Без срока'),[undated])
        self.assertEqual(len(ids('Все активные')),5)
        self.assertIn(far,ids('Все активные'))
        self.assertEqual(plannerProjects(self.owner,self.today)[-1]['status'],'Проверьте дату')

    def test_invalid_month_day_and_filter_are_rejected(self):
        for args in ((2027,2,'Месяц',29),(2028,13,'Месяц',None),(0,1,'Месяц',None),
                     (True,1,'Месяц',None),(2028,1,'invalid',None)):
            with self.subTest(args=args),self.assertRaises(ValueError):monthPlan(self.owner,*args)
        self.assertEqual(monthPlan(self.owner,9999,12)['weeks'][-1][-3:],[31,0,0])

    def test_reminders_are_deduplicated_persist_read_state_and_add_only_current_milestone(self):
        self.project(2); self.project(3); self.project(); self.project(0,self.other)
        rows = syncProjectReminders(self.owner,today=self.today)
        self.assertEqual([r['kind'] for r in rows],['2'])
        reminder = rows[0]['reminderId']
        markProjectRemindersRead(self.owner,reminder)
        db.initializeDatabase()
        rows = syncProjectReminders(self.owner,today=self.today)
        self.assertEqual(len(rows),1); self.assertEqual(rows[0]['isRead'],1)
        self.assertEqual(rows[0]['reminderId'],reminder)
        rows = syncProjectReminders(self.owner,today=self.today+timedelta(days=2))
        self.assertEqual({r['kind'] for r in rows},{'2','0','1'})
        self.assertEqual(len(rows),3)  # Пропущенный день не создаётся задним числом.

    def test_overdue_reminder_is_not_repeated_every_day_and_other_owner_cannot_read_it(self):
        self.project(-2)
        rows = syncProjectReminders(self.owner,today=self.today)
        reminder = rows[0]['reminderId']
        self.assertEqual(markProjectRemindersRead(self.other,reminder),0)
        self.assertEqual(len(syncProjectReminders(self.owner,today=self.today+timedelta(days=4))),1)
        self.assertEqual(syncProjectReminders(self.other,today=self.today),[])
        self.assertEqual(markProjectRemindersRead(self.owner),1)

    def test_move_deadline_complete_delete_and_delete_account_remove_old_notices(self):
        project = self.project(0)
        self.assertEqual(len(syncProjectReminders(self.owner,today=self.today)),1)
        editProject(project,self.owner,'Фигурка','Другое','15.03.2028','')
        self.assertEqual(syncProjectReminders(self.owner,today=self.today),[])
        editProject(project,self.owner,'Фигурка','Другое','28.02.2028','')
        self.assertEqual(len(syncProjectReminders(self.owner,today=self.today)),1)
        step = saveProjectStep(project,'Подготовить основу',self.owner)[2]
        saveProjectStepPhoto(project,step,self.owner,photo())
        changeProjectStepStatus(project,step,True,self.owner)
        self.assertEqual(syncProjectReminders(self.owner,today=self.today),[])
        changeProjectStepStatus(project,step,False,self.owner)
        self.assertEqual(len(syncProjectReminders(self.owner,today=self.today)),1)
        removeProject(project,self.owner)
        self.project(1); syncProjectReminders(self.owner,today=self.today)
        self.assertTrue(db.deleteUserDataById(self.owner))
        with db.openDatabase() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM projectReminders').fetchone()[0],0)

    def test_disabled_or_blocked_user_gets_no_notices_and_existing_read_state_is_retained(self):
        self.project(0)
        self.assertEqual(syncProjectReminders(self.owner,False,self.today),[])
        rows = syncProjectReminders(self.owner,True,self.today)
        markProjectRemindersRead(self.owner)
        self.assertEqual(syncProjectReminders(self.owner,False,self.today),[])
        self.assertEqual(syncProjectReminders(self.owner,True,self.today)[0]['isRead'],1)
        with db.openDatabase() as c:c.execute('UPDATE users SET isBlocked=1 WHERE userId=?',(self.owner,))
        self.assertEqual(syncProjectReminders(self.owner,True,self.today),[])
        self.assertEqual(plannerProjects(self.owner,self.today),[])
        self.assertEqual(markProjectRemindersRead(self.owner,rows[0]['reminderId']),0)

    def test_hundred_limit_is_stable_with_many_projects_and_does_not_recreate_unread_on_refresh(self):
        for _ in range(110):self.project(0)
        rows = syncProjectReminders(self.owner,today=self.today)
        self.assertEqual(len(rows),100)
        before = {r['reminderId'] for r in rows}
        markProjectRemindersRead(self.owner)
        for _ in range(3):
            rows = syncProjectReminders(self.owner,today=self.today)
            self.assertEqual({r['reminderId'] for r in rows},before)
            self.assertTrue(all(r['isRead'] for r in rows))
