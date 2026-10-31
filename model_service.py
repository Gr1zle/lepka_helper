"""Каталог встроенных OBJ и личное избранное моделей."""
from copy import deepcopy
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED
from database import openDatabase
from learning_assets import MODEL_ITEMS
from mesh_renderer import parseObj

ASSET_ROOT=Path(__file__).resolve().parent/'assets'
MODEL_CATEGORIES=('Все',*dict.fromkeys(item['category'] for item in MODEL_ITEMS))


def getModel(modelId):
    return next((deepcopy(item) for item in MODEL_ITEMS if item['modelId']==modelId),None)


def requireModel(modelId):
    model=getModel(modelId)
    if model is None:raise ValueError('Модель не найдена')
    return model


@lru_cache(maxsize=6)
def loadModel(modelId):
    requireModel(modelId)
    return parseObj((ASSET_ROOT/'models'/f'{modelId}.obj').read_text(encoding='utf-8'),
                    (ASSET_ROOT/'models'/f'{modelId}.mtl').read_text(encoding='utf-8'))


def searchModels(query='',category='Все',level='Все',maxTime=None):
    from lesson_service import getLessonById,IDEA_LEVELS
    if not isinstance(query,str) or len(query)>120:
        raise ValueError('Поисковый запрос должен быть не длиннее 120 символов')
    if category not in MODEL_CATEGORIES or level not in ('Все',*IDEA_LEVELS):
        raise ValueError('Выберите категорию и сложность')
    query=' '.join(query.split()).casefold().replace('ё','е')
    if query and len(query)<2:return []
    if maxTime is not None and (isinstance(maxTime,bool) or not str(maxTime).isdecimal()):
        raise ValueError('Некорректное время')
    result=[]
    for item in MODEL_ITEMS:
        lesson=getLessonById(item['lessonId'])
        haystack=' '.join(('3d модель фигурка',item['title'],item['category'],*item['tags'],lesson['title'],lesson['description'],*lesson['materials'])).casefold().replace('ё','е')
        if (category!='Все' and item['category']!=category or level!='Все' and lesson['level']!=level
                or maxTime is not None and lesson['timeMinutes']>int(maxTime)
                or not all(word in haystack for word in query.split())):continue
        result.append(deepcopy(item))
    return result


def favoriteModelIds(userId):
    with openDatabase() as connection:
        records=connection.execute('''SELECT f.modelId FROM modelFavorites f JOIN users u ON u.userId=f.userId
            WHERE f.userId=? AND u.isBlocked=0''',(userId,)).fetchall()
    return {row['modelId'] for row in records if getModel(row['modelId'])}


def saveModelFavorite(userId,modelId,selected):
    requireModel(modelId)
    if type(selected) is not bool:raise ValueError('Некорректная отметка избранного')
    with openDatabase() as connection:
        connection.execute('BEGIN IMMEDIATE')
        if connection.execute("SELECT userId FROM users WHERE userId=? AND isBlocked=0 AND roleName!='deleted'",(userId,)).fetchone() is None:
            raise ValueError('Аккаунт недоступен')
        if selected:
            connection.execute('INSERT OR IGNORE INTO modelFavorites(userId,modelId) VALUES (?,?)',(userId,modelId))
        else:
            connection.execute('DELETE FROM modelFavorites WHERE userId=? AND modelId=?',(userId,modelId))
    return selected


def modelBundle(modelId):
    requireModel(modelId)
    output=BytesIO()
    with ZipFile(output,'w',ZIP_DEFLATED) as archive:
        for extension in ('obj','mtl'):
            name=f'{modelId}.{extension}'
            archive.writestr(name,(ASSET_ROOT/'models'/name).read_bytes())
        archive.writestr('README.txt','Author-created geometric learning model from Lepka Helper.\nKeep OBJ and MTL in the same folder.\n')
    return output.getvalue()
