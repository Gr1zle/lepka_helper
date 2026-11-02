"""Explicit project completion, drag drafts, and portable stage metadata."""
import base64,json
from types import SimpleNamespace
from unittest.mock import patch
import unittest
import flet as ft
import test_startup as harness
import database as db
import project_service as p
from project_archive import exportProject,importProject,decodeProject
from personal_snapshot import exportSnapshot,applySnapshot
from project_sharing import publishProject,readPublishedProject
from workshop_service import addWorkshopAsProject
from image_fixtures import photo

class WorkflowTests(unittest.IsolatedAsyncioTestCase):
    setUp=harness.StartupTests.setUp
    tearDown=harness.StartupTests.tearDown
    mount=harness.StartupTests.mount
    def project(self):return p.saveProject(self.user['userId'],'Котик','Животные','','Приватные заметки')[2]
    def step(self,pid,title='Основа',details='Размять материал'):
        ok,msg,sid=p.saveStep(pid,self.user['userId'],title,details);self.assertTrue(ok,msg);return sid
    def complete(self,pid):
        for s in p.getProjectSteps(pid,self.user['userId']):p.changeProjectStepStatus(pid,s['stepId'],True,self.user['userId'])
        p.saveFinalPhoto(pid,self.user['userId'],photo())
        self.assertTrue(p.finishProject(pid,self.user['userId'])[0])

    async def test_personal_steps_without_photo_need_explicit_final_completion(self):
        pid=self.project();sid=self.step(pid)
        self.assertEqual(p.changeProjectStepStatus(pid,sid,True,self.user['userId']),100)
        self.assertFalse(db.getProjectById(pid,self.user['userId'])['isFinished'])
        self.assertFalse(p.finishProject(pid,self.user['userId'])[0])
        p.saveFinalPhoto(pid,self.user['userId'],photo())
        self.assertTrue(p.finishProject(pid,self.user['userId'])[0])
        row=db.getProjectById(pid,self.user['userId']);self.assertTrue(row['completedAt'])
        self.assertFalse(p.removeFinalPhoto(pid,self.user['userId'])[0])
        p.changeProjectStepStatus(pid,sid,False,self.user['userId'])
        row=db.getProjectById(pid,self.user['userId']);self.assertFalse(row['isFinished']);self.assertIsNone(row['completedAt'])

    async def test_zero_stage_project_can_finish_and_reopen_with_final_photo(self):
        pid=self.project();self.complete(pid)
        self.assertEqual(p.refreshProjectProgress(pid,self.user['userId']),100)
        self.assertTrue(p.finishProject(pid,self.user['userId'],False)[0])
        self.assertEqual(db.getProjectById(pid,self.user['userId'])['progressPercent'],0)
        self.assertTrue(p.removeFinalPhoto(pid,self.user['userId'])[0])

    async def test_other_owner_cannot_edit_finish_or_read_final_photo(self):
        pid=self.project();sid=self.step(pid)
        other=db.createUser('other@example.com','hash','salt','other')
        self.assertFalse(p.saveStep(pid,other,'Другой','',sid)[0])
        self.assertFalse(p.saveFinalPhoto(pid,other,photo())[0])
        self.assertFalse(p.finishProject(pid,other)[0])
        self.assertIsNone(db.projectFinalPhoto(pid,other))
        self.assertEqual(p.getProjectSteps(pid,self.user['userId'])[0]['details'],'Размять материал')

    async def test_archive_and_snapshot_roundtrip_preserve_details_result_and_finish(self):
        pid=self.project();self.step(pid);self.complete(pid)
        content=exportProject(pid,self.user['userId']);self.assertEqual(json.loads(content)['version'],2)
        other=db.createUser('other@example.com','hash','salt','other')
        restored=importProject(other,content)
        self.assertTrue(db.getProjectById(restored,other)['isFinished'])
        self.assertEqual(p.getProjectSteps(restored,other)[0]['details'],'Размять материал')
        snapshot=exportSnapshot(self.user['userId'])
        with db.openDatabase() as c:applySnapshot(other,snapshot,c)
        self.assertEqual(snapshot,exportSnapshot(other))

    async def test_legacy_v1_project_remains_importable(self):
        body={'format':'lepka-helper-project','version':1,'project':{'name':'Старый котик','category':'Животные','deadline':'','notes':''},
            'steps':[{'description':'Подготовить материал','completed':True,'photo':None}],'mixtures':[]}
        pid=importProject(self.user['userId'],json.dumps(body).encode())
        self.assertTrue(p.getProjectSteps(pid,self.user['userId'])[0]['isCompleted'])
        self.assertFalse(db.getProjectById(pid,self.user['userId'])['isFinished'])

    async def test_migration_preserves_old_title_photo_order_and_completion_date(self):
        pid=self.project();sid=self.step(pid);p.saveProjectStepPhoto(pid,sid,self.user['userId'],photo())
        old=db.getProjectStepPhoto(pid,sid,self.user['userId'])
        with db.openDatabase() as c:
            c.execute("UPDATE projects SET progressPercent=100,completedAt='2026-01-02T03:04:05Z' WHERE projectId=?",(pid,))
            for column in ('finalPhotoImage','isFinished'):c.execute('ALTER TABLE projects DROP COLUMN '+column)
            c.execute('ALTER TABLE projectSteps DROP COLUMN detailsText')
        db.initializeDatabase();db.initializeDatabase()
        row=db.getProjectById(pid,self.user['userId'])
        self.assertTrue(row['isFinished']);self.assertEqual(row['completedAt'],'2026-01-02T03:04:05Z')
        self.assertEqual(db.projectFinalPhoto(pid,self.user['userId']),old)
        self.assertEqual(p.getProjectSteps(pid,self.user['userId'])[0]['title'],'Основа')

    async def test_publication_requires_selected_stage_photos_and_keeps_structured_copy(self):
        pid=self.project();sid=self.step(pid);self.complete(pid)
        args=(pid,self.user['userId'],'Учебный котик','Работа с подробными этапами','Животные','лепка',None,[sid],[])
        self.assertFalse(publishProject(*args)[0])
        p.saveProjectStepPhoto(pid,sid,self.user['userId'],photo())
        ok,msg,postId=publishProject(*args);self.assertTrue(ok,msg)
        with db.openDatabase() as c:
            raw=c.execute('SELECT projectDetailsJson FROM posts WHERE postId=?',(postId,)).fetchone()[0]
        public=readPublishedProject(raw)
        self.assertEqual(public['steps'][0]['title'],'Основа');self.assertTrue(public['steps'][-1]['result'])
        self.assertNotIn('Приватные',raw)
        ok,msg,newId=addWorkshopAsProject(postId,self.user['userId']);self.assertTrue(ok,msg)
        copy=p.getProjectSteps(newId,self.user['userId'])
        self.assertEqual(len(copy),1);self.assertEqual(copy[0]['details'],'Размять материал')
        self.assertIsNone(db.projectFinalPhoto(newId,self.user['userId']))

    async def test_drag_draft_replaces_list_and_does_not_write_before_save(self):
        from views.project_step_order import createOrderEditor
        pid=self.project();ids=[self.step(pid,title) for title in ('Основа','Детали','Сборка')]
        saved=[];layout=createOrderEditor(self.page,self.user,pid,lambda:saved.append(True),lambda:None)
        root=self.mount(ft.View('/order',controls=[layout]));old=harness.find(root,ft.ReorderableListView)
        old.on_reorder(SimpleNamespace(old_index=2,new_index=0))
        current=harness.find(root,ft.ReorderableListView);self.assertIsNot(current,old)
        self.assertEqual([s['stepId'] for s in p.getProjectSteps(pid,self.user['userId'])],ids)
        # A late duplicate event from the disposed list cannot move twice.
        old.on_reorder(SimpleNamespace(old_index=2,new_index=0))
        harness.find(root,ft.ElevatedButton,text='Сохранить порядок').on_click(None)
        self.assertEqual([s['stepId'] for s in p.getProjectSteps(pid,self.user['userId'])],[ids[2],ids[0],ids[1]])
        self.assertEqual(saved,[True])

    async def test_editor_keeps_delete_behind_confirmation_and_photo_as_an_icon(self):
        from views.project_editor import createProjectEditor
        pid=self.project();sid=self.step(pid)
        view=self.mount(ft.View('/editor',controls=[createProjectEditor(self.page,self.user,pid)]))
        self.assertIsNotNone(harness.find(view,ft.IconButton,tooltip='Фото этапа'))
        self.assertFalse(any(isinstance(c,ft.TextButton) and c.text=='Удалить этап' for c in harness.walk(view)))
        harness.find(view,ft.IconButton,tooltip='Редактировать этап').on_click(None)
        harness.find(view,ft.TextButton,text='Удалить этап').on_click(None)
        self.assertEqual(len(p.getProjectSteps(pid,self.user['userId'])),1)
        harness.find(view,ft.FilledButton,text='Подтвердить удаление').on_click(None)
        self.assertEqual(p.getProjectSteps(pid,self.user['userId']),[])

    async def test_stage_limit_keeps_new_projects_exportable(self):
        pid=self.project()
        with db.openDatabase() as c:
            c.executemany('INSERT INTO projectSteps(projectId,stepDescription,sortOrder) VALUES (?,?,?)',[(pid,'Этап '+str(i),i) for i in range(100)])
        self.assertFalse(p.saveStep(pid,self.user['userId'],'Лишний этап')[0])
        self.assertEqual(len(decodeProject(exportProject(pid,self.user['userId']))['steps']),100)
