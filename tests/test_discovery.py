"""Product navigation and delayed detail loading, using real Flet controls."""
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import flet as ft
import test_startup as harness
from views.home_view import createHomeView,createSearchTab,createProjectsTab,createColorsTab
from views.discovery import openCreate,createPostTile,openPost
from project_service import saveProject,saveProjectStep
from community_gateway import CommunityClient
from color_service import saveColorMixture,calculateRecipe,BASE_COLORS

class DiscoveryTests(unittest.IsolatedAsyncioTestCase):
    setUp=harness.StartupTests.setUp
    tearDown=harness.StartupTests.tearDown
    mount=harness.StartupTests.mount
    def dialog(self):return next(c for c in reversed(self.page.overlay) if isinstance(c,ft.AlertDialog) and c.open)

    async def test_home_has_discovery_not_composer_or_settings_and_notices_are_a_tab(self):
        view=self.mount(createHomeView(self.page))
        nav=harness.find(view,ft.NavigationBar)
        self.assertNotIn('Поиск',[d.label for d in nav.destinations])
        self.assertIn('Входящие',[d.label for d in nav.destinations])
        self.assertFalse(any(isinstance(c,ft.TextField) and c.label=='Название работы' for c in harness.walk(view)))
        self.assertFalse(any(isinstance(c,ft.TextButton) and c.text=='Доставка уведомлений' for c in harness.walk(view)))
        nav.selected_index=1;nav.on_change(SimpleNamespace(control=nav))
        self.assertIsNotNone(harness.find(view,ft.Dropdown,label='Источник уведомлений'))
        self.assertIsNotNone(harness.find(view,ft.IconButton,tooltip='Создать'))

    async def test_search_is_initially_empty_and_accepts_filter_only(self):
        root=self.mount(ft.View('/search',controls=[createSearchTab(self.page,self.user,startEmpty=True)]))
        self.assertFalse(any(isinstance(c,ft.TextButton) and c.text=='Открыть' for c in harness.walk(root)))
        category=harness.find(root,ft.Dropdown,label='Категория')
        category.value='Животные';category.on_change(SimpleNamespace(control=category))
        self.assertTrue(any(isinstance(c,ft.TextButton) and c.text=='Открыть' for c in harness.walk(root)))

    async def test_global_creation_opens_a_modal_without_changing_current_tab(self):
        root=self.mount(createHomeView(self.page))
        self.page.session.get('navigateHomeTab')(2)
        harness.find(root,ft.IconButton,tooltip='Создать').on_click(None)
        option=next(c for c in harness.walk(self.dialog()) if isinstance(c,ft.ListTile) and c.title.value=='Публикация')
        option.on_click(None)
        self.assertEqual(self.page.session.get('homeTab'),2)
        self.assertIsNotNone(harness.find(self.dialog(),ft.TextField,label='Название работы'))

    async def test_project_summary_hides_steps_until_opened_and_edits_refresh_the_modal(self):
        ok,_,pid=saveProject(self.user['userId'],'Фигурка','Животные','','Заметка')
        self.assertTrue(ok);step=saveProjectStep(pid,'Каркас',self.user['userId'])[2]
        from project_service import saveProjectStepPhoto
        from image_fixtures import photo
        saveProjectStepPhoto(pid,step,self.user['userId'],photo())
        root=self.mount(ft.View('/projects',controls=[createProjectsTab(self.page,self.user,mode='list')]))
        self.assertFalse(any(isinstance(c,ft.TextField) and c.label=='Новый этап' for c in harness.walk(root)))
        tile=next(c for c in harness.walk(root) if isinstance(c,ft.ListTile) and c.title.value=='Фигурка')
        tile.on_click(None)
        self.assertIsNotNone(harness.find(self.page.views[-1],ft.Text,value='Каркас'))
        checkbox=harness.find(self.page.views[-1],ft.Checkbox)
        checkbox.value=True;checkbox.on_change(SimpleNamespace(control=checkbox))
        self.assertTrue(harness.find(self.page.views[-1],ft.Checkbox).value)

    async def test_cover_does_not_fetch_comments_until_opened(self):
        item={'postId':1,'titleText':'Работа','nickname':'Автор','photoIds':[]}
        with patch.object(CommunityClient,'getCommentsPage',side_effect=AssertionError('Comments fetched too early')):
            tile=createPostTile(self.page,item,self.user)
            self.mount(ft.View('/test',controls=[tile]))
        self.assertFalse(any(isinstance(c,ft.TextField) and c.label=='Комментарий' for c in harness.walk(tile)))

    async def test_no_palette_search_and_duplicate_mixture_is_rejected_per_owner(self):
        layout=createColorsTab(self.page,self.user)
        self.assertFalse(any(isinstance(c,ft.TextField) and 'Поиск базового' in (c.label or '') for c in harness.walk(layout)))
        colors=[{**BASE_COLORS[0],'proportion':50},{**BASE_COLORS[1],'proportion':50}]
        recipe=calculateRecipe(colors,100)
        saveColorMixture(self.user['userId'],'Серая','#808080',100,recipe)
        with self.assertRaisesRegex(ValueError,'уже сохранена'):
            saveColorMixture(self.user['userId'],'  сЕрая  ','#808080',100.004,recipe)
        saveColorMixture(self.user['userId'],'Другой рецепт','#808080',100,recipe)

    async def test_native_refresh_acknowledges_the_request(self):
        from pull_refresh import PullRefresh
        with patch('views.project_transfer.androidClient',return_value=True):
            root=self.mount(createHomeView(self.page))
        refresh=harness.find(root,PullRefresh)
        refresh._refresh(SimpleNamespace(data='request-1'))
        self.assertEqual(refresh._get_attr('refreshDone'),'request-1')

    async def test_fullscreen_photo_keeps_the_sample_when_returning(self):
        from views.color_scan import openColorScan
        from image_fixtures import photo
        captured=[];applied=[]
        with patch('views.color_scan.createPhotoPicker',side_effect=lambda page,user,callback,*a: (captured.append(callback) or ft.Container())):
            self.mount(createHomeView(self.page));openColorScan(self.page,self.user,applied.append,lambda c:None)
        captured[0](photo())
        scan=self.dialog()
        harness.find(scan,ft.TextButton,text='Открыть фото во весь экран').on_click(None)
        scan.on_dismiss(None)
        viewer=harness.find(self.page.views[-1],ft.InteractiveViewer)
        self.assertGreaterEqual(viewer.max_scale,8)
        gesture=harness.find(viewer,ft.GestureDetector)
        gesture.on_tap_up(SimpleNamespace(local_x=183,local_y=270))
        harness.find(self.page.views[-1],ft.FilledButton,text='Готово').on_click(None)
        harness.find(self.dialog(),ft.TextButton,text='В целевой HEX').on_click(None)
        self.assertEqual(applied,['#FF6B6B'])

    async def test_duplicate_guard_serialises_concurrent_saves(self):
        from concurrent.futures import ThreadPoolExecutor
        colors=[{**BASE_COLORS[0],'proportion':50},{**BASE_COLORS[1],'proportion':50}]
        recipe=calculateRecipe(colors,100)
        def save():
            try:saveColorMixture(self.user['userId'],'Общий рецепт','#808080',100,recipe);return True
            except ValueError:return False
        with ThreadPoolExecutor(max_workers=2) as pool:result=list(pool.map(lambda _:save(),range(2)))
        self.assertEqual(sorted(result),[False,True])

    async def test_catalogue_starts_with_builtin_lessons_without_network_search(self):
        with patch.object(CommunityClient,'getPosts',side_effect=AssertionError('Offline catalogue requested posts')):
            root=self.mount(ft.View('/catalogue',controls=[createSearchTab(self.page,self.user,catalogMode=True)]))
        self.assertIsNotNone(harness.find(root,ft.TextField,label='Поиск в учебном каталоге'))
        self.assertIsNotNone(harness.find(root,ft.TextButton,text='Открыть'))
        self.assertIsNotNone(harness.find(root,ft.OutlinedButton,text='Материалы преподавателей'))
