"""Простые расчёты объёма/массы и таймер на монотонных часах."""
import math
import time


def positiveNumber(value, name, maximum=1_000_000):
    try:
        if isinstance(value, bool):
            raise ValueError()
        number = float(str(value).replace(',', '.'))
        if not math.isfinite(number) or not 0 < number <= maximum:
            raise ValueError()
        return number
    except (TypeError, ValueError, OverflowError):
        raise ValueError(f'{name}: введите положительное число не больше {maximum:g}') from None


def calculateClay(shape, dimensions, density, reserve=10):
    density = positiveNumber(density, 'Плотность', 10)
    try:
        reserve = float(str(reserve).replace(',', '.'))
    except (ValueError, TypeError):
        raise ValueError('Запас: введите число от 0 до 100') from None
    if not math.isfinite(reserve) or not 0 <= reserve <= 100:
        raise ValueError('Запас: введите число от 0 до 100')
    sizes = [positiveNumber(value, 'Объём' if shape == 'Объём' else 'Размер',
                            1_000_000 if shape == 'Объём' else 10000) for value in dimensions]
    if shape == 'Объём' and len(sizes) == 1:
        volume = sizes[0]
    elif shape == 'Брусок' and len(sizes) == 3:
        volume = math.prod(sizes)
    elif shape == 'Шар' and len(sizes) == 1:
        volume = math.pi * sizes[0]**3 / 6  # Диаметр в сантиметрах.
    elif shape == 'Цилиндр' and len(sizes) == 2:
        volume = math.pi * sizes[0]**2 / 4 * sizes[1]
    else:
        raise ValueError('Выберите форму и заполните её размеры')
    if volume > 1_000_000:
        raise ValueError('Объём должен быть не больше 1 000 000 см³')
    mass = volume * density
    return {'volume': volume, 'mass': mass, 'withReserve': mass * (1 + reserve / 100)}


class ClayTimer:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.duration = 300.0
        self.remaining = self.duration
        self.deadline = None

    def seconds(self):
        return max(0, math.ceil(self.deadline-self.clock() if self.deadline is not None else self.remaining))

    @property
    def running(self):
        return self.deadline is not None and self.seconds() > 0

    def start(self, minutes=None):
        if minutes is not None:
            self.duration = positiveNumber(minutes, 'Минуты', 1440) * 60
            self.remaining = self.duration
            self.deadline = None
        if self.seconds() == 0:
            self.remaining = self.duration
        if not self.running:
            self.deadline = self.clock() + self.remaining

    def pause(self):
        if self.deadline is not None:
            self.remaining = max(0, self.deadline-self.clock())
            self.deadline = None

    def reset(self):
        self.deadline = None
        self.remaining = self.duration

    def display(self):
        seconds = self.seconds()
        return f'{seconds//3600:02d}:{seconds//60%60:02d}:{seconds%60:02d}'
