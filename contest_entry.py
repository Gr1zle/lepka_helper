"""Теги конкурса и отбор публикаций в уже открытой транзакции."""
import re

TAG = re.compile(r'^#challenge-([1-9][0-9]{0,18})$')


def tag(challengeId):
    return f'#challenge-{challengeId}'


def tokens(text):
    return [value.strip() for value in (text or '').split(',') if value.strip()]


def inPeriod(c, challenge, createdAt):
    day=c.execute("SELECT date(?, '+3 hours')",(createdAt,)).fetchone()[0]
    start=challenge['startsOn'] or c.execute("SELECT date(?, '+3 hours')",(challenge['createdAt'],)).fetchone()[0]
    return bool(day and start<=day<=challenge['deadline'])


def publicationTags(c, userId, text, challengeId=None):
    from challenge_service import getChallenge,status
    from post_service import normalizeTags
    values=tokens(text)
    if challengeId is not None:
        challenge=getChallenge(c,challengeId)
        if status(challenge)!='open':raise ValueError('Выбранный конкурс сейчас не принимает работы')
        if c.execute('SELECT 1 FROM challengeEntries WHERE challengeId=? AND userId=?',(challengeId,userId)).fetchone():
            raise ValueError('Вы уже участвуете в этом конкурсе. Сначала отзовите прежнюю заявку')
        c.execute('DELETE FROM challengeOptOuts WHERE challengeId=? AND userId=?',(challengeId,userId))
        if tag(challengeId) not in values:values.append(tag(challengeId))
    return normalizeTags(', '.join(values))


def enroll(c, postId, strict=False):
    from challenge_service import getChallenge
    post=c.execute('''SELECT p.* FROM posts p JOIN users u ON u.userId=p.userId
        WHERE p.postId=? AND p.isDeleted=0 AND u.isBlocked=0 AND u.emailVerified=1 AND u.roleName!='deleted' ''',(postId,)).fetchone()
    if post is None:return
    for value in tokens(post['tagsText']):
        match=TAG.fullmatch(value)
        if not match:continue
        try:challenge=getChallenge(c,int(match[1]))
        except ValueError:
            if strict:raise ValueError('Конкурс из тега не найден') from None
            continue
        if challenge['state']!='open' or not inPeriod(c,challenge,post['createdAt']):
            if strict:raise ValueError('Дата публикации не входит в период конкурса')
            continue
        opted=c.execute('SELECT 1 FROM challengeOptOuts WHERE challengeId=? AND userId=?',(challenge['challengeId'],post['userId'])).fetchone()
        if opted and not strict:continue
        if strict:c.execute('DELETE FROM challengeOptOuts WHERE challengeId=? AND userId=?',(challenge['challengeId'],post['userId']))
        current=c.execute('SELECT postId FROM challengeEntries WHERE challengeId=? AND userId=?',
                          (challenge['challengeId'],post['userId'])).fetchone()
        if current and current[0]!=postId:
            if strict:raise ValueError('В конкурсе уже участвует другая ваша работа')
            continue
        c.execute('INSERT OR IGNORE INTO challengeEntries(challengeId,userId,postId) VALUES(?,?,?)',
                  (challenge['challengeId'],post['userId'],postId))


def sync(c):
    # Сначала отбор по тегу/дате, затем фиксация итогов. Старые места не пересчитываются.
    for row in c.execute("SELECT postId FROM posts WHERE isDeleted=0 AND tagsText LIKE '%#challenge-%' ORDER BY createdAt,postId").fetchall():
        enroll(c,row['postId'])
