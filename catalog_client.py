"""Complete, checked offline packages, scoped to the current account and API."""
import base64
from datetime import datetime, timezone
import hashlib
import json
import time
from database import openDatabase
from api_client import apiRequest, ApiError, getApiUrl
from account_gateway import getSessionUser
from lesson_library import requireOwner
from learning_catalog import validateDocument, validateAsset
import learning_catalog as local

MAX_CACHE_BYTES=100*1024*1024


class CatalogClient:
    def __init__(self,user):
        self.user=user;self.url=getApiUrl()
    def active(self):
        if not self.user or getApiUrl()!=self.url:raise ApiError('Аккаунт или сервер изменился',401)
        verified=getSessionUser(self.user.get('sessionToken'))
        if not verified or verified['userId']!=self.user['userId']:raise ApiError('Выполните вход снова',401)
        return verified
    def request(self,method,path,payload=None,callback=None):
        user=self.active()
        if self.url:
            if user.get('offline'):raise ApiError('Сервер недоступен. Сохранённые материалы доступны офлайн.')
            return apiRequest(method,path,payload,user['sessionToken'])['data']
        return callback(user['userId'])
    def index(self,refresh=True):
        self.active()
        with openDatabase() as c:
            previous=c.execute('SELECT itemsJson FROM learningIndex WHERE userId=? AND apiUrl=?',(self.user['userId'],self.url)).fetchone()
        if not refresh:return json.loads(previous[0]) if previous else []
        try:items=self.request('GET','/learning/catalog',callback=local.listing)
        except ApiError as error:
            if error.statusCode not in (0,503,502,504):raise
            if previous:return json.loads(previous[0])
            raise
        self.active()
        with openDatabase() as c:
            subscribed={r[0] for r in c.execute('SELECT category FROM learningSubscriptions WHERE userId=? AND apiUrl=?',(self.user['userId'],self.url))}
            known={r['contentId']:r['revision'] for r in json.loads(previous[0])} if previous else {}
            for item in items:
                if previous and item['category'] in subscribed and item['revision']>known.get(item['contentId'],0):
                    c.execute('INSERT OR IGNORE INTO learningCatalogNotices(userId,apiUrl,contentId,revision,title,createdAt) VALUES (?,?,?,?,?,?)',
                        (self.user['userId'],self.url,item['contentId'],item['revision'],item['title'],datetime.now(timezone.utc).isoformat()))
            c.execute('INSERT OR REPLACE INTO learningIndex VALUES (?,?,?)',(self.user['userId'],self.url,json.dumps(items,ensure_ascii=False)))
            c.execute('''DELETE FROM learningCatalogNotices WHERE userId=? AND apiUrl=? AND rowid NOT IN
                (SELECT rowid FROM learningCatalogNotices WHERE userId=? AND apiUrl=? ORDER BY createdAt DESC LIMIT 100)''',
                (self.user['userId'],self.url,self.user['userId'],self.url))
        return items
    def adminIndex(self):return self.request('GET','/admin/catalog',callback=lambda uid:local.listing(uid,True))
    def detail(self,contentId,admin=False):
        return self.request('GET',('/admin' if admin else '/learning')+'/catalog/'+contentId,callback=lambda uid:local.detail(uid,contentId,admin))
    def upload(self,name,kind,content):
        validateAsset(name,content,kind)
        return self.request('POST','/admin/catalog-assets',dict(name=name,kind=kind,contentBase64=base64.b64encode(content).decode()),lambda uid:local.upload(uid,name,kind,content))
    def save(self,cid,revision,state,document,reason):
        return self.request('PUT','/admin/catalog/'+cid,dict(expectedRevision=revision,state=state,document=document,reason=reason),lambda uid:local.save(uid,cid,revision,state,document,reason))
    def statistics(self):return self.request('GET','/admin/catalog-statistics',callback=local.statistics)
    def cleanup(self):return self.request('POST','/admin/catalog-cleanup',callback=local.cleanUnused)
    def download(self,cid):
        info=self.detail(cid);document,refs=validateDocument(info['document']);assets={}
        size=len(json.dumps(info,ensure_ascii=False).encode())
        for assetId,kind in set(refs):
            record=self.request('GET','/learning/assets/'+assetId,callback=lambda uid,aid=assetId:local.asset(uid,aid))
            raw=base64.b64decode(record['contentBase64'],validate=True)
            if record['kind']!=kind or hashlib.sha256(kind.encode()+raw).hexdigest()!=assetId:raise ValueError('Контрольная сумма учебного файла не совпала')
            validateAsset(record['name'],raw,kind)
            assets[assetId]={**record,'assetId':assetId};size+=len(record['contentBase64'])
            if size>MAX_CACHE_BYTES:raise ValueError('Материал не помещается в кеш 100 МБ')
        infoJson=json.dumps(info,ensure_ascii=False);assetsJson=json.dumps(assets)
        size=len(infoJson.encode())+len(assetsJson.encode())
        # A concurrent edit must not create a mixed-version offline package.
        if self.detail(cid)['revision']!=info['revision']:raise ValueError('Материал изменился во время загрузки. Повторите скачивание')
        self.active()
        with openDatabase() as c:
            c.execute('BEGIN IMMEDIATE');requireOwner(c,self.user['userId'])
            total,count=c.execute('SELECT COALESCE(SUM(byteCount),0),COUNT(*) FROM learningCache WHERE userId=? AND apiUrl=? AND contentId!=?',(self.user['userId'],self.url,cid)).fetchone()
            if total+size>MAX_CACHE_BYTES or count>=20:raise ValueError('Кеш заполнен: максимум 20 материалов и 100 МБ. Удалите ненужную копию')
            c.execute('INSERT OR REPLACE INTO learningCache VALUES (?,?,?,?,?,?,?,?)',(self.user['userId'],self.url,cid,info['revision'],infoJson,assetsJson,size,time.time()))
        return info
    def cached(self,cid):
        self.active()
        with openDatabase() as c:row=c.execute('SELECT documentJson,assetsJson FROM learningCache WHERE userId=? AND apiUrl=? AND contentId=?',(self.user['userId'],self.url,cid)).fetchone()
        if not row:raise ValueError('Сначала сохраните материал для офлайн-просмотра')
        return json.loads(row[0]),json.loads(row[1])
    def downloads(self):
        self.active()
        with openDatabase() as c:return [dict(r) for r in c.execute('SELECT contentId,revision,byteCount FROM learningCache WHERE userId=? AND apiUrl=?',(self.user['userId'],self.url))]
    def removeDownload(self,cid):
        self.active()
        with openDatabase() as c:c.execute('DELETE FROM learningCache WHERE userId=? AND apiUrl=? AND contentId=?',(self.user['userId'],self.url,cid))
    def personal(self,cid):
        self.active()
        with openDatabase() as c:row=c.execute('SELECT * FROM learningPersonal WHERE userId=? AND apiUrl=? AND contentId=?',(self.user['userId'],self.url,cid)).fetchone()
        return dict(row) if row else dict(revision=0,checkedJson='[]',favorite=0,note='')
    def savePersonal(self,cid,revision,checked,favorite,note):
        info,_=self.cached(cid)
        if revision!=info['revision']:raise ValueError('Сохранённая версия изменилась. Откройте её заново')
        steps=info['document']['steps']
        if not isinstance(checked,list) or any(type(i) is not int or not 0<=i<len(steps) for i in checked) or len(set(checked))!=len(checked):raise ValueError('Некорректные этапы')
        if type(favorite) is not bool or not isinstance(note,str) or len(note)>2000:raise ValueError('Заметка до 2000 символов')
        complete=info['kind']=='lesson' and bool(steps) and len(checked)==len(steps)
        with openDatabase() as c:
            c.execute('''INSERT INTO learningPersonal VALUES (?,?,?,?,?,?,?,1,?) ON CONFLICT(userId,apiUrl,contentId) DO UPDATE SET
                revision=excluded.revision,checkedJson=excluded.checkedJson,favorite=excluded.favorite,note=excluded.note,
                viewPending=1,completePending=excluded.completePending''',(self.user['userId'],self.url,cid,revision,json.dumps(checked),int(favorite),note,int(complete)))
        return complete
    def flushUsage(self):
        self.active()
        with openDatabase() as c:rows=c.execute('SELECT * FROM learningPersonal WHERE userId=? AND apiUrl=? AND viewPending=1',(self.user['userId'],self.url)).fetchall()
        for row in rows:
            try:self.request('POST','/learning/catalog/'+row['contentId']+'/usage',dict(revision=row['revision'],completed=bool(row['completePending'])),lambda uid:local.usage(uid,row['contentId'],row['revision'],bool(row['completePending'])))
            except ApiError as error:
                if error.statusCode in (404,409):continue
                raise
            except (LookupError,local.CatalogConflict):continue
            with openDatabase() as c:c.execute('UPDATE learningPersonal SET viewPending=0 WHERE userId=? AND apiUrl=? AND contentId=? AND revision=? AND checkedJson=? AND completePending=?',(self.user['userId'],self.url,row['contentId'],row['revision'],row['checkedJson'],row['completePending']))
    def subscribe(self,category,selected):
        self.active()
        if category not in local.CATEGORIES or type(selected) is not bool:raise ValueError('Выберите категорию')
        with openDatabase() as c:
            if selected:c.execute('INSERT OR IGNORE INTO learningSubscriptions VALUES (?,?,?)',(self.user['userId'],self.url,category))
            else:c.execute('DELETE FROM learningSubscriptions WHERE userId=? AND apiUrl=? AND category=?',(self.user['userId'],self.url,category))


def catalogNotices(user):
    if not user:return []
    from personal_notices import settings
    with openDatabase() as c:
        owner=c.execute('SELECT notificationsEnabled FROM users WHERE userId=?',(user['userId'],)).fetchone()
        if not owner or not owner[0] or not settings(user['userId'])['lessonsEnabled']:return []
        rows=c.execute('SELECT rowid,* FROM learningCatalogNotices WHERE userId=? AND apiUrl=? ORDER BY createdAt DESC',(user['userId'],getApiUrl())).fetchall()
    return [dict(noticeId='catalog:'+str(r['rowid']),source='learning',kind='catalog',title=r['title'],preview='Новая версия учебного материала',createdAt=r['createdAt'],isRead=r['isRead'],contentId=r['contentId']) for r in rows]


def readCatalog(userId,noticeId=None):
    with openDatabase() as c:
        requireOwner(c,userId)
        if noticeId is None:c.execute('UPDATE learningCatalogNotices SET isRead=1 WHERE userId=? AND apiUrl=?',(userId,getApiUrl()))
        else:c.execute('UPDATE learningCatalogNotices SET isRead=1 WHERE userId=? AND apiUrl=? AND rowid=?',(userId,getApiUrl(),int(noticeId.split(':')[1])))
