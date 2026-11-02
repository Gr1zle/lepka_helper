from localization import tr, term
"""Discovery, independent detail pages and shared creation dialogs."""
import base64
import flet as ft
from api_client import ApiError
from ui_helpers import authenticatedAction,serverAction,createLoadError,isWebClient
from design_system import polish,presentView


def openPage(page,title,content,route):
    def back(event=None):
        if page.views and page.views[-1] is view:
            page.views.pop();page.update()
    view=presentView(page,ft.View(route,appbar=ft.AppBar(title=ft.Text(term(page,title)),leading=ft.IconButton(ft.Icons.ARROW_BACK,tooltip=tr(page, 'Назад'),on_click=back)),controls=[content]))
    page.views.append(view);page.update()
    return view


def openSearch(page,user):
    from views.home_view import createSearchTab
    try:body=createSearchTab(page,user,startEmpty=True)
    except ApiError as error:body=createLoadError(page,error,lambda:openSearch(page,user))
    return openPage(page,tr(page, 'Поиск'),body,'/discovery/search')


def openBuiltinCatalog(page,user):
    from views.home_view import createSearchTab
    return openPage(page,tr(page, 'Учебный каталог'),createSearchTab(page,user,catalogMode=True),'/discovery/catalog')


def openPost(page,user,postId,onChanged=None):
    from community_gateway import CommunityClient
    from views.community_tab import createPostCard
    client=CommunityClient(user)
    def render(changed=True):
        item=client.getPost(postId)
        body.controls=[createPostCard(page,item,user,render)] if item else [ft.Text(tr(page, 'Публикация недоступна'))]
        polish(body)
        if changed and onChanged:onChanged()
        page.update()
    body=ft.ListView(expand=True,padding=16,spacing=12)
    render(False)
    return openPage(page,tr(page, 'Работа'),body,'/discovery/post/'+str(postId))


def createPostTile(page,item,user,onChanged=None):
    """Only a cover and caption; comments/photos are fetched when opened."""
    photoIds=item.get('photoIds') or []
    cover=ft.Container(height=150,bgcolor=ft.Colors.PRIMARY_CONTAINER,
        alignment=ft.alignment.center,content=ft.Icon(ft.Icons.IMAGE_OUTLINED,size=36,color=ft.Colors.PRIMARY))
    if photoIds:
        from community_gateway import CommunityClient
        from views.community_tab import webAddress
        client=CommunityClient(user)
        image=ft.Image(height=180 if item['postId']%2 else 225,fit=ft.ImageFit.COVER,
            semantics_label=item['titleText'],border_radius=14)
        if isWebClient(page) and not client.remote:image.src=webAddress(page,'/post-photos/'+str(photoIds[0]))
        else:
            data=client.getThumbnail(photoIds[0])
            if data:image.src_base64=base64.b64encode(data).decode()
        if image.src or image.src_base64:cover=image
    action=authenticatedAction(page,user) if user else serverAction(page)
    tile=ft.Container(col={'xs':6,'md':4,'xl':3},border_radius=14,clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,padding=0,
        on_click=action(lambda e:openPost(page,user,item['postId'],onChanged)),
        content=ft.Column(spacing=6,controls=[cover,ft.Container(padding=ft.padding.only(left=10,right=10,bottom=10),
            content=ft.Column(spacing=3,controls=[ft.Text(item['titleText'],size=14,weight=ft.FontWeight.W_600,max_lines=2,overflow=ft.TextOverflow.ELLIPSIS),
                ft.Text(item['nickname'],size=12,color=ft.Colors.ON_SURFACE_VARIANT)]))]))

    tile.content=ft.Semantics(label=tr(page, 'Открыть работу: ')+item['titleText'],container=True,button=True,exclude_semantics=True,
        on_tap=action(lambda e:openPost(page,user,item['postId'],onChanged)),content=tile.content)
    return tile


def creationDialog(page,title,body,compact=False):
    def close(event=None):page.close(dialog)
    dialog=ft.AlertDialog(modal=True,title=ft.Text(term(page,title)),inset_padding=12,
        content_padding=12,content=ft.Container(width=min(620,max(260,(page.width or 390)-48)),
            height=max(230,min(430 if compact else 650,(page.height or 780)-180)),content=body),
        actions=[ft.TextButton(tr(page, 'Закрыть'),on_click=close)])
    page.open(dialog)
    return dialog


def openCreate(page,user):
    @authenticatedAction(page,user)
    def choose(event,kind):
        page.close(menu)
        from views.home_view import createProjectsTab
        from views.community_tab import createHomeTab
        def published():
            page.close(dialog)
            callback=page.session.get('refreshCommunityFeed')
            if callable(callback):callback()
        def created(projectId):
            page.close(dialog)
            navigate=page.session.get('navigateHomeTab')
            if callable(navigate):navigate(3)
        body=(createHomeTab(page,user,user['nickname'],mode='compose',onPublished=published) if kind=='post'
            else createProjectsTab(page,user,mode='create',onCreated=created))
        dialog=creationDialog(page,'Новая публикация' if kind=='post' else 'Новый проект',body,compact=True)
    menu=ft.AlertDialog(title=ft.Text(tr(page, 'Создать')),content=ft.Column(tight=True,controls=[
        ft.ListTile(leading=ft.Icon(ft.Icons.ADD_PHOTO_ALTERNATE_OUTLINED),title=ft.Text(tr(page, 'Публикация')),subtitle=ft.Text(tr(page, 'Фото и описание работы')),on_click=lambda e:choose(e,'post')),
        ft.ListTile(leading=ft.Icon(ft.Icons.CHECKLIST),title=ft.Text(tr(page, 'Личный проект')),subtitle=ft.Text(tr(page, 'План и этапы лепки')),on_click=lambda e:choose(e,'project'))]),
        actions=[ft.TextButton(tr(page, 'Отмена'),on_click=lambda e:page.close(menu))])
    page.open(menu)


def createDiscovery(page,user,nickname):
    from views.community_tab import createHomeTab
    return createHomeTab(page,user,nickname,mode='feed')


class Masonry(ft.Row):
    def __init__(self,page):
        super().__init__(spacing=12,vertical_alignment=ft.CrossAxisAlignment.START)
        self.pageRef=page;self.items=[];self.count=0
    def setItems(self,items):
        self.items=list(items);self.reflow(force=True)
    def reflow(self,force=False):
        width=self.pageRef.width or 390
        width=min(1040,width-(210 if width>=1180 else 80 if width>=760 else 0))-32
        count=4 if width>=960 else 3 if width>=620 else 2
        if not force and self.count==count:return
        self.count=count
        columns=[ft.Column(expand=True,spacing=12) for _ in range(count)]
        for i,item in enumerate(self.items):columns[i%count].controls.append(item)
        self.controls=columns
