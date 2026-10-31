from io import BytesIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient
import database as db
import model_import as models
import model_upload as uploads
from model_service import getModel,loadModel,searchModels,modelBundle,saveModelFavorite,favoriteModelIds
from auth_service import ensureDemoUser,loginUser
from account_security import logoutUser
from download_service import createDownload,downloadRecipe

OBJ=b'v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n'


def bundle(files):
    stream=BytesIO()
    with ZipFile(stream,'w') as z:
        for name,content in files:z.writestr(name,content)
    return stream.getvalue()


class ImportModelTests(unittest.TestCase):
    def setUp(self):
        folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup)
        for p in (patch.object(db,'DATABASE_PATH',Path(folder.name)/'test.db'),patch('account_gateway.getApiUrl',return_value='')):
            p.start();self.addCleanup(p.stop)
        db.initializeDatabase();ensureDemoUser()
        self.user=loginUser('test@email.com','Test123456')[2];self.owner=self.user['userId']
        self.other=db.createUser('other@example.com','hash','salt','other')
        uploads._uploads.clear();self.addCleanup(uploads._uploads.clear)

    def test_obj_and_zip_round_trip_with_private_preview_search_favorite_and_restart(self):
        identifier=models.importModel(self.owner,'cat.zip',modelBundle('cat'),'Мой котик')
        db.initializeDatabase()
        self.assertEqual(len(loadModel(identifier,self.owner).faces),848)
        item=getModel(identifier,self.owner)
        self.assertEqual(item['title'],'Мой котик');self.assertTrue(item['previewImage'].startswith(b'\x89PNG'))
        self.assertEqual([r['modelId'] for r in searchModels('мой котик',userId=self.owner)],[identifier])
        saveModelFavorite(self.owner,identifier,True)
        self.assertEqual(favoriteModelIds(self.owner),{identifier})
        self.assertIsNone(getModel(identifier,self.other));self.assertIsNone(getModel(identifier))
        self.assertEqual(searchModels('мой котик',userId=self.other),[])
        with self.assertRaises(ValueError):modelBundle(identifier,self.other)
        with self.assertRaises(ValueError):saveModelFavorite(self.other,identifier,True)
        exported=modelBundle(identifier,self.owner)
        decoded=models.decodeModel('export.zip',exported)
        self.assertEqual(len(decoded['mesh'].faces),848)
        self.assertIn('mtllib model.mtl',decoded['objText'])
        with ZipFile(BytesIO(exported)) as z:self.assertEqual(set(z.namelist()),{'model.obj','model.mtl','README.txt'})

    def test_plain_obj_never_loads_external_materials_and_uses_filename_for_title(self):
        data=b'mtllib ../../private.mtl\n'+OBJ
        with patch('builtins.open',side_effect=AssertionError('external file')):
            decoded=models.decodeModel('figure.obj',data)
        self.assertNotIn('mtllib',decoded['objText'])
        self.assertEqual(decoded['title'],'figure')
        identifier=models.importModel(self.owner,'figure.obj',data)
        self.assertEqual(len(loadModel(identifier,self.owner).faces),1)

    def test_unsupported_corrupt_and_oversized_inputs_leave_no_records(self):
        for name,content in [('scene.glb',OBJ),('scene.obj',b'\xff'),('empty.obj',b''),('wrong.obj',b'no mesh'),('bad.zip',b'PKbad')]:
            with self.subTest(name=name),self.assertRaises(ValueError):models.importModel(self.owner,name,content)
        with patch.object(models,'MAX_IMPORT_TRIANGLES',1),self.assertRaises(ValueError):models.importModel(self.owner,'cat.zip',modelBundle('cat'))
        with patch.object(models,'MAX_MODEL_BYTES',10),self.assertRaises(ValueError):models.importModel(self.owner,'x.obj',OBJ)
        self.assertEqual(models.listImportedModels(self.owner),[])

    def test_zip_rejects_paths_duplicates_multiple_meshes_and_textures(self):
        variants=[ [('../x.obj',OBJ)],[('/x.obj',OBJ)],[('C:/x.obj',OBJ)], [('a\\x.obj',OBJ)],
                  [('x.obj',OBJ),('X.OBJ',OBJ)],[('x.obj',OBJ),('y.obj',OBJ)],
                  [('x.obj',OBJ),('x.png',b'image')],[('x.obj',OBJ),('a.mtl',b''),('b.mtl',b'')],
                  [('a.txt',b'hello')]]
        for files in variants:
            with self.subTest(files=files),self.assertRaises(ValueError):models.decodeModel('x.zip',bundle(files))
        with patch.object(models,'MAX_OBJ_BYTES',5),self.assertRaises(ValueError):models.decodeModel('x.zip',bundle([('x.obj',OBJ)]))
        self.assertEqual(len(models.decodeModel('x.zip',bundle([('nested/x.obj',OBJ)]))['mesh'].faces),1)

    def test_owner_limits_blocking_deletion_and_account_cleanup(self):
        identifier=models.importModel(self.owner,'x.obj',OBJ)
        saveModelFavorite(self.owner,identifier,True)
        self.assertFalse(models.deleteImportedModel(self.other,identifier))
        with patch.object(models,'MAX_IMPORTED_MODELS',1),self.assertRaises(ValueError):models.importModel(self.owner,'y.obj',OBJ)
        with db.openDatabase() as c:c.execute('UPDATE users SET isBlocked=1 WHERE userId=?',(self.owner,))
        self.assertIsNone(getModel(identifier,self.owner));self.assertEqual(models.listImportedModels(self.owner),[])
        self.assertFalse(models.deleteImportedModel(self.owner,identifier))
        with self.assertRaises(ValueError):models.importModel(self.owner,'x.obj',OBJ)
        with db.openDatabase() as c:c.execute('UPDATE users SET isBlocked=0 WHERE userId=?',(self.owner,))
        self.assertTrue(models.deleteImportedModel(self.owner,identifier));self.assertEqual(favoriteModelIds(self.owner),set())
        models.importModel(self.owner,'z.obj',OBJ)
        self.assertTrue(db.deleteUserDataById(self.owner))
        with db.openDatabase() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM importedModels').fetchone()[0],0)
            self.assertEqual(c.execute('PRAGMA foreign_key_check').fetchall(),[])

    def test_http_upload_is_single_use_private_bounded_and_checks_revoked_session(self):
        app=Starlette(routes=[Route('/models/{ticket}',uploads.uploadModel,methods=['PUT']),
                              Route('/downloads/{ticket}',downloadRecipe,methods=['GET'])])
        with TestClient(app) as client:
            ticket=uploads.createModelUpload(self.user,'x.obj')
            self.assertEqual(client.put('/models/'+ticket,content=OBJ).status_code,200)
            self.assertEqual(client.put('/models/'+ticket,content=OBJ).status_code,404)
            with self.assertRaises(ValueError):uploads.takeModelUpload(ticket,self.other)
            self.assertEqual(uploads.takeModelUpload(ticket,self.owner),('x.obj',OBJ))
            with self.assertRaises(ValueError):uploads.takeModelUpload(ticket,self.owner)
            ticket=uploads.createModelUpload(self.user,'x.obj')
            with patch.object(uploads,'MAX_MODEL_BYTES',10):self.assertEqual(client.put('/models/'+ticket,content=OBJ).status_code,413)
            ticket=uploads.createModelUpload(self.user,'x.obj')
            self.assertEqual(client.put('/models/'+ticket,content=b'bad').status_code,400)
            ticket=uploads.createModelUpload(self.user,'x.obj');uploads.cancelModelUpload(ticket,self.owner)
            self.assertEqual(client.put('/models/'+ticket,content=OBJ).status_code,404)
            identifier=models.importModel(self.owner,'x.obj',OBJ)
            download=createDownload(modelBundle(identifier,self.owner),'lepka-model.zip','application/zip',self.user)
            ticket=uploads.createModelUpload(self.user,'x.obj');logoutUser(self.user['sessionToken'])
            self.assertEqual(client.put('/models/'+ticket,content=OBJ).status_code,401)
            self.assertEqual(client.get('/downloads/'+download).status_code,401)
