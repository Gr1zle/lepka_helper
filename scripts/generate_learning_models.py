"""Авторские OBJ из геометрических деталей и 37 пошаговых 3D-схем.

Воспроизведение: python -m scripts.generate_learning_models
Схемы показывают сборку геометрических форм, а не фотографии лепки руками.
"""
from io import BytesIO
import math
from pathlib import Path
import sys
from PIL import Image,ImageDraw,ImageFont

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from learning_assets import MODEL_ITEMS
from mesh_renderer import cross,dot,subtract,parseObj,projectMesh

PALETTE={'grey':'#9fa6b2','white':'#fff7e9','pink':'#e6a3ae','black':'#272b37',
         'brown':'#a67953','beige':'#e3c69f','green':'#76a56d','leaf':'#43836c',
         'yellow':'#e2c966','red':'#c96454','blue':'#699cbe','skin':'#eac5a7','dark':'#414d69'}


class Builder:
    def __init__(self):
        self.vertices=[]
        self.parts=[]

    def add(self,points,faces,stage,color,center):
        offset=len(self.vertices)
        self.vertices.extend(points)
        indices=[]
        for face in faces:
            a,b,c=(points[i] for i in face)
            normal=cross(subtract(b,a),subtract(c,a))
            midpoint=tuple((x+y+z)/3 for x,y,z in zip(a,b,c))
            if dot(normal,subtract(midpoint,center))<0:face=(face[0],face[2],face[1])
            indices.append(tuple(i+offset+1 for i in face))
        self.parts.append((stage,color,indices))

    def sphere(self,center,size,stage,color,segments=8,rings=4):
        points=[]
        for row in range(rings+1):
            latitude=math.pi*row/rings
            for column in range(segments):
                longitude=2*math.pi*column/segments
                raw=(math.sin(latitude)*math.cos(longitude),math.cos(latitude),math.sin(latitude)*math.sin(longitude))
                points.append(tuple(c+r*s for c,r,s in zip(center,raw,size)))
        faces=[]
        for row in range(rings):
            for col in range(segments):
                a=row*segments+col;b=row*segments+(col+1)%segments;c=a+segments;d=b+segments
                if row:faces.append((a,b,c))
                if row<rings-1:faces.append((b,d,c))
        self.add(points,faces,stage,color,center)

    def box(self,center,size,stage,color):
        points=[tuple(c+s*v for c,s,v in zip(center,size,p)) for p in
                ((-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1))]
        faces=[]
        for a,b,c,d in ((0,1,2,3),(4,5,6,7),(0,1,5,4),(2,3,7,6),(0,3,7,4),(1,2,6,5)):
            faces.extend(((a,b,c),(a,c,d)))
        self.add(points,faces,stage,color,center)

    def cylinder(self,center,radius,height,stage,color,axis='y',cone=False,segments=10):
        def transform(p):
            if axis=='z':p=(p[0],-p[2],p[1])
            if axis=='x':p=(p[1],p[0],p[2])
            return tuple(a+b for a,b in zip(center,p))
        points=[]
        for y,r in ((-height/2,radius),(height/2,0 if cone else radius)):
            points.extend(transform((r*math.cos(i*2*math.pi/segments),y,r*math.sin(i*2*math.pi/segments))) for i in range(segments))
        points.extend((transform((0,-height/2,0)),transform((0,height/2,0))))
        faces=[]
        for i in range(segments):
            j=(i+1)%segments
            faces.extend(((i,j,i+segments),(j,j+segments,i+segments),(2*segments,i,j)))
            if not cone:faces.append((2*segments+1,i+segments,j+segments))
        self.add(points,faces,stage,color,center)

    def wing(self,side,stage):
        base=[(side*.27,.1,-.08),(side*1.02,.7,-.22),(side*.95,-.15,-.15)]
        points=base+[(x,y,z+.055) for x,y,z in base]
        faces=[(0,1,2),(3,4,5),(0,1,4),(0,4,3),(1,2,5),(1,5,4),(2,0,3),(2,3,5)]
        center=tuple(sum(p[i] for p in points)/len(points) for i in range(3))
        self.add(points,faces,stage,'leaf',center)

    def obj(self,modelId,step=100):
        lines=[f'# Procedural learning model: {modelId}',f'mtllib {modelId}.mtl']
        lines.extend('v '+' '.join(f'{v:.6f}' for v in p) for p in self.vertices)
        for index,(stage,color,faces) in enumerate(self.parts):
            if stage>step:continue
            lines.extend((f'g stage_{stage}_part_{index}',f'usemtl {color}'))
            lines.extend('f '+' '.join(str(i) for i in face) for face in faces)
        return '\n'.join(lines)+'\n'


