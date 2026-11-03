"""Generate portable sample assets using a temporary DB; never provision a real server account."""
import argparse
import hashlib
import json
from pathlib import Path
import tempfile
from zipfile import ZipFile,ZIP_DEFLATED

ROOT=Path(__file__).resolve().parents[1]

def generate(output):
    output=Path(output).expanduser().resolve()
    if output.exists() and any(output.iterdir()):raise ValueError('Выберите новую или пустую папку демонстрационных файлов')
    output.mkdir(parents=True,exist_ok=True)
    from PIL import Image,ImageDraw
    import database as db
    from project_service import saveProject,saveStep,saveProjectStepPhoto
    from project_sharing import addProjectMixture
    from project_archive import exportProject,decodeProject
    from color_service import BASE_COLORS,calculateMixedColor,calculateRecipe,saveColorMixture
    from color_export import createRecipePng,createRecipePdf
    from model_import import decodeModel
    photo=(ROOT/'assets/models/cat-preview.png').read_bytes()
    (output/'result-demo.png').write_bytes(photo)
    image=Image.new('RGB',(800,400),'white');ImageDraw.Draw(image).rectangle((0,0,399,399),fill='#FF3B30');image.save(output/'color-card.png')
    obj='mtllib clay.mtl\nv 0 0 0\nv 1 0 0\nv 0 1 0\nv 0 0 1\nusemtl clay\nf 1 3 2\nf 1 2 4\nf 1 4 3\nf 2 3 4\n'
    with ZipFile(output/'demo-model.zip','w',ZIP_DEFLATED) as z:
        z.writestr('demo.obj',obj);z.writestr('clay.mtl','newmtl clay\nKd 0.85 0.35 0.22\n')
    decodeModel('demo-model.zip',(output/'demo-model.zip').read_bytes())
    colors=[{**BASE_COLORS[0],'proportion':50},{**BASE_COLORS[2],'proportion':50}]
    recipe=calculateRecipe(colors,100);hexValue=calculateMixedColor(colors)
    (output/'mixture-recipe.png').write_bytes(createRecipePng('Учебный розовый',colors,100))
    (output/'mixture-recipe.pdf').write_bytes(createRecipePdf('Учебный розовый',colors,100))
    previous=db.DATABASE_PATH
    try:
        with tempfile.TemporaryDirectory(prefix='lepka-demo-assets-') as folder:
            db.DATABASE_PATH=Path(folder)/'assets.db';db.initializeDatabase()
            # Only a disposable owner for validating an export, not a login/registration bypass.
            uid=db.createUser('fixture@example.com','','','Fixture')
            pid=saveProject(uid,'Котик для защиты','Животные','','Личные заметки не должны попасть в публикацию')[2]
            steps=[saveStep(pid,uid,title,details)[2] for title,details in [('Подготовить материал','Размять пластилин и подготовить доску'),('Слепить основу','Сформировать тело и голову'),('Добавить детали','Добавить ушки, лапки и хвост')]]
            for sid in steps:saveProjectStepPhoto(pid,sid,uid,{'name':'result.png','data':photo})
            mid=saveColorMixture(uid,'Учебный розовый',hexValue,100,recipe);addProjectMixture(pid,uid,mid)
            content=exportProject(pid,uid);decodeProject(content);(output/'project-demo.json').write_bytes(content)
    finally:db.DATABASE_PATH=previous
    (output/'README.md').write_text('''# Учебные файлы для технического прогона

Это синтетические данные и встроенная геометрическая иллюстрация, не фотографии реальной поделки. Для защиты подготовьте собственные фото результата и этапов.

- project-demo.json: незавершённый проект с тремя этапами, необязательными описаниями, фото и копией рецепта. Импорт создаёт новую личную запись без ID владельца.
- result-demo.png: копия встроенного cat-preview для проверки загрузки фото; не выдавать за фотографию лепки.
- color-card.png: слева RGB (255,59,48), HEX #FF3B30; справа белый. Проверка выбора цвета с фото.
- demo-model.zip: собственный минимальный OBJ/MTL-тетраэдр без текстур.
- mixture-recipe.png/pdf: пример экспорта 100 г, 50% белого + 50% красного.

Генератор не меняет пользовательские базы, не создаёт настоящих аккаунтов/публикаций и не подменяет регистрацию. Два подтверждённых аккаунта нужно подготовить отдельно по DEPLOYMENT/DEMO_SCENARIO.\n''',encoding='utf-8')
    manifest={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(output.iterdir()) if p.is_file()}
    (output/'SHA256.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    return output

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True);args=parser.parse_args()
    try:print(generate(args.output))
    except (ValueError,OSError) as error:parser.exit(1,str(error)+'\n')
