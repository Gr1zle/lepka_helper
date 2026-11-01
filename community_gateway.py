"""Сообщество: локальные сервисы или сервер API, без подмены режима при сбое.

ID автора на сервере нельзя сравнивать с ID локальной технической записи.
Для кнопок владельца используется явный признак isOwn, рассчитанный сервером.
"""
import base64
import hashlib
import json
import uuid
from urllib.parse import urlencode

import account_gateway as accounts
from api_client import ApiError, apiRequest
from remote_account_cache import requireCachedUser
import database as db
import post_service as posts
import project_sharing as sharing
import workshop_service as workshops


def ownsItem(item, user):
    return bool(user and item.get('isOwn', item['userId'] == user['userId']))


class CommunityClient:
    def __init__(self, user):
        self.user = user
        self.apiUrl = accounts.getApiUrl()
        self.remote = bool(self.apiUrl)
        self.publicationKeys = {}

    def request(self, method, path, payload=None, personal=False):
        if accounts.getApiUrl() != self.apiUrl:
            raise ApiError('Адрес API изменился. Откройте приложение заново')
        if personal:
            if self.user is None:
                raise ApiError('Выполните вход', 401)
            requireCachedUser(self.user['userId'], self.user.get('sessionToken'))
        from community_cache import readCache,writeCache
        uid=self.user['userId'] if self.user else None
        from offline_access import coolingDown,cachedUser,noteUnavailable
        if method=='GET' and self.user and coolingDown() and cachedUser(self.user.get('sessionToken')):
            cached=readCache(uid,self.apiUrl,path)
            if cached is not None:return cached
            raise ApiError('Оффлайн: эти данные ещё не сохранены')
        try:
            data=apiRequest(method,'/community'+path,payload,self.user.get('sessionToken') if self.user else None)['data']
            if method=='GET':writeCache(uid,self.apiUrl,path,data)
            return data
        except ApiError as error:
            if method=='GET' and (error.statusCode==0 or error.statusCode>=500):
                noteUnavailable()
                cached=readCache(uid,self.apiUrl,path)
                if cached is not None:return cached
            raise

    def getPostsPage(self,mine=False,query='',category='Все',sort='new',offset=0,limit=12):
        if self.remote:
            try:
                batch=self.request('GET','/feed?'+urlencode(dict(mine=str(mine).lower(),query=query,category=category,sort=sort,offset=offset,limit=limit)),personal=mine)
            except ApiError as error:
                if error.statusCode!=0 and error.statusCode<500:raise
                batch={'items':[],'hasMore':False,'offline':True}
            from offline_access import coolingDown
            if coolingDown():batch={**batch,'offline':True}
            from community_cache import writeCache
            from community_outbox import lastLike
            items=[]
            for raw in batch['items']:
                item=dict(raw)
                if self.user:
                    writeCache(self.user['userId'],self.apiUrl,'like:'+str(item['postId']),dict(isLiked=item['isLiked'],likesCount=item['likesCount']))
                    desired=lastLike(self.user,self.apiUrl,item['postId'])
                    if desired is not None:
                        item['likesCount']=max(0,item['likesCount']+int(desired)-int(item['isLiked']));item['isLiked']=desired
                items.append(item)
            return {**batch,'items':items}
        import feed_service
        return feed_service.page(self.user['userId'] if self.user else None,mine,query,category,sort,offset,limit)

    def userStats(self):
        if not self.user:raise ApiError('Выполните вход',401)
        if self.remote:
            try:return self.request('GET','/my-stats',personal=True)
            except ApiError as error:
                if error.statusCode==0 or error.statusCode>=500:return {'posts':'—','likes':'—','offline':True}
                if error.statusCode!=404:raise
                items=self.getPosts(mine=True)  # Совместимость с сервером 0.7.0.
                return {'posts':len(items),'likes':sum(p['likesCount'] for p in items)}
        from feed_service import userStats
        return userStats(self.user['userId'])

    def getPosts(self, mine=False, search=None):
        if not self.remote:
            if search is not None:
                return workshops.searchCommunityWorks(**search)
            return posts.getUserPosts(self.user['userId']) if mine else posts.getCommunityPosts()
        query = {'mine': str(mine).lower(), 'limit': 100}
        if search is not None:
            query['searchMode'] = 'true'
            query.update({key: str(value).lower() if isinstance(value, bool) else value
                          for key, value in search.items() if value is not None})
            query['searchText'] = query.pop('queryText', '')
        items, offset, seenIds = [], 0, set()
        while True:
            batch = self.request('GET', '/posts?' + urlencode({**query, 'offset': offset}), personal=mine)
            for item in batch['items']:
                if item['postId'] not in seenIds:
                    seenIds.add(item['postId'])
                    items.append(item)
            if not batch['hasMore'] or not batch['items']:
                return items
            offset += len(batch['items'])

    def getPost(self, postId):
        if self.remote:
            try:
                return self.request('GET', f'/posts/{postId}')
            except ApiError as error:
                if error.statusCode == 404: return None
                raise
        with db.openDatabase() as connection:
            row = connection.execute('SELECT userId FROM posts WHERE postId=? AND isDeleted=0', (postId,)).fetchone()
        return next((item for item in posts.getUserPosts(row['userId']) if item['postId']==postId), None) if row else None

    def getComments(self, postId):
        if not self.remote:
            return posts.getPostComments(postId)
        try:
            return self.request('GET', f'/posts/{postId}/comments')
        except ApiError as error:
            if error.statusCode == 404:
                return []
            raise

    def getCommentsPage(self,postId,offset=0,limit=20):
        if self.remote:
            try:return self.request('GET',f'/posts/{postId}/comments-page?'+urlencode(dict(offset=offset,limit=limit)))
            except ApiError as error:
                if error.statusCode==404 or error.statusCode==0 or error.statusCode>=500:return {'items':[],'hasMore':False}
                raise
        rows=posts.getPostComments(postId,offset,limit+1,True)
        return {'items':rows[:limit],'hasMore':len(rows)>limit}

    def getPhoto(self, photoId):
        if not self.remote:
            return db.getPostPhoto(photoId)
        try:
            return base64.b64decode(self.request('GET', f'/photos/{photoId}')['imageBase64'], validate=True)
        except ApiError as error:
            if error.statusCode == 404 or error.statusCode==0 or error.statusCode>=500:
                return None
            raise

    def getThumbnail(self,photoId):
        if self.remote:
            try:return base64.b64decode(self.request('GET',f'/photos/{photoId}?thumbnail=true')['imageBase64'],validate=True)
            except ApiError as error:
                if error.statusCode==404 or error.statusCode==0 or error.statusCode>=500:return None
                raise
        from photo_service import photoThumbnail
        data=db.getPostPhoto(photoId)
        return photoThumbnail(data) if data else None

    def isLiked(self, item):
        if self.remote:
            return item.get('isLiked', False)
        return bool(self.user and posts.checkPostLikedByUser(item['postId'], self.user['userId']))

    def toggleLike(self, postId):
        if not self.remote:
            return posts.togglePostLike(postId, self.user['userId'])
        from community_cache import readCache,writeCache
        from community_outbox import lastLike
        from deferred_community import submit
        state=readCache(self.user['userId'],self.apiUrl,'like:'+str(postId))
        if state is None:
            item=self.getPost(postId)
            if not item:return False,None
            state={'isLiked':item.get('isLiked',False),'likesCount':item['likesCount']}
            writeCache(self.user['userId'],self.apiUrl,'like:'+str(postId),state)
        pending=lastLike(self.user,self.apiUrl,postId)
        current=state['isLiked'] if pending is None else pending
        desired=not current
        success,message,response=submit(self.user,self.apiUrl,'like',dict(postId=postId,isLiked=desired))
        if not success:raise ApiError(message,400)
        if response:
            writeCache(self.user['userId'],self.apiUrl,'like:'+str(postId),response)
            return response['isLiked'],response['likesCount']
        return desired,max(0,state['likesCount']+int(desired)-int(state['isLiked']))

    def deletePost(self, postId):
        return self.request('DELETE', f'/posts/{postId}', personal=True) if self.remote else posts.removePost(postId, self.user['userId'])

    def saveComment(self, postId, text,replyToId=None):
        if not self.remote:
            return posts.savePostComment(postId, self.user['userId'], text,replyToId)
        from deferred_community import submit
        try:
            success,message,response=submit(self.user,self.apiUrl,'comment',dict(postId=postId,commentText=text,replyToId=replyToId))
            return success,message,response['commentId'] if response else None
        except ValueError as error:return False,str(error),None

    def editComment(self, commentId, text):
        if not self.remote:
            return posts.editPostComment(commentId, self.user['userId'], text)
        self.request('PUT', f'/comments/{commentId}', {'commentText': text}, personal=True)
        return True, 'Комментарий изменён'

    def deleteComment(self, commentId):
        return self.request('DELETE', f'/comments/{commentId}', personal=True) if self.remote else posts.removePostComment(commentId, self.user['userId'])

    def sendPublication(self,payload):
        from deferred_community import submit
        payloadKey=hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()
        requestId=self.publicationKeys.setdefault(payloadKey,uuid.uuid4().hex)
        try:success,message,postId=submit(self.user,self.apiUrl,'publication',payload,requestId)
        except ValueError as error:return False,str(error),None
        if success and postId is not None:self.publicationKeys.pop(payloadKey,None)
        return success,message,postId

    def publishPost(self, titleText, descriptionText, categoryName, tagsText, photoFiles, challengeId=None):
        if not self.remote:
            return posts.savePost(self.user['userId'], titleText, descriptionText, categoryName, tagsText, photoFiles,challengeId=challengeId)
        payload = {'challengeId':challengeId,'titleText': titleText, 'descriptionText': descriptionText, 'categoryName': categoryName, 'tagsText': tagsText,
                   'photos': [{'name': photo['name'], 'imageBase64': base64.b64encode(photo['data']).decode()} for photo in photoFiles]}
        return self.sendPublication(payload)

    def publishProject(self, projectId, titleText, descriptionText, categoryName, tagsText,
                       resultStepId, otherStepIds, projectMixtureIds, workshopInfo=None,challengeId=None):
        args = (projectId, self.user['userId'], titleText, descriptionText, categoryName, tagsText,
                resultStepId, otherStepIds, projectMixtureIds, workshopInfo)
        if not self.remote:
            return sharing.publishProject(*args,challengeId=challengeId)
        requireCachedUser(self.user['userId'], self.user.get('sessionToken'))
        success, message, payload = sharing.prepareProjectPublication(*args)
        if not success:
            return False, message, None
        payload['challengeId']=challengeId
        payload['photos'] = [{'name': f'Этап-{index}.jpg', 'imageBase64': base64.b64encode(image).decode()}
                             for index, image in enumerate(payload['photos'])]
        return self.sendPublication(payload)

    def getWorkshop(self, postId):
        if not self.remote:
            return workshops.getWorkshop(postId)
        try:
            return self.request('GET', f'/workshops/{postId}')
        except ApiError as error:
            if error.statusCode == 404:
                return None
            raise

    def getState(self, postId):
        return self.request('GET', f'/workshops/{postId}/progress', personal=True) if self.remote else workshops.getUserWorkshopState(self.user['userId'], postId)

    def saveState(self, postId, state):
        return self.request('PUT', f'/workshops/{postId}/progress', state, personal=True) if self.remote else workshops.saveUserWorkshopState(self.user['userId'], postId, state)

    def copyRecipe(self, postId, mixtureIndex):
        if not self.remote:
            return sharing.copyPublishedMixture(postId, mixtureIndex, self.user['userId'])
        requireCachedUser(self.user['userId'], self.user.get('sessionToken'))
        workshop = self.getWorkshop(postId)
        if not workshop or type(mixtureIndex) is not int or not 0 <= mixtureIndex < len(workshop['mixtures']):
            return False, 'Рецепт недоступен', None
        return sharing.saveMixtureCopy(self.user['userId'], workshop['mixtures'][mixtureIndex])

    def copyProject(self, postId):
        if not self.remote:
            return workshops.addWorkshopAsProject(postId, self.user['userId'])
        requireCachedUser(self.user['userId'], self.user.get('sessionToken'))
        workshop = self.getWorkshop(postId)
        if workshop is None:
            return False, 'Мастер-класс недоступен', None
        return workshops.addWorkshopAsProject(postId, self.user['userId'], workshopData=workshop)

    def getLocalPosts(self):
        requireCachedUser(self.user['userId'], self.user.get('sessionToken'))
        return posts.getUserPosts(self.user['userId'])

    def exportLocalPost(self, localPostId):
        requireCachedUser(self.user['userId'], self.user.get('sessionToken'))
        with db.openDatabase() as connection:
            connection.execute('BEGIN IMMEDIATE')
            source = connection.execute('SELECT * FROM posts WHERE postId = ? AND userId = ? AND isDeleted = 0',
                                        (localPostId, self.user['userId'])).fetchone()
            if source is None:
                return False, 'Локальная работа недоступна', None
            payload = {key: source[key] or '' for key in ('titleText', 'descriptionText', 'categoryName', 'tagsText', 'projectDetailsJson')}
            # Служебный ID локального конкурса не принадлежит серверному пространству ID.
            from contest_entry import tokens,TAG
            payload['tagsText']=', '.join(v for v in tokens(payload['tagsText']) if not TAG.fullmatch(v))
            payload['photos'] = [{'name': f'Фото-{index}.jpg', 'imageBase64': base64.b64encode(record['imageData']).decode()}
                for index, record in enumerate(connection.execute('SELECT imageData FROM postPhotos WHERE postId = ? ORDER BY position', (localPostId,)))]
            if not payload['photos']:
                return False, 'У старой работы нет фото. Опубликуйте её заново с фотографией', None
            record = connection.execute('SELECT requestId, serverPostId FROM localPostExports WHERE apiUrl = ? AND userId = ? AND localPostId = ?',
                                        (self.apiUrl, self.user['userId'], localPostId)).fetchone()
            if record and record['serverPostId'] is not None:
                return True, 'Эта работа уже отправлена на сервер', record['serverPostId']
            requestId = record['requestId'] if record else uuid.uuid4().hex
            if record is None:
                connection.execute('INSERT INTO localPostExports VALUES (?, ?, ?, ?, NULL)',
                                   (self.apiUrl, self.user['userId'], localPostId, requestId))
        postId = self.request('POST', '/posts', {**payload, 'requestId': requestId}, personal=True)
        with db.openDatabase() as connection:
            connection.execute('UPDATE localPostExports SET serverPostId = ? WHERE apiUrl = ? AND userId = ? AND localPostId = ?',
                               (postId, self.apiUrl, self.user['userId'], localPostId))
        return True, 'Работа отправлена на сервер. Местная копия сохранена', postId
