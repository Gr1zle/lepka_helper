import base64
from io import BytesIO
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch,Mock
from PIL import Image
from color_photo import readImage,pngBytes,sampleColor,nearestColor,cropReference,removeBackground
from color_export import createRecipePng,createRecipePdf
from color_service import BASE_COLORS,calculateRecipe
from clay_tools import recipeLengths
from file_export import writeAtomic


class ColorPhotoTests(unittest.TestCase):
    def test_letterbox_sampling_average_and_nearest_rgb(self):
        image=Image.new('RGBA',(100,50),'#FF3B30')
        self.assertIsNone(sampleColor(image,140,5))
        sample=sampleColor(image,140,140)
        self.assertEqual(sample['hex'],'#FF3B30');self.assertEqual(sample['nearest']['colorId'],3)
        self.assertEqual(nearestColor('#000000')['colorId'],2)
        with self.assertRaises(ValueError):sampleColor(image,float('nan'),50)
        with self.assertRaises(ValueError):sampleColor(Image.new('RGBA',(10,10),(1,2,3,0)),140,140)

    def test_background_only_removes_connected_border_not_same_color_inside_object(self):
        from PIL import ImageDraw
        image=Image.new('RGBA',(40,40),'white');draw=ImageDraw.Draw(image)
        draw.rectangle((8,8,31,31),fill='red');draw.rectangle((15,15,20,20),fill='white')
        processed=removeBackground(image,'#FFFFFF',10)
        self.assertEqual(processed.getpixel((0,0))[3],0)
        self.assertEqual(processed.getpixel((16,16))[3],255)
        self.assertEqual(processed.getpixel((9,9))[3],255)
        self.assertEqual(image.getpixel((0,0))[3],255)
        with self.assertRaises(ValueError):removeBackground(image,'#FFFFFF',151)

    def test_crop_and_normalisation_strip_metadata_preserve_alpha_and_bound_size(self):
        image=Image.new('RGBA',(100,80),(1,2,3,120));image.info['exif']=b'Exif\0\0private'
        clean=readImage(pngBytes(image))
        self.assertFalse(clean.info)
        cropped=cropReference(clean,10,25,10,25)
        self.assertEqual(cropped.size,(80,40));self.assertEqual(cropped.getpixel((0,0))[3],120)
        for args in [(60,0,40,0),(0,float('inf'),0,0)]:
            with self.assertRaises(ValueError):cropReference(clean,*args)

    def test_png_and_a4_pdf_contain_real_recipe_with_calibrated_centimeters(self):
        selected=[{**color,'proportion':50} for color in BASE_COLORS[:2]]
        png=createRecipePng('Смесь для курсовой',selected,100,(20,8))
        with Image.open(BytesIO(png)) as image:
            self.assertEqual(json.loads(image.info['Recipe'])['totalWeight'],100)
            self.assertGreater(len(image.getcolors(image.width*image.height)),20)
        pdf=createRecipePdf('Смесь для курсовой',selected,100,(20,8))
        self.assertTrue(pdf.startswith(b'%PDF-'));self.assertIn(b'%%EOF',pdf)
        self.assertIn(b'/MediaBox',pdf);self.assertGreater(len(pdf),10000)
        lengths=recipeLengths(calculateRecipe(selected,100),20,8)
        self.assertEqual([r['centimeters'] for r in lengths],[20,20])
        for value in ('0','nan',True):
            with self.assertRaises(ValueError):recipeLengths([],value,8)

    def test_zero_byte_placeholder_is_replaced_with_complete_png(self):
        png=createRecipePng('Проверка',[{**c,'proportion':50} for c in BASE_COLORS[:2]],10)
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'recipe.png';path.touch()
            self.assertEqual(writeAtomic(path,png),len(png))
            with Image.open(path) as image:image.verify()
            with self.assertRaises(FileExistsError):writeAtomic(path,b'new bytes')
            with patch('file_export.os.replace',side_effect=OSError('disk failed')):
                with self.assertRaises(OSError):writeAtomic(path,b'new bytes',overwrite=True)
            self.assertEqual(path.read_bytes(),png)
            self.assertEqual(list(Path(folder).iterdir()),[path])

    def test_content_uri_is_never_treated_as_desktop_path(self):
        with self.assertRaises(ValueError):writeAtomic('content://documents/one',b'png')

    def test_android_ui_dialog_does_not_block_normal_platform_calls(self):
        from secure_device import ProtectedSession
        control=ProtectedSession();callback=Mock()
        def update():
            command=control._get_attr('command')
            if command:
                record=json.loads(command)
                control._received(SimpleNamespace(data=json.dumps(dict(requestId=record['requestId'],ok=True,value='normal-call'))))
        with patch.object(control,'update',side_effect=update):
            control.requestUi('cameraCapture',None,callback)
            pending=control._uiPending
            self.assertEqual(control.call('read'),'normal-call')
            callback.assert_not_called()
            control._received(SimpleNamespace(data=json.dumps(dict(requestId=pending,ok=True,value='{"cancelled":true}'))))
            callback.assert_called_once();self.assertIsNone(control._uiPending)
            self.assertEqual(control._get_attr('uiCommand'),'')


