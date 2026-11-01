"""Уведомления об активности: события записываются в транзакции самого действия."""


def record(c,recipient,actor,kind,postId,commentId=None):
    if recipient==actor:return
    enabled=c.execute("SELECT notificationsEnabled FROM users WHERE userId=? AND isBlocked=0 AND emailVerified=1 AND roleName!='deleted'",(recipient,)).fetchone()
    if not enabled or not enabled[0]:return
    key=f'{kind}:{postId}:{actor}' if kind=='like' else f'{kind}:{commentId}'
    c.execute('''INSERT OR IGNORE INTO activityNotices(userId,actorId,kind,postId,commentId,eventKey)
        VALUES(?,?,?,?,?,?)''',(recipient,actor,kind,postId,commentId,key))


def comment(c,postId,actor,commentId,replyToId):
    owner=c.execute('SELECT userId FROM posts WHERE postId=?',(postId,)).fetchone()[0]
    parent=c.execute('SELECT userId FROM postComments WHERE commentId=?',(replyToId,)).fetchone() if replyToId else None
    if parent:
        record(c,parent[0],actor,'reply',postId,commentId)
    if not parent or parent[0]!=owner:
        record(c,owner,actor,'comment',postId,commentId)
