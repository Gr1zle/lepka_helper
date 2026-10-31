"""Жалобы и администрирование. actorId передаёт проверенный шлюз/API."""
from database import openDatabase,erasePost


class ModerationDenied(ValueError):
    pass


def requireAdmin(connection,actorId):
    record=connection.execute("SELECT userId,nickname FROM users WHERE userId=? AND roleName='admin' AND isBlocked=0 AND emailVerified=1",(actorId,)).fetchone()
    if record is None:raise ModerationDenied('Доступно только администратору')
    return record


def cleanReason(value):
    if not isinstance(value,str) or not 10<=len(value.strip())<=500:
        raise ValueError('Укажите причину от 10 до 500 символов')
    return value.strip()


def audit(connection,actor,action,targetType,targetId,reason):
    connection.execute('INSERT INTO adminAudit(actorId,actorNickname,action,targetType,targetId,reason) VALUES (?,?,?,?,?,?)',
                       (actor['userId'],actor['nickname'],action,targetType,targetId,reason))


def targetInfo(connection,targetType,targetId):
    if type(targetId) is not int or targetId<1:raise ValueError('Некорректный идентификатор материала')
    if targetType=='post':
        row=connection.execute('''SELECT p.postId,p.titleText AS title,p.descriptionText AS text,u.nickname
            FROM posts p JOIN users u ON u.userId=p.userId WHERE p.postId=? AND p.isDeleted=0''',(targetId,)).fetchone()
    elif targetType=='comment':
        row=connection.execute('''SELECT c.postId,p.titleText AS title,c.commentText AS text,u.nickname
            FROM postComments c JOIN posts p ON p.postId=c.postId JOIN users u ON u.userId=c.userId
            WHERE c.commentId=?''',(targetId,)).fetchone()
    else:raise ValueError('Выберите публикацию или комментарий')
    if row is None:return None
    result=dict(row)
    result['photoIds']=[item['photoId'] for item in connection.execute('SELECT photoId FROM postPhotos WHERE postId=? ORDER BY position',(row['postId'],))]
    return result


def reportMaterial(userId,targetType,targetId,reason):
    reason=cleanReason(reason)
    with openDatabase() as c:
        c.execute('BEGIN IMMEDIATE')
        if c.execute("SELECT userId FROM users WHERE userId=? AND isBlocked=0 AND emailVerified=1 AND roleName!='deleted'",(userId,)).fetchone() is None:
            raise ModerationDenied('Выполните вход в доступный аккаунт')
        if targetInfo(c,targetType,targetId) is None:raise ValueError('Материал уже недоступен')
        old=c.execute('SELECT reportId FROM moderationReports WHERE reporterId=? AND targetType=? AND targetId=?',(userId,targetType,targetId)).fetchone()
        if old:return old['reportId']
        if c.execute("SELECT COUNT(*) FROM moderationReports WHERE reporterId=? AND createdAt>=datetime('now','-1 day')",(userId,)).fetchone()[0]>=10:
            raise ValueError('Можно отправить не больше 10 жалоб за сутки')
        return c.execute('INSERT INTO moderationReports(reporterId,targetType,targetId,reason) VALUES (?,?,?,?)',
                         (userId,targetType,targetId,reason)).lastrowid


def listReports(actorId,status='open',offset=0):
    if status not in ('open','resolved','rejected','all') or type(offset) is not int or offset<0:
        raise ValueError('Некорректный фильтр жалоб')
    with openDatabase() as c:
        requireAdmin(c,actorId)
        rows=c.execute('''SELECT r.*,COALESCE(u.nickname,'Удалённый аккаунт') AS reporter
            FROM moderationReports r LEFT JOIN users u ON u.userId=r.reporterId
            WHERE (?='all' OR r.status=?) ORDER BY r.reportId DESC LIMIT 50 OFFSET ?''',(status,status,offset)).fetchall()
        return [{**dict(row),'material':targetInfo(c,row['targetType'],row['targetId'])} for row in rows]


def resolveReport(actorId,reportId,status,reason):
    reason=cleanReason(reason)
    if status not in ('resolved','rejected'):raise ValueError('Выберите решение по жалобе')
    with openDatabase() as c:
        c.execute('BEGIN IMMEDIATE');actor=requireAdmin(c,actorId)
        row=c.execute('SELECT status FROM moderationReports WHERE reportId=?',(reportId,)).fetchone()
        if row is None:raise ValueError('Жалоба не найдена')
        if row['status']!='open':return False
        c.execute("UPDATE moderationReports SET status=?,resolution=?,resolvedBy=?,resolvedAt=CURRENT_TIMESTAMP WHERE reportId=?",(status,reason,actorId,reportId))
        audit(c,actor,'report.'+status,'report',reportId,reason)
        return True


