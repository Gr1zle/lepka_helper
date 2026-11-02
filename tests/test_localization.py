"""Language is per page; only app-owned captions are translated."""
import ast
import json
from pathlib import Path
import re
import string
from types import SimpleNamespace
import unittest
import flet as ft
import test_startup as harness
from localization import tr,term,message,setLanguage,restoreLanguage,localizeHints,catalog
from views.home_view import createHomeView,createColorsTab,createProjectsTab,createSearchTab
from views.auth_view import createAuthView
from views.project_editor import createProjectEditor
from project_service import saveProject,saveStep,getProjectSteps
from profile_service import saveUserSettings,getUserProfile
from lesson_service import searchLessons

class LocalizationTests(unittest.IsolatedAsyncioTestCase):
    setUp=harness.StartupTests.setUp
    tearDown=harness.StartupTests.tearDown
    mount=harness.StartupTests.mount

    async def test_english_tabs_forms_and_filter_keys_in_both_themes(self):
        setLanguage(self.page,'en')
        for theme in (ft.ThemeMode.LIGHT,ft.ThemeMode.DARK):
            self.page.theme_mode=theme
            view=self.mount(createHomeView(self.page))
            nav=harness.find(view,ft.NavigationBar)
            self.assertEqual([d.label for d in nav.destinations],['Home','Inbox','Colors','Projects','Profile'])
            for index in (5,2,3,4,0):self.page.session.get('navigateHomeTab')(index)
            colors=self.mount(ft.View('/colors',controls=[createColorsTab(self.page,self.user)]))
            self.assertTrue(any(isinstance(c,ft.TextButton) and c.text=='My mixtures' for c in harness.walk(colors)))
            search=self.mount(ft.View('/search',controls=[createSearchTab(self.page,self.user,startEmpty=True)]))
            category=harness.find(search,ft.Dropdown,label='Category')
            animal=next(o for o in category.options if o.key=='Животные')
            self.assertEqual(animal.text,'Animals')
            category.value='Животные';category.on_change(SimpleNamespace(control=category))
            self.assertEqual(category.value,'Животные')

    async def test_user_titles_descriptions_and_step_text_are_never_translated(self):
        pid=saveProject(self.user['userId'],'Главная','Животные','','Сохранить')[2]
        saveStep(pid,self.user['userId'],'Новый этап','Описание не переводить')
        setLanguage(self.page,'en')
        root=self.mount(ft.View('/project',controls=[createProjectEditor(self.page,self.user,pid)]))
        values=[c.value for c in harness.walk(root) if isinstance(c,ft.Text)]
        self.assertIn('Главная',values);self.assertIn('Сохранить',values);self.assertIn('Новый этап',values)
        self.assertIn('Описание не переводить',values)
        self.assertTrue(any(v and 'Animals' in v for v in values))
        self.assertEqual(getProjectSteps(pid,self.user['userId'])[0]['title'],'Новый этап')

    async def test_language_persists_and_profile_uses_supported_codes(self):
        setLanguage(self.page,'en');self.page.session.clear();restoreLanguage(self.page)
        self.assertEqual(tr(self.page,'Сохранить'),'Save')
        self.assertEqual(self.page.locale_configuration.current_locale.language_code,'en')
        self.assertTrue(saveUserSettings(self.user['userId'],'dark','en',True)[0])
        self.assertEqual(getUserProfile(self.user['userId'])['languageCode'],'en')
        self.assertFalse(saveUserSettings(self.user['userId'],'dark','xx',True)[0])
        setLanguage(self.page,'ru');self.assertEqual(tr(self.page,'Сохранить'),'Сохранить')

    async def test_templates_preserve_user_values_and_translate_service_messages(self):
        setLanguage(self.page,'en')
        self.assertEqual(tr(self.page,'Автор: {v0} · {v1}',v0='Сохранить',v1='Animals'),'Author: Сохранить · Animals')
        self.assertEqual(message(self.page,'Добавьте фото финального результата'),'Add a photo of the final result')
        self.assertEqual(message(self.page,'Страница 2'),'Page 2')
        result=message(self.page,'Фотография должна быть не больше 10 МБ')
        self.assertFalse(re.search('[А-Яа-яЁё]',result))
        self.assertEqual(message(self.page,'Неизвестный пользовательский текст'),'Неизвестный пользовательский текст')

    async def test_hints_translate_errors_without_touching_input_or_option_keys(self):
        setLanguage(self.page,'en')
        field=ft.TextField(label='Название проекта',value='Главная',error_text='Введите пароль')
        options=ft.Dropdown(value='Животные',options=[ft.dropdown.Option('Животные','Animals')])
        localizeHints(self.page,ft.Column([field,options]))
        self.assertEqual(field.label,'Project name');self.assertEqual(field.value,'Главная')
        self.assertEqual(field.error_text,'Enter your password');self.assertEqual(options.value,'Животные')

    async def test_signin_has_language_picker_and_russian_can_be_restored(self):
        setLanguage(self.page,'en');root=self.mount(createAuthView(self.page))
        picker=harness.find(root,ft.Dropdown,label='Language');picker.value='ru';picker.on_change(SimpleNamespace(control=picker))
        self.assertEqual(tr(self.page,'Войти'),'Войти')

    async def test_english_search_finds_builtin_lessons_without_rewriting_sources(self):
        self.assertTrue(searchLessons('cat'))
        self.assertTrue(searchLessons('кот'))
        self.assertTrue(any(re.search('[А-Яа-я]',l['title']) for l in searchLessons('cat')))

    async def test_unknown_language_falls_back_to_russian(self):
        setLanguage(self.page,'xx');self.assertEqual(tr(self.page,'Сохранить'),'Сохранить')

    async def test_all_main_sections_have_english_system_labels(self):
        setLanguage(self.page,'en');root=self.mount(createHomeView(self.page))
        for tab in (0,1,2,3,4,5):
            self.page.session.get('navigateHomeTab')(tab)
            for c in harness.walk(root):
                values=[c.value] if isinstance(c,ft.Text) else []
                values += [getattr(c,a,None) for a in ('text','label','hint_text','tooltip')]
                for value in values:
                    if isinstance(value,str) and value!='Русский':self.assertFalse(re.search('[А-Яа-яЁё]',value),(tab,value))

    async def test_profile_favorite_colors_save_original_keys_after_translation(self):
        from views.profile_tab import createProfileTab
        setLanguage(self.page,'en');root=self.mount(ft.View('/profile',controls=[createProfileTab(self.page,self.user['nickname'],self.user['email'])]))
        white=harness.find(root,ft.Checkbox,label='White');white.value=True
        harness.find(root,ft.ElevatedButton,text='Save profile').on_click(None)
        self.assertEqual(getUserProfile(self.user['userId'])['favoriteColors'],['Белый'])

    async def test_logout_retains_language_but_removes_account_session(self):
        from ui_helpers import logoutPage
        setLanguage(self.page,'en');logoutPage(self.page)
        self.assertIsNone(self.page.session.get('currentUser'))
        self.assertEqual(tr(self.page,'Войти'),'Sign in')


