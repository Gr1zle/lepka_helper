"""HTTP сообщества: временная серверная база, права, фото и повторная отправка."""
import base64
from concurrent.futures import ThreadPoolExecutor
import json
import tempfile
import unittest
from unittest.mock import patch
import uuid

from fastapi.testclient import TestClient

import account_security
from backend.main import createApp
import database as db
from password_service import createPasswordHash
from image_fixtures import photo
from color_service import BASE_COLORS, calculateRecipe


def publicationPayload(workshop=False):
    payload = {'titleText': 'Серверный котик', 'descriptionText': 'Пошаговый мастер-класс нашего котика',
        'categoryName': 'Животные', 'tagsText': 'котик, лепка', 'requestId': uuid.uuid4().hex,
        'photos': [{'name': 'Котик.png', 'imageBase64': base64.b64encode(photo()['data']).decode()}]}
    if workshop:
        selected = [{**item, 'proportion': 50} for item in BASE_COLORS[:2]]
        payload['projectDetailsJson'] = json.dumps({'formatVersion': 2,
            'workshopInfo': {'level': 'Средний', 'timeMinutes': 45, 'materials': ['Пластилин'], 'tools': ['Стек']},
            'steps': [{'description': 'Слепить котика', 'photoPosition': 0}],
            'mixtures': [{'mixtureName': 'Серый котик', 'resultHex': '#808080', 'totalWeight': 100,
                          'recipeItems': calculateRecipe(selected, 100)}]})
    return payload


class CommunityApiTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.client = TestClient(createApp(self.folder.name))
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)
        passwordHash, salt = createPasswordHash('Student123')
        self.owner = db.createUser('owner@example.com', passwordHash, salt, 'Автор')
        self.other = db.createUser('reader@example.com', passwordHash, salt, 'Читатель')
        with db.openDatabase() as connection:
            self.token = account_security.createSession(connection, db.getUserByEmail('owner@example.com'))['sessionToken']
            self.readerToken = account_security.createSession(connection, db.getUserByEmail('reader@example.com'))['sessionToken']
        self.headers = {'Authorization': 'Bearer ' + self.token}
        self.reader = {'Authorization': 'Bearer ' + self.readerToken}

    def publish(self, payload=None, headers=None):
        response = self.client.post('/community/posts', json=payload or publicationPayload(), headers=headers or self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()['data']

    def test_public_feed_photos_and_viewer_ownership(self):
        postId = self.publish()
        guest = self.client.get('/community/posts').json()['data']['items'][0]
        self.assertEqual(guest['postId'], postId)
        self.assertFalse(guest['isOwn'])
        owner = self.client.get('/community/posts', headers=self.headers).json()['data']['items'][0]
        reader = self.client.get('/community/posts', headers=self.reader).json()['data']['items'][0]
        self.assertTrue(owner['isOwn'])
        self.assertFalse(reader['isOwn'])
        result = self.client.get('/community/photos/' + str(guest['photoIds'][0]))
        self.assertEqual(result.status_code, 200)
        self.assertTrue(base64.b64decode(result.json()['data']['imageBase64']).startswith(b'\xff\xd8'))
        self.assertEqual(self.client.get('/community/photos/99999').status_code, 404)

    def test_mutations_require_current_bearer_session(self):
        postId = self.publish(publicationPayload(True))
        for method, path, payload in (
            ('POST', '/posts', publicationPayload()), ('DELETE', f'/posts/{postId}', None),
            ('POST', f'/posts/{postId}/like', None), ('POST', f'/posts/{postId}/comments', {'commentText': 'Красивый котик'}),
            ('PUT', f'/workshops/{postId}/progress', {'lastStep': 0, 'completedSteps': [], 'checkedMaterials': []})):
            self.assertEqual(self.client.request(method, '/community' + path, json=payload).status_code, 401)
        account_security.logoutUser(self.token)
        self.assertEqual(self.client.post('/community/posts', json=publicationPayload(), headers=self.headers).status_code, 401)
        self.assertEqual(self.client.get('/community/posts', headers=self.headers).status_code, 401)

    def test_owner_is_from_token_and_extra_user_id_is_rejected(self):
        payload = publicationPayload()
        payload['userId'] = self.other
        self.assertEqual(self.client.post('/community/posts', json=payload, headers=self.headers).status_code, 422)
        payload.pop('userId')
        response = self.client.post('/community/posts?userId=' + str(self.other), json=payload, headers=self.headers)
        postId = response.json()['data']
        self.assertEqual(self.client.get('/community/posts', headers=self.headers).json()['data']['items'][0]['userId'], self.owner)
        self.assertEqual(self.client.delete(f'/community/posts/{postId}', headers=self.reader).status_code, 404)

    def test_retry_is_idempotent_per_owner_and_conflicting_payload_is_rejected(self):
        payload = publicationPayload()
        postId = self.publish(payload)
        self.assertEqual(self.publish(payload), postId)
        changed = {**payload, 'titleText': 'Другая работа'}
        self.assertEqual(self.client.post('/community/posts', json=changed, headers=self.headers).status_code, 409)
        self.assertNotEqual(self.publish(payload, self.reader), postId)
        self.assertEqual(len(self.client.get('/community/posts').json()['data']['items']), 2)

    def test_concurrent_retries_create_one_post_and_one_photo(self):
        payload = publicationPayload()
        with ThreadPoolExecutor(max_workers=4) as executor:
            results = list(executor.map(lambda _: self.client.post('/community/posts', json=payload, headers=self.headers), range(6)))
        self.assertTrue(all(result.status_code == 200 for result in results))
        self.assertEqual(len({result.json()['data'] for result in results}), 1)
        with db.openDatabase() as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM posts').fetchone()[0], 1)
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM postPhotos').fetchone()[0], 1)

    def test_invalid_photo_and_workshop_do_not_leave_rows_or_retry_keys(self):
        for changes in ({'photos': []}, {'photos': [{'name': 'bad.png', 'imageBase64': '%%%'}]},
                        {'photos': [{'name': 'bad.png', 'imageBase64': base64.b64encode(b'bad').decode()}]},
                        {'projectDetailsJson': '{broken'}, {'categoryName': 'неизвестная'}, {'tagsText': 'x'}):
            payload = {**publicationPayload(), **changes}
            self.assertIn(self.client.post('/community/posts', json=payload, headers=self.headers).status_code, (400, 422))
        payload = publicationPayload(True)
        details = json.loads(payload['projectDetailsJson'])
        details['steps'][0]['photoPosition'] = 5
        payload['projectDetailsJson'] = json.dumps(details)
        self.assertEqual(self.client.post('/community/posts', json=payload, headers=self.headers).status_code, 400)
        with db.openDatabase() as connection:
            for table in ('posts', 'postPhotos', 'communityRequests'):
                self.assertEqual(connection.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0], 0)

    def test_actual_body_stream_is_bounded_even_with_false_content_length(self):
        with patch('backend.community.MAX_COMMUNITY_BODY', 256):
            response = self.client.post('/community/posts', content=iter([b'x'*200, b'x'*200]),
                                       headers={**self.headers, 'content-length': '0', 'content-type': 'application/json'})
        self.assertEqual(response.status_code, 413)

    def test_server_likes_comments_and_own_comment_controls(self):
        postId = self.publish()
        url = f'/community/posts/{postId}'
        self.assertEqual(self.client.post(url + '/like', headers=self.reader).json()['data'], {'isLiked': True, 'likesCount': 1})
        comment = self.client.post(url + '/comments', headers=self.reader, json={'commentText': 'Красивый котик'})
        commentId = comment.json()['data']
        self.assertFalse(self.client.get(url + '/comments', headers=self.headers).json()['data'][0]['isOwn'])
        self.assertTrue(self.client.get(url + '/comments', headers=self.reader).json()['data'][0]['isOwn'])
        self.assertEqual(self.client.put(f'/community/comments/{commentId}', headers=self.headers, json={'commentText': 'Подмена автора'}).status_code, 400)
        self.assertEqual(self.client.delete(f'/community/comments/{commentId}', headers=self.headers).status_code, 404)
        self.assertEqual(self.client.put(f'/community/comments/{commentId}', headers=self.reader, json={'commentText': 'Спасибо за мастер-класс'}).status_code, 200)
        self.assertEqual(self.client.delete(f'/community/comments/{commentId}', headers=self.reader).status_code, 200)

    def test_comment_minute_limit_and_editing_window_are_checked_on_server(self):
        postId = self.publish()
        url = f'/community/posts/{postId}/comments'
        self.assertEqual(self.client.post(url, headers=self.reader, json={'commentText': '🙂🙂🙂🙂🙂'}).status_code, 400)
        comments = [self.client.post(url, headers=self.reader, json={'commentText': 'Хорошая работа'}).json()['data'] for _ in range(5)]
        self.assertEqual(self.client.post(url, headers=self.reader, json={'commentText': 'Шестой комментарий'}).status_code, 400)
        with db.openDatabase() as connection:
            connection.execute("UPDATE postComments SET createdAt = datetime('now', '-31 minutes')")
        self.assertEqual(self.client.put(f'/community/comments/{comments[0]}', headers=self.reader, json={'commentText': 'Позднее изменение'}).status_code, 400)

    def test_workshop_progress_is_private_validated_and_survives_initialization(self):
        postId = self.publish(publicationPayload(True))
        workshop = self.client.get(f'/community/workshops/{postId}').json()['data']
        self.assertEqual(workshop['level'], 'Средний')
        url = f'/community/workshops/{postId}/progress'
        self.assertEqual(self.client.get(url).status_code, 401)
        state = {'lastStep': 0, 'completedSteps': [0], 'checkedMaterials': [1]}
        self.assertTrue(self.client.put(url, headers=self.reader, json=state).json()['data']['isCompleted'])
        self.assertEqual(self.client.get(url, headers=self.headers).json()['data']['completedSteps'], [])
        db.initializeDatabase()
        self.assertEqual(self.client.get(url, headers=self.reader).json()['data']['checkedMaterials'], [1])
        self.assertEqual(self.client.put(url, headers=self.reader, json={**state, 'userId': self.owner}).status_code, 422)
        self.assertEqual(self.client.put(url, headers=self.reader, json={**state, 'lastStep': -1}).status_code, 400)

    def test_search_and_pagination_and_own_feed_use_server_data(self):
        postId = self.publish(publicationPayload(True))
        self.publish(headers=self.reader)
        first = self.client.get('/community/posts?limit=1').json()['data']
        self.assertTrue(first['hasMore'])
        self.assertNotEqual(first['items'][0]['postId'], self.client.get('/community/posts?limit=1&offset=1').json()['data']['items'][0]['postId'])
        own = self.client.get('/community/posts?mine=true', headers=self.headers).json()['data']['items']
        self.assertEqual([item['postId'] for item in own], [postId])
        filtered = self.client.get('/community/posts', params={'searchText': 'Стек', 'levelName': 'Средний', 'maxTime': 60}).json()['data']['items']
        self.assertEqual([item['postId'] for item in filtered], [postId])
        self.assertEqual(self.client.get('/community/posts?mine=true').status_code, 401)

    def test_delete_erases_media_progress_comments_and_replay_key(self):
        postId = self.publish(publicationPayload(True))
        photoId = self.client.get('/community/posts').json()['data']['items'][0]['photoIds'][0]
        self.client.post(f'/community/posts/{postId}/comments', headers=self.reader, json={'commentText': 'Красивый котик'})
        self.client.put(f'/community/workshops/{postId}/progress', headers=self.reader,
                        json={'lastStep': 0, 'completedSteps': [0], 'checkedMaterials': []})
        self.assertEqual(self.client.delete(f'/community/posts/{postId}', headers=self.headers).status_code, 200)
        self.assertEqual(self.client.get(f'/community/photos/{photoId}').status_code, 404)
        self.assertEqual(self.client.get(f'/community/workshops/{postId}').status_code, 404)
        with db.openDatabase() as connection:
            for table in ('postPhotos', 'postComments', 'workshopProgress', 'communityRequests'):
                self.assertEqual(connection.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0], 0)
            self.assertEqual(connection.execute('PRAGMA foreign_key_check').fetchall(), [])

    def test_account_deletion_keeps_others_comments_under_tombstone(self):
        postId = self.publish(publicationPayload(True))
        photoId = self.client.get('/community/posts').json()['data']['items'][0]['photoIds'][0]
        self.client.post(f'/community/posts/{postId}/comments', headers=self.reader, json={'commentText': 'Чужой комментарий'})
        response = self.client.request('DELETE', '/account', headers=self.headers, json={'password': 'Student123'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get(f'/community/photos/{photoId}').status_code, 404)
        self.assertEqual(len(self.client.get(f'/community/posts/{postId}/comments').json()['data']), 1)
        self.assertTrue(self.client.get('/community/posts').json()['data']['items'][0]['isDeleted'])
        self.assertEqual(self.client.get('/community/posts?searchMode=true').json()['data']['items'], [])
