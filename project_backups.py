"""Копии JSON в закрытом каталоге Android, раздельно для местных владельцев."""
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import uuid
from app_paths import DATA_DIRECTORY
from project_archive import MAX_ARCHIVE_BYTES, decodeProject


def backupDirectory(userId):
    if type(userId) is not int or userId < 1:
        raise ValueError('Некорректный владелец копии')
    return DATA_DIRECTORY / 'exports' / f'user-{userId}'


def backupPath(userId, name):
    if not isinstance(name,str) or not re.fullmatch(r'project-[0-9]{8}-[0-9]{6}-[a-f0-9]{8}\.json',name):
        raise ValueError('Некорректное имя копии')
    path = backupDirectory(userId)/name
    if path.is_symlink():
        raise ValueError('Копия недоступна')
    return path


def saveBackup(userId, content):
    decodeProject(content)
    name = datetime.now(timezone.utc).strftime('project-%Y%m%d-%H%M%S-')+uuid.uuid4().hex[:8]+'.json'
    path = backupPath(userId,name)
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    created = False
    try:
        descriptor = os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        created = True
        with os.fdopen(descriptor,'wb') as stream:
            stream.write(content)
    except OSError:
        if created:
            path.unlink(missing_ok=True)
        raise
    return name


def listBackups(userId):
    return sorted((p.name for p in backupDirectory(userId).glob('project-*.json') if p.is_file() and not p.is_symlink()),reverse=True)


def readBackup(userId,name):
    with backupPath(userId,name).open('rb') as stream:
        content = stream.read(MAX_ARCHIVE_BYTES+1)
    decodeProject(content)
    return content


def deleteBackup(userId,name):
    backupPath(userId,name).unlink()
