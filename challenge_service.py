"""Конкурсы: единые транзакции для локального режима и API."""
from datetime import datetime, date, timedelta, timezone
import database as db
from moderation_service import requireAdmin, ModerationDenied, audit, cleanReason

MOSCOW = timezone(timedelta(hours=3))


def today():
    return datetime.now(MOSCOW).date().isoformat()


def activeUser(c, userId):
    user = c.execute("SELECT userId,nickname FROM users WHERE userId=? AND emailVerified=1 AND isBlocked=0 AND roleName!='deleted'", (userId,)).fetchone()
    if user is None:
        raise ModerationDenied('Выполните вход в доступный аккаунт')
    return user


def identifier(value):
    if type(value) is not int or value < 1:
        raise ValueError('Некорректный идентификатор')
    return value


def getChallenge(c, challengeId):
    row = c.execute('SELECT * FROM challenges WHERE challengeId=?', (identifier(challengeId),)).fetchone()
    if row is None:
        raise ValueError('Задание не найдено')
    return dict(row)


def status(item):
    return 'judging' if item['state'] == 'open' and item['deadline'] < today() else item['state']


def create(userId, title, rules, deadline):
    if not isinstance(title, str) or not 3 <= len(title.strip()) <= 100:
        raise ValueError('Название: от 3 до 100 символов')
    if not isinstance(rules, str) or not 10 <= len(rules.strip()) <= 2000:
        raise ValueError('Правила: от 10 до 2000 символов')
    try:
        parsed = date.fromisoformat(deadline)
        if parsed.isoformat() != deadline or not date.fromisoformat(today()) <= parsed <= date.fromisoformat(today()) + timedelta(days=366):
            raise ValueError()
    except (ValueError, TypeError):
        raise ValueError('Срок: дата ГГГГ-ММ-ДД от сегодня до года вперёд') from None
    with db.openDatabase() as c:
        c.execute('BEGIN IMMEDIATE')
        actor = requireAdmin(c, userId)
        if c.execute("SELECT COUNT(*) FROM challenges WHERE state='open' AND deadline>=?", (today(),)).fetchone()[0] >= 30:
            raise ValueError('Одновременно можно открыть до 30 заданий')
        newId = c.execute('INSERT INTO challenges(title,rules,deadline,createdBy) VALUES(?,?,?,?)',
                          (title.strip(), rules.strip(), deadline, userId)).lastrowid
        audit(c, actor, 'challenge.create', 'challenge', newId, title.strip())
        return newId


def listing(userId, mode='active', offset=0):
    if mode not in ('active', 'finished', 'mine') or type(offset) is not int or offset < 0:
        raise ValueError('Некорректный фильтр')
    with db.openDatabase() as c:
        activeUser(c, userId)
        where = "state='open'" if mode == 'active' else "state!='open'"
        args = []
        if mode == 'mine':
            where = 'EXISTS(SELECT 1 FROM challengeEntries e WHERE e.challengeId=challenges.challengeId AND e.userId=?)'
            args.append(userId)
        rows = c.execute(f'SELECT * FROM challenges WHERE {where} ORDER BY challengeId DESC LIMIT 50 OFFSET ?', (*args, offset))
        result = []
        for row in rows:
            item = dict(row)
            item['status'] = status(item)
            item['entriesCount'] = c.execute('SELECT COUNT(*) FROM challengeEntries WHERE challengeId=?', (item['challengeId'],)).fetchone()[0]
            result.append(item)
        return result


def detail(userId, challengeId, offset=0, sort='new'):
    if sort not in ('new', 'votes'):
        raise ValueError('Некорректная сортировка')
    if type(offset) is not int or offset < 0:
        raise ValueError('Некорректная страница')
    with db.openDatabase() as c:
        activeUser(c, userId)
        item = getChallenge(c, challengeId)
        item['status'] = status(item)
        item['entriesCount'] = c.execute('SELECT COUNT(*) FROM challengeEntries WHERE challengeId=?', (challengeId,)).fetchone()[0]
        item['myPostId'] = c.execute('SELECT postId FROM challengeEntries WHERE challengeId=? AND userId=?', (challengeId, userId)).fetchone()
        item['myPostId'] = item['myPostId'][0] if item['myPostId'] else None
        order = 'votes DESC,e.createdAt,e.postId' if sort == 'votes' else 'e.createdAt DESC,e.postId DESC'
        item['entries'] = [dict(r) for r in c.execute(f'''SELECT e.postId,e.createdAt,p.titleText,u.nickname,
            (SELECT COUNT(*) FROM challengeVotes v WHERE v.challengeId=e.challengeId AND v.postId=e.postId) AS votes,
            EXISTS(SELECT 1 FROM challengeVotes v WHERE v.challengeId=e.challengeId AND v.postId=e.postId AND v.userId=?) AS isVoted,
            e.userId=? AS isOwn
            FROM challengeEntries e JOIN posts p ON p.postId=e.postId JOIN users u ON u.userId=e.userId
            WHERE e.challengeId=? ORDER BY {order} LIMIT 50 OFFSET ?''', (userId, userId, challengeId, offset))]
        winner = c.execute('SELECT p.titleText,u.nickname FROM posts p JOIN users u ON u.userId=p.userId WHERE p.postId=? AND p.isDeleted=0', (item['winnerPostId'],)).fetchone()
        item['winner'] = dict(winner) if winner else None
        return item


