from io import BytesIO
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile
from PIL import Image
import database as db
from mesh_renderer import parseObj,projectMesh
from model_service import MODEL_ITEMS,loadModel,searchModels,modelBundle,favoriteModelIds,saveModelFavorite
from learning_assets import MODEL_ASSETS,STEP_ASSETS
from lesson_service import getLessonById


TRIANGLE='v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n'


class MeshTests(unittest.TestCase):
    def test_all_models_are_real_bounded_meshes_and_all_step_images_exist(self):
        root=Path(__file__).resolve().parents[1]/'assets'
        self.assertEqual(len(MODEL_ITEMS),6)
        self.assertEqual(len(STEP_ASSETS),37)
        for item in MODEL_ITEMS:
            mesh=loadModel(item['modelId'])
            self.assertGreater(len(mesh.vertices),100)
            self.assertGreater(len(mesh.faces),100)
            self.assertTrue(all(math.isfinite(v) and abs(v)<=1.000001 for p in mesh.vertices for v in p))
            lesson=getLessonById(item['lessonId'])
            self.assertEqual(len(lesson['stepImages']),len(lesson['steps']))
            for path in lesson['stepImages']:
                with Image.open(root/path) as image:
                    self.assertEqual(image.size,(640,480));image.verify()
        self.assertTrue(all((root/path).is_file() for path in MODEL_ASSETS))

    def test_obj_negative_indices_materials_and_no_external_reads(self):
        with patch('builtins.open',side_effect=AssertionError('external read')):
            mesh=parseObj('mtllib ../../private.mtl\nusemtl red\n'+TRIANGLE.replace('f 1 2 3','f -3 -2 -1'),
                          'newmtl red\nKd 1 0 0\n')
        self.assertEqual(mesh.faces[0][0],(0,1,2))
        self.assertEqual(mesh.faces[0][1],(1,0,0))

    def test_invalid_meshes_and_materials_are_rejected(self):
        for text in ('','v nan 0 0\n'+TRIANGLE,'v inf 0 0\n'+TRIANGLE,
                     TRIANGLE.replace('f 1 2 3','f 0 2 3'),TRIANGLE.replace('f 1 2 3','f 1 2 99'),
                     'v 0 0 0\nf 1 1 1'):
            with self.subTest(text=text),self.assertRaises(ValueError):parseObj(text)
        with self.assertRaises(ValueError):parseObj(TRIANGLE,'newmtl red\nKd 2 0 0')
        with patch('mesh_renderer.MAX_VERTICES',2),self.assertRaises(ValueError):parseObj(TRIANGLE)

    def test_rotation_zoom_and_light_change_projection_without_mutating_mesh(self):
        mesh=loadModel('cat')
        original=mesh.vertices
        front=projectMesh(mesh,320,300,yaw=0,pitch=0)
        side=projectMesh(mesh,320,300,yaw=90,pitch=0)
        self.assertNotEqual(front,side)
        self.assertNotEqual(front,projectMesh(mesh,320,300,yaw=0,pitch=0,zoom=1.8))
        self.assertNotEqual([f['color'] for f in front],
            [f['color'] for f in projectMesh(mesh,320,300,yaw=0,pitch=0,light=120)])
        self.assertEqual(mesh.vertices,original)
        self.assertEqual([f['depth'] for f in front],sorted(f['depth'] for f in front))
        self.assertTrue(all(math.isfinite(n) for face in front for point in face['points'] for n in point))
        with self.assertRaises(ValueError):projectMesh(mesh,320,300,zoom=10)
        with self.assertRaises(ValueError):projectMesh(mesh,320,300,yaw=float('nan'))

    def test_catalog_search_and_portable_obj_zip(self):
        self.assertEqual([m['modelId'] for m in searchModels('3D кот')],['cat'])
        self.assertEqual([m['modelId'] for m in searchModels('',category='Транспорт')],['car'])
        self.assertEqual([m['modelId'] for m in searchModels('',maxTime=30)],['pizza'])
        for identifier in ('../../secret','unknown','https://example.com/a.obj'):
            with self.assertRaises(ValueError):loadModel(identifier)
        with ZipFile(BytesIO(modelBundle('cat'))) as archive:
            self.assertEqual(set(archive.namelist()),{'cat.obj','cat.mtl','README.txt'})
            mesh=parseObj(archive.read('cat.obj').decode(),archive.read('cat.mtl').decode())
            self.assertEqual(len(mesh.faces),len(loadModel('cat').faces))


class ModelFavoriteTests(unittest.TestCase):
    def setUp(self):
        folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup)
        p=patch.object(db,'DATABASE_PATH',Path(folder.name)/'test.db');p.start();self.addCleanup(p.stop)
        db.initializeDatabase()
        self.owner=db.createUser('one@example.com','hash','salt','one')
        self.other=db.createUser('two@example.com','hash','salt','two')

    def test_favorites_are_private_idempotent_and_removed_with_owner(self):
        for user in (self.owner,self.other):saveModelFavorite(user,'cat',True)
        saveModelFavorite(self.owner,'cat',True)
        saveModelFavorite(self.owner,'dragon',True)
        db.initializeDatabase()
        self.assertEqual(favoriteModelIds(self.owner),{'cat','dragon'})
        self.assertEqual(favoriteModelIds(self.other),{'cat'})
        saveModelFavorite(self.owner,'cat',False)
        self.assertEqual(favoriteModelIds(self.owner),{'dragon'})
        self.assertTrue(db.deleteUserDataById(self.owner))
        self.assertEqual(favoriteModelIds(self.owner),set())
        self.assertEqual(favoriteModelIds(self.other),{'cat'})

    def test_invalid_model_and_blocked_user_cannot_save(self):
        with self.assertRaises(ValueError):saveModelFavorite(self.owner,'../cat',True)
        with db.openDatabase() as c:c.execute('UPDATE users SET isBlocked=1 WHERE userId=?',(self.owner,))
        with self.assertRaises(ValueError):saveModelFavorite(self.owner,'cat',True)