class ReferenceTests(unittest.TestCase):
    def setUp(self):
        import database as db
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        p=patch.object(db,'DATABASE_PATH',Path(self.folder.name)/'refs.db');p.start();self.addCleanup(p.stop)
        p=patch('reference_service.getApiUrl',return_value='https://server.example');p.start();self.addCleanup(p.stop)
        db.initializeDatabase();self.owner=db.createUser('one@example.com','','','one');self.other=db.createUser('two@example.com','','','two')
    def test_owner_api_quota_and_delete_account(self):
        from reference_service import saveReference,listReferences,deleteReference
        import database as db
        data=pngBytes(Image.new('RGBA',(10,10),(255,0,0,100)))
        rid=saveReference(self.owner,'Фигурка',data)
        self.assertEqual(len(listReferences(self.owner)),1);self.assertEqual(listReferences(self.other),[])
        self.assertFalse(deleteReference(self.other,rid))
        with patch('reference_service.getApiUrl',return_value='https://other.example'):self.assertEqual(listReferences(self.owner),[])
        for i in range(19):saveReference(self.owner,'Фигура '+str(i),data)
        with self.assertRaises(ValueError):saveReference(self.owner,'Переполнение',data)
        db.deleteUserDataById(self.owner)
        with db.openDatabase() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM referenceImages').fetchone()[0],0)


class CameraUiTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        import test_startup
        test_startup.StartupTests.setUp(self)
    def tearDown(self):
        import test_startup
        test_startup.StartupTests.tearDown(self)
    async def test_android_png_export_sends_bytes_to_document_writer_and_waits_for_result(self):
        import flet as ft
        from views.home_view import createColorsTab
        from test_startup import find,StartupTests
        self.page._set_attr('platform','android');self.page._set_attr('web','false')
        view=ft.View('/home',controls=[createColorsTab(self.page,self.user)]);self.page.views[:]=[view];self.page.update()
        StartupTests.chooseBaseColor(self,view,'Белый');StartupTests.chooseBaseColor(self,view,'Чёрный')
        bridge=Mock()
        with patch('secure_device.getProtectedSession',return_value=bridge),patch.object(ft.FilePicker,'save_file') as old:
            find(view,ft.OutlinedButton,text='Экспорт PNG').on_click(None)
            old.assert_not_called()
        operation,value,callback=bridge.requestUi.call_args.args
        self.assertEqual(operation,'fileSave');payload=json.loads(value)
        data=base64.b64decode(payload['base64']);self.assertTrue(data.startswith(b'\x89PNG'))
        self.assertGreater(len(data),1000)
        callback(dict(ok=True,value=json.dumps(dict(cancelled=False,bytes=len(data)))))
        messages=[c.content.value for c in self.page.overlay if isinstance(c,ft.SnackBar)]
        self.assertTrue(any('Файл сохранён' in m for m in messages))
    async def test_scan_applies_selected_image_color_without_starting_recipe_search(self):
        import flet as ft
        from views.color_scan import openColorScan
        from test_startup import find,walk
        selected=[];apply=Mock()
        def picker(page,user,fn,label):selected.append(fn);return ft.Container()
        with patch('views.color_scan.createPhotoPicker',side_effect=picker):openColorScan(self.page,self.user,apply,Mock())
        dialog=next(c for c in self.page.overlay if isinstance(c,ft.AlertDialog))
        self.assertTrue(selected[0](dict(data=pngBytes(Image.new('RGBA',(100,50),'#FF3B30'))))[0])
        gesture=next(c for c in walk(dialog) if isinstance(c,ft.GestureDetector))
        gesture.on_tap_down(SimpleNamespace(local_x=140,local_y=140))
        find(dialog,ft.TextButton,text='В целевой HEX').on_click(None)
        apply.assert_called_once_with('#FF3B30')

    async def test_browser_camera_requires_live_ticket_and_uploads_real_jpeg(self):
        from fastapi.testclient import TestClient
        from starlette.applications import Starlette
        from starlette.routing import Route
        from camera_web import cameraPage
        from photo_upload import createPhotoUpload,uploadPhoto,takePhotoUpload
        ticket=createPhotoUpload(self.user,'camera.jpg')
        jpeg=BytesIO();Image.new('RGB',(80,50),'#FF3B30').save(jpeg,format='JPEG')
        with TestClient(Starlette(routes=[Route('/camera/{ticket}',cameraPage),Route('/photo-uploads/{ticket}',uploadPhoto,methods=['PUT'])])) as browser:
            response=browser.get('/camera/'+ticket)
            self.assertEqual(response.status_code,200)
            self.assertIn('getUserMedia',response.text);self.assertIn('capture="environment"',response.text)
            self.assertEqual(response.headers['cache-control'],'no-store')
            self.assertEqual(browser.get('/camera/'+'a'*43).status_code,404)
            with patch('photo_upload.getSessionUser',return_value=self.user):
                self.assertEqual(browser.put('/photo-uploads/'+ticket,content=jpeg.getvalue()).status_code,200)
            photo=takePhotoUpload(ticket,self.user['userId'])
            with Image.open(BytesIO(photo['data'])) as image:self.assertEqual(image.size,(80,50))

    async def test_reference_editor_preserves_alpha_when_saved(self):
        import flet as ft
        from views.reference_gallery import createReferenceGallery
        from test_startup import find
        from reference_service import listReferences
        captured=[]
        def picker(page,user,fn,label):captured.append(fn);return ft.Container()
        with patch('views.reference_gallery.createPhotoPicker',side_effect=picker),patch('reference_service.getApiUrl',return_value=''):
            view=createReferenceGallery(self.page);self.page.views[:]=[view];self.page.update()
            image=Image.new('RGBA',(30,30),'white');image.putpixel((15,15),(255,0,0,255))
            self.assertTrue(captured[0](dict(data=pngBytes(image)))[0])
            find(view,ft.OutlinedButton,text='Удалить однотонный фон').on_click(None)
            find(view,ft.FilledButton,text='Сохранить референс').on_click(None)
            records=listReferences(self.user['userId']);self.assertEqual(len(records),1)
            with Image.open(BytesIO(records[0]['image'])) as stored:
                self.assertEqual(stored.getpixel((0,0))[3],0);self.assertEqual(stored.getpixel((15,15))[3],255)
