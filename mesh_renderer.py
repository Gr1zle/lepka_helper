"""Небольшой OBJ-просмотрщик: перспективная проекция, отсечение граней и свет.

Объекты — непрозрачные треугольные сетки. Сортировка по глубине подходит для
наших небольших выпуклых деталей; это не универсальный GPU-рендерер.
"""
from dataclasses import dataclass
import math

MAX_VERTICES = 6000
MAX_TRIANGLES = 10000


def subtract(a,b):
    return tuple(x-y for x,y in zip(a,b))


def cross(a,b):
    return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])


def dot(a,b):
    return sum(x*y for x,y in zip(a,b))


def unit(value):
    length=math.sqrt(dot(value,value))
    return tuple(x/length for x in value) if length>1e-12 else (0,0,0)


@dataclass(frozen=True)
class Mesh:
    vertices: tuple
    faces: tuple  # (индексы, цвет RGB 0..1, нормаль)


def parseObj(objText,materialText=''):
    if len(objText)>2_000_000 or len(materialText)>100_000:
        raise ValueError('Модель слишком большая')
    colors={'default':(0.6,0.65,0.7)}
    name='default'
    try:
        for line in materialText.splitlines():
            values=line.split('#',1)[0].split()
            if not values:continue
            if values[0]=='newmtl' and len(values)==2:
                name=values[1]
            elif values[0]=='Kd' and len(values)==4:
                color=tuple(float(v) for v in values[1:])
                if not all(math.isfinite(v) and 0<=v<=1 for v in color):
                    raise ValueError('Некорректный цвет материала')
                colors[name]=color
        vertices,faces=[],[]
        color=colors['default']
        for line in objText.splitlines():
            values=line.split('#',1)[0].split()
            if not values:continue
            if values[0]=='v':
                if len(values)!=4:raise ValueError('Некорректная вершина OBJ')
                point=tuple(float(v) for v in values[1:])
                if not all(math.isfinite(v) and abs(v)<=1_000_000 for v in point):
                    raise ValueError('Некорректные координаты OBJ')
                vertices.append(point)
                if len(vertices)>MAX_VERTICES:raise ValueError('Слишком много вершин')
            elif values[0]=='usemtl':
                if len(values)!=2:raise ValueError('Некорректный материал OBJ')
                color=colors.get(values[1],colors['default'])
            elif values[0]=='f':
                if not 4<=len(values)<=9:raise ValueError('Некорректная грань OBJ')
                indices=[]
                for value in values[1:]:
                    index=int(value.split('/')[0])
                    index=index-1 if index>0 else len(vertices)+index if index<0 else -1
                    if not 0<=index<len(vertices):raise ValueError('Индекс вершины вне модели')
                    indices.append(index)
                for i in range(1,len(indices)-1):
                    faces.append(((indices[0],indices[i],indices[i+1]),color))
                    if len(faces)>MAX_TRIANGLES:raise ValueError('Слишком много граней')
        if not vertices or not faces:raise ValueError('В OBJ нет геометрии')
        lo=[min(p[i] for p in vertices) for i in range(3)]
        hi=[max(p[i] for p in vertices) for i in range(3)]
        span=max(b-a for a,b in zip(lo,hi))
        if span<1e-9:raise ValueError('Модель имеет нулевой размер')
        center=[(a+b)/2 for a,b in zip(lo,hi)]
        vertices=tuple(tuple((v-c)*2/span for v,c in zip(point,center)) for point in vertices)
        triangles=[]
        for indices,color in faces:
            a,b,c=(vertices[i] for i in indices)
            normal=unit(cross(subtract(b,a),subtract(c,a)))
            if normal!=(0,0,0):triangles.append((indices,color,normal))
        if not triangles:raise ValueError('В модели нет ненулевых треугольников')
        return Mesh(vertices,tuple(triangles))
    except (TypeError,OverflowError,IndexError) as error:
        raise ValueError('Не удалось прочитать OBJ') from error


def projectMesh(mesh,width,height,yaw=-25,pitch=15,zoom=1,light=-45,brightness=1):
    if not all(math.isfinite(v) for v in (width,height,yaw,pitch,zoom,light,brightness)):
        raise ValueError('Некорректные параметры просмотра')
    if not 0<width<=2000 or not 0<height<=2000 or not 0.5<=zoom<=2.5 or not 0.4<=brightness<=1.6:
        raise ValueError('Параметры просмотра вне допустимых границ')
    cy,sy=math.cos(math.radians(yaw)),math.sin(math.radians(yaw))
    cp,sp=math.cos(math.radians(pitch)),math.sin(math.radians(pitch))
    def rotate(p):
        x,y,z=p
        x,z=x*cy+z*sy,-x*sy+z*cy
        return (x,y*cp-z*sp,y*sp+z*cp)
    points=[rotate(p) for p in mesh.vertices]
    scale=min(width,height)*1.45*zoom
    projected=[(width/2+x*scale/(4-z),height/2-y*scale/(4-z)) for x,y,z in points]
    lightDirection=unit((math.sin(math.radians(light)),0.8,math.cos(math.radians(light))))
    result=[]
    for indices,color,normal in mesh.faces:
        n=rotate(normal)
        center=tuple(sum(points[i][axis] for i in indices)/3 for axis in range(3))
        if dot(n,(-center[0],-center[1],4-center[2]))<=0:continue
        shade=(0.3+0.7*max(0,dot(n,lightDirection)))*brightness
        rgb=tuple(max(0,min(255,round(component*shade*255))) for component in color)
        result.append({'points':tuple(projected[i] for i in indices),'color':'#'+''.join(f'{c:02x}' for c in rgb),'depth':center[2]})
    result.sort(key=lambda face:face['depth'])
    return result
