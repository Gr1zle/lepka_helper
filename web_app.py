"""Веб-запуск Flet с отдельным маршрутом скачивания PNG."""
from pathlib import Path

import flet as ft
from starlette.routing import Route

from download_service import downloadRecipe


def createWebApp():
    from main import main
    application = ft.app(target=main, export_asgi_app=True,
                         assets_dir=str(Path(__file__).resolve().parent / 'assets'))
    # Маршрут должен находиться перед корневым Mount Flet.
    application.router.routes.insert(0, Route('/downloads/{ticket}', downloadRecipe, methods=['GET']))
    return application
