"""Regressions reproduced from Android feedback: taps, locale and no-contest publishing."""
import asyncio
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import flet as ft
import test_startup as h
import database as db
from community_gateway import CommunityClient
from image_fixtures import photo
from views.discovery import createPostTile,openPost,openCreate
from views.community_tab import createHomeTab
from views.auth_view import createAuthView
from views.profile_tab import createProfileTab
from views.contest_picker import createContestPicker,selectedContest,NO_CONTEST
from profile_service import getUserProfile
from localization import language
import post_service as posts
from api_client import ApiError

class InteractionFixTests(unittest.IsolatedAsyncioTestCase):
    setUp=h.StartupTests.setUp
    tearDown=h.StartupTests.tearDown
    mount=h.StartupTests.mount

    def post(self):return posts.savePost(self.user['userId'],'Готовая фигурка','Описание готовой фигурки','Животные','кот',[photo()])[2]

    async def test_thirty_taps_show_one_loading_page_and_make_one_detail_request(self):
        pid=self.post();client=CommunityClient(self.user)
        root=self.mount(ft.View('/home',controls=[createPostTile(self.page,client.getPost(pid),self.user)]))
        tile=h.find(root,ft.Semantics);gate=threading.Event();started=threading.Event()
        original=CommunityClient.getPostDetail
        def slow(client,pid):started.set();gate.wait(3);return original(client,pid)
        with patch.object(CommunityClient,'getPostDetail',slow),patch('ui_helpers.getCurrentUser',side_effect=AssertionError('Public opening fetched auth/me')):
            tile.on_tap(None)
            view=self.page.views[-1]
            self.assertIsNotNone(h.find(view,ft.ProgressRing))
            for _ in range(30):tile.on_tap(None)
            self.assertEqual(len(self.page.views),2)
            for _ in range(100):
                if started.is_set():break
                await asyncio.sleep(.01)
            self.assertTrue(started.is_set());gate.set()
            await asyncio.wrap_future(view._load_future)
        self.assertIsNotNone(h.find(view,ft.Text,value='Готовая фигурка'))
        self.assertEqual(len(self.page.views),2)

    async def test_back_before_slow_load_finishes_does_not_reopen_page(self):
        pid=self.post();self.mount(ft.View('/home'));gate=threading.Event()
        data=CommunityClient(self.user).getPostDetail(pid)
        def slow(*args):gate.wait(2);return data
        with patch.object(CommunityClient,'getPostDetail',slow):
            view=openPost(self.page,self.user,pid);self.page.views.remove(view);gate.set()
            await asyncio.wrap_future(view._load_future)
        self.assertEqual([v.route for v in self.page.views],['/home'])

    async def test_load_error_can_be_retried_without_creating_another_view(self):
        pid=self.post();data=CommunityClient(self.user).getPostDetail(pid);self.mount(ft.View('/home'))
        with patch.object(CommunityClient,'getPostDetail',side_effect=[ApiError('Нет связи',503),data]) as request:
            view=openPost(self.page,self.user,pid);await asyncio.wrap_future(view._load_future)
            h.find(view,ft.ElevatedButton,text='Повторить загрузку').on_click(None)
            await asyncio.wrap_future(view._load_future)
            self.assertEqual(request.call_count,2);self.assertEqual(len(self.page.views),2)
            self.assertIsNotNone(h.find(view,ft.Text,value='Готовая фигурка'))

    async def test_initial_bundle_renders_without_separate_photo_comment_workshop_access_calls(self):
        pid=self.post();self.mount(ft.View('/home'))
        with patch.object(CommunityClient,'getPhoto',side_effect=AssertionError('Extra photo')),patch.object(CommunityClient,'getCommentsPage',side_effect=AssertionError('Extra comments')),patch.object(CommunityClient,'getWorkshop',side_effect=AssertionError('Extra workshop')),patch('views.community_tab.panelAccess',side_effect=AssertionError('Extra access')):
            view=openPost(self.page,self.user,pid);await asyncio.wrap_future(view._load_future)
            self.assertIsNotNone(h.find(view,ft.TextField,label='Комментарий'))

    async def test_english_choice_before_demo_login_is_applied_and_saved(self):
        root=self.mount(createAuthView(self.page))
        picker=h.find(root,ft.Dropdown,label='Язык приложения');picker.value='en';picker.on_change(SimpleNamespace(control=picker))
        h.find(root,ft.ElevatedButton,text='Войти').on_click(None)
        self.assertEqual(language(self.page),'en')
        self.assertEqual(getUserProfile(self.user['userId'])['languageCode'],'en')

    async def test_profile_language_is_visible_and_changes_without_opening_an_expansion(self):
        root=self.mount(createProfileTab(self.page,self.user['nickname'],self.user['email']))
        picker=h.find(root,ft.Dropdown,label='Язык приложения')
        # It is a direct Settings workspace control, never inside an ExpansionTile.
        self.assertFalse(any(picker in list(h.walk(c)) for c in h.walk(root) if isinstance(c,ft.ExpansionTile)))
        picker.value='en';picker.on_change(SimpleNamespace(control=picker))
        self.assertEqual(language(self.page),'en');self.assertEqual(getUserProfile(self.user['userId'])['languageCode'],'en')

    async def test_language_change_rebuilds_auth_even_when_route_is_unchanged(self):
        def render(event):self.mount(createAuthView(self.page))
        self.page.on_route_change=render;self.page.go('/auth');await asyncio.sleep(.03)
        picker=h.find(self.page.views[-1],ft.Dropdown,label='Язык приложения')
        picker.value='en';picker.on_change(SimpleNamespace(control=picker))
        self.assertIsNotNone(h.find(self.page.views[-1],ft.ElevatedButton,text='Sign in'))

    async def test_language_change_rebuilds_home_and_keeps_settings_open(self):
        from views.home_view import createHomeView
        def render(event):self.mount(createHomeView(self.page))
        self.page.on_route_change=render;self.page.go('/home');await asyncio.sleep(.03)
        self.page.session.get('navigateHomeTab')(4)
        picker=h.find(self.page.views[-1],ft.Dropdown,label='Язык приложения')
        picker.value='en';picker.on_change(SimpleNamespace(control=picker))
        self.assertIsNotNone(h.find(self.page.views[-1],ft.Dropdown,label='Language'))
        self.assertEqual(self.page.session.get('homeTab'),4)

    async def test_no_contest_has_nonempty_native_key_and_invalid_caption_is_friendly(self):
        picker,_=createContestPicker(self.page,self.user)
        self.assertEqual(picker.value,NO_CONTEST);self.assertTrue(picker.options[0].key)
        self.assertIsNone(selectedContest(picker))
        picker.value='Без конкурса'
        with self.assertRaisesRegex(ValueError,'Выберите конкурс'):selectedContest(picker)

    async def test_compose_is_fullscreen_and_contains_no_draft_controls(self):
        self.mount(ft.View('/home'));openCreate(self.page,self.user)
        menu=next(c for c in self.page.overlay if isinstance(c,ft.AlertDialog) and c.open)
        next(c for c in h.walk(menu) if isinstance(c,ft.ListTile) and c.title.value=='Публикация').on_click(None)
        menu.on_dismiss(None);menu.on_dismiss(None)
        self.assertEqual([v.route for v in self.page.views],['/home','/discovery/compose'])
        self.assertFalse(any(isinstance(c,ft.TextButton) and 'черновик' in (c.text or '').lower() for c in h.walk(self.page.views[-1])))

    async def test_publish_without_refreshing_contests_and_repeated_taps_make_one_post(self):
        root=self.mount(ft.View('/compose',controls=[createHomeTab(self.page,self.user,self.user['nickname'],mode='compose')]))
        h.find(root,ft.TextField,label='Название работы').value='Новая публикация'
        h.find(root,ft.TextField,label='Описание').value='Фото без участия в конкурсе'
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'result.png';path.write_bytes(photo()['data'])
            h.find(root,ft.OutlinedButton,text='Добавить фото').on_click(None)
            picker=next(c for c in self.page.overlay if isinstance(c,ft.FilePicker))
            picker.on_result(SimpleNamespace(files=[SimpleNamespace(name=path.name,size=path.stat().st_size,path=str(path))]))
        publish=h.find(root,ft.ElevatedButton,text='Опубликовать')
        gate=threading.Event();started=threading.Event();original=CommunityClient.publishPost
        def slow(client,*args,**kwargs):started.set();gate.wait(3);return original(client,*args,**kwargs)
        with patch.object(CommunityClient,'publishPost',slow):
            job=asyncio.create_task(asyncio.to_thread(publish.on_click,None))
            for _ in range(100):
                if started.is_set():break
                await asyncio.sleep(.01)
            self.assertTrue(started.is_set());self.assertTrue(publish.disabled)
            for _ in range(30):publish.on_click(None)
            gate.set();await job
        self.assertEqual(len(posts.getUserPosts(self.user['userId'])),1)
        publish.on_click(None);self.assertEqual(len(posts.getUserPosts(self.user['userId'])),1)
