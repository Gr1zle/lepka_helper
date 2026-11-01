"""Периоды, автоматический топ-3, атомарность и личные призовые уведомления."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date,timedelta
from unittest.mock import patch
import unittest
import test_challenges as fixtures
from test_community_api import publicationPayload
import database as db
import challenge_service as service
from password_service import createPasswordHash


class ResultTests(unittest.TestCase):
    setUp=fixtures.ChallengeTests.setUp

    def contest(self,**kwargs):
        return service.create(self.admin,'Кубок фигурок','Оцениваются форма и выразительность фигурки',service.today(),resultMode='votes',**kwargs)

    def expire(self,cid):
        with db.openDatabase() as c:c.execute("UPDATE challenges SET deadline='2000-01-01' WHERE challengeId=?",(cid,))

    def secondPost(self):
        return self.client.post('/community/posts',headers=self.headers['other'],json=publicationPayload()).json()['data']

    def test_automatic_top_three_ties_are_stable_and_only_one_set_of_notices(self):
        cid=self.contest(theme='Животные')
        service.submit(self.author,cid,self.post)
        other=self.secondPost();service.submit(self.other,cid,other)
        hashed,salt=createPasswordHash('Student123')
        owners=[]
        for n in range(2):
            uid=db.createUser(f'new{n}@example.com',hashed,salt,'Участник '+str(n))
            # Используем тот же проверенный сервис публикации с валидным фото.
            from post_service import savePost
            from image_fixtures import photo
            pid=savePost(uid,'Фигурка '+str(n),'Описание готовой фигурки','Животные','кот',[photo()])[2]
            service.submit(uid,cid,pid);owners.append((uid,pid))
        service.vote(self.admin,cid,self.post,True)
        service.vote(self.admin,cid,other,True)
        service.vote(self.author,cid,other,True)
        self.expire(cid)
        with self.assertRaises(ValueError):service.finish(self.admin,cid,'cancelled','Попытка отменить завершившийся конкурс')
        self.assertEqual(service.settleDue(),1)
        self.assertEqual(service.settleDue(),0)
        item=service.detail(self.author,cid)
        self.assertEqual(item['state'],'finished')
        self.assertEqual([a['postId'] for a in item['awards']],[other,self.post,owners[0][1]])
        self.assertEqual([a['votes'] for a in item['awards']],[2,1,0])
        self.assertEqual(service.notices(self.other)[0]['place'],1)
        self.assertEqual(service.profile(self.other)[0]['place'],1)
        with db.openDatabase() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM communityNotices').fetchone()[0],3)
            self.assertEqual(c.execute("SELECT COUNT(*) FROM adminAudit WHERE action='challenge.auto'").fetchone()[0],1)
        with self.assertRaises(ValueError):service.vote(self.admin,cid,self.post,True)

    def test_server_worker_settles_on_start_without_a_read_request(self):
        from threading import Event
        from fastapi.testclient import TestClient
        from backend.main import createApp
        from pathlib import Path
        cid=self.contest();service.submit(self.author,cid,self.post);self.expire(cid)
        finished=Event()
        original=service.settleDue
        def tick():
            result=original();finished.set();return result
        with patch('backend.main.challenge_service.settleDue',side_effect=tick):
            with TestClient(createApp(str(Path(db.DATABASE_PATH).parent))):
                self.assertTrue(finished.wait(3),'Background settlement did not run')
                with db.openDatabase() as c:
                    self.assertEqual(c.execute('SELECT state FROM challenges WHERE challengeId=?',(cid,)).fetchone()[0],'finished')
        self.assertEqual(service.notices(self.author)[0]['place'],1)

    def test_period_validation_and_scheduled_actions(self):
        start=(date.fromisoformat(service.today())+timedelta(days=1)).isoformat()
        end=(date.fromisoformat(service.today())+timedelta(days=3)).isoformat()
        cid=service.create(self.admin,'Будущий конкурс','Правила будущего конкурса',end,start,'Птицы','votes')
        self.assertEqual(service.detail(self.author,cid)['status'],'scheduled')
        with self.assertRaises(ValueError):service.submit(self.author,cid,self.post)
        with patch('challenge_service.today',return_value=start):
            self.assertTrue(service.submit(self.author,cid,self.post))
        with self.assertRaises(ValueError):service.create(self.admin,'Конкурс','Правила конкурса',end,'2099-01-01')
        with self.assertRaises(ValueError):service.create(self.admin,'Конкурс','Правила конкурса',end,theme='x'*81)
        with self.assertRaises(ValueError):service.create(self.admin,'Конкурс','Правила конкурса',end,resultMode='unknown')

    def test_notifications_disabled_and_read_is_owner_scoped(self):
        cid=self.contest();other=self.secondPost()
        service.submit(self.author,cid,self.post);service.submit(self.other,cid,other)
        with db.openDatabase() as c:c.execute('UPDATE users SET notificationsEnabled=0 WHERE userId=?',(self.other,))
        self.expire(cid)
        notices=self.client.get('/community/notices',headers=self.headers['author']).json()['data']
        self.assertEqual(len(notices),1)
        self.assertEqual(service.notices(self.other),[])
        nid=notices[0]['noticeId']
        self.assertFalse(self.client.put(f'/community/notices/{nid}/read',headers=self.headers['other']).json()['data'])
        self.assertFalse(service.notices(self.author)[0]['isRead'])
        self.assertTrue(self.client.put(f'/community/notices/{nid}/read',headers=self.headers['author']).json()['data'])
        self.assertTrue(service.notices(self.author)[0]['isRead'])
        self.assertEqual(self.client.get('/community/notices').status_code,401)
        self.assertEqual(self.client.get('/community/notices?offset=-1',headers=self.headers['author']).status_code,422)
        self.assertEqual(service.notices(self.author,50),[])

    def test_settlement_failure_rolls_back_awards_state_audit_and_notices(self):
        cid=self.contest();service.submit(self.author,cid,self.post);self.expire(cid)
        original=service.saveAward
        def fail(*args):
            original(*args);raise ValueError('Synthetic failure')
        with patch('challenge_service.saveAward',side_effect=fail):
            with self.assertRaises(ValueError):service.settleDue()
        with db.openDatabase() as c:
            self.assertEqual(c.execute('SELECT state FROM challenges WHERE challengeId=?',(cid,)).fetchone()[0],'open')
            self.assertEqual(c.execute('SELECT COUNT(*) FROM challengeAwards').fetchone()[0],0)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM communityNotices').fetchone()[0],0)
        self.assertEqual(service.settleDue(),1)

    def test_concurrent_settlement_and_deleted_winner_do_not_rerank(self):
        cid=self.contest();service.submit(self.author,cid,self.post);self.expire(cid)
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(lambda _:service.settleDue(),range(2))),[0,1])
        from moderation_service import removeMaterial
        removeMaterial(self.admin,'post',self.post,'Работа удалена за нарушение правил')
        item=service.detail(self.admin,cid)
        self.assertIsNone(item['awards'][0]['postId'])
        self.assertIsNone(item['awards'][0]['titleText'])
        self.assertEqual(len(service.notices(self.author)),1)
        db.deleteUserDataById(self.author)
        with db.openDatabase() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM communityNotices').fetchone()[0],0)
            self.assertEqual(c.execute('PRAGMA foreign_key_check').fetchall(),[])

    def test_empty_cancelled_blocked_authors_and_blocked_voters(self):
        empty=self.contest();self.expire(empty);service.settleDue()
        self.assertEqual(service.detail(self.admin,empty)['awards'],[])
        cid=self.contest();service.finish(self.admin,cid,'cancelled','Конкурс отменён организатором');self.expire(cid)
        self.assertEqual(service.settleDue(),0)
        cid=self.contest();service.submit(self.author,cid,self.post)
        other=self.secondPost();service.submit(self.other,cid,other)
        service.vote(self.other,cid,self.post,True)
        with db.openDatabase() as c:c.execute('UPDATE users SET isBlocked=1 WHERE userId=?',(self.other,))
        self.expire(cid);service.settleDue()
        awards=service.detail(self.admin,cid)['awards']
        self.assertEqual(len(awards),1);self.assertEqual(awards[0]['votes'],0)

    def test_legacy_modes_preserved_and_http_create_has_new_fields(self):
        self.assertEqual(service.detail(self.admin,self.cid)['resultMode'],'manual')
        response=self.client.post('/admin/challenges',headers=self.headers['admin'],json=dict(title='Новый конкурс',rules='Правила нового конкурса',deadline=service.today(),startsOn=service.today(),theme='Природа',resultMode='votes'))
        self.assertEqual(response.status_code,200,response.text)
        detail=self.client.get('/community/challenges/'+str(response.json()['data']),headers=self.headers['author']).json()['data']
        self.assertEqual(detail['theme'],'Природа')
        self.assertEqual(detail['resultMode'],'votes')
        self.assertEqual(self.client.get('/community/challenge-profile',headers=self.headers['other']).json()['data'],[])

if __name__=='__main__':unittest.main()
