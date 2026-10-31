"""Ограниченный импорт OBJ/MTL без распаковки файлов в файловую систему."""
from io import BytesIO
from pathlib import PurePosixPath
import re
import secrets
from zipfile import ZipFile, BadZipFile
from PIL import Image, ImageDraw
from database import openDatabase
from mesh_renderer import parseObj, projectMesh

MAX_MODEL_BYTES = 3 * 1024 * 1024
MAX_OBJ_BYTES = 2_000_000
MAX_MTL_BYTES = 100_000
MAX_IMPORTED_MODELS = 20
MAX_IMPORT_TRIANGLES = 3000


def decodeModel(filename, content):
    if not isinstance(filename,str) or not isinstance(content,bytes) or not 0 < len(content) <= MAX_MODEL_BYTES:
        raise ValueError('Выберите OBJ или ZIP не больше 3 МБ')
    name = PurePosixPath(filename.replace('\\','/')).name
    extension = PurePosixPath(name).suffix.lower()
    obj, material = content, b''
    if extension == '.zip':
        try:
            with ZipFile(BytesIO(content)) as archive:
                files = archive.infolist()
                if not 1 <= len(files) <= 8: raise ValueError('В ZIP должно быть не больше 8 файлов')
                objFiles, mtlFiles, seen = [], [], set()
                size = 0
                for info in files:
                    path = PurePosixPath(info.filename)
                    if ('\\' in info.filename or path.is_absolute() or '..' in path.parts or ':' in info.filename
                            or info.filename.casefold() in seen or info.flag_bits & 1
                            or (info.external_attr >> 16) & 0o170000 == 0o120000):
                        raise ValueError('ZIP содержит неподдерживаемый путь или файл')
                    seen.add(info.filename.casefold())
                    size += info.file_size
                    if size > MAX_OBJ_BYTES+MAX_MTL_BYTES+20_000: raise ValueError('Распакованная модель слишком большая')
                    if info.is_dir(): continue
                    suffix = path.suffix.lower()
                    if suffix == '.obj': objFiles.append(info)
                    elif suffix == '.mtl': mtlFiles.append(info)
                    elif suffix not in ('.txt','.md'): raise ValueError('ZIP поддерживает OBJ, MTL и текстовое описание. Текстуры пока не поддерживаются')
                if len(objFiles)!=1 or len(mtlFiles)>1: raise ValueError('В ZIP нужен ровно один OBJ и не больше одного MTL')
                if objFiles[0].file_size>MAX_OBJ_BYTES or mtlFiles and mtlFiles[0].file_size>MAX_MTL_BYTES:
                    raise ValueError('OBJ должен быть не больше 2 МБ, MTL — 100 КБ')
                obj = archive.read(objFiles[0]); material = archive.read(mtlFiles[0]) if mtlFiles else b''
                name = PurePosixPath(objFiles[0].filename).name
        except (BadZipFile, RuntimeError, NotImplementedError, OSError) as error:
            raise ValueError('Не удалось прочитать ZIP с моделью') from error
    elif extension != '.obj': raise ValueError('Поддерживаются OBJ и ZIP с OBJ/MTL')
    if len(obj)>MAX_OBJ_BYTES or len(material)>MAX_MTL_BYTES: raise ValueError('OBJ должен быть не больше 2 МБ, MTL — 100 КБ')
    try:
        objText, materialText = obj.decode('utf-8-sig'), material.decode('utf-8-sig')
    except UnicodeError as error: raise ValueError('OBJ и MTL должны быть текстом UTF-8') from error
    mesh = parseObj(objText,materialText)
    if len(mesh.faces)>MAX_IMPORT_TRIANGLES:
        raise ValueError('Для плавного просмотра допускается до 3000 треугольников. Упростите модель перед импортом')
    # Ссылки исходного файла не переходят в экспорт и никогда не читаются с диска/из сети.
    objText = '\n'.join(line for line in objText.splitlines() if line.split('#',1)[0].split()[:1]!=['mtllib'])
    if materialText: objText = 'mtllib model.mtl\n'+objText
    # Сохраняем только поддерживаемые цвета; текстуры и внешние пути не экспортируются.
    materialText = '\n'.join(line for line in materialText.splitlines() if line.split('#',1)[0].split()[:1] in (['newmtl'],['Kd']))
    title = PurePosixPath(name).stem.strip()[:80] or 'Моя модель'
    return {'title':title,'objText':objText,'materialText':materialText,'mesh':mesh}


def modelPreview(mesh):
    image = Image.new('RGB',(360,280),'#edf1f5')
    draw = ImageDraw.Draw(image)
    for face in projectMesh(mesh,360,280): draw.polygon(face['points'],fill=face['color'])
    buffer = BytesIO(); image.save(buffer,format='PNG')
    return buffer.getvalue()


def importModel(userId, filename, content, title=None):
    decoded = decodeModel(filename,content)
    title = decoded['title'] if title is None else title.strip() if isinstance(title,str) else ''
    if not 1 <= len(title) <= 80: raise ValueError('Название модели должно содержать от 1 до 80 символов')
    preview = modelPreview(decoded['mesh'])
    modelId = 'user-'+secrets.token_hex(12)
    with openDatabase() as connection:
        connection.execute('BEGIN IMMEDIATE')
        if connection.execute("SELECT userId FROM users WHERE userId=? AND isBlocked=0 AND roleName!='deleted'",(userId,)).fetchone() is None:
            raise ValueError('Аккаунт недоступен')
        if connection.execute('SELECT COUNT(*) FROM importedModels WHERE userId=?',(userId,)).fetchone()[0]>=MAX_IMPORTED_MODELS:
            raise ValueError('Можно хранить до 20 личных моделей. Удалите ненужные перед импортом')
        connection.execute('INSERT INTO importedModels(modelId,userId,title,objText,materialText,previewImage) VALUES (?,?,?,?,?,?)',
            (modelId,userId,title,decoded['objText'],decoded['materialText'],preview))
    return modelId


def importedModel(modelId,userId):
    if not isinstance(modelId,str) or not re.fullmatch(r'user-[0-9a-f]{24}',modelId) or userId is None: return None
    with openDatabase() as connection:
        record = connection.execute('''SELECT m.* FROM importedModels m JOIN users u ON u.userId=m.userId
            WHERE m.modelId=? AND m.userId=? AND u.isBlocked=0 AND u.roleName!='deleted' ''',(modelId,userId)).fetchone()
    return dict(record) if record else None


def listImportedModels(userId):
    with openDatabase() as connection:
        rows = connection.execute('''SELECT m.modelId,m.title,m.previewImage FROM importedModels m
            JOIN users u ON u.userId=m.userId WHERE m.userId=? AND u.isBlocked=0 AND u.roleName!='deleted'
            ORDER BY m.createdAt DESC,m.rowid DESC''',(userId,)).fetchall()
    return [dict(row) for row in rows]


def deleteImportedModel(userId,modelId):
    with openDatabase() as connection:
        connection.execute('BEGIN IMMEDIATE')
        cursor = connection.execute('''DELETE FROM importedModels WHERE userId=? AND modelId=? AND EXISTS (
            SELECT 1 FROM users WHERE userId=? AND isBlocked=0 AND roleName!='deleted')''',(userId,modelId,userId))
        if cursor.rowcount:
            connection.execute('DELETE FROM modelFavorites WHERE userId=? AND modelId=?',(userId,modelId))
        return bool(cursor.rowcount)
