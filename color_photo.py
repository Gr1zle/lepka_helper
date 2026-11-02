"""Camera/gallery colour sampling and simple, explicit reference-image operations."""
from io import BytesIO
import math
from PIL import Image,ImageOps,ImageChops,ImageDraw,UnidentifiedImageError
from color_service import BASE_COLORS,convertHexToRgb,normalizeHexColor


def readImage(content):
    if not isinstance(content,bytes) or not 0<len(content)<=5*1024*1024:raise ValueError('Изображение должно быть не больше 5 МБ')
    try:
        with Image.open(BytesIO(content)) as source:
            if source.format not in ('PNG','JPEG','WEBP') or source.width*source.height>20_000_000 or getattr(source,'n_frames',1)!=1:raise ValueError('Выберите неподвижное изображение до 20 мегапикселей')
            image=ImageOps.exif_transpose(source).convert('RGBA');image.thumbnail((1000,1000))
            image.info.clear()
            return image.copy()
    except (OSError,UnidentifiedImageError,Image.DecompressionBombError):raise ValueError('Не удалось прочитать изображение') from None


def pngBytes(image):
    output=BytesIO();image.save(output,format='PNG');return output.getvalue()


def nearestColor(hexColor):
    rgb=convertHexToRgb(hexColor)
    result=min(BASE_COLORS,key=lambda color:sum((a-b)**2 for a,b in zip(rgb,convertHexToRgb(color['hex']))))
    return {**result,'distance':round(math.sqrt(sum((a-b)**2 for a,b in zip(rgb,convertHexToRgb(result['hex'])))),1)}


def sampleColor(image,x,y,displayWidth=280,displayHeight=280):
    if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in (x,y,displayWidth,displayHeight)) or min(displayWidth,displayHeight)<=0:raise ValueError('Некорректная точка изображения')
    scale=min(displayWidth/image.width,displayHeight/image.height)
    left=(displayWidth-image.width*scale)/2;top=(displayHeight-image.height*scale)/2
    if not left<=x<left+image.width*scale or not top<=y<top+image.height*scale:return None
    pixelX=int((x-left)/scale);pixelY=int((y-top)/scale)
    pixels=[]
    for row in range(max(0,pixelY-2),min(image.height,pixelY+3)):
        for col in range(max(0,pixelX-2),min(image.width,pixelX+3)):
            value=image.getpixel((col,row))
            if value[3]>=128:pixels.append(value[:3])
    if not pixels:raise ValueError('Выберите непрозрачную область изображения')
    rgb=tuple(round(sum(v[i] for v in pixels)/len(pixels)) for i in range(3))
    hexColor='#'+''.join(f'{v:02X}' for v in rgb)
    return dict(hex=hexColor,rgb=rgb,nearest=nearestColor(hexColor))


def cropReference(image,left,top,right,bottom):
    try:
        values=[float(str(v).replace(',','.')) for v in (left,top,right,bottom)]
    except (ValueError,TypeError):raise ValueError('Обрезка: введите проценты от 0 до 90') from None
    if any(not math.isfinite(v) or not 0<=v<=90 for v in values) or values[0]+values[2]>=95 or values[1]+values[3]>=95:raise ValueError('Оставьте хотя бы 5% ширины и высоты')
    box=(round(image.width*values[0]/100),round(image.height*values[1]/100),round(image.width*(1-values[2]/100)),round(image.height*(1-values[3]/100)))
    if box[2]<=box[0] or box[3]<=box[1]:raise ValueError('После обрезки не осталось изображения')
    return image.crop(box)


def removeBackground(image,hexColor,tolerance):
    if type(tolerance) is not int or not 0<=tolerance<=150:raise ValueError('Допуск фона: целое число от 0 до 150')
    rgb=convertHexToRgb(normalizeHexColor(hexColor))
    difference=ImageChops.difference(image.convert('RGB'),Image.new('RGB',image.size,rgb))
    red,green,blue=difference.split();distance=ImageChops.lighter(ImageChops.lighter(red,green),blue)
    eligible=distance.point(lambda v:255 if v<=tolerance else 0)
    padded=Image.new('L',(image.width+2,image.height+2),255);padded.paste(eligible,(1,1))
    ImageDraw.floodfill(padded,(0,0),128,thresh=0)
    mask=padded.crop((1,1,image.width+1,image.height+1)).point(lambda v:255 if v==128 else 0)
    output=image.copy();output.putalpha(ImageChops.subtract(image.getchannel('A'),mask))
    return output
