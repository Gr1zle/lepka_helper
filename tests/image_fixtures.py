"""Небольшая тестовая картинка; фотографии пользователя тестам не нужны."""
from io import BytesIO
from PIL import Image


def photo():
    buffer = BytesIO()
    with Image.new('RGB', (80, 60), '#FF6B6B') as image:
        image.save(buffer, format='PNG')
    return {'name': 'Тест.png', 'data': buffer.getvalue()}
