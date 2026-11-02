"""Navigation and disclosure regressions: real controls, unchanged draft objects."""
from types import SimpleNamespace
import unittest
import flet as ft
import test_startup as harness
from views.home_view import createHomeView, createColorsTab, createProjectsTab
from views.profile_tab import createProfileTab
from design_system import makeTheme, presentView, resizeLayouts


class DesignTests(unittest.IsolatedAsyncioTestCase):
    setUp = harness.StartupTests.setUp
    tearDown = harness.StartupTests.tearDown
    mount = harness.StartupTests.mount

    async def test_resize_keeps_project_draft_and_synchronises_navigation(self):
        root=self.mount(createHomeView(self.page))
        navigate=self.page.session.get('navigateHomeTab')
        navigate(3)
        field=harness.find(root,ft.TextField,label='Название проекта')
        field.value='Не сохранённая фигурка'
        for width in (320,820,1440,390):
            self.page._set_attr('width',width)
            self.page.session.get('resizeHomeView')(SimpleNamespace())
            self.assertIs(harness.find(root,ft.TextField,label='Название проекта'),field)
            self.assertEqual(field.value,'Не сохранённая фигурка')
            self.assertEqual(harness.find(root,ft.NavigationBar).visible,width<760)
        rail=harness.find(root,ft.NavigationRail)
        rail.selected_index=2
        rail.on_change(SimpleNamespace(control=rail))
        self.assertEqual(harness.find(root,ft.NavigationBar).selected_index,2)
        self.assertEqual(self.page.session.get('homeTab'),2)

    async def test_colour_tasks_preserve_fields_and_selected_colours(self):
        layout=createColorsTab(self.page,self.user)
        self.mount(ft.View('/test',controls=[layout]))
        field=harness.find(layout,ft.TextField,label='Название смеси')
        field.value='Моя глина'
        detector=next(c for c in harness.walk(layout) if isinstance(c,ft.GestureDetector)
            and any(isinstance(t,ft.Text) and t.value=='Белый' for t in harness.walk(c)))
        detector.on_tap(None)
        slider=harness.find(layout,ft.Slider)
        for index in (1,2,0):layout.select_workspace(index)
        self.assertIs(harness.find(layout,ft.Slider),slider)
        self.assertIs(harness.find(layout,ft.TextField,label='Название смеси'),field)
        self.assertEqual(field.value,'Моя глина')
        # Palette is a wrapping row inside the sole outer scroll owner.
        self.assertFalse(any(isinstance(c,ft.GridView) for c in harness.walk(layout)))

    async def test_profile_settings_remain_available_behind_task_switch(self):
        layout=createProfileTab(self.page,self.user['nickname'],self.user['email'])
        self.mount(ft.View('/test',controls=[layout]))
        theme=harness.find(layout,ft.Dropdown,label='Тема приложения')
        layout.select_workspace(1)
        self.assertIs(harness.find(layout,ft.Dropdown,label='Тема приложения'),theme)
        self.assertTrue(any(isinstance(c,ft.ElevatedButton) and c.text=='Удалить аккаунт' for c in harness.walk(layout)))
        self.assertTrue(all(c.maintain_state for c in harness.walk(layout) if isinstance(c,ft.ExpansionTile)))

    async def test_detail_width_changes_without_recreating_scroll_or_editor(self):
        field=ft.TextField(value='Черновик урока')
        listing=ft.ListView(controls=[field],expand=True)
        root=presentView(self.page,ft.View('/catalog-edit/test',controls=[listing]))
        self.mount(root)
        for width in (320,1440):
            self.page._set_attr('width',width)
            resizeLayouts(self.page)
            self.assertIs(harness.find(root,ft.ListView),listing)
            self.assertEqual(field.value,'Черновик урока')
            frame=next(c for c in harness.walk(root) if getattr(c,'_design_bound',False))
            self.assertEqual(frame.width,min(1040,width))

    async def test_both_material_themes_serialize_with_real_flet(self):
        self.page.theme=makeTheme()
        self.page.dark_theme=makeTheme(True)
        for mode in (ft.ThemeMode.LIGHT,ft.ThemeMode.DARK):
            self.page.theme_mode=mode
            self.mount(createHomeView(self.page))
            self.page.update()

    async def test_theme_copy_and_palette_labels_have_readable_contrast(self):
        from design_system import relativeLuminance,swatchTextColor
        from color_service import BASE_COLORS
        def contrast(first,second):
            a,b=sorted((relativeLuminance(first),relativeLuminance(second)))
            return (b+0.05)/(a+0.05)
        for dark in (False,True):
            theme=makeTheme(dark)
            for style in (theme.text_theme.body_medium,theme.text_theme.title_large,
                    theme.appbar_theme.title_text_style,theme.navigation_bar_theme.label_text_style[ft.ControlState.DEFAULT]):
                self.assertGreaterEqual(contrast(style.color,theme.color_scheme.surface),4.5)
        for item in BASE_COLORS:
            text='#000000' if swatchTextColor(item['hex'])==ft.Colors.BLACK else '#FFFFFF'
            self.assertGreaterEqual(contrast(text,item['hex']),4.5)
