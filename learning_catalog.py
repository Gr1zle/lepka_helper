"""Editable catalogue. Publications are versioned; binary files are immutable."""
import base64
from datetime import datetime, timezone
import hashlib
import json
import re
import time
import uuid
from database import openDatabase
from role_service import require, accessIn
from moderation_service import audit, cleanReason
from photo_service import preparePhoto
from model_import import decodeModel

MAX_ASSET=12*1024*1024
CATEGORIES=('Животные','Еда','Персонажи','Транспорт','Аниме','Природа','Другое')
LEVELS=('Начинающий','Средний','Продвинутый')


class CatalogConflict(ValueError):pass


def timestamp():return datetime.now(timezone.utc).isoformat()


def validateAsset(name,content,kind):
    if not isinstance(name,str) or not 1<=len(name)<=120 or '/' in name or '\\' in name:
        raise ValueError('Укажите имя файла без пути, до 120 символов')
    if not isinstance(content,bytes) or not 0<len(content)<=MAX_ASSET:raise ValueError('Файл должен быть не больше 12 МБ')
    if kind=='image':
        photo=preparePhoto(name,content)
        return photo['data'],'image/jpeg','image.jpg'
    if kind=='model':
        decodeModel(name,content)
        return content,'application/zip' if name.lower().endswith('.zip') else 'text/plain',name
    if kind=='video':
        # Bound and structurally inspect ISO BMFF boxes; never execute an uploaded file.
        if not name.lower().endswith('.mp4') or len(content)<32 or content[4:8]!=b'ftyp':
            raise ValueError('Видео: выберите MP4 (рекомендуется H.264/AAC), до 12 МБ')
        offset=0;boxes=set()
        while offset<len(content):
            if offset+8>len(content):raise ValueError('Повреждённый MP4')
            size=int.from_bytes(content[offset:offset+4],'big');header=8
            if size==1:
                if offset+16>len(content):raise ValueError('Повреждённый MP4')
                size=int.from_bytes(content[offset+8:offset+16],'big');header=16
            if size==0:size=len(content)-offset
            if size<header or offset+size>len(content):raise ValueError('Повреждённый MP4')
            boxes.add(content[offset+4:offset+8]);offset+=size
        if not {b'ftyp',b'moov',b'mdat'}<=boxes:raise ValueError('MP4 должен содержать видео и индекс воспроизведения')
        return content,'video/mp4',name
    raise ValueError('Неизвестный тип файла')


def upload(actorId,name,kind,content):
    with openDatabase() as c:require(c,actorId,'catalog.manage')
    content,mime,name=validateAsset(name,content,kind)
    assetId=hashlib.sha256(kind.encode()+content).hexdigest()
    with openDatabase() as c:
        c.execute('BEGIN IMMEDIATE');require(c,actorId,'catalog.manage')
        if not c.execute('SELECT 1 FROM learningAssets WHERE assetId=?',(assetId,)).fetchone():
            size=c.execute('SELECT COALESCE(SUM(LENGTH(content)),0) FROM learningAssets').fetchone()[0]
            if size+len(content)>128*1024*1024:raise ValueError('Хранилище учебных файлов заполнено (128 МБ). Удалите неиспользуемые файлы')
            c.execute('INSERT INTO learningAssets VALUES (?,?,?,?,?,?,?)',(assetId,kind,name,mime,content,actorId,time.time()))
    return dict(assetId=assetId,kind=kind,name=name,mime=mime,byteCount=len(content))


def text(value,label,minimum,maximum):
    if not isinstance(value,str) or not minimum<=len(value.strip())<=maximum:raise ValueError(f'{label}: от {minimum} до {maximum} символов')
    return value.strip()