def build(modelId):
    b=Builder()
    if modelId=='cat':
        b.sphere((0,-.35,0),(.45,.6,.32),1,'grey')
        b.sphere((0,.42,.03),(.48,.42,.37),2,'grey')
        for x in (-.3,.3):
            b.cylinder((x,.86,.01),.19,.43,3,'grey',cone=True,segments=4)
            b.sphere((x,.9,.12),(.09,.12,.03),3,'pink')
        for x in (-.14,.14):b.sphere((x,.27,.37),(.17,.12,.07),4,'white')
        b.sphere((0,.34,.45),(.065,.055,.035),4,'pink')
        for x in (-.2,.2):
            b.sphere((x,.51,.355),(.06,.075,.04),5,'black')
            b.sphere((x-.015,.54,.39),(.018,.02,.012),5,'white',rings=3)
        for x in (-.3,.3):b.sphere((x,-.87,.16),(.19,.14,.23),5,'grey')
        for x in (-.4,.4):b.sphere((x,-.39,.15),(.12,.28,.12),5,'grey')
        for c,s in (((.48,-.6,-.08),(.16,.15,.15)),((.61,-.49,-.1),(.14,.2,.13)),((.63,-.26,-.1),(.12,.18,.12))):b.sphere(c,s,5,'grey')
    elif modelId=='pizza':
        b.cylinder((0,-.06,0),.9,.13,1,'beige',segments=16)
        b.cylinder((0,.025,0),.81,.05,2,'yellow',segments=16)
        for x,z in ((-.42,-.25),(.2,-.4),(.45,.13),(-.27,.38),(.02,.05)):
            b.cylinder((x,.068,z),.13,.035,3,'red',segments=10)
        for x,z in ((-.4,.05),(.08,.48),(.45,-.3)):
            b.sphere((x,.09,z),(.08,.025,.16),4,'leaf')
    elif modelId=='dragon':
        b.sphere((0,-.2,0),(.43,.6,.35),1,'green')
        b.sphere((0,.55,.08),(.38,.34,.31),2,'green')
        b.sphere((0,.43,.34),(.28,.18,.22),2,'green')
        for center,size in (((0,-.45,-.42),(.27,.2,.3)),((0,-.48,-.72),(.19,.14,.25)),((0,-.5,-.94),(.12,.09,.2))):b.sphere(center,size,3,'green')
        for x in (-.38,.38):
            b.sphere((x,-.65,.16),(.2,.17,.29),4,'green')
            b.sphere((x,-.08,.17),(.12,.3,.12),4,'green')
        b.wing(-1,5);b.wing(1,5)
        for x in (-.19,.19):
            b.sphere((x,.63,.34),(.055,.07,.035),6,'black')
            b.cylinder((x,.93,-.03),.075,.26,6,'white',cone=True,segments=6)
        for y,z in ((.45,-.23),(.18,-.32),(-.12,-.4),(-.33,-.62)):
            b.cylinder((0,y,z),.1,.22,7,'yellow',cone=True,segments=4)
    elif modelId=='car':
        b.box((0,-.05,0),(.77,.18,.35),1,'blue')
        b.box((-.07,.25,0),(.39,.2,.3),2,'blue')
        for x in (-.49,.49):
            for z in (-.37,.37):
                b.cylinder((x,-.23,z),.22,.15,3,'black',axis='z',segments=12)
                b.cylinder((x,-.23,z+(.08 if z>0 else -.08)),.1,.012,4,'grey',axis='z',segments=10)
        for x in (-.25,.14):
            for z in (-.305,.305):b.box((x,.26,z),(.15,.13,.012),5,'white')
        for z in (-.22,.22):b.sphere((.78,-.03,z),(.025,.065,.075),5,'yellow')
    elif modelId=='anime':
        b.sphere((0,.6,0),(.37,.44,.3),1,'skin')
        for x in (-.14,.14):
            b.sphere((x,.63,.28),(.1,.11,.025),2,'black')
            b.sphere((x,.64,.304),(.075,.075,.014),3,'white')
            b.sphere((x,.63,.32),(.034,.055,.013),3,'blue')
        b.sphere((0,.94,-.02),(.39,.23,.31),4,'black')
        for x in (-.33,.33):b.sphere((x,.6,-.05),(.11,.37,.28),4,'black')
        b.box((0,-.17,0),(.29,.34,.18),5,'blue')
        for x in (-.4,.4):b.sphere((x,-.18,0),(.1,.32,.12),5,'blue')
        for x in (-.16,.16):b.box((x,-.73,0),(.12,.25,.14),5,'dark')
        b.cylinder((0,.23,0),.12,.22,6,'skin')
        for x in (-.08,.08):b.sphere((x,.015,.205),(.09,.055,.03),7,'pink')
        for y in (-.17,-.32):b.sphere((0,y,.19),(.025,.025,.018),7,'yellow',rings=3)
    elif modelId=='bear':
        b.sphere((0,-.3,0),(.48,.58,.36),1,'brown')
        b.sphere((0,.43,0),(.49,.42,.37),2,'brown')
        for x in (-.39,.39):
            b.sphere((x,.78,-.02),(.19,.19,.14),3,'brown')
            b.sphere((x,.79,.105),(.1,.11,.025),3,'beige')
        b.sphere((0,.28,.36),(.24,.16,.075),4,'beige')
        b.sphere((0,.37,.45),(.075,.055,.035),5,'black')
        for x in (-.19,.19):b.sphere((x,.53,.34),(.055,.07,.04),5,'black')
        for x in (-.38,.38):
            b.sphere((x,-.38,.1),(.18,.3,.15),6,'brown')
            b.sphere((x,-.81,.14),(.2,.16,.22),6,'brown')
        for x in (-.31,.31):b.sphere((x,.33,.33),(.08,.045,.025),6,'pink')
    else:raise ValueError('Unknown model')
    return b


