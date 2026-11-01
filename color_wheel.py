"""Кешируемое изображение круга и выбор оттенка по координатам."""
import base64
import colorsys
import math
import struct
import zlib
from functools import lru_cache

def rgbToHex(redValue, greenValue, blueValue):
    return "#{:02X}{:02X}{:02X}".format(
        int(round(redValue * 255)),
        int(round(greenValue * 255)),
        int(round(blueValue * 255)),
    )

def getColorWheelHexAtPoint(xPosition, yPosition, wheelSize):
    center = wheelSize / 2
    dx = xPosition - center
    dy = center - yPosition
    radius = math.sqrt(dx * dx + dy * dy)
    maxRadius = wheelSize / 2

    if radius > maxRadius:
        return None

    saturation = min(1.0, radius / maxRadius)
    hue = (math.atan2(dy, dx) / (2 * math.pi)) % 1.0

    if saturation < 0.04:
        return "#FFFFFF"

    redValue, greenValue, blueValue = colorsys.hsv_to_rgb(hue, saturation, 1.0)
    return rgbToHex(redValue, greenValue, blueValue)

def createPngChunk(chunkType, chunkData):
    chunkHeader = struct.pack(">I", len(chunkData)) + chunkType + chunkData
    checksum = zlib.crc32(chunkHeader[4:]) & 0xFFFFFFFF
    return chunkHeader + struct.pack(">I", checksum)

@lru_cache(maxsize=2)
def createColorWheelBase64(wheelSize):
    rawRows = []

    for yPosition in range(wheelSize):
        rowBytes = bytearray()
        rowBytes.append(0)

        for xPosition in range(wheelSize):
            center = wheelSize / 2
            dx = xPosition - center
            dy = center - yPosition
            radius = math.sqrt(dx * dx + dy * dy)
            maxRadius = wheelSize / 2 - 1

            if radius > maxRadius:
                rowBytes.extend([255, 255, 255, 0])
                continue

            saturation = min(1.0, radius / maxRadius)
            hue = (math.atan2(dy, dx) / (2 * math.pi)) % 1.0
            redValue, greenValue, blueValue = colorsys.hsv_to_rgb(hue, saturation, 1.0)

            rowBytes.extend([
                int(round(redValue * 255)),
                int(round(greenValue * 255)),
                int(round(blueValue * 255)),
                255,
            ])

        rawRows.append(bytes(rowBytes))

    pngHeader = b"\x89PNG\r\n\x1a\n"
    imageHeader = struct.pack(">IIBBBBB", wheelSize, wheelSize, 8, 6, 0, 0, 0)
    imageData = zlib.compress(b"".join(rawRows), 9)
    pngBytes = (
        pngHeader
        + createPngChunk(b"IHDR", imageHeader)
        + createPngChunk(b"IDAT", imageData)
        + createPngChunk(b"IEND", b"")
    )

    return base64.b64encode(pngBytes).decode("ascii")

