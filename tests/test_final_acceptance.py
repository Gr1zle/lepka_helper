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
