"""Веб-запуск Flet с отдельным маршрутом скачивания PNG."""
from pathlib import Path

import flet as ft
from starlette.routing import Route

from download_service import downloadRecipe
from photo_upload import uploadPhoto, publishedPhoto
from project_upload import uploadProject


def createWebApp():
    from main import main

    def webMain(page):
        # Признак задаёт сервер. Клиент не должен включить чтение путей ПК,
        # подменив isWeb в сообщении WebSocket. page.data не очищается при выходе.
        page.data = {'isWebServer': True}
        main(page)

    application = ft.app(target=webMain, export_asgi_app=True,
                         assets_dir=str(Path(__file__).resolve().parent / 'assets'))
    # Маршрут должен находиться перед корневым Mount Flet.
    application.router.routes.insert(0, Route('/downloads/{ticket}', downloadRecipe, methods=['GET']))
    application.router.routes.insert(0, Route('/photo-uploads/{ticket}', uploadPhoto, methods=['PUT']))
    application.router.routes.insert(0, Route('/project-uploads/{ticket}', uploadProject, methods=['PUT']))
    application.router.routes.insert(0, Route('/post-photos/{photoId:int}', publishedPhoto, methods=['GET']))
    return application