def validateDocument(document):
    fields={'kind','title','category','level','timeMinutes','description','tags','materials','steps','coverAsset','modelAsset'}
    if not isinstance(document,dict) or set(document)!=fields:raise ValueError('Некорректные поля учебного материала')
    clean=dict(document)
    if clean['kind'] not in ('lesson','model') or clean['category'] not in CATEGORIES or clean['level'] not in LEVELS:raise ValueError('Выберите тип, категорию и сложность')
    clean['title']=text(clean['title'],'Название',3,100);clean['description']=text(clean['description'],'Описание',10,3000)
    if type(clean['timeMinutes']) is not int or not 1<=clean['timeMinutes']<=600:raise ValueError('Время: от 1 до 600 минут')
    for field,limit,length in [('tags',10,40),('materials',30,120)]:
        if not isinstance(clean[field],list) or len(clean[field])>limit:raise ValueError('Слишком много тегов или материалов')
        clean[field]=[text(v,field,1,length) for v in clean[field]]
    if not isinstance(clean['steps'],list) or len(clean['steps'])>20:raise ValueError('До 20 этапов')
    refs=[]
    def ref(value,kind):
        if value is not None:
            if not isinstance(value,str) or not re.fullmatch('[a-f0-9]{64}',value):raise ValueError('Некорректная ссылка на файл')
            refs.append((value,kind))
    ref(clean['coverAsset'],'image');ref(clean['modelAsset'],'model')
    if clean['kind']=='model' and not clean['modelAsset']:raise ValueError('Для 3D-материала нужен OBJ или ZIP')
    if clean['kind']=='lesson' and (not clean['steps'] or not clean['materials']):raise ValueError('Для урока нужны материалы и хотя бы один этап')
    cleanSteps=[]
    for step in clean['steps']:
        if not isinstance(step,dict) or set(step)!={'text','imageAsset','videoAsset'}:raise ValueError('Некорректный этап')
        cleanSteps.append({**step,'text':text(step['text'],'Этап',3,2000)})
        ref(step['imageAsset'],'image');ref(step['videoAsset'],'video')
    clean['steps']=cleanSteps
    return clean,refs


def rowData(row,details=False):
    doc=json.loads(row['documentJson'])
    result=dict(contentId=row['contentId'],revision=row['revision'],state=row['state'],updatedAt=row['updatedAt'],
                **{key:doc[key] for key in ('kind','title','category','level','timeMinutes','description','tags')})
    result['withVideo']=any(s['videoAsset'] for s in doc['steps'])
    result['author']=row['author'] if 'author' in row.keys() else 'Сотрудник'
    if details:result['document']=doc
    return result


def save(actorId,contentId,expectedRevision,state,document,reason):
    reason=cleanReason(reason)
    if not isinstance(contentId,str) or not re.fullmatch('[a-f0-9]{32}',contentId):raise ValueError('Некорректный ID материала')
    if type(expectedRevision) is not int or not 0<=expectedRevision<2**63-2 or state not in ('draft','published','archived'):raise ValueError('Некорректная версия или статус')
    document,refs=validateDocument(document)
    with openDatabase() as c:
        c.execute('BEGIN IMMEDIATE');actor=require(c,actorId,'catalog.manage')
        row=c.execute('SELECT * FROM learningCatalog WHERE contentId=?',(contentId,)).fetchone()
        if (row['revision'] if row else 0)!=expectedRevision:raise CatalogConflict('Материал изменён другим сотрудником. Откройте актуальную версию')
        if row and json.loads(row['documentJson'])['kind']!=document['kind']:raise ValueError('Тип существующего материала менять нельзя')
        if not row and c.execute('SELECT COUNT(*) FROM learningCatalog').fetchone()[0]>=200:raise ValueError('Каталог ограничен 200 материалами')
        for assetId,kind in refs:
            asset=c.execute('SELECT kind FROM learningAssets WHERE assetId=?',(assetId,)).fetchone()
            if not asset or asset[0]!=kind:raise ValueError('Файл отсутствует или имеет другой тип')
        c.execute('''INSERT INTO learningCatalog VALUES (?,?,?,?,?,?) ON CONFLICT(contentId) DO UPDATE SET
            revision=excluded.revision,state=excluded.state,documentJson=excluded.documentJson,updatedAt=excluded.updatedAt''',
            (contentId,expectedRevision+1,state,json.dumps(document,ensure_ascii=False),actorId,timestamp()))
        audit(c,actor,'catalog.save','catalog',0,f'{contentId} v{expectedRevision+1} {state}: {reason}')
        return rowData(c.execute('SELECT * FROM learningCatalog WHERE contentId=?',(contentId,)).fetchone(),True)


