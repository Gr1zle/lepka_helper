"""User-visible final acceptance regressions; all data lives in temporary fixtures."""
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import flet as ft
import test_startup as h
import database as db
import challenge_service as challenges
from image_fixtures import photo
from views.challenge_view import createChallengeView
from views.discovery import openPostComposer

class FinalAcceptanceTests(unittest.IsolatedAsyncioTestCase):
    setUp=h.StartupTests.setUp
    tearDown=h.StartupTests.tearDown
    mount=h.StartupTests.mount

    async def test_challenge_shortcut_opens_prefilled_composer_and_returns_to_updated_challenge(self):
        with db.openDatabase() as c:c.execute("UPDATE users SET roleName='admin' WHERE userId=?",(self.user['userId'],))
        challenges.create(self.user['userId'],'Первое задание','Проверка разных идентификаторов',challenges.today())
        cid=challenges.create(self.user['userId'],'Учебное задание','Слепить учебную фигурку',challenges.today())
        self.page.session.set('openChallengeId',cid)
        root=self.mount(createChallengeView(self.page))
        h.find(root,ft.OutlinedButton,text='Опубликовать новую работу в конкурс').on_click(None)
        composer=self.page.views[-1]
        self.assertEqual(composer.route,'/discovery/compose')
        self.assertEqual(h.find(composer,ft.Dropdown,label='Участие в конкурсе').value,str(cid))
        h.find(composer,ft.TextField,label='Название работы').value='Работа для задания'
        h.find(composer,ft.TextField,label='Описание').value='Фигурка подготовлена для конкурса'
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'result.png';path.write_bytes(photo()['data'])
            h.find(composer,ft.OutlinedButton,text='Добавить фото').on_click(None)
            picker=next(c for c in reversed(self.page.overlay) if isinstance(c,ft.FilePicker))
            picker.on_result(SimpleNamespace(files=[SimpleNamespace(name=path.name,size=path.stat().st_size,path=str(path))]))
        h.find(composer,ft.ElevatedButton,text='Опубликовать').on_click(None)
        self.assertEqual(self.page.views[-1],root)
        self.assertIsNotNone(h.find(root,ft.OutlinedButton,text='Отозвать мою заявку'))
        self.assertEqual(challenges.detail(self.user['userId'],cid)['entriesCount'],1)

    async def test_duplicate_composer_entry_returns_existing_page(self):
        self.mount(ft.View('/home'))
        first=openPostComposer(self.page,self.user)
        for _ in range(30):self.assertIs(openPostComposer(self.page,self.user),first)
        self.assertEqual(len(self.page.views),2)

    async def test_late_composer_success_does_not_refresh_another_account(self):
        captured=[];changed=[]
        def body(*args,**kwargs):captured.append(kwargs['onPublished']);return ft.ListView()
        self.mount(ft.View('/home'))
        with patch('views.community_tab.createHomeTab',side_effect=body):view=openPostComposer(self.page,self.user,onPublished=lambda:changed.append(True))
        self.page.session.set('currentUser',dict(userId=999,sessionToken='other'))
        captured[0]()
        self.assertEqual(changed,[])

    async def test_android_project_json_uses_document_writer_with_real_archive(self):
        import base64,json
        from unittest.mock import Mock
        from project_service import saveProject
        from project_archive import decodeProject
        from views.project_transfer import createProjectExport
        ok,message,project=saveProject(self.user['userId'],'Перенос на телефон','Животные','','')
        self.assertTrue(ok,message)
        self.page._set_attr('platform','android');self.page._set_attr('web','false')
        root=self.mount(ft.View('/project',controls=[createProjectExport(self.page,self.user,project)]))
        bridge=Mock()
        with patch('secure_device.getProtectedSession',return_value=bridge),patch.object(ft.FilePicker,'save_file') as old,patch('views.project_transfer.saveBackup') as internal:
            h.find(root,ft.TextButton,text='Экспорт JSON').on_click(None)
            old.assert_not_called();internal.assert_called_once()
        op,value,finished=bridge.requestUi.call_args.args;payload=json.loads(value)
        self.assertEqual((op,payload['mime'],payload['name']),('fileSave','application/json','lepka-project.json'))
        content=base64.b64decode(payload['base64']);self.assertEqual(decodeProject(content)['project']['projectName'],'Перенос на телефон')
        finished(dict(ok=True,value=json.dumps(dict(bytes=len(content)))))
        self.assertTrue(any(isinstance(c,ft.SnackBar) and 'Файл сохранён' in c.content.value for c in self.page.overlay))

    async def test_android_personal_json_is_exported_not_only_saved_internally(self):
        import base64,json
        from unittest.mock import Mock
        from views.personal_data import createPersonalDataButton
        from personal_snapshot import decodeSnapshot
        from project_service import saveProject
        saveProject(self.user['userId'],'Личный архив телефона','Животные','','')
        self.page._set_attr('platform','android');self.page._set_attr('web','false')
        root=self.mount(ft.View('/profile',controls=[createPersonalDataButton(self.page,self.user)]))
        h.find(root,ft.TextButton,text='Личные данные и синхронизация').on_click(None)
        dialog=next(c for c in reversed(self.page.overlay) if isinstance(c,ft.AlertDialog) and c.open)
        bridge=Mock()
        with patch('secure_device.getProtectedSession',return_value=bridge),patch('views.personal_data.saveCheckpoint') as internal:
            h.find(dialog,ft.TextButton,text='Экспорт полного JSON').on_click(None);internal.assert_not_called()
        op,value,finished=bridge.requestUi.call_args.args;payload=json.loads(value)
        self.assertEqual((op,payload['mime'],payload['name']),('fileSave','application/json','lepka-personal.json'))
        document=decodeSnapshot(base64.b64decode(payload['base64']))[0]
        self.assertTrue(any(p['archive']['project']['name']=='Личный архив телефона' for p in document['projects']))
        finished(dict(ok=True,value='{"cancelled":true}'))
        self.assertTrue(dialog.open)

    async def test_color_fullscreen_repeated_done_keeps_one_dialog_and_sample(self):
        from views.color_scan import openColorScan
        captured=[];applied=[]
        self.mount(ft.View('/home'))
        with patch('views.color_scan.createPhotoPicker',side_effect=lambda page,user,fn,*args:(captured.append(fn) or ft.Container())):
            openColorScan(self.page,self.user,applied.append,lambda color:None)
        captured[0](photo());scan=next(c for c in reversed(self.page.overlay) if isinstance(c,ft.AlertDialog) and c.open)
        for _ in range(3):
            h.find(scan,ft.TextButton,text='Открыть фото во весь экран').on_click(None)
            viewer=h.find(scan,ft.InteractiveViewer)
            h.find(viewer,ft.GestureDetector).on_tap_up(SimpleNamespace(local_x=183,local_y=270))
            done=h.find(scan,ft.FilledButton,text='Готово').on_click
            done(None);done(None)
            self.assertTrue(scan.open);self.assertEqual(scan.title.value,'Цвет с камеры или фото')
            self.assertEqual(len(self.page.views),1)
            self.assertEqual(applied,[])
        h.find(scan,ft.TextButton,text='В целевой HEX').on_click(None)
        self.assertEqual(applied,['#FF6B6B'])