def removeMaterial(actorId,targetType,targetId,reason):
    reason=cleanReason(reason)
    with openDatabase() as c:
        c.execute('BEGIN IMMEDIATE');actor=requireAdmin(c,actorId)
        material=targetInfo(c,targetType,targetId)
        if material is None:return False
        if targetType=='post':
            # Жалобы на дочерние комментарии закрываются до удаления самих комментариев.
            c.execute('''UPDATE moderationReports SET status='resolved',resolution=?,resolvedBy=?,resolvedAt=CURRENT_TIMESTAMP
                WHERE status='open' AND ((targetType='post' AND targetId=?) OR (targetType='comment' AND targetId IN (
                    SELECT commentId FROM postComments WHERE postId=?)))''',(reason,actorId,targetId,targetId))
            erasePost(c,targetId)
        else:
            c.execute('DELETE FROM postComments WHERE commentId=?',(targetId,))
            c.execute("UPDATE moderationReports SET status='resolved',resolution=?,resolvedBy=?,resolvedAt=CURRENT_TIMESTAMP WHERE status='open' AND targetType='comment' AND targetId=?",(reason,actorId,targetId))
        audit(c,actor,'material.delete',targetType,targetId,reason)
        return True


def listUsers(actorId,query='',offset=0):
    if not isinstance(query,str) or len(query)>100 or type(offset) is not int or offset<0:raise ValueError('Некорректный поиск аккаунтов')
    with openDatabase() as c:
        requireAdmin(c,actorId)
        c.create_function('casefold',1,lambda value:value.casefold())
        rows=c.execute('''SELECT u.userId,u.nickname,u.email,u.roleName,u.isBlocked,u.emailVerified
            FROM users u WHERE u.roleName!='deleted' AND NOT EXISTS (SELECT 1 FROM remoteAccounts r WHERE r.localUserId=u.userId)
            AND (instr(casefold(u.email),?)>0 OR instr(casefold(u.nickname),?)>0)
            ORDER BY u.userId DESC LIMIT 50 OFFSET ?''',(query.strip().casefold(),query.strip().casefold(),offset)).fetchall()
    return [dict(row) for row in rows]


def changeUser(actorId,userId,reason,blocked=None,role=None):
    reason=cleanReason(reason)
    if (blocked is None)==(role is None) or blocked is not None and type(blocked) is not bool or role is not None and role not in ('user','admin'):
        raise ValueError('Выберите одно изменение аккаунта')
    with openDatabase() as c:
        c.execute('BEGIN IMMEDIATE');actor=requireAdmin(c,actorId)
        if actorId==userId:raise ValueError('Свою роль и блокировку через панель изменить нельзя')
        target=c.execute("SELECT * FROM users WHERE userId=? AND roleName!='deleted' AND NOT EXISTS (SELECT 1 FROM remoteAccounts WHERE localUserId=users.userId)",(userId,)).fetchone()
        if target is None:raise ValueError('Аккаунт не найден')
        if role=='admin' and (target['isBlocked'] or not target['emailVerified']):raise ValueError('Администратором может стать подтверждённый незаблокированный аккаунт')
        losingAdmin=target['roleName']=='admin' and not target['isBlocked'] and (blocked is True or role=='user')
        if losingAdmin and c.execute("SELECT COUNT(*) FROM users WHERE roleName='admin' AND isBlocked=0 AND emailVerified=1").fetchone()[0]<=1:
            raise ValueError('Нельзя отключить последнего действующего администратора')
        column,value=('isBlocked',int(blocked)) if blocked is not None else ('roleName',role)
        if target[column]==value:return False
        c.execute(f'UPDATE users SET {column}=? WHERE userId=?',(value,userId))
        c.execute('DELETE FROM accountSessions WHERE userId=?',(userId,))
        action=('user.block' if blocked else 'user.unblock') if blocked is not None else 'role.'+role
        audit(c,actor,action,'user',userId,reason)
        return True


def listAudit(actorId,offset=0):
    if type(offset) is not int or offset<0:raise ValueError('Некорректная страница журнала')
    with openDatabase() as c:
        requireAdmin(c,actorId)
        return [dict(row) for row in c.execute('SELECT * FROM adminAudit ORDER BY eventId DESC LIMIT 50 OFFSET ?',(offset,))]
