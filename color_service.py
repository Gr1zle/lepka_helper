import json
import re
import math
from decimal import Decimal, ROUND_HALF_UP
import itertools
import threading

from database import createColorMixture, getColorMixturesByUserId, deleteColorMixtureById

BASE_COLORS = [
    {"colorId": 1, "name": "Белый", "hex": "#FFFFFF"},
    {"colorId": 2, "name": "Чёрный", "hex": "#000000"},
    {"colorId": 3, "name": "Красный", "hex": "#FF3B30"},
    {"colorId": 4, "name": "Оранжевый", "hex": "#FF9500"},
    {"colorId": 5, "name": "Жёлтый", "hex": "#FFD60A"},
    {"colorId": 6, "name": "Зелёный", "hex": "#34C759"},
    {"colorId": 7, "name": "Голубой", "hex": "#5AC8FA"},
    {"colorId": 8, "name": "Синий", "hex": "#007AFF"},
    {"colorId": 9, "name": "Фиолетовый", "hex": "#AF52DE"},
    {"colorId": 10, "name": "Розовый", "hex": "#FF2D55"},
    {"colorId": 11, "name": "Коричневый", "hex": "#8B4513"},
    {"colorId": 12, "name": "Бежевый", "hex": "#F5DEB3"},
]


def validateHexColor(hexColor):
    if not isinstance(hexColor, str) or not hexColor:
        return False

    cleanHex = hexColor.strip()

    if not cleanHex.startswith("#"):
        cleanHex = f"#{cleanHex}"

    if len(cleanHex) != 7:
        return False

    return re.fullmatch(r'#[0-9A-Fa-f]{6}', cleanHex) is not None


def normalizeHexColor(hexColor):
    if not validateHexColor(hexColor):
        raise ValueError("Некорректный HEX-цвет")
    cleanHex = hexColor.strip().upper()

    if not cleanHex.startswith("#"):
        cleanHex = f"#{cleanHex}"

    return cleanHex


def convertHexToRgb(hexColor):
    cleanHex = normalizeHexColor(hexColor).replace("#", "")

    redValue = int(cleanHex[0:2], 16)
    greenValue = int(cleanHex[2:4], 16)
    blueValue = int(cleanHex[4:6], 16)

    return redValue, greenValue, blueValue


def clampColorValue(value):
    return max(0, min(255, int(round(value))))


def convertRgbToHex(redValue, greenValue, blueValue):
    return "#{:02X}{:02X}{:02X}".format(
        clampColorValue(redValue),
        clampColorValue(greenValue),
        clampColorValue(blueValue),
    )


def normalizeWeight(totalWeight):
    if totalWeight is None or totalWeight == '':
        return 100.0
    if isinstance(totalWeight, bool):
        raise ValueError("Введите положительный вес смеси")
    try:
        weight = float(str(totalWeight).replace(',', '.'))
    except (TypeError, ValueError):
        raise ValueError("Введите вес смеси числом") from None
    if not math.isfinite(weight) or weight < 0.01:
        raise ValueError("Вес должен быть конечным числом не меньше 0,01 г")
    units = int((Decimal(str(weight)) * 100).to_integral_value(rounding=ROUND_HALF_UP))
    return float(Decimal(units) / 100)


def allocatePercentUnits(proportions):
    # Проценты в десятых долях: 1000 единиц = 100%. Остаток не теряется.
    total = sum(proportions)
    rawUnits = [value / total * 1000 for value in proportions]
    units = [math.floor(value) for value in rawUnits]
    order = sorted(range(len(units)), key=lambda index: rawUnits[index] - units[index], reverse=True)
    for index in order[:1000 - sum(units)]:
        units[index] += 1
    return units


def normalizeProportion(value):
    if isinstance(value, bool):
        raise ValueError('Доля цвета должна быть числом от 0 до 100')
    try:
        value = float(str(value).replace(',', '.'))
    except (TypeError, ValueError):
        raise ValueError('Доля цвета должна быть числом от 0 до 100') from None
    if not math.isfinite(value) or not 0 <= value <= 100:
        raise ValueError('Доля цвета должна быть конечным числом от 0 до 100')
    return value


