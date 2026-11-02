"""PNG-рецепт: одинаковая кириллица на всех ОС благодаря включённому шрифту."""
from io import BytesIO
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, PngImagePlugin

from color_service import calculateMixedColor, calculateRecipe, normalizeSelectedColors, normalizeWeight


def createRecipePng(mixtureName, selectedColors, totalWeight, calibration=None, languageCode='ru'):
    en=languageCode=='en'
    from interface_catalog import english
    colors = normalizeSelectedColors(selectedColors, minimumCount=2)
    weight = normalizeWeight(totalWeight)
    recipe = calculateRecipe(colors, weight)
    resultHex = calculateMixedColor(colors)
    lengths=None
    if calibration is not None:
        from clay_tools import recipeLengths
        lengths=recipeLengths(recipe,*calibration)
    name = ' '.join((mixtureName or '').split()) or ('My mixture' if en else 'Моя смесь')
    if not 1 <= len(name) <= 80:
        raise ValueError('Название должно быть не длиннее 80 символов')
    fontPath = Path(__file__).resolve().parent / 'assets' / 'fonts' / 'DejaVuSans.ttf'
    titleFont = ImageFont.truetype(str(fontPath), 34)
    font = ImageFont.truetype(str(fontPath), 24)
    smallFont = ImageFont.truetype(str(fontPath), 20)
    lines = ['']
    for character in name:
        if font.getlength(lines[-1] + character) > 900:
            lines.append(character)
        else:
            lines[-1] += character
    offset = max(0, 100 + len(lines) * 30 - 160)
    canvas = Image.new('RGB', (1000, 420 + 75 * len(recipe) + offset), '#FAFAFC')
    draw = ImageDraw.Draw(canvas)
    draw.text((40, 25), ('Clay Companion · Mixture recipe' if en else 'Lepka Helper · Рецепт смеси'), font=titleFont, fill='#252535')
    draw.multiline_text((40, 85), '\n'.join(lines), font=font, fill='#252535', spacing=5)
    draw.rounded_rectangle((40, 160 + offset, 170, 270 + offset), radius=18, fill=resultHex, outline='#777777', width=2)
    draw.text((195, 175 + offset), (f'Result: {resultHex}' if en else f'Результат: {resultHex}'), font=font, fill='#252535')
    draw.text((195, 220 + offset), (f'Total weight: {weight:g} g' if en else f'Общий вес: {weight:g} г'), font=font, fill='#252535')
    for index, item in enumerate(recipe):
        top = 295 + offset + index * 75
        draw.rounded_rectangle((40, top, 88, top + 48), radius=9, fill=item['hex'], outline='#777777')
        draw.text((110, top + 8), english(item['name']) if en else item['name'], font=font, fill='#252535')
        draw.text((510, top + 8), f"{item['percent']:g}%", font=font, fill='#252535')
        draw.text((690, top + 8), f"{item['grams']:g} "+('g' if en else 'г'), font=font, fill='#252535')
        if lengths:draw.text((830,top+8),f"{lengths[index]['centimeters']:g} "+('cm' if en else 'см'),font=smallFont,fill='#252535')
    footer = 320 + offset + len(recipe) * 75
    draw.text((40, footer), ('RGB preview is approximate; actual clay may differ.' if en else 'RGB-предпросмотр приблизительный: реальный пластилин может отличаться.'),
              font=smallFont, fill='#555566')
    if calibration:
        draw.text((40,footer+30),(f'Bar: {calibration[0]} g / {calibration[1]} cm. Approximate lengths.' if en else f'Брусок: {calibration[0]} г / {calibration[1]} см. Длины приблизительные.'),font=smallFont,fill='#555566')
    meta = PngImagePlugin.PngInfo()
    meta.add_text('Recipe', json.dumps({'name': name, 'resultHex': resultHex,
                                      'totalWeight': weight, 'items': recipe}, ensure_ascii=False))
    result = BytesIO()
    canvas.save(result, format='PNG', pnginfo=meta)
    return result.getvalue()


def createRecipePdf(mixtureName,selectedColors,totalWeight,calibration=None,languageCode='ru'):
    # Render the bundled Cyrillic font before writing PDF: no platform font substitution.
    png=createRecipePng(mixtureName,selectedColors,totalWeight,calibration,languageCode)
    with Image.open(BytesIO(png)) as image:
        image=image.convert('RGB');image.thumbnail((1120,1500))
        page=Image.new('RGB',(1240,1754),'white');page.paste(image,((1240-image.width)//2,70))
    output=BytesIO();page.save(output,format='PDF',resolution=150,title='Clay Companion - mixture recipe' if languageCode=='en' else 'Lepka Helper — рецепт смеси')
    return output.getvalue()
