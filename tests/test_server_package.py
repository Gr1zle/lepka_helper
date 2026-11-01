"""Состав отдельного сервера, изолированный запуск и резервные копии SQLite."""
import ast
from contextlib import closing
from pathlib import Path
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import json
from scripts.prepare_server import prepareServer,FILES,ROOT
from scripts.server_backup import copyDatabase
import test_moderation as fixtures
import database as db


class ServerPackageTests(unittest.TestCase):
    def setUp(self):
        root=Path(os.environ.get('RUNNER_TEMP','/workspace'))/'work';root.mkdir(parents=True,exist_ok=True)
        folder=tempfile.TemporaryDirectory(dir=root);self.addCleanup(folder.cleanup);self.root=Path(folder.name)

    def test_explicit_package_has_all_transitive_local_imports_and_no_gui_or_data(self):
        folder=prepareServer(self.root/'server')
        manifest=json.loads((folder/'SERVER_MANIFEST.json').read_text())
        self.assertEqual(set(manifest['files']),set(FILES))
        for name in FILES:
            if not name.endswith('.py'):continue
            for node in ast.walk(ast.parse((folder/name).read_text())):
                modules=[a.name for a in node.names] if isinstance(node,ast.Import) else [node.module] if isinstance(node,ast.ImportFrom) and node.module else []
                for module in modules:
                    self.assertNotEqual(module.split('.')[0],'flet')
                    target=module.replace('.','/')+'.py'
                    if (ROOT/target).is_file():self.assertIn(target,FILES,(name,target))
        self.assertFalse(list(folder.rglob('*.db')))
        self.assertFalse((folder/'assets').exists());self.assertFalse((folder/'views').exists())
        with self.assertRaises(ValueError):prepareServer(folder)

    def test_packaged_api_starts_in_isolated_process_without_importing_flet(self):
        folder=prepareServer(self.root/'server');data=self.root/'data'
        code="""
import sys
sys.path.insert(0,sys.argv[1])
from fastapi.testclient import TestClient
from backend.main import createApp
with TestClient(createApp(sys.argv[2])) as client:
    assert client.get('/ready').status_code==200
    assert client.get('/community/feed').status_code==200
    assert client.get('/community/access').status_code==401
    assert client.get('/community/notices').status_code==401
    assert client.get('/admin/roles').status_code==401
assert 'flet' not in sys.modules
print('Isolated server package OK')
"""
        env=os.environ.copy();env['LEPKA_DATA_DIR']=str(data)
        env.pop('LEPKA_MAIL_API_KEY',None);env.pop('LEPKA_MAIL_FROM',None)
        result=subprocess.run([sys.executable,'-I','-c',code,str(folder),str(data)],cwd=self.root,env=env,text=True,capture_output=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('Isolated server package OK',result.stdout)

    def test_dockerfile_copies_manifest_python_modules_and_checks_readiness(self):
        docker=(ROOT/'backend/Dockerfile').read_text()
        copied=[]
        for line in docker.splitlines():
            if line.startswith('COPY '):copied.extend(p for p in line.split()[1:-1] if not p.startswith('--'))
        for name in FILES:
            if name.endswith('.py'):self.assertIn(name,copied)
        self.assertIn('/ready',docker);self.assertIn('USER 65534:65534',docker)
        self.assertIn('/app/scripts',docker)


class ServerBackupTests(unittest.TestCase):
    setUp=fixtures.ModerationTests.setUp
    login=fixtures.ModerationTests.login

    def test_consistent_backup_restore_preserves_data_but_clears_tokens_and_codes(self):
        with db.openDatabase() as c:
            c.execute("INSERT INTO accountCodes(email,purpose,userId,codeHash,expiresAt,sentAt) VALUES('author@example.com','recovery',?,'test-hash',9999999999,0)",(self.author,))
            sessions=c.execute('SELECT COUNT(*) FROM accountSessions').fetchone()[0]
        backup=copyDatabase(db.DATABASE_PATH,self.root/'backup.db')
        restored=copyDatabase(backup,self.root/'restored.db',True)
        with closing(sqlite3.connect(restored)) as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM accountSessions').fetchone()[0],0)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM accountCodes').fetchone()[0],0)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM posts').fetchone()[0],1)
            self.assertEqual(c.execute("SELECT COUNT(*) FROM adminAudit WHERE action='backup.restore'").fetchone()[0],1)
        with db.openDatabase() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM accountSessions').fetchone()[0],sessions)
        self.assertEqual(backup.stat().st_mode&0o077,0)
        self.assertEqual(self.client.get('/profile',headers=self.authorHeaders).status_code,200)

    def test_existing_output_wrong_database_and_restore_failure_never_destroy_source(self):
        output=self.root/'existing.db';output.write_bytes(b'keep existing file')
        with self.assertRaises(FileExistsError):copyDatabase(db.DATABASE_PATH,output)
        self.assertEqual(output.read_bytes(),b'keep existing file')
        wrong=self.root/'wrong.db'
        with closing(sqlite3.connect(wrong)) as c:c.execute('CREATE TABLE unrelated (id INTEGER)')
        with self.assertRaises(ValueError):copyDatabase(wrong,self.root/'refused.db')
        self.assertFalse((self.root/'refused.db').exists())
        with self.assertRaises(ValueError):copyDatabase(db.DATABASE_PATH,db.DATABASE_PATH)
        self.assertTrue(Path(db.DATABASE_PATH).is_file())

    def test_readiness_does_not_create_a_missing_database_or_reveal_paths(self):
        missing=self.root/'missing.db'
        with patch.object(db,'DATABASE_PATH',missing):
            result=self.client.get('/ready')
            self.assertEqual(result.status_code,503)
            self.assertNotIn(str(missing),result.text)
        self.assertFalse(missing.exists())

if __name__=='__main__':unittest.main()