def normalizeSelectedColors(selectedColors, minimumCount=1):
    if not isinstance(selectedColors, list) or not minimumCount <= len(selectedColors) <= 5:
        raise ValueError(f"Выберите от {minimumCount} до 5 цветов")
    result = []
    seenIds = set()
    for item in selectedColors:
        if not isinstance(item, dict) or type(item.get('colorId')) is not int:
            raise ValueError("Выберите цвет из базовой палитры")
        base = next((color for color in BASE_COLORS if color['colorId'] == item['colorId']), None)
        if base is None or item['colorId'] in seenIds:
            raise ValueError("Цвета должны быть из палитры и не повторяться")
        hexValue = item.get('hex', base['hex'])
        if not isinstance(hexValue, str) or hexValue.upper() != base['hex']:
            raise ValueError("HEX не соответствует выбранному цвету палитры")
        seenIds.add(item['colorId'])
        value = normalizeProportion(item.get('proportion', 0))
        result.append({**base, 'proportion': value})
    if sum(item['proportion'] for item in result) <= 0:
        raise ValueError("Сумма долей должна быть больше нуля")
    units = allocatePercentUnits([item['proportion'] for item in result])
    for item, value in zip(result, units):
        item['proportion'] = value / 10
    return result


def _blendColors(selectedColors):
    total = sum(item['proportion'] for item in selectedColors)
    channels = [0.0, 0.0, 0.0]
    for item in selectedColors:
        for index, value in enumerate(convertHexToRgb(item['hex'])):
            channels[index] += value * item['proportion'] / total
    return convertRgbToHex(*channels)


def calculateMixedColor(selectedColors):
    if selectedColors == []:
        return "#FFFFFF"  # Пустая палитра предпросмотра.
    return _blendColors(normalizeSelectedColors(selectedColors))