def submit(userId, challengeId, postId):
    identifier(postId)
    with db.openDatabase() as c:
        c.execute('BEGIN IMMEDIATE')
        activeUser(c, userId)
        item = getChallenge(c, challengeId)
        if status(item) != 'open':
            raise ValueError('Приём работ завершён')
        if c.execute('SELECT postId FROM posts WHERE postId=? AND userId=? AND isDeleted=0', (postId, userId)).fetchone() is None:
            raise ValueError('Можно отправить только свою доступную публикацию')
        existing = c.execute('SELECT postId FROM challengeEntries WHERE challengeId=? AND userId=?', (challengeId, userId)).fetchone()
        if existing:
            if existing[0] == postId:
                return False
            raise ValueError('Одна работа на участника. Сначала отзовите текущую заявку')
        c.execute('INSERT INTO challengeEntries(challengeId,userId,postId) VALUES(?,?,?)', (challengeId, userId, postId))
        return True


def withdraw(userId, challengeId):
    with db.openDatabase() as c:
        c.execute('BEGIN IMMEDIATE')
        activeUser(c, userId)
        if status(getChallenge(c, challengeId)) != 'open':
            raise ValueError('После срока отозвать заявку нельзя')
        return bool(c.execute('DELETE FROM challengeEntries WHERE challengeId=? AND userId=?', (challengeId, userId)).rowcount)


def finish(userId, challengeId, state, reason, winnerPostId=None):
    reason = cleanReason(reason)
    if state not in ('finished', 'cancelled') or (state == 'cancelled' and winnerPostId is not None):
        raise ValueError('Некорректное решение')
    if winnerPostId is not None:
        identifier(winnerPostId)
    with db.openDatabase() as c:
        c.execute('BEGIN IMMEDIATE')
        actor = requireAdmin(c, userId)
        item = getChallenge(c, challengeId)
        if item['state'] != 'open':
            raise ValueError('Итоги уже опубликованы')
        if state == 'finished' and status(item) != 'judging':
            raise ValueError('Итоги можно подвести после срока приёма работ')
        if winnerPostId is not None:
            if c.execute('''SELECT e.postId FROM challengeEntries e JOIN posts p ON p.postId=e.postId
                JOIN users u ON u.userId=e.userId WHERE e.challengeId=? AND e.postId=? AND p.isDeleted=0
                AND u.isBlocked=0 AND u.emailVerified=1 AND u.roleName!='deleted' ''', (challengeId, winnerPostId)).fetchone() is None:
                raise ValueError('Победитель должен быть доступным участником задания')
        c.execute('UPDATE challenges SET state=?,winnerPostId=?,result=? WHERE challengeId=?', (state, winnerPostId, reason, challengeId))
        audit(c, actor, 'challenge.' + state, 'challenge', challengeId, reason)
        return True


def vote(userId, challengeId, postId, liked):
    identifier(postId)
    if type(liked) is not bool:
        raise ValueError('Некорректный голос')
    with db.openDatabase() as c:
        c.execute('BEGIN IMMEDIATE')
        activeUser(c, userId)
        if status(getChallenge(c, challengeId)) != 'open':
            raise ValueError('Голосование завершено')
        entry = c.execute('SELECT userId FROM challengeEntries WHERE challengeId=? AND postId=?', (challengeId, postId)).fetchone()
        if entry is None:
            raise ValueError('Заявка недоступна')
        if entry['userId'] == userId:
            raise ValueError('За свою работу голосовать нельзя')
        if liked:
            c.execute('INSERT OR IGNORE INTO challengeVotes VALUES(?,?,?)', (challengeId, postId, userId))
        else:
            c.execute('DELETE FROM challengeVotes WHERE challengeId=? AND postId=? AND userId=?', (challengeId, postId, userId))
        return c.execute('SELECT COUNT(*) FROM challengeVotes WHERE challengeId=? AND postId=?', (challengeId, postId)).fetchone()[0]
