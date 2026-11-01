"""Согласованная копия SQLite; восстановление только в новый файл, без старых сессий."""
import argparse
from contextlib import closing
from pathlib import Path
import os
import sqlite3


def copyDatabase(source,output,restore=False):
    source=Path(source).expanduser().resolve();output=Path(output).expanduser().absolute()
    if not source.is_file():raise ValueError('Укажите существующую базу')
    if source==output.resolve():raise ValueError('Исходник и копия должны различаться')
    output.parent.mkdir(parents=True,exist_ok=True)
    descriptor=None;created=False
    try:
        with closing(sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)) as src:
            columns={row[1] for row in src.execute('PRAGMA table_info(users)')}
            if not {'userId','email','roleName','passwordHash'}<=columns:raise ValueError('Это не база Lepka Helper')
            if src.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise ValueError('База не прошла проверку целостности')
            descriptor=os.open(output,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
            created=True
            os.close(descriptor);descriptor=None
            with closing(sqlite3.connect(output)) as dst:
                src.backup(dst)
                if restore:
                    dst.execute('DELETE FROM accountSessions')
                    dst.execute('DELETE FROM accountCodes')
                    if dst.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='adminAudit'").fetchone():
                        dst.execute("INSERT INTO adminAudit(actorNickname,action,targetType,targetId,reason) VALUES('Консоль','backup.restore','database',0,'Восстановлена новая копия базы, прежние сессии отозваны')")
                    dst.commit()
                if dst.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise ValueError('Копия не прошла проверку целостности')
        return output
    except Exception:
        if descriptor is not None:os.close(descriptor)
        if created:output.unlink(missing_ok=True)
        raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation',choices=('backup','restore'))
    parser.add_argument('--source',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args()
    try:result=copyDatabase(args.source,args.output,args.operation=='restore')
    except (ValueError,OSError,sqlite3.Error) as error:parser.exit(1,str(error)+'\n')
    print(result)