def listing(userId,admin=False):
    with openDatabase() as c:
        accessIn(c,userId)
        if admin:require(c,userId,'catalog.manage')
        rows=c.execute("SELECT l.*,COALESCE(u.nickname,'Сотрудник') AS author FROM learningCatalog l LEFT JOIN users u ON u.userId=l.creatorId "+('' if admin else "WHERE l.state='published' ")+'ORDER BY l.updatedAt DESC,l.contentId').fetchall()
    return [rowData(r) for r in rows]


def detail(userId,contentId,admin=False):
    with openDatabase() as c:
        accessIn(c,userId)
        if admin:require(c,userId,'catalog.manage')
        row=c.execute("SELECT l.*,COALESCE(u.nickname,'Сотрудник') AS author FROM learningCatalog l LEFT JOIN users u ON u.userId=l.creatorId WHERE l.contentId=?",(contentId,)).fetchone()
    if not row or (not admin and row['state']!='published'):raise LookupError('Учебный материал недоступен')
    return rowData(row,True)


def asset(userId,assetId):
    with openDatabase() as c:
        actor=accessIn(c,userId)
        if 'catalog.manage' not in actor['permissions']:
            found=False
            for row in c.execute("SELECT documentJson FROM learningCatalog WHERE state='published'"):
                if any(ref==assetId for ref,_ in validateDocument(json.loads(row[0]))[1]):found=True;break
            if not found:raise LookupError('Файл недоступен')
        row=c.execute('SELECT * FROM learningAssets WHERE assetId=?',(assetId,)).fetchone()
        if not row:raise LookupError('Файл недоступен')
        return dict(assetId=assetId,kind=row['kind'],name=row['name'],mime=row['mime'],contentBase64=base64.b64encode(row['content']).decode())


def usage(userId,contentId,revision,completed=False):
    if type(revision) is not int or type(completed) is not bool:raise ValueError('Некорректная статистика')
    with openDatabase() as c:
        c.execute('BEGIN IMMEDIATE');accessIn(c,userId)
        row=c.execute("SELECT revision,documentJson FROM learningCatalog WHERE contentId=? AND state='published'",(contentId,)).fetchone()
        if not row:raise LookupError('Материал недоступен')
        if row['revision']!=revision:raise CatalogConflict('Версия материала изменилась')
        if completed and json.loads(row['documentJson'])['kind']!='lesson':raise ValueError('Завершить можно урок')
        c.execute('''INSERT INTO learningUsage VALUES (?,?,?,?,?) ON CONFLICT(userId,contentId,revision) DO UPDATE SET
            completedAt=COALESCE(learningUsage.completedAt,excluded.completedAt)''',(userId,contentId,revision,timestamp(),timestamp() if completed else None))
    return True


def statistics(actorId):
    with openDatabase() as c:
        require(c,actorId,'catalog.manage')
        items=[dict(r) for r in c.execute('''SELECT l.contentId,l.revision,l.state,l.documentJson,
            COUNT(DISTINCT u.userId) AS readers,COUNT(DISTINCT CASE WHEN u.completedAt IS NOT NULL THEN u.userId END) AS completed
            FROM learningCatalog l LEFT JOIN learningUsage u ON u.contentId=l.contentId GROUP BY l.contentId ORDER BY l.updatedAt DESC''')]
        size=c.execute('SELECT COALESCE(SUM(LENGTH(content)),0) FROM learningAssets').fetchone()[0]
    for item in items:item['title']=json.loads(item.pop('documentJson'))['title']
    return dict(items=items,assetBytes=size)


def cleanUnused(actorId):
    with openDatabase() as c:
        c.execute('BEGIN IMMEDIATE');actor=require(c,actorId,'catalog.manage')
        used={ref for row in c.execute('SELECT documentJson FROM learningCatalog') for ref,_ in validateDocument(json.loads(row[0]))[1]}
        removed=0
        for row in c.execute('SELECT assetId FROM learningAssets').fetchall():
            if row[0] not in used:removed+=c.execute('DELETE FROM learningAssets WHERE assetId=?',(row[0],)).rowcount
        audit(c,actor,'catalog.cleanup','catalog',0,f'Неиспользуемых файлов удалено: {removed}')
    return removed
