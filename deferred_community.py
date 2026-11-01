"""Проверка и постановка пользовательских отправок до первого сетевого запроса."""
import base64
import json
from api_client import ApiError
from community_outbox import enqueue,flush,result
from post_service import validatePostTitle,validatePostDescription,validateCommentText,POST_CATEGORIES,normalizeTags


def validatePublication(payload):
    for callback,key in ((validatePostTitle,'titleText'),(validatePostDescription,'descriptionText')):
        error=callback(payload.get(key,''))
        if error:raise ValueError(error)
    if payload.get('categoryName') not in POST_CATEGORIES:raise ValueError('Выберите категорию работы')
    normalizeTags(payload.get('tagsText',''))
    photos=payload.get('photos',[])
    if not isinstance(photos,list) or not 1<=len(photos)<=10:raise ValueError('Добавьте от 1 до 10 фото')
    for photo in photos:
        if not isinstance(photo,dict) or set(photo)!={'name','imageBase64'} or not isinstance(photo['name'],str):raise ValueError('Некорректное фото')
        try:data=base64.b64decode(photo['imageBase64'],validate=True)
        except (ValueError,TypeError):raise ValueError('Некорректное фото') from None
        if not 0<len(data)<=10*1024*1024:raise ValueError('Фотография больше 10 МБ')
    if len(json.dumps(payload).encode())>48*1024*1024-1024:raise ValueError('Публикация больше 48 МБ')


def submit(user,apiUrl,kind,payload,requestId=None):
    if kind=='publication':validatePublication(payload)
    elif kind=='comment':
        error=validateCommentText(payload['commentText'])
        if error:raise ValueError(error)
    requestId=enqueue(user,apiUrl,kind,payload,requestId)
    from offline_access import coolingDown,cachedUser
    try:
        if not (coolingDown() and cachedUser(user.get('sessionToken'))):flush(user,apiUrl,force=True)
    except ApiError as error:
        if error.statusCode==401:raise
        if error.statusCode!=0 and error.statusCode<500:raise
    row=result(user,apiUrl,requestId)
    if row['state']=='done':return True,'Отправлено на сервер',json.loads(row['resultJson'])
    if row['state']=='blocked':return False,row['lastError'],None
    return True,'Сохранено в очередь. Отправится при доступном сервере и открытом приложении',None
