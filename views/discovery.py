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


# Only protect navigation-state changes; never hold this lock during network I/O.
import threading
_navigationLock=threading.RLock()


def openPost(page,user,postId,onChanged=None):
    from community_gateway import CommunityClient
    from views.community_tab import createPostCard
    import asyncio
    route='/discovery/post/'+str(postId)
    token=user.get('sessionToken') if user else None
    with _navigationLock:
        if (page.session.get('currentUser') or {}).get('sessionToken')!=token:return None
        existing=next((v for v in page.views if v.route==route),None)
        if existing is not None:return existing
        body=ft.ListView(expand=True,padding=16,spacing=12)
        body.controls=[ft.ProgressRing(),ft.Text(tr(page,'Загрузка публикации…'))]
        view=openPage(page,tr(page,'Работа'),body,route)
    client=CommunityClient(user)
    def active():
        owner=page.session.get('currentUser') or {}
        return view in page.views and owner.get('sessionToken')==token
    loading={'value':False}
    async def load(changed=False):
        try:
            data=await asyncio.to_thread(client.getPostDetail,postId)
            if not active():return
            body.controls=[createPostCard(page,data['post'],user,lambda:schedule(True),initial=data)] if data else [ft.Text(tr(page,'Публикация недоступна'))]
            polish(body);page.update()
            if changed and onChanged:onChanged()
        except ApiError as error:
            if not active():return
            if error.statusCode==401:
                from ui_helpers import serverAction
                @serverAction(page)
                def fail():raise error
                fail();return
            body.controls=[createLoadError(page,error,lambda:schedule())];page.update()
        except Exception:
            import logging
            logging.exception('Post detail rendering failed')
            if active():
                body.controls=[createLoadError(page,tr(page,'Не удалось загрузить публикацию'),lambda:schedule())];page.update()
        finally:loading['value']=False
    def schedule(changed=False):
        if not active() or loading['value']:return
        loading['value']=True
        body.controls=[ft.ProgressRing(),ft.Text(tr(page,'Загрузка публикации…'))];page.update()
        view._load_future=page.run_task(load,changed)
    schedule()
    return view


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
    action=serverAction(page)
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


def openPostComposer(page,user,challengeId=None,onPublished=None):
    """Shared full-page entry point, including challenge shortcuts."""
    from views.community_tab import createHomeTab
    token=user.get('sessionToken') if user else None
    with _navigationLock:
        if not user or (page.session.get('currentUser') or {}).get('sessionToken')!=token:return None
        existing=next((v for v in page.views if v.route=='/discovery/compose'),None)
        if existing is not None:return existing
        view=openPage(page,tr(page,'Новая публикация'),ft.ProgressRing(),'/discovery/compose')
    if challengeId is not None:
        page.session.set('publicationChallenge',dict(challengeId=challengeId,userId=user['userId'],sessionToken=token))
    def published():
        if view not in page.views or (page.session.get('currentUser') or {}).get('sessionToken')!=token:return
        page.views.remove(view);page.update()
        if onPublished:onPublished()
        callback=page.session.get('refreshCommunityFeed')
        if callable(callback):callback()
        page.update()
    try:
        body=createHomeTab(page,user,user['nickname'],mode='compose',onPublished=published)
    except Exception:
        if view in page.views:page.views.remove(view);page.update()
        raise
    if view in page.views and (page.session.get('currentUser') or {}).get('sessionToken')==token:
        view.controls=[body];presentView(page,view);page.update()
    return view


def openCreate(page,user):
    chosen={'value':False}
    @authenticatedAction(page,user)
    def choose(event,kind):
        if chosen['value']:return
        chosen['value']=True
        # Wait for the modal route to leave before pushing a full page.
        opened={'value':False}
        @serverAction(page)
        def dismissed(event):
            if opened['value']:return
            opened['value']=True
            if (page.session.get('currentUser') or {}).get('sessionToken')!=user.get('sessionToken'):return
            from views.home_view import createProjectsTab
            from views.community_tab import createHomeTab
            if kind=='post':
                openPostComposer(page,user)
            else:
                def created(projectId):
                    page.close(dialog)
                    navigate=page.session.get('navigateHomeTab')
                    if callable(navigate):navigate(3)
                body=createProjectsTab(page,user,mode='create',onCreated=created)
                dialog=creationDialog(page,'Новый проект',body,compact=True)
        menu.on_dismiss=dismissed
        page.close(menu)
    menu=ft.AlertDialog(title=ft.Text(tr(page,'Создать')),content=ft.Column(tight=True,controls=[
        ft.ListTile(leading=ft.Icon(ft.Icons.ADD_PHOTO_ALTERNATE_OUTLINED),title=ft.Text(tr(page,'Публикация')),subtitle=ft.Text(tr(page,'Фото и описание работы')),on_click=lambda e:choose(e,'post')),
        ft.ListTile(leading=ft.Icon(ft.Icons.CHECKLIST),title=ft.Text(tr(page,'Личный проект')),subtitle=ft.Text(tr(page,'План и этапы лепки')),on_click=lambda e:choose(e,'project'))]),
        actions=[ft.TextButton(tr(page,'Отмена'),on_click=lambda e:page.close(menu))])
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
