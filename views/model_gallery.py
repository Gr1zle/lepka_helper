import flet as ft
from model_service import searchModels,MODEL_CATEGORIES,favoriteModelIds,saveModelFavorite
from lesson_library import normalizeSearchQuery,rememberSearch
from ui_helpers import getCurrentUser,authenticatedAction,showMessage
from api_client import ApiError


def modelUser(page):
    try:return getCurrentUser(page)
    except ApiError:return None  # Публичная геометрия доступна, личные действия отключены.


def createModelFavorite(page,user,modelId):
    selected=user is not None and modelId in favoriteModelIds(user['userId'])
    button=ft.TextButton('Убрать модель из избранного' if selected else 'Модель в избранное',
                        icon=ft.Icons.BOOKMARK if selected else ft.Icons.BOOKMARK_BORDER,disabled=user is None)
    @authenticatedAction(page,user)
    def save(event):
        nonlocal selected
        try:
            selected=saveModelFavorite(user['userId'],modelId,not selected)
            button.text='Убрать модель из избранного' if selected else 'Модель в избранное'
            button.icon=ft.Icons.BOOKMARK if selected else ft.Icons.BOOKMARK_BORDER
            page.update()
        except ValueError as error:showMessage(page,str(error),True)
    button.on_click=save
    return button


def createModelCard(page,item):
    return ft.Card(content=ft.Container(padding=12,content=ft.Column(controls=[
        ft.Image(src=f"models/{item['modelId']}-preview.png",height=145,fit=ft.ImageFit.CONTAIN),
        ft.Text(item['title'],size=18,weight=ft.FontWeight.BOLD),
        ft.Text(f"{item['category']} · встроенная 3D-модель",size=12),
        ft.TextButton('Открыть 3D',on_click=lambda event:page.go('/models/'+item['modelId']))])))


def createModelGallery(page):
    user=modelUser(page)
    query=ft.TextField(label='Поиск 3D-моделей',max_length=120)
    category=ft.Dropdown(label='Категория модели',value='Все',options=[ft.dropdown.Option(c) for c in MODEL_CATEGORIES])
    onlyFavorites=ft.Checkbox(label='Только избранные модели',value=bool(user and page.session.get('modelFavoritesOnly')),disabled=user is None)
    result=ft.Column(spacing=8)
    def refresh(event=None):
        try:
            items=searchModels(query.value or '',category.value)
            saved=favoriteModelIds(user['userId']) if user else set()
            result.controls=[createModelCard(page,item) for item in items if not onlyFavorites.value or item['modelId'] in saved]
            if not result.controls:result.controls=[ft.Text('Подходящих моделей пока нет. Измените запрос или фильтры.')]
            query.error_text=None
        except ValueError as error:query.error_text=str(error)
        page.update()
    @authenticatedAction(page,user)
    def personalFilter(event):refresh()
    def submit(event):
        value=normalizeSearchQuery(query.value or '')
        if user and len(value)>=2:
            @authenticatedAction(page,user)
            def save():rememberSearch(user['userId'],value)
            save()
        refresh()
    query.on_change=refresh;query.on_submit=submit
    category.on_change=refresh;onlyFavorites.on_change=personalFilter
    refresh()
    return ft.View('/models',padding=12,
        appbar=ft.AppBar(title=ft.Text('3D-галерея'),leading=ft.IconButton(icon=ft.Icons.ARROW_BACK,on_click=lambda event:page.go('/home'))),
        controls=[ft.ListView(expand=True,spacing=12,controls=[
            ft.Text('Поверните фигурку, приблизьте детали и измените свет. Модели входят в приложение.',size=14),
            query,category,onlyFavorites,result])])


def createFavoriteModelsButton(page,user):
    @authenticatedAction(page,user)
    def openGallery(event):
        page.session.set('modelFavoritesOnly',True)
        page.go('/models')
    return ft.TextButton('Избранные модели',icon=ft.Icons.VIEW_IN_AR_OUTLINED,on_click=openGallery)
