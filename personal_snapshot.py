"""Перенос личных данных без аккаунтов, токенов, чужих ID и публикаций."""
import base64
from datetime import datetime
from io import BytesIO
import json
from zipfile import ZipFile,ZIP_DEFLATED
from color_service import normalizeMixture
from database import openDatabase
from lesson_service import LESSON_ITEMS,getLessonById,normalizeLessonState
from learning_assets import MODEL_ITEMS
from model_import import decodeModel,modelPreview
from project_archive import decodeProject,exportProject,importProject

MAX_SNAPSHOT_BYTES=20*1024*1024
MAX_PROJECTS=100
MAX_MIXTURES=300


def encodeSnapshot(document):
    content=json.dumps(document,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')
    if len(content)>MAX_SNAPSHOT_BYTES:raise ValueError('Личный архив больше 20 МБ. Уменьшите число фотографий или моделей')
    return content


def requireOwner(connection,userId):
    if connection.execute("SELECT 1 FROM users WHERE userId=? AND isBlocked=0 AND roleName!='deleted'",(userId,)).fetchone() is None:
        raise ValueError('Аккаунт недоступен')


def timestamp(text,nullable=False):
    if text is None and nullable:return
    if not isinstance(text,str) or len(text)>40:raise ValueError('Некорректная дата в архиве')
    try:datetime.fromisoformat(text)
    except ValueError:raise ValueError('Некорректная дата в архиве') from None


def decodeSnapshot(content):
    if not isinstance(content,bytes) or not 0<len(content)<=MAX_SNAPSHOT_BYTES:
        raise ValueError('Выберите личный JSON-архив не больше 20 МБ')
    try:
        document=json.loads(content.decode('utf-8-sig'))
        if not isinstance(document,dict) or set(document)!={'format','version','projects','mixtures','lessons','models','modelFavorites'} or document['format']!='lepka-personal' or type(document['version']) is not int or document['version']!=1:
            raise ValueError('Неподдерживаемый формат личного архива')
        for key,limit in [('projects',MAX_PROJECTS),('mixtures',MAX_MIXTURES),('lessons',len(LESSON_ITEMS)),('models',20),('modelFavorites',len(MODEL_ITEMS))]:
            if not isinstance(document[key],list) or len(document[key])>limit:raise ValueError('Превышен лимит раздела '+key)
        cleanProjects=[]
        for item in document['projects']:
            if not isinstance(item,dict) or set(item)!={'archive','createdAt','completedAt'}:raise ValueError('Некорректный проект архива')
            cleanProjects.append(decodeProject(encodeSnapshot(item['archive'])))
            timestamp(item['createdAt']);timestamp(item['completedAt'],True)
        cleanMixtures=[]
        for item in document['mixtures']:
            if not isinstance(item,dict) or set(item)!={'mixtureName','resultHex','totalWeight','recipeItems'}:raise ValueError('Некорректная смесь архива')
            cleanMixtures.append(normalizeMixture(**item))
        seen=set()
        for item in document['lessons']:
            if not isinstance(item,dict) or set(item)!={'lessonId','state','updatedAt','note','favorite'}:raise ValueError('Некорректный урок архива')
            lessonId=item['lessonId'];lesson=getLessonById(lessonId) if type(lessonId) is int else None
            if not lesson or lessonId in seen:raise ValueError('Неизвестный или повторный урок')
            seen.add(lessonId)
            if not isinstance(item['note'],str) or len(item['note'])>2000 or type(item['favorite']) is not bool:raise ValueError('Некорректная заметка или избранное')
            if item['state'] is not None:
                if not isinstance(item['state'],dict) or set(item['state'])!={'lastStep','completedSteps','checkedMaterials','isCompleted'}:raise ValueError('Некорректные поля прогресса урока')
                normalizeLessonState(lesson,item['state']);timestamp(item['updatedAt'])
            elif item['updatedAt'] is not None:raise ValueError('Дата без прогресса урока')
        cleanModels=[]
        for item in document['models']:
            if not isinstance(item,dict) or set(item)!={'title','objText','materialText','favorite'}:raise ValueError('Некорректная модель архива')
            if not isinstance(item['title'],str) or not 1<=len(item['title'])<=80 or type(item['favorite']) is not bool:raise ValueError('Некорректное название модели')
            if not isinstance(item['objText'],str) or not isinstance(item['materialText'],str):raise ValueError('Некорректный OBJ/MTL')
            buffer=BytesIO()
            with ZipFile(buffer,'w',ZIP_DEFLATED) as archive:
                archive.writestr('model.obj',item['objText']);archive.writestr('model.mtl',item['materialText'])
            decoded=decodeModel('model.zip',buffer.getvalue());cleanModels.append(decoded)
        valid={item['modelId'] for item in MODEL_ITEMS}
        if any(not isinstance(value,str) or value not in valid for value in document['modelFavorites']) or len(set(document['modelFavorites']))!=len(document['modelFavorites']):raise ValueError('Неизвестная модель в избранном')
        return document,cleanProjects,cleanMixtures,cleanModels
    except (UnicodeError,KeyError,TypeError,RecursionError,OverflowError) as error:
        raise ValueError('Не удалось прочитать личный архив') from error


def exportSnapshot(userId,existingConnection=None):
    from contextlib import nullcontext
    with (nullcontext(existingConnection) if existingConnection is not None else openDatabase()) as connection:
        if not connection.in_transaction:connection.execute('BEGIN')
        requireOwner(connection,userId)
        projects=[]
        for row in connection.execute('SELECT projectId,createdAt,completedAt FROM projects WHERE userId=? ORDER BY projectId',(userId,)).fetchall():
            projects.append(dict(archive=json.loads(exportProject(row['projectId'],userId,connection)),createdAt=row['createdAt'],completedAt=row['completedAt']))
        mixtures=[dict(mixtureName=row['mixtureName'],resultHex=row['resultHex'],totalWeight=row['totalWeight'],recipeItems=json.loads(row['recipeJson']))
                  for row in connection.execute('SELECT * FROM colorMixtures WHERE userId=? ORDER BY mixtureId',(userId,))]
        lessons=[]
        for lesson in LESSON_ITEMS:
            lessonId=lesson['lessonId']
            row=connection.execute('SELECT stateJson,updatedAt FROM lessonProgress WHERE userId=? AND lessonId=?',(userId,lessonId)).fetchone()
            note=connection.execute('SELECT noteText FROM lessonNotes WHERE userId=? AND lessonId=?',(userId,lessonId)).fetchone()
            favorite=connection.execute('SELECT 1 FROM lessonFavorites WHERE userId=? AND lessonId=?',(userId,lessonId)).fetchone() is not None
            if row or note or favorite:lessons.append(dict(lessonId=lessonId,state=normalizeLessonState(lesson,json.loads(row['stateJson'])) if row else None,updatedAt=row['updatedAt'] if row else None,note=note[0] if note else '',favorite=favorite))
        favorites={row[0] for row in connection.execute('SELECT modelId FROM modelFavorites WHERE userId=?',(userId,))}
        models=[dict(title=row['title'],objText=row['objText'],materialText=row['materialText'],favorite=row['modelId'] in favorites)
                for row in connection.execute('SELECT * FROM importedModels WHERE userId=? ORDER BY rowid',(userId,))]
        document=dict(format='lepka-personal',version=1,projects=projects,mixtures=mixtures,lessons=lessons,models=models,modelFavorites=sorted(favorites&{item['modelId'] for item in MODEL_ITEMS}))
        content=encodeSnapshot(document)
    decodeSnapshot(content)
    return content


def applySnapshot(userId,content,connection):
    """Вызывается только внутри общей транзакции и после сохранения страховочной копии."""
    import secrets
    document,cleanProjects,cleanMixtures,cleanModels=decodeSnapshot(content)
    requireOwner(connection,userId)
    for table in ('projectMixtures','projectSteps'):
        connection.execute(f'DELETE FROM {table} WHERE projectId IN (SELECT projectId FROM projects WHERE userId=?)',(userId,))
    for table in ('projects','colorMixtures','lessonProgress','lessonNotes','lessonFavorites','importedModels','modelFavorites','learningNotices'):
        connection.execute(f'DELETE FROM {table} WHERE userId=?',(userId,))
    for item in document['projects']:
        projectId=importProject(userId,encodeSnapshot(item['archive']),connection)
        connection.execute('UPDATE projects SET createdAt=?,completedAt=? WHERE projectId=?',(item['createdAt'],item['completedAt'],projectId))
        # Архив уже проверен декодером изображений; не пережимаем JPEG повторно.
        stepIds=[row[0] for row in connection.execute('SELECT stepId FROM projectSteps WHERE projectId=? ORDER BY sortOrder,stepId',(projectId,))]
        for stepId,step in zip(stepIds,item['archive']['steps']):
            if step['photo'] is not None:connection.execute('UPDATE projectSteps SET photoImage=? WHERE stepId=?',(base64.b64decode(step['photo'],validate=True),stepId))
        final=item['archive']['project'].get('finalPhoto')
        if final is not None:connection.execute('UPDATE projects SET finalPhotoImage=? WHERE projectId=?',(base64.b64decode(final,validate=True),projectId))
    for item in cleanMixtures:
        connection.execute('INSERT INTO colorMixtures(userId,mixtureName,resultHex,totalWeight,recipeJson) VALUES (?,?,?,?,?)',
                           (userId,item['mixtureName'],item['resultHex'],item['totalWeight'],json.dumps(item['recipeItems'],ensure_ascii=False)))
    for item in document['lessons']:
        lessonId=item['lessonId']
        if item['state'] is not None:connection.execute('INSERT INTO lessonProgress VALUES (?,?,?,?)',(userId,lessonId,json.dumps(item['state'],ensure_ascii=False),item['updatedAt']))
        if item['note']:connection.execute('INSERT INTO lessonNotes(userId,lessonId,noteText) VALUES (?,?,?)',(userId,lessonId,item['note']))
        if item['favorite']:connection.execute('INSERT INTO lessonFavorites(userId,lessonId) VALUES (?,?)',(userId,lessonId))
    for original,decoded in zip(document['models'],cleanModels):
        modelId='user-'+secrets.token_hex(12)
        connection.execute('INSERT INTO importedModels(modelId,userId,title,objText,materialText,previewImage) VALUES (?,?,?,?,?,?)',
            (modelId,userId,original['title'],decoded['objText'],decoded['materialText'],modelPreview(decoded['mesh'])))
        if original['favorite']:connection.execute('INSERT INTO modelFavorites VALUES (?,?)',(userId,modelId))
    connection.executemany('INSERT INTO modelFavorites VALUES (?,?)',[(userId,modelId) for modelId in document['modelFavorites']])
    return snapshotSummary(document)


def snapshotSummary(document):
    return {key:len(document[key]) for key in ('projects','mixtures','lessons','models')}
