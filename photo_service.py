"""Проверка фотографий до записи: исходники пользователя не изменяются."""
from io import BytesIO
import warnings

from PIL import Image, ImageDraw, ImageOps, UnidentifiedImageError

MAX_PHOTO_BYTES = 10 * 1024 * 1024
MAX_PHOTO_PIXELS = 20_000_000
PHOTO_EXTENSIONS = {'jpg': 'JPEG', 'jpeg': 'JPEG', 'png': 'PNG', 'webp': 'WEBP'}


def preparePhoto(name, data):
    if not isinstance(name, str) or '.' not in name:
        raise ValueError('Выберите файл JPG, PNG или WebP')
    extension = name.rsplit('.', 1)[-1].lower()
    if extension not in PHOTO_EXTENSIONS:
        raise ValueError('Разрешены фотографии JPG, PNG или WebP')
    if not isinstance(data, bytes) or not 0 < len(data) <= MAX_PHOTO_BYTES:
        raise ValueError('Размер каждой фотографии должен быть от 1 байта до 10 МБ')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as source:
                if source.format != PHOTO_EXTENSIONS[extension]:
                    raise ValueError('Содержимое фотографии не соответствует расширению файла')
                if source.width * source.height > MAX_PHOTO_PIXELS:
                    raise ValueError('Фотография слишком большая: максимум 20 мегапикселей')
                if getattr(source, 'n_frames', 1) != 1:
                    raise ValueError('Выберите неподвижную фотографию вместо анимации')
                source.load()
                image = ImageOps.exif_transpose(source).convert('RGBA')
                image.thumbnail((1600, 1600))
                background = Image.new('RGB', image.size, 'white')
                background.paste(image, mask=image.getchannel('A'))
                # Новое изображение не содержит EXIF, GPS и исходных метаданных.
                output = BytesIO()
                background.save(output, format='JPEG', quality=85)
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ValueError('Не удалось прочитать фотографию') from None
    cleanName = name.replace('\\', '/').rsplit('/', 1)[-1].rsplit('.', 1)[0][:100] or 'photo'
    return {'name': cleanName + '.jpg', 'data': output.getvalue()}


def prepareAvatar(name, data):
    photo = preparePhoto(name, data)
    with Image.open(BytesIO(photo['data'])) as source:
        # Квадрат из центра, затем круглая маска без EXIF и GPS.
        image = ImageOps.fit(source, (512, 512), method=Image.Resampling.LANCZOS).convert('RGBA')
        mask = Image.new('L', (512, 512), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, 511, 511), fill=255)
        image.putalpha(mask)
        output = BytesIO()
        image.save(output, format='PNG')
        return output.getvalue()
