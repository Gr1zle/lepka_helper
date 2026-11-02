"""Offline Russian/English presentation; database values and user text stay intact."""
import json
import re
import string
from functools import lru_cache
from pathlib import Path
import flet as ft
from app_state import getAppState,setAppState

SUPPORTED=('ru','en')

from interface_catalog import englishCatalog as catalog


def language(page):
    value=page.session.get('languageCode')
    return value if value in SUPPORTED else 'ru'


def setLanguage(page,code,persist=True):
    code=code if code in SUPPORTED else 'ru'
    page.session.set('languageCode',code)
    page.locale_configuration=ft.LocaleConfiguration(supported_locales=[ft.Locale('ru','RU'),ft.Locale('en','US')],current_locale=ft.Locale(code,'US' if code=='en' else 'RU'))
    page.title='Clay Companion' if code=='en' else 'Помощник по лепке'
    if persist:setAppState('languageCode',code)
    return code


def restoreLanguage(page):
    return setLanguage(page,getAppState('languageCode','ru'),persist=False)


def tr(page,source,**values):
    """Translate an explicit interface template; interpolate user values afterwards."""
    text=catalog().get(source,source) if language(page)=='en' else source
    return text.format(**values) if values else text


def term(page,value):
    """Caption of a controlled vocabulary. Never use for a user's title or text."""
    return tr(page,value) if isinstance(value,str) else value


@lru_cache(maxsize=1)
def messagePatterns():
    patterns=[]
    for source,translated in catalog().items():
        if not re.search(r'\{v\d+',source):continue
        try:
            chunks=list(string.Formatter().parse(source))
        except ValueError:continue
        expression='';names=set();literalSize=0
        for literal,name,spec,conversion in chunks:
            expression+=re.escape(literal);literalSize+=len(literal)
            if name is not None:
                if not re.fullmatch(r'v\d+',name):break
                expression+=r'(?P<'+name+r'>.*?)' if name not in names else r'(?P='+name+r')'
                names.add(name)
        else:
            if names and literalSize>=8:patterns.append((literalSize,re.compile(expression,re.DOTALL),translated))
    return sorted(patterns,key=lambda p:-p[0])


def message(page,value):
    """Known service messages only; template captures preserve supplied values."""
    if not value or language(page)!='en' or not isinstance(value,str):return value
    if value in catalog():return catalog()[value]
    for _,pattern,translated in messagePatterns():
        match=pattern.fullmatch(value)
        if match:
            try:
                # Captures are already formatted strings (dates/numbers included).
                return ''.join(literal+(match[name] if name is not None else '') for literal,name,spec,conv in string.Formatter().parse(translated))
            except (KeyError,ValueError):continue
    return value


def localizeHints(page,root):
    """Translate system labels/errors, never field values, captions of user data or keys."""
    def walk(control):
        for attr in ('tooltip','hint_text','helper_text','error_text'):
            value=getattr(control,attr,None)
            if isinstance(value,str):setattr(control,attr,message(page,value))
        if isinstance(control,(ft.TextField,ft.Dropdown,ft.NavigationBarDestination,ft.NavigationRailDestination)):
            if isinstance(control.label,str):control.label=term(page,control.label)
        for child in control._get_children():walk(child)
    walk(root)


def builtinContent(page,value):
    """Display a copy of bundled teaching content. Never pass community/user data."""
    if language(page)!='en':return value
    if isinstance(value,str):return catalog().get(value,value)
    if isinstance(value,list):return [builtinContent(page,v) for v in value]
    if isinstance(value,dict):return {k:(v if k in ('category','level','theme','modelId','lessonId') else builtinContent(page,v)) for k,v in value.items()}
    return value


def clearSession(page):
    """Sign out credentials while retaining this page's interface language."""
    code=page.session.get('languageCode')
    page.session.clear()
    if code in SUPPORTED:page.session.set('languageCode',code)


def rebuildCurrentRoute(page):
    """Flet suppresses go() for an unchanged route; locale needs an actual rebuild."""
    handler=page.on_route_change
    if callable(handler):handler(None)
    else:page.go(page.route or (getattr(page.views[0],'route',None) if page.views else None) or '/')
