"""Назначить первого администратора в явно выбранной существующей базе.

python -m scripts.manage_admin --database /path/to/accounts.db --email owner@example.com
Не создаёт аккаунтов, не меняет пароли и не отправляет писем.
"""
import argparse
from pathlib import Path
import sqlite3
from contextlib import closing


def grantAdmin(databasePath,email):
    target=Path(databasePath).expanduser().resolve()
    if not target.is_file():raise ValueError('Укажите существующую базу приложения')
    with closing(sqlite3.connect(target.as_uri()+'?mode=rw',uri=True)) as c:
        columns={row[1] for row in c.execute('PRAGMA table_info(users)')}
        if not {'userId','email','roleName','isBlocked','emailVerified'}<=columns:
            raise ValueError('Это не база аккаунтов Lepka Helper')
    import database as db
    previous=db.DATABASE_PATH
    try:
        db.DATABASE_PATH=target;db.initializeDatabase()
        with db.openDatabase() as c:
            c.execute('BEGIN IMMEDIATE')
            user=c.execute('''SELECT * FROM users WHERE email=? AND isBlocked=0 AND emailVerified=1
                AND roleName!='deleted' AND NOT EXISTS (SELECT 1 FROM remoteAccounts r WHERE r.localUserId=users.userId)''',(email.strip().lower(),)).fetchone()
            if user is None:raise ValueError('Нужен существующий подтверждённый незаблокированный аккаунт этой базы')
            if user['roleName']=='admin':return False
            c.execute("UPDATE users SET roleName='admin' WHERE userId=?",(user['userId'],))
            c.execute('DELETE FROM accountSessions WHERE userId=?',(user['userId'],))
            c.execute('''INSERT INTO adminAudit(actorNickname,action,targetType,targetId,reason)
                VALUES ('Консоль','role.admin','user',?,'Первичное назначение администратора через консоль')''',(user['userId'],))
            return True
    finally:db.DATABASE_PATH=previous


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database',required=True)
    parser.add_argument('--email',required=True)
    options=parser.parse_args()
    try:
        changed=grantAdmin(options.database,options.email)
    except (ValueError,sqlite3.Error) as error:parser.exit(1,str(error)+'\n')
    print('Роль администратора назначена. Войдите в приложение заново.' if changed else 'Аккаунт уже администратор.')
