"""Единый личный список: награды и события публикаций, без копирования текста материалов."""

KINDS=('all','award','like','comment','reply')
QUERY='''SELECT n.noticeId,n.challengeId,n.place,n.isRead,n.createdAt,h.title,
    'award' AS kind,NULL AS postId,NULL AS commentId,NULL AS actor,NULL AS preview
    FROM communityNotices n JOIN challenges h ON h.challengeId=n.challengeId WHERE n.userId=?
    UNION ALL
    SELECT -n.noticeId,NULL,NULL,n.isRead,n.createdAt,p.titleText,n.kind,n.postId,n.commentId,
    u.nickname,c.commentText FROM activityNotices n JOIN posts p ON p.postId=n.postId AND p.isDeleted=0
    JOIN users u ON u.userId=n.actorId LEFT JOIN postComments c ON c.commentId=n.commentId WHERE n.userId=?'''


def listing(c,userId,offset=0,kind='all',unread=False):
    if type(offset) is not int or offset<0 or kind not in KINDS or type(unread) is not bool:
        raise ValueError('Некорректный фильтр уведомлений')
    return [dict(r) for r in c.execute(f'''SELECT * FROM ({QUERY})
        WHERE (?='all' OR kind=?) AND (?=0 OR isRead=0)
        ORDER BY createdAt DESC,ABS(noticeId) DESC,kind LIMIT 50 OFFSET ?''',(userId,userId,kind,kind,int(unread),offset))]


def summary(c,userId):
    rows=c.execute(f'SELECT kind,COUNT(*) AS count FROM ({QUERY}) WHERE isRead=0 GROUP BY kind',(userId,userId))
    counts={r['kind']:r['count'] for r in rows}
    return {'unread':sum(counts.values()),'byKind':counts}


def read(c,userId,noticeId):
    if type(noticeId) is not int or not 0<abs(noticeId)<=9223372036854775807:raise ValueError('Некорректное уведомление')
    table='communityNotices' if noticeId>0 else 'activityNotices'
    return bool(c.execute(f'UPDATE {table} SET isRead=1 WHERE noticeId=? AND userId=?',(abs(noticeId),userId)).rowcount)


def readAll(c,userId):
    count=0
    for table in ('communityNotices','activityNotices'):
        count+=c.execute(f'UPDATE {table} SET isRead=1 WHERE userId=? AND isRead=0',(userId,)).rowcount
    return count
