import json
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
    if not hexColor:
        return False

    cleanHex = hexColor.strip()

    if not cleanHex.startswith("#"):
        cleanHex = f"#{cleanHex}"

    if len(cleanHex) != 7:
        return False

    try:
        int(cleanHex[1:], 16)
    except ValueError:
        return False

    return True


def normalizeHexColor(hexColor):
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


def calculateMixedColor(selectedColors):
    if len(selectedColors) == 0:
        return "#FFFFFF"

    totalProportion = sum(colorItem.get("proportion", 0) for colorItem in selectedColors)

    if totalProportion <= 0:
        return "#FFFFFF"

    redSum = 0
    greenSum = 0
    blueSum = 0

    for colorItem in selectedColors:
        redValue, greenValue, blueValue = convertHexToRgb(colorItem["hex"])
        colorWeight = colorItem.get("proportion", 0) / totalProportion

        redSum += redValue * colorWeight
        greenSum += greenValue * colorWeight
        blueSum += blueValue * colorWeight

    return convertRgbToHex(redSum, greenSum, blueSum)


def calculateRecipe(selectedColors, totalWeight):
    totalProportion = sum(colorItem.get("proportion", 0) for colorItem in selectedColors)

    if totalProportion <= 0:
        return []

    recipeItems = []

    for colorItem in selectedColors:
        normalizedPercent = colorItem.get("proportion", 0) / totalProportion * 100
        colorWeight = totalWeight * normalizedPercent / 100

        recipeItems.append(
            {
                "colorId": colorItem["colorId"],
                "name": colorItem["name"],
                "hex": colorItem["hex"],
                "percent": round(normalizedPercent, 1),
                "grams": round(colorWeight, 1),
            }
        )

    return recipeItems


def saveColorMixture(userId, mixtureName, resultHex, totalWeight, recipeItems):
    recipeJson = json.dumps(recipeItems, ensure_ascii=False)

    return createColorMixture(
        userId,
        mixtureName,
        resultHex,
        totalWeight,
        recipeJson,
    )


def deleteColorMixture(userId, mixtureId):
    return deleteColorMixtureById(userId, mixtureId)

def getUserColorMixtures(userId):
    mixtureRecords = getColorMixturesByUserId(userId)
    mixtureItems = []

    for mixtureRecord in mixtureRecords:
        mixtureItems.append(
            {
                "mixtureId": mixtureRecord["mixtureId"],
                "mixtureName": mixtureRecord["mixtureName"],
                "resultHex": mixtureRecord["resultHex"],
                "totalWeight": mixtureRecord["totalWeight"],
                "recipeItems": json.loads(mixtureRecord["recipeJson"]),
                "createdAt": mixtureRecord["createdAt"],
            }
        )

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

                    resultHex = calculateMixedColor(selectedColors)
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

    normalizedWeight = round(float(totalWeight), 2)
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

    recipeItems = calculateRecipe(bestRecipe, totalWeight)

    recipeResult = {
        "targetHex": normalizedTargetHex,
        "resultHex": bestResultHex,
        "distance": round(bestDistance, 2),
        "selectedColors": [dict(colorItem) for colorItem in bestRecipe],
        "recipeItems": recipeItems,
    }

    _RECIPE_RESULT_CACHE[cacheKey] = _copyRecipeResult(recipeResult)

    return recipeResult
