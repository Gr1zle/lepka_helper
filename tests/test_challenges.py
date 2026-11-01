"""HTTP и транзакции полного конкурсного цикла в отдельной временной БД."""
from pathlib import Path
import tempfile
import os
import unittest
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from fastapi.testclient import TestClient
from backend.main import createApp
from scripts.manage_admin import grantAdmin
from password_service import createPasswordHash
from test_community_api import publicationPayload
import database as db
import challenge_service as service
import moderation_service


class ChallengeTests(unittest.TestCase):
    def setUp(self):
        root = Path(os.environ.get('RUNNER_TEMP', '/workspace')) / 'work'
        root.mkdir(parents=True, exist_ok=True)
        folder = tempfile.TemporaryDirectory(dir=root)
        self.addCleanup(folder.cleanup)
        self.client = TestClient(createApp(folder.name))
        self.client.__enter__(); self.addCleanup(self.client.__exit__, None, None, None)
        hashed, salt = createPasswordHash('Student123')
        self.admin = db.createUser('admin@example.com', hashed, salt, 'Администратор')
        self.author = db.createUser('author@example.com', hashed, salt, 'Автор')
        self.other = db.createUser('other@example.com', hashed, salt, 'Другой')
        grantAdmin(db.DATABASE_PATH, 'admin@example.com')
        self.headers = {}
        for email in ('admin', 'author', 'other'):
            res = self.client.post('/auth/login', json={'email': email+'@example.com', 'password':'Student123'})
            self.headers[email] = {'Authorization': 'Bearer '+res.json()['data']['sessionToken']}
        self.post = self.client.post('/community/posts', headers=self.headers['author'], json=publicationPayload()).json()['data']
        self.cid = service.create(self.admin, 'Осенний кот', 'Слепите котика и опубликуйте фото готовой работы.', service.today())

    def test_permissions_strict_payload_and_live_role_checks(self):
        body = dict(title='Задание', rules='Правила нового задания', deadline=service.today())
        self.assertEqual(self.client.get('/community/challenges').status_code, 401)
        self.assertEqual(self.client.post('/admin/challenges', headers=self.headers['author'], json=body).status_code, 403)
        self.assertEqual(self.client.post('/admin/challenges', headers=self.headers['admin'], json={**body,'actorId':self.admin}).status_code,422)
        with db.openDatabase() as c: c.execute("UPDATE users SET roleName='user' WHERE userId=?", (self.admin,))
        self.assertEqual(self.client.post('/admin/challenges',headers=self.headers['admin'],json=body).status_code,403)

    def test_entry_owner_duplicate_replace_withdraw_and_single_post(self):
        path=f'/community/challenges/{self.cid}/entry'
        self.assertEqual(self.client.put(path, headers=self.headers['other'], json={'postId':self.post}).status_code,400)
        self.assertTrue(self.client.put(path, headers=self.headers['author'], json={'postId':self.post}).json()['data'])
        self.assertFalse(self.client.put(path, headers=self.headers['author'], json={'postId':self.post}).json()['data'])
        self.assertEqual(self.client.get(f'/community/posts/{self.post}', headers=self.headers['other']).json()['data']['isOwn'],False)
        self.assertEqual(self.client.get(f'/community/posts/{self.post}', headers=self.headers['author']).json()['data']['isOwn'],True)
        self.assertEqual(service.detail(self.author,self.cid)['myPostId'],self.post)
        self.assertEqual(len(service.listing(self.author,'mine')),1)
        self.assertTrue(service.withdraw(self.author,self.cid))
        self.assertFalse(service.withdraw(self.author,self.cid))
        self.assertEqual(service.listing(self.author,'mine'),[])

    def test_deadline_final_decision_and_immutable_results(self):
        service.submit(self.author,self.cid,self.post)
        with self.assertRaises(ValueError):service.finish(self.admin,self.cid,'finished','Достойная работа участника',self.post)
        with patch('challenge_service.today',return_value='2099-01-01'):
            self.assertEqual(service.detail(self.author,self.cid)['status'],'judging')
            with self.assertRaises(ValueError):service.withdraw(self.author,self.cid)
            with self.assertRaises(ValueError):service.submit(self.other,self.cid,self.post)
            service.finish(self.admin,self.cid,'finished','Победа за аккуратную проработку формы',self.post)
        item=service.detail(self.author,self.cid)
        self.assertEqual(item['winner']['nickname'],'Автор')
        self.assertEqual(item['status'],'finished')
        self.assertEqual(service.listing(self.author),[])
        self.assertEqual(len(service.listing(self.author,'finished')),1)
        with self.assertRaises(ValueError):service.finish(self.admin,self.cid,'cancelled','Другая причина отмены')
        with db.openDatabase() as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM adminAudit WHERE action='challenge.finished'").fetchone()[0],1)

    def test_cancel_and_finish_without_winner(self):
        service.finish(self.admin,self.cid,'cancelled','Задание отменено организатором')
        with self.assertRaises(ValueError):service.submit(self.author,self.cid,self.post)
        cid=service.create(self.admin,'Второе задание','Достаточно подробные правила',service.today())
        with patch('challenge_service.today',return_value='2099-01-01'):
            service.finish(self.admin,cid,'finished','Ни одна работа не была подана')
        self.assertIsNone(service.detail(self.author,cid)['winner'])

    def test_moderator_deletion_cascades_and_removed_winner_is_not_displayed(self):
        service.submit(self.author,self.cid,self.post)
        with patch('challenge_service.today',return_value='2099-01-01'):
            service.finish(self.admin,self.cid,'finished','Выбрана эта работа победителем',self.post)
        moderation_service.removeMaterial(self.admin,'post',self.post,'Публикация нарушает правила сообщества')
        item=service.detail(self.author,self.cid)
        self.assertEqual(item['entriesCount'],0)
        self.assertIsNone(item['winnerPostId'])
        self.assertIsNone(item['winner'])
        with db.openDatabase() as c:self.assertEqual(c.execute('PRAGMA foreign_key_check').fetchall(),[])

    def test_votes_are_separate_idempotent_and_close_with_deadline(self):
        service.submit(self.author,self.cid,self.post)
        path=f'/community/challenges/{self.cid}/votes/{self.post}'
        self.assertEqual(self.client.put(path,headers=self.headers['author'],json={'liked':True}).status_code,400)
        for _ in range(2):
            self.assertEqual(self.client.put(path,headers=self.headers['other'],json={'liked':True}).json()['data'],1)
        detail=self.client.get(f'/community/challenges/{self.cid}?sort=votes',headers=self.headers['other']).json()['data']
        self.assertEqual(detail['entries'][0]['votes'],1)
        self.assertTrue(detail['entries'][0]['isVoted'])
        with db.openDatabase() as c:self.assertEqual(c.execute('SELECT likesCount FROM posts WHERE postId=?',(self.post,)).fetchone()[0],0)
        with patch('challenge_service.today',return_value='2099-01-01'):
            self.assertEqual(self.client.put(path,headers=self.headers['other'],json={'liked':False}).status_code,400)
        self.assertEqual(service.vote(self.other,self.cid,self.post,False),0)
        self.assertEqual(service.vote(self.other,self.cid,self.post,False),0)
        service.vote(self.other,self.cid,self.post,True)
        service.withdraw(self.author,self.cid)
        with db.openDatabase() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM challengeVotes').fetchone()[0],0)

    def test_vote_ranking_pagination_and_concurrent_duplicates(self):
        service.submit(self.author,self.cid,self.post)
        otherPost=self.client.post('/community/posts',headers=self.headers['other'],json=publicationPayload()).json()['data']
        service.submit(self.other,self.cid,otherPost)
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(list(pool.map(lambda _:service.vote(self.other,self.cid,self.post,True),range(2))),[1,1])
        ranked=service.detail(self.admin,self.cid,sort='votes')['entries']
        self.assertEqual([r['postId'] for r in ranked],[self.post,otherPost])
        self.assertEqual(service.detail(self.admin,self.cid,offset=50)['entries'],[])
        with self.assertRaises(ValueError):service.detail(self.admin,self.cid,sort='injection')

    def test_gateway_rejects_revoked_session_and_api_mode_change(self):
        from challenge_gateway import ChallengeClient
        import account_gateway as accounts
        from api_client import ApiError
        with patch('account_gateway.getApiUrl',return_value=''):
            user=accounts.loginUser('author@example.com','Student123')[2]
            client=ChallengeClient(user)
            self.assertEqual(len(client.listing()),1)
            with patch('account_gateway.getApiUrl',return_value='https://example.invalid'):
                with self.assertRaises(ApiError):client.submit(self.cid,self.post)
            accounts.logoutUser(user['sessionToken'])
            with self.assertRaises(ApiError):client.submit(self.cid,self.post)
        self.assertEqual(service.detail(self.admin,self.cid)['entriesCount'],0)

    def test_validation_and_request_size(self):
        for title,rules,deadline in [(' ','Правила задания',service.today()),('Имя',' ','2026-01-01'),('Имя','Правила задания','2026-02-30'),('Имя','Правила задания','2999-01-01')]:
            with self.assertRaises(ValueError): service.create(self.admin,title,rules,deadline)
        response=self.client.put(f'/community/challenges/{self.cid}/entry',headers=self.headers['author'],content=b'x'*33000)
        self.assertEqual(response.status_code,413)
        self.assertEqual(self.client.get('/community/challenges?offset=-1',headers=self.headers['author']).status_code,422)

    def test_long_cyrillic_rules_are_accepted_with_ascii_json_encoding(self):
        import json
        body=dict(title='Большое задание', rules='Правила для участников. '*80, deadline=service.today())
        result=self.client.post('/admin/challenges',headers={**self.headers['admin'],'Content-Type':'application/json'},content=json.dumps(body))
        self.assertEqual(result.status_code,200,result.text)

    def test_concurrent_entry_is_unique_and_audit_failure_rolls_back(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:service.submit(self.author,self.cid,self.post),range(2)))
        self.assertEqual(sorted(results),[False,True])
        with patch('challenge_service.audit',side_effect=ValueError('audit failed')):
            with self.assertRaises(ValueError):service.finish(self.admin,self.cid,'cancelled','Задание отменено организатором')
        self.assertEqual(service.detail(self.author,self.cid)['status'],'open')

    def test_blocked_participant_cannot_win_and_deleted_account_loses_entry(self):
        service.submit(self.author,self.cid,self.post)
        with db.openDatabase() as c:c.execute('UPDATE users SET isBlocked=1 WHERE userId=?',(self.author,))
        with patch('challenge_service.today',return_value='2099-01-01'):
            with self.assertRaises(ValueError):service.finish(self.admin,self.cid,'finished','Необходимо выбрать победителя',self.post)
        db.deleteUserDataById(self.author)
        self.assertEqual(service.detail(self.admin,self.cid)['entriesCount'],0)

if __name__=='__main__':unittest.main()
