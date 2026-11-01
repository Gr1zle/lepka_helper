"""Сквозной пакет публикации/конкурса, ответов, событий и порционной ленты."""
import unittest
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from PIL import Image
import test_challenges as fixtures
from test_community_api import publicationPayload
import database as db
import challenge_service as contests
import post_service as posts
from contest_entry import tag


class CommunityBatchTests(unittest.TestCase):
    setUp=fixtures.ChallengeTests.setUp

    def publish(self,**updates):
        body=publicationPayload();body.update(updates)
        return self.client.post('/community/posts',headers=self.headers['author'],json=body)

    def test_publish_selected_contest_is_atomic_tagged_and_retry_safe(self):
        body=publicationPayload();body['challengeId']=self.cid
        responses=[self.client.post('/community/posts',headers=self.headers['author'],json=body) for _ in range(2)]
        self.assertEqual([r.status_code for r in responses],[200,200])
        pid=responses[0].json()['data'];self.assertEqual(pid,responses[1].json()['data'])
        detail=contests.detail(self.author,self.cid)
        self.assertEqual(detail['myPostId'],pid)
        self.assertIn(tag(self.cid),posts.getUserPosts(self.author)[0]['tagsText'])
        count=len(posts.getUserPosts(self.author))
        self.assertEqual(self.publish(challengeId=self.cid).status_code,400)
        self.assertEqual(len(posts.getUserPosts(self.author)),count)
        contests.withdraw(self.author,self.cid)
        self.assertNotIn(tag(self.cid),next(p for p in posts.getUserPosts(self.author) if p['postId']==pid)['tagsText'])
        contests.settleDue();self.assertIsNone(contests.detail(self.author,self.cid)['myPostId'])

    def test_period_future_expired_tag_limits_and_non_reserved_substrings(self):
        with db.openDatabase() as c:c.execute("UPDATE challenges SET startsOn='2099-01-01' WHERE challengeId=?",(self.cid,))
        count=len(posts.getUserPosts(self.author))
        self.assertEqual(self.publish(challengeId=self.cid).status_code,400)
        self.assertEqual(self.publish(tagsText=tag(self.cid)).status_code,400)
        self.assertEqual(len(posts.getUserPosts(self.author)),count)
        with db.openDatabase() as c:c.execute('UPDATE challenges SET startsOn=? WHERE challengeId=?',(contests.today(),self.cid))
        self.assertEqual(self.publish(challengeId=self.cid,tagsText=', '.join('тег'+str(i) for i in range(10))).status_code,400)
        self.assertEqual(self.publish(tagsText=tag(self.cid)+'-копия').status_code,200)
        self.assertIsNone(contests.detail(self.author,self.cid)['myPostId'])

    def test_publication_failure_after_insert_leaves_no_rows_or_replay_keys(self):
        with db.openDatabase() as c:
            before=[c.execute('SELECT COUNT(*) FROM '+table).fetchone()[0] for table in ('posts','postPhotos','communityRequests')]
        with patch('contest_entry.enroll',side_effect=ValueError('Синтетическая ошибка отбора')):
            self.assertEqual(self.publish(challengeId=self.cid).status_code,400)
        with db.openDatabase() as c:
            after=[c.execute('SELECT COUNT(*) FROM '+table).fetchone()[0] for table in ('posts','postPhotos','communityRequests')]
        self.assertEqual(before,after)

    def test_tagged_backfill_date_filter_and_deterministic_first_work(self):
        # Имитируем старый клиент/импорт: теги существовали до нового механизма.
        second=self.publish().json()['data']
        with db.openDatabase() as c:
            c.execute('UPDATE posts SET tagsText=? WHERE postId IN (?,?)',(tag(self.cid),self.post,second))
            c.execute("UPDATE posts SET createdAt='2000-01-01 12:00:00' WHERE postId=?",(self.post,))
        self.assertEqual(contests.detail(self.author,self.cid)['myPostId'],second)
        contests.withdraw(self.author,self.cid)
        self.assertIsNone(contests.detail(self.author,self.cid)['myPostId'])

    def test_old_publication_replay_hash_and_existing_notice_ids_survive_upgrade(self):
        import hashlib,json
        body=publicationPayload();result=self.client.post('/community/posts',headers=self.headers['author'],json=body)
        payload={k:v for k,v in body.items() if k!='requestId'};payload.setdefault('projectDetailsJson','')
        oldHash=hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()
        with db.openDatabase() as c:c.execute('UPDATE communityRequests SET payloadHash=? WHERE requestId=?',(oldHash,body['requestId']))
        replay=self.client.post('/community/posts',headers=self.headers['author'],json=body)
        self.assertEqual(replay.status_code,200,replay.text);self.assertEqual(replay.json()['data'],result.json()['data'])

    def test_pre_batch_schema_migration_preserves_comments_and_award_notices(self):
        parent=posts.savePostComment(self.post,self.other,'Старый комментарий до обновления')[2]
        contests.submit(self.author,self.cid,self.post)
        with patch('challenge_service.today',return_value='2099-01-01'):
            contests.finish(self.admin,self.cid,'finished','Победитель выбран администратором',self.post)
        nid=contests.notices(self.author,kind='award')[0]['noticeId']
        with db.openDatabase() as c:
            c.execute('DROP TABLE activityNotices');c.execute('DROP TABLE challengeOptOuts')
            c.execute('ALTER TABLE postComments DROP COLUMN replyToId')
        db.initializeDatabase();db.initializeDatabase()
        self.assertEqual(posts.getPostComments(self.post)[0]['commentId'],parent)
        self.assertIsNone(posts.getPostComments(self.post)[0]['replyToId'])
        self.assertEqual(contests.notices(self.author,kind='award')[0]['noticeId'],nid)
        with db.openDatabase() as c:self.assertEqual(c.execute('PRAGMA foreign_key_check').fetchall(),[])

    def test_withdraw_opt_out_prevents_other_tagged_work_from_reentering(self):
        second=self.publish().json()['data']
        with db.openDatabase() as c:c.execute('UPDATE posts SET tagsText=? WHERE postId IN (?,?)',(tag(self.cid),self.post,second))
        self.assertEqual(contests.detail(self.author,self.cid)['myPostId'],self.post)
        contests.withdraw(self.author,self.cid)
        self.assertIsNone(contests.detail(self.author,self.cid)['myPostId'])
        self.assertTrue(contests.submit(self.author,self.cid,second))
        self.assertEqual(contests.detail(self.author,self.cid)['myPostId'],second)

    def test_comments_page_is_bounded_newest_first_and_has_no_overlap(self):
        with db.openDatabase() as c:
            c.executemany('INSERT INTO postComments(postId,userId,commentText) VALUES(?,?,?)',[(self.post,self.other,'Комментарий '+str(i)) for i in range(25)])
        first=self.client.get(f'/community/posts/{self.post}/comments-page').json()['data']
        second=self.client.get(f'/community/posts/{self.post}/comments-page?offset=20').json()['data']
        self.assertTrue(first['hasMore']);self.assertFalse(second['hasMore'])
        self.assertEqual(len(first['items']),20);self.assertEqual(len(second['items']),5)
        self.assertGreater(first['items'][0]['commentId'],second['items'][0]['commentId'])
        self.assertFalse(set(i['commentId'] for i in first['items'])&set(i['commentId'] for i in second['items']))
        self.assertEqual(self.client.get(f'/community/posts/{self.post}/comments-page?limit=100').status_code,422)

    def test_project_publication_participates_and_duplicate_does_not_leave_a_post(self):
        import project_service as projects
        import project_sharing as sharing
        from image_fixtures import photo
        project=projects.saveProject(self.author,'Конкурсный проект','Животные','','')[2]
        step=projects.saveProjectStep(project,'Готовая фигурка',self.author)[2]
        projects.saveProjectStepPhoto(project,step,self.author,photo())
        args=dict(projectId=project,userId=self.author,titleText='Проект для конкурса',descriptionText='Описание готовой фигурки',categoryName='Животные',tagsText='кот',resultStepId=step,otherStepIds=[],projectMixtureIds=[],challengeId=self.cid)
        success,message,pid=sharing.publishProject(**args)
        self.assertTrue(success,message);self.assertEqual(contests.detail(self.author,self.cid)['myPostId'],pid)
        count=len(posts.getUserPosts(self.author))
        self.assertFalse(sharing.publishProject(**args)[0])
        self.assertEqual(len(posts.getUserPosts(self.author)),count)

    def test_like_events_deduplicate_and_self_actions_do_not_notify(self):
        for _ in range(3):posts.togglePostLike(self.post,self.other)
        items=contests.notices(self.author)
        self.assertEqual(len(items),1);self.assertEqual(items[0]['kind'],'like')
        self.assertLess(items[0]['noticeId'],0)
        contests.readNotice(self.author,items[0]['noticeId'])
        posts.togglePostLike(self.post,self.other);posts.togglePostLike(self.post,self.other)
        self.assertTrue(contests.notices(self.author)[0]['isRead'])
        posts.togglePostLike(self.post,self.author)
        self.assertEqual(len(contests.notices(self.author)),1)
        self.assertEqual(contests.noticeSummary(self.author)['unread'],0)

    def test_replies_notify_parent_and_owner_without_duplicate_and_validate_same_post(self):
        first=self.client.post(f'/community/posts/{self.post}/comments',headers=self.headers['other'],json={'commentText':'Какую глину вы используете?'})
        parent=first.json()['data']
        result=self.client.post(f'/community/posts/{self.post}/comments',headers=self.headers['admin'],json={'commentText':'Для этой фигурки подходит мягкая глина.','replyToId':parent})
        self.assertEqual(result.status_code,200,result.text)
        author=contests.notices(self.author);reader=contests.notices(self.other)
        self.assertEqual([r['kind'] for r in reader],['reply'])
        self.assertEqual(len(author),2)
        data=self.client.get(f'/community/posts/{self.post}/comments').json()['data']
        self.assertEqual(data[-1]['replyToId'],parent);self.assertEqual(data[-1]['replyNickname'],'Другой')
        otherPost=self.publish().json()['data']
        bad=self.client.post(f'/community/posts/{otherPost}/comments',headers=self.headers['other'],json={'commentText':'Ответ к другой работе','replyToId':parent})
        self.assertEqual(bad.status_code,400)
        self.assertEqual(self.client.put(f"/community/comments/{result.json()['data']}",headers=self.headers['admin'],json={'commentText':'Новый текст ответа','replyToId':parent}).status_code,422)

    def test_reply_to_post_owner_creates_one_reply_event_and_delete_cleans_context(self):
        parent=posts.savePostComment(self.post,self.author,'Авторская подпись к своей работе')[2]
        reply=posts.savePostComment(self.post,self.other,'Отличная аккуратная фигурка',parent)[2]
        self.assertEqual([r['kind'] for r in contests.notices(self.author)],['reply'])
        posts.removePostComment(parent,self.author)
        self.assertIsNone(posts.getPostComments(self.post)[0]['replyToId'])
        posts.removePostComment(reply,self.other)
        self.assertEqual(contests.notices(self.author),[])

    def test_settings_filters_read_all_and_notice_ownership(self):
        with db.openDatabase() as c:c.execute('UPDATE users SET notificationsEnabled=0 WHERE userId=?',(self.author,))
        posts.togglePostLike(self.post,self.other);posts.savePostComment(self.post,self.other,'Очень красивая фигурка')
        self.assertEqual(contests.notices(self.author),[])
        with db.openDatabase() as c:c.execute('UPDATE users SET notificationsEnabled=1 WHERE userId=?',(self.author,))
        posts.togglePostLike(self.post,self.other);posts.togglePostLike(self.post,self.other)
        posts.savePostComment(self.post,self.admin,'Подскажите размер этой фигурки')
        self.assertEqual(len(contests.notices(self.author,kind='like')),1)
        self.assertEqual(len(contests.notices(self.author,kind='comment')),1)
        nid=contests.notices(self.author)[0]['noticeId']
        self.assertFalse(self.client.put(f'/community/notices/{nid}/read',headers=self.headers['other']).json()['data'])
        self.assertEqual(self.client.get('/community/notice-summary',headers=self.headers['author']).json()['data']['unread'],2)
        self.assertEqual(self.client.put('/community/notices-read-all',headers=self.headers['other']).json()['data'],0)
        self.assertEqual(self.client.put('/community/notices-read-all',headers=self.headers['author']).json()['data'],2)
        self.assertEqual(contests.notices(self.author,unread=True),[])
        self.assertEqual(len(contests.notices(self.author)),2)
        self.assertEqual(self.client.get('/community/notices?kind=unknown',headers=self.headers['author']).status_code,422)
        self.assertEqual(self.client.put('/community/notices/0/read',headers=self.headers['author']).status_code,400)

    def test_activity_failure_rolls_back_comment_and_like(self):
        with patch('activity_service.record',side_effect=ValueError('Не удалось сохранить событие')):
            with self.assertRaises(ValueError):posts.togglePostLike(self.post,self.other)
            self.assertFalse(posts.savePostComment(self.post,self.other,'Комментарий с откатом')[0])
        self.assertEqual(posts.getPostComments(self.post),[])
        self.assertFalse(posts.checkPostLikedByUser(self.post,self.other))

    def test_feed_pages_search_sort_owner_and_thumbnail(self):
        for i in range(13):self.publish(titleText=f'Работа серии {i:02}')
        first=self.client.get('/community/feed?limit=12').json()['data']
        second=self.client.get('/community/feed?limit=12&offset=12').json()['data']
        self.assertTrue(first['hasMore']);self.assertFalse(second['hasMore'])
        self.assertFalse(set(r['postId'] for r in first['items'])&set(r['postId'] for r in second['items']))
        self.assertEqual(len(first['items'])+len(second['items']),14)
        search=self.client.get('/community/feed',params={'query':'СЕРИИ 05','sort':'popular'},headers=self.headers['author']).json()['data']['items']
        self.assertEqual(len(search),1);self.assertTrue(search[0]['isOwn'])
        self.assertEqual(self.client.get('/community/feed?mine=true').status_code,401)
        self.assertEqual(self.client.get('/community/feed?category=Unknown').status_code,400)
        posts.togglePostLike(self.post,self.other)
        top=self.client.get('/community/feed?sort=popular').json()['data']['items'][0]
        self.assertEqual(top['postId'],self.post)
        import base64
        image=self.client.get(f"/community/photos/{top['photoIds'][0]}?thumbnail=true").json()['data']['imageBase64']
        with Image.open(BytesIO(base64.b64decode(image))) as preview:
            self.assertLessEqual(preview.width,400);self.assertLessEqual(preview.height,300)

    def test_concurrent_like_event_and_delete_account_materials(self):
        with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(lambda _:posts.togglePostLike(self.post,self.other),range(2)))
        self.assertEqual(len(contests.notices(self.author)),1)
        posts.removePost(self.post,self.author)
        self.assertEqual(contests.notices(self.author),[])
        with db.openDatabase() as c:self.assertEqual(c.execute('PRAGMA foreign_key_check').fetchall(),[])

if __name__=='__main__':unittest.main()
