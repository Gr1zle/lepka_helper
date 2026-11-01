"""Явные полномочия администрирования; встроенные роли не редактируются."""
import json
import re
import database as db

PERMISSIONS={
    'reports.manage':'Рассматривать жалобы',
    'materials.remove':'Удалять материалы',
    'accounts.view':'Список аккаунтов',
    'accounts.block':'Блокировать аккаунты',
    'accounts.delete':'Удалять аккаунты',
    'contests.manage':'Управлять конкурсами',
    'audit.view':'Читать журнал'}
RESERVED={'user','admin','guest','deleted'}
CODE=re.compile(r'^[a-z][a-z0-9_]{2,23}$')


class PermissionDenied(ValueError):
    pass


def accessIn(c,userId):
    user=c.execute("SELECT userId,nickname,roleName FROM users WHERE userId=? AND isBlocked=0 AND emailVerified=1 AND roleName!='deleted'",(userId,)).fetchone()
    if user is None:raise PermissionDenied('Аккаунт недоступен')
    if user['roleName']=='admin':perms=[*PERMISSIONS,'roles.manage'];label='Администратор'
    elif user['roleName']=='user':perms=[];label='Пользователь'
    else:
        role=c.execute('SELECT title,permissionsJson FROM customRoles WHERE roleCode=?',(user['roleName'],)).fetchone()
        perms=json.loads(role['permissionsJson']) if role else []
        label=role['title'] if role else 'Неизвестная роль'
    return {**dict(user),'permissions':perms,'roleLabel':label}


def access(userId):
    with db.openDatabase() as c:return accessIn(c,userId)


def require(c,userId,permission):
    actor=accessIn(c,userId)
    if permission not in actor['permissions']:raise PermissionDenied('Недостаточно прав для этого действия')
    return actor


def roles(actorId):
    with db.openDatabase() as c:
        require(c,actorId,'roles.manage')
        custom=[{**dict(r),'permissions':json.loads(r['permissionsJson'])} for r in c.execute('''SELECT r.*,
            (SELECT COUNT(*) FROM users u WHERE u.roleName=r.roleCode) AS assignedCount
            FROM customRoles r ORDER BY r.roleCode''')]
        return {'catalog':PERMISSIONS,'items':custom}


def save(actorId,code,title,permissions,reason,create=False):
    from moderation_service import cleanReason,audit
    reason=cleanReason(reason)
    if not isinstance(code,str) or not CODE.fullmatch(code) or code in RESERVED:raise ValueError('Код роли: 3–24 латинские буквы, цифры и _, встроенные имена запрещены')
    if not isinstance(title,str) or not 3<=len(title.strip())<=50:raise ValueError('Название роли: 3–50 символов')
    if not isinstance(permissions,list) or any(not isinstance(v,str) or v not in PERMISSIONS for v in permissions) or len(set(permissions))!=len(permissions):
        raise ValueError('Выберите права из списка без повторений')
    if any(v in permissions for v in ('accounts.block','accounts.delete')) and 'accounts.view' not in permissions:
        raise ValueError('Для работы с аккаунтами также нужен просмотр списка аккаунтов')
    with db.openDatabase() as c:
        c.execute('BEGIN IMMEDIATE');actor=require(c,actorId,'roles.manage')
        old=c.execute('SELECT * FROM customRoles WHERE roleCode=?',(code,)).fetchone()
        if create and old:raise ValueError('Роль с таким кодом уже существует')
        if not create and not old:raise ValueError('Роль не найдена')
        if create and c.execute('SELECT COUNT(*) FROM customRoles').fetchone()[0]>=20:raise ValueError('Можно создать до 20 пользовательских ролей')
        payload=json.dumps(sorted(permissions))
        if old and old['title']==title.strip() and old['permissionsJson']==payload:return False
        if create:c.execute('INSERT INTO customRoles VALUES(?,?,?)',(code,title.strip(),payload))
        else:c.execute('UPDATE customRoles SET title=?,permissionsJson=? WHERE roleCode=?',(title.strip(),payload,code))
        c.execute('DELETE FROM accountSessions WHERE userId IN (SELECT userId FROM users WHERE roleName=?)',(code,))
        audit(c,actor,'role.create' if create else 'role.update','role',0,f'{code}: {reason}')
        return True


def remove(actorId,code,reason):
    from moderation_service import cleanReason,audit
    reason=cleanReason(reason)
    if code in RESERVED:raise ValueError('Встроенную роль удалить нельзя')
    with db.openDatabase() as c:
        c.execute('BEGIN IMMEDIATE');actor=require(c,actorId,'roles.manage')
        if c.execute('SELECT 1 FROM users WHERE roleName=?',(code,)).fetchone():raise ValueError('Сначала назначьте пользователям другую роль')
        if not c.execute('DELETE FROM customRoles WHERE roleCode=?',(code,)).rowcount:return False
        audit(c,actor,'role.delete','role',0,f'{code}: {reason}')
        return True