class TranslationCatalogTests(unittest.TestCase):
    def test_all_explicit_templates_are_present_and_keep_named_arguments(self):
        root=Path(__file__).resolve().parents[1]
        for p in [*root.joinpath('views').glob('*.py'),root/'ui_helpers.py',root/'photo_picker.py',root/'date_field.py']:
            for n in ast.walk(ast.parse(p.read_text())):
                if not (isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='tr' and len(n.args)>1 and isinstance(n.args[1],ast.Constant)):continue
                source=n.args[1].value;self.assertIn(source,catalog(),(p.name,source))
                if n.keywords:
                    names={name for _,name,_,_ in string.Formatter().parse(catalog()[source]) if name is not None}
                    self.assertEqual(names,{k.arg for k in n.keywords},(p.name,source))

    def test_english_export_keeps_recipe_numbers_and_user_name(self):
        from color_export import createRecipePng,createRecipePdf
        from color_service import BASE_COLORS
        from io import BytesIO
        from PIL import Image
        selected=[{**BASE_COLORS[0],'proportion':50},{**BASE_COLORS[2],'proportion':50}]
        outputs=[createRecipePng('Главная',selected,20,languageCode=code) for code in ('ru','en')]
        with Image.open(BytesIO(outputs[0])) as ru,Image.open(BytesIO(outputs[1])) as en:
            self.assertEqual(json.loads(ru.info['Recipe']),json.loads(en.info['Recipe']))
            self.assertEqual(json.loads(en.info['Recipe'])['name'],'Главная')
            self.assertNotEqual(ru.tobytes(),en.tobytes())
        self.assertTrue(createRecipePdf('Главная',selected,20,languageCode='en').startswith(b'%PDF-'))

    def test_catalog_is_offline_and_english_except_language_self_name(self):
        self.assertGreater(len(catalog()),1500)
        for key,value in catalog().items():
            if key!='Русский':self.assertFalse(re.search('[А-Яа-яЁё]',value),(key,value))