def calculateRecipe(selectedColors, totalWeight):
    weight = normalizeWeight(totalWeight)
    if selectedColors == []:
        return []
    colors = normalizeSelectedColors(selectedColors)
    percentUnits = [int(round(item['proportion'] * 10)) for item in colors]
    weightUnits = int((Decimal(str(weight)) * 100).to_integral_value(rounding=ROUND_HALF_UP))
    gramUnits = [weightUnits * value // 1000 for value in percentUnits]
    order = sorted(range(len(colors)), key=lambda index: weightUnits * percentUnits[index] % 1000, reverse=True)
    for index in order[:weightUnits - sum(gramUnits)]:
        gramUnits[index] += 1
    return [{**{key: item[key] for key in ('colorId', 'name', 'hex')},
             'percent': item['proportion'], 'grams': float(Decimal(grams) / 100)}
            for item, grams in zip(colors, gramUnits)]


def saveColorMixture(userId, mixtureName, resultHex, totalWeight, recipeItems):
    name = (mixtureName or '').strip()
    if not 3 <= len(name) <= 80:
        raise ValueError("Название смеси должно содержать от 3 до 80 символов")
    if not isinstance(recipeItems, list):
        raise ValueError("Некорректный рецепт")
    selected = [dict(item, proportion=item.get('percent')) for item in recipeItems if isinstance(item, dict)]
    if len(selected) != len(recipeItems):
        raise ValueError("Некорректный рецепт")
    selected = normalizeSelectedColors(selected, minimumCount=2)
    weight = normalizeWeight(totalWeight)
    recipe = calculateRecipe(selected, weight)
    mixed = calculateMixedColor(selected)
    if not validateHexColor(resultHex) or normalizeHexColor(resultHex) != mixed:
        raise ValueError("Итоговый цвет не соответствует рецепту")
    for provided, expected in zip(recipeItems, recipe):
        try:
            grams = float(provided['grams'])
        except (KeyError, TypeError, ValueError):
            raise ValueError("Некорректная масса компонентов") from None
        if not math.isfinite(grams) or not math.isclose(grams, expected['grams'], abs_tol=0.005):
            raise ValueError("Масса компонентов не соответствует рецепту")
    return createColorMixture(userId, name, mixed, weight, json.dumps(recipe, ensure_ascii=False))


def deleteColorMixture(userId, mixtureId):
    return deleteColorMixtureById(userId, mixtureId)

def getUserColorMixtures(userId):
    mixtureItems = []
    for record in getColorMixturesByUserId(userId):
        corrupted = False
        try:
            recipe = json.loads(record['recipeJson'])
            if not isinstance(recipe, list) or not 2 <= len(recipe) <= 5:
                raise ValueError('Некорректный рецепт')
            required = {'colorId', 'name', 'hex', 'percent', 'grams'}
            if any(not isinstance(item, dict) or not required.issubset(item)
                   or not isinstance(item['name'], str)
                   or any(type(item[key]) not in (int, float) for key in ('percent', 'grams'))
                   for item in recipe):
                raise ValueError('Некорректные поля рецепта')
            normalizeSelectedColors([dict(item, proportion=item['percent']) for item in recipe], minimumCount=2)
            normalizeWeight(record['totalWeight'])
            if any(not math.isfinite(float(item['grams'])) or float(item['grams']) < 0 for item in recipe):
                raise ValueError('Некорректная масса')
        except (ValueError, TypeError, KeyError):
            recipe = []
            corrupted = True
        hexColor = record['resultHex']
        if not validateHexColor(hexColor):
            hexColor = '#808080'
            corrupted = True
        mixtureItems.append({'mixtureId': record['mixtureId'], 'mixtureName': record['mixtureName'],
            'resultHex': hexColor, 'totalWeight': record['totalWeight'], 'recipeItems': recipe,
            'recipeError': corrupted, 'createdAt': record['createdAt']})
    return mixtureItems


def calculateColorDistance(firstHex, secondHex):
    """
    Более точное сравнение цветов, чем обычная RGB-дистанция.
    Зелёный канал учитывается сильнее, потому что глаз лучше замечает отличия в зелёном.
    """
    firstRed, firstGreen, firstBlue = convertHexToRgb(firstHex)
    secondRed, secondGreen, secondBlue = convertHexToRgb(secondHex)

    redMean = (firstRed + secondRed) / 2

    redDifference = firstRed - secondRed
    greenDifference = firstGreen - secondGreen
    blueDifference = firstBlue - secondBlue

    return (
        (2 + redMean / 256) * redDifference * redDifference
        + 4 * greenDifference * greenDifference
        + (2 + (255 - redMean) / 256) * blueDifference * blueDifference
    ) ** 0.5


def generateProportionVariants(colorCount, step=5, minPercent=5):
    """
    Генерирует варианты процентов, сумма которых равна 100.

    Например для 2 цветов:
    5/95, 10/90, 15/85 ... 95/5

    Для 3 цветов:
    5/5/90, 5/10/85 и т.д.
    """
    if colorCount == 1:
        return [[100]]

    variants = []

    def buildVariant(currentVariant, remainingColors, remainingPercent):
        if remainingColors == 1:
            if remainingPercent >= minPercent and remainingPercent % step == 0:
                variants.append(currentVariant + [remainingPercent])
            return

        maxPercent = remainingPercent - minPercent * (remainingColors - 1)

        for percent in range(minPercent, maxPercent + 1, step):
            buildVariant(
                currentVariant + [percent],
                remainingColors - 1,
                remainingPercent - percent,
            )

    buildVariant([], colorCount, 100)

    return variants


_RECIPE_CANDIDATE_CACHE = None
_RECIPE_CANDIDATE_CACHE_LOCK = threading.Lock()
_RECIPE_RESULT_CACHE = {}


def _getRecipeCandidateCache():
    global _RECIPE_CANDIDATE_CACHE

    if _RECIPE_CANDIDATE_CACHE is not None:
        return _RECIPE_CANDIDATE_CACHE

    with _RECIPE_CANDIDATE_CACHE_LOCK:
        if _RECIPE_CANDIDATE_CACHE is not None:
            return _RECIPE_CANDIDATE_CACHE

        candidates = []

        for combinationSize in [1, 2, 3, 4]:
            for colorCombination in itertools.combinations(BASE_COLORS, combinationSize):
                colorCount = len(colorCombination)

                if colorCount == 4:
                    proportionVariants = generateProportionVariants(colorCount, step=10, minPercent=10)
                else:
                    proportionVariants = generateProportionVariants(colorCount, step=5, minPercent=5)

                for proportionVariant in proportionVariants:
                    selectedColors = []

                    for colorIndex, colorItem in enumerate(colorCombination):
                        selectedColors.append(
                            {
                                "colorId": colorItem["colorId"],
                                "name": colorItem["name"],
                                "hex": colorItem["hex"],
                                "proportion": proportionVariant[colorIndex],
                            }
                        )

                    resultHex = _blendColors(selectedColors)
                    resultRgb = convertHexToRgb(resultHex)
                    candidates.append((resultHex, resultRgb, selectedColors))

        _RECIPE_CANDIDATE_CACHE = candidates
        return _RECIPE_CANDIDATE_CACHE


def _calculateColorDistanceFromRgb(firstRgb, secondRgb):
    firstRed, firstGreen, firstBlue = firstRgb
    secondRed, secondGreen, secondBlue = secondRgb

    redMean = (firstRed + secondRed) / 2

    redDifference = firstRed - secondRed
    greenDifference = firstGreen - secondGreen
    blueDifference = firstBlue - secondBlue

    return (
        (2 + redMean / 256) * redDifference * redDifference
        + 4 * greenDifference * greenDifference
        + (2 + (255 - redMean) / 256) * blueDifference * blueDifference
    ) ** 0.5


def _copyRecipeResult(recipeResult):
    return {
        "targetHex": recipeResult["targetHex"],
        "resultHex": recipeResult["resultHex"],
        "distance": recipeResult["distance"],
        "selectedColors": [dict(colorItem) for colorItem in recipeResult["selectedColors"]],
        "recipeItems": [dict(recipeItem) for recipeItem in recipeResult["recipeItems"]],
    }

def findClosestRecipeForTargetColor(targetHex, totalWeight):
    normalizedTargetHex = normalizeHexColor(targetHex)

    if not validateHexColor(normalizedTargetHex):
        raise ValueError("Некорректный HEX-цвет")

    normalizedWeight = normalizeWeight(totalWeight)
    cacheKey = (normalizedTargetHex, normalizedWeight)

    cachedRecipe = _RECIPE_RESULT_CACHE.get(cacheKey)

    if cachedRecipe is not None:
        return _copyRecipeResult(cachedRecipe)

    targetRgb = convertHexToRgb(normalizedTargetHex)
    bestRecipe = None
    bestDistance = None
    bestResultHex = None

    for resultHex, resultRgb, selectedColors in _getRecipeCandidateCache():
        colorDistance = _calculateColorDistanceFromRgb(targetRgb, resultRgb)

        if bestDistance is None or colorDistance < bestDistance:
            bestDistance = colorDistance
            bestRecipe = selectedColors
            bestResultHex = resultHex

    recipeItems = calculateRecipe(bestRecipe, normalizedWeight)

    recipeResult = {
        "targetHex": normalizedTargetHex,
        "resultHex": bestResultHex,
        "distance": round(bestDistance, 2),
        "selectedColors": [dict(colorItem) for colorItem in bestRecipe],
        "recipeItems": recipeItems,
    }

    _RECIPE_RESULT_CACHE[cacheKey] = _copyRecipeResult(recipeResult)

    return recipeResult
