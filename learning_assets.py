"""Явный каталог авторских геометрических моделей и учебных схем."""
MODEL_ITEMS=(
    {'modelId':'cat','lessonId':1,'title':'Котик','category':'Животные','tags':('кот','кавай','животные'),'steps':6},
    {'modelId':'pizza','lessonId':2,'title':'Пицца','category':'Еда','tags':('пицца','еда','миниатюра'),'steps':5},
    {'modelId':'dragon','lessonId':3,'title':'Дракон','category':'Персонажи','tags':('дракон','фэнтези','крылья'),'steps':7},
    {'modelId':'car','lessonId':4,'title':'Машинка','category':'Транспорт','tags':('машина','транспорт','колёса'),'steps':6},
    {'modelId':'anime','lessonId':5,'title':'Персонаж','category':'Аниме','tags':('аниме','персонаж','лицо'),'steps':7},
    {'modelId':'bear','lessonId':6,'title':'Медвежонок','category':'Кавай','tags':('медведь','кавай','животные'),'steps':6},
)
MODEL_ASSETS=tuple(path for item in MODEL_ITEMS for path in (
    f"models/{item['modelId']}.obj",f"models/{item['modelId']}.mtl",f"models/{item['modelId']}-preview.png"))
STEP_ASSETS=tuple(f"lessons/steps/lesson_{item['lessonId']}_{step}.png" for item in MODEL_ITEMS for step in range(1,item['steps']+1))