def materials():
    lines=['# Original solid-color materials']
    for name,color in PALETTE.items():
        lines.extend((f'newmtl {name}','Kd '+' '.join(f'{int(color[i:i+2],16)/255:.6f}' for i in (1,3,5))))
    return '\n'.join(lines)+'\n'


def renderImage(obj,mtl,label,pitch=15):
    mesh=parseObj(obj,mtl)
    image=Image.new('RGB',(800,600),'#edf1f5')
    draw=ImageDraw.Draw(image)
    draw.ellipse((230,475,570,510),fill='#d9dfe7')
    for face in projectMesh(mesh,800,560,pitch=pitch):
        draw.polygon(face['points'],fill=face['color'])
    font=ImageFont.truetype(str(ROOT/'assets/fonts/DejaVuSans.ttf'),24)
    draw.text((28,556),label,font=font,fill='#465267')
    image=image.resize((640,480),Image.Resampling.LANCZOS)
    output=BytesIO();image.save(output,format='PNG',optimize=True)
    return output.getvalue()


def generate():
    models=ROOT/'assets/models';steps=ROOT/'assets/lessons/steps'
    models.mkdir(parents=True,exist_ok=True);steps.mkdir(parents=True,exist_ok=True)
    mtl=materials()
    for item in MODEL_ITEMS:
        builder=build(item['modelId']);obj=builder.obj(item['modelId'])
        (models/f"{item['modelId']}.obj").write_text(obj,encoding='utf-8')
        (models/f"{item['modelId']}.mtl").write_text(mtl,encoding='utf-8')
        pitch=45 if item['modelId']=='pizza' else 15
        (models/f"{item['modelId']}-preview.png").write_bytes(renderImage(obj,mtl,'3D-схема · '+item['title'],pitch))
        for step in range(1,item['steps']+1):
            path=steps/f"lesson_{item['lessonId']}_{step}.png"
            path.write_bytes(renderImage(builder.obj(item['modelId'],step),mtl,f"3D-схема · Шаг {step} из {item['steps']}",pitch))
        mesh=parseObj(obj,mtl)
        print(item['modelId'],len(mesh.vertices),'vertices',len(mesh.faces),'triangles')


if __name__=='__main__':generate()
