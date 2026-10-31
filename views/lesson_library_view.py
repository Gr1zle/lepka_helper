"""Личная библиотека уроков: избранное, заметки и текст для отправки."""
import flet as ft
from lesson_library import (favoriteLessonIds,saveLessonFavorite,getLessonNote,saveLessonNote,
                            lessonShareText,lessonSearchResults)
from lesson_service import searchLessons
from ui_helpers import authenticatedAction,showMessage


def createLessonFavorite(page,user,lessonId,onChanged=None):
    selected = user is not None and lessonId in favoriteLessonIds(user['userId'])
    button = ft.TextButton('Убрать из избранного' if selected else 'В избранное',
                          icon=ft.Icons.BOOKMARK if selected else ft.Icons.BOOKMARK_BORDER, disabled=user is None)
    @authenticatedAction(page,user)
    def save(event):
        nonlocal selected
        try:
            value = saveLessonFavorite(user['userId'],lessonId,not selected)
            selected = value
            button.text = 'Убрать из избранного' if value else 'В избранное'
            button.icon = ft.Icons.BOOKMARK if value else ft.Icons.BOOKMARK_BORDER
            if onChanged:
                onChanged()
            page.update()
        except ValueError as error:
            showMessage(page,str(error),True)
    button.on_click = save
    return button


def createLessonNotebook(page,user,lessonId,draft):
    if not user:
        return ft.Text('Войдите, чтобы сохранять личные заметки.',size=12)
    if draft.get('lessonId') != lessonId:
        draft.update(lessonId=lessonId,value=getLessonNote(user['userId'],lessonId))
    version=draft.get('_version',0)+1
    draft['_version']=version
    field = ft.TextField(label='Личная заметка к уроку',value=draft['value'],multiline=True,
                         min_lines=3,max_lines=6,max_length=2000)
    def changed(event):
        if draft.get('lessonId')==lessonId and draft.get('_version')==version:
            draft['value'] = field.value or ''
    field.on_change = changed
    @authenticatedAction(page,user)
    def save(event):
        if draft.get('lessonId')!=lessonId or draft.get('_version')!=version:
            return
        try:
            draft['value'] = saveLessonNote(user['userId'],lessonId,field.value or '')
            field.value = draft['value']
            field.error_text = None
            showMessage(page,'Заметка сохранена' if draft['value'] else 'Заметка удалена')
        except ValueError as error:
            field.error_text = str(error)
        page.update()
    return ft.Card(content=ft.Container(padding=14,content=ft.Column(controls=[field,
        ft.Text('Заметка личная и хранится на устройстве. Пустое поле при сохранении удаляет заметку.',size=12),
        ft.ElevatedButton('Сохранить заметку',on_click=save)])))


def createLessonShare(page,user,lessonId):
    @authenticatedAction(page,user)
    def copy(event):
        page.set_clipboard(lessonShareText(lessonId))
        showMessage(page,'Текст урока скопирован. Его можно вставить в сообщение.')
    return ft.TextButton('Скопировать урок',icon=ft.Icons.CONTENT_COPY,on_click=copy,disabled=user is None)


def createProfileLessonLibrary(page,user):
    def openLesson(lessonId):
        page.session.set('openBuiltinLesson',lessonId)
        page.session.set('homeTab',1)
        navigate = page.session.get('navigateHomeTab')
        if callable(navigate):
            navigate(1)
        else:
            page.go('/home')

    @authenticatedAction(page,user)
    def saved(event,progressOnly=False):
        lessons = lessonSearchResults(searchLessons(''),'',user['userId'],favoritesOnly=not progressOnly,inProgressOnly=progressOnly)
        entries = []
        for lesson in lessons:
            @authenticatedAction(page,user)
            def openItem(event,lessonId=lesson['lessonId']):
                page.close(dialog)
                openLesson(lessonId)
            entries.append(ft.TextButton(lesson['title'],on_click=openItem))
        dialog = ft.AlertDialog(modal=True,title=ft.Text('Продолжить уроки' if progressOnly else 'Избранные уроки'),
            content=ft.Container(width=360,height=300,content=ft.ListView(controls=entries or [ft.Text('Здесь пока нет уроков')])),
            actions=[ft.TextButton('Закрыть',on_click=lambda event:page.close(dialog))])
        page.open(dialog)
    return ft.Row(wrap=True,controls=[ft.TextButton('Избранные уроки',icon=ft.Icons.BOOKMARK_BORDER,on_click=saved),
        ft.TextButton('Продолжить уроки',icon=ft.Icons.PLAY_ARROW,on_click=lambda event:saved(event,True))])
