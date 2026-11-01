"""Повторяемые серверные действия: заданный лайк и комментарий с квитанцией."""
import hashlib
import json
import re
from database import openDatabase,createPostComment
from post_service import validateCommentText


class ActionConflict(ValueError):pass
class ActionRateLimit(ValueError):pass


def applyAction(userId,requestId,kind,payload):
    if not isinstance(requestId,str) or not re.fullmatch('[a-f0-9]{32}',requestId):raise ValueError('Некорректный идентификатор действия')
    if kind not in ('like','comment') or not isinstance(payload,dict):raise ValueError('Неизвестное действие')
    required={'postId','isLiked'} if kind=='like' else {'postId','commentText','replyToId'}
    if set(payload)!=required or type(payload['postId']) is not int or not 0<payload['postId']<2**63:raise ValueError('Некорректные поля действия')
    if kind=='like' and type(payload['isLiked']) is not bool:raise ValueError('Задайте состояние лайка')
    if kind=='comment':
        error=validateCommentText(payload['commentText']) if isinstance(payload['commentText'],str) else 'Введите текст комментария'
        if error:raise ValueError(error)
    digest=hashlib.sha256(json.dumps(payload,sort_keys=True,allow_nan=False).encode()).hexdigest()
    with openDatabase() as connection:
        connection.execute('BEGIN IMMEDIATE')
        old=connection.execute('SELECT * FROM communityActionReceipts WHERE userId=? AND requestId=?',(userId,requestId)).fetchone()
        if old:
            if old['kind']!=kind or old['payloadHash']!=digest:raise ActionConflict('Этот идентификатор уже использован для другого действия')
            return json.loads(old['resultJson'])
        available=connection.execute('''SELECT p.userId FROM posts p JOIN users u ON u.userId=?
            WHERE p.postId=? AND p.isDeleted=0 AND u.isBlocked=0 AND u.emailVerified=1''',(userId,payload['postId'])).fetchone()
        if available is None:raise ValueError('Публикация или аккаунт недоступны')
        if kind=='like':
            if payload['isLiked']:
                inserted=connection.execute('INSERT OR IGNORE INTO postLikes(postId,userId) VALUES (?,?)',(payload['postId'],userId)).rowcount
                if inserted:
                    from activity_service import record
                    record(connection,available['userId'],userId,'like',payload['postId'])
            else:connection.execute('DELETE FROM postLikes WHERE postId=? AND userId=?',(payload['postId'],userId))
            count=connection.execute('SELECT COUNT(*) FROM postLikes WHERE postId=?',(payload['postId'],)).fetchone()[0]
            connection.execute('UPDATE posts SET likesCount=? WHERE postId=?',(count,payload['postId']))
            result={'isLiked':payload['isLiked'],'likesCount':count}
        else:
            count=connection.execute("SELECT COUNT(*) FROM commentEvents WHERE userId=? AND createdAt>datetime('now','-1 minute')",(userId,)).fetchone()[0]
            if count>=5:raise ActionRateLimit('Можно отправить не больше 5 комментариев в минуту')
            cid=createPostComment(payload['postId'],userId,payload['commentText'].strip(),payload['replyToId'],connection)
            if cid is None:raise ValueError('Публикация недоступна')
            result={'commentId':cid}
        connection.execute('INSERT INTO communityActionReceipts VALUES (?,?,?,?,?)',(userId,requestId,kind,digest,json.dumps(result)))
        return result
