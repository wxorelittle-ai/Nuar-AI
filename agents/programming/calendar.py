"""Календарь поводов для программы заведения.

Курированный набор дат (гражданские, культурные, музыкальные, «барные»,
сезонные) с уклоном под вечерний бар/нуар. Считает конкретные даты для
заданного месяца, включая плавающие поводы (пятница 13-е, World Whisky Day,
последняя пятница месяца). Без внешних ключей и сети.
"""
from __future__ import annotations

import calendar as _cal
from dataclasses import dataclass, asdict
from datetime import date, timedelta

WEEKDAYS_RU = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]


@dataclass
class Occasion:
    title: str
    date: str                 # ISO YYYY-MM-DD
    kind: str                 # civic | cultural | music | bar | cinema | seasonal
    note: str = ""            # чем интересно
    fit: str = ""             # как ложится на вечерний бар
    lead_days: int = 7        # за сколько дней начинать тизерить
    festive: bool = True      # уместен ли развлекательный формат

    @property
    def weekday(self) -> str:
        y, m, d = (int(x) for x in self.date.split("-"))
        return WEEKDAYS_RU[date(y, m, d).weekday()]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["weekday"] = self.weekday
        return d


# Фиксированные поводы: (месяц, день, title, kind, note, fit, lead_days, festive)
FIXED = [
    (1, 1, "Новый год", "civic", "Главная ночь года", "Уже позади — фокус на постпраздничные форматы", 14, True),
    (1, 14, "Старый Новый год", "cultural", "Уютный неофициальный повод", "Камерный вечер «второй НГ» с джазом", 7, True),
    (1, 25, "Татьянин день / День студента", "cultural", "Молодая аудитория", "Тематический вечер, но следить за средним чеком", 7, True),
    (2, 6, "День бармена", "bar", "Профессиональный праздник бара", "Гость-бартендер, авторские коктейли, шоу за стойкой", 10, True),
    (2, 14, "День святого Валентина", "civic", "Пары, романтика", "Сет для двоих, тёмный свет, живая музыка", 12, True),
    (2, 23, "День защитника Отечества", "civic", "Мужская аудитория", "Виски/крафт-вечер, сигарный сет (без табака в помещении)", 10, True),
    (3, 8, "Международный женский день", "civic", "Женская аудитория", "Игристое, парфюм-коллаб, цветочная подача коктейлей", 12, True),
    (3, 17, "День святого Патрика", "cultural", "Мировой «барный» праздник", "Ирландская тема, стауты, живая музыка", 10, True),
    (4, 30, "Международный день джаза", "music", "Праздник ЮНЕСКО", "Профильный повод для джаз-бара: джем, приглашённое трио", 14, True),
    (5, 1, "Праздник весны и труда", "civic", "Длинные выходные", "Старт сезона террасы/вечерних выходных", 7, True),
    (5, 9, "День Победы", "civic", "Памятная дата", "Не развлекательный формат: сдержанно, уместен жест памяти", 7, False),
    (5, 13, "Всемирный день коктейля", "bar", "Профильный праздник коктейльной культуры",
     "Авторская карта, гость-бартендер, история коктейля", 10, True),
    (6, 1, "Сезон летних вечеров", "seasonal", "Тёплые вечера и поздний закат",
     "Поздние сеты, лёгкие коктейли, веранда", 7, True),
    (6, 12, "День России", "civic", "Длинные выходные", "Летний вечерний формат", 7, True),
    (6, 21, "Летнее солнцестояние — самая короткая ночь", "seasonal", "Самая короткая ночь года",
     "Ночной джем до рассвета, «белая ночь» в тёмном баре", 10, True),
    (7, 1, "Разгар лета", "seasonal", "Пик отпусков — по будням город пустеет",
     "Ставка на выходные, вечерние сеты, гости из других городов", 7, True),
    (7, 19, "Международный день джаза в городе", "music", "Летний музыкальный сезон",
     "Open-air джем или вечер приглашённого состава", 10, True),
    (8, 27, "День российского кино", "cinema", "Профильный киноповод",
     "Кинонуар-вечер, коктейли по фильмам", 10, True),
    (9, 1, "Бархатный сезон", "seasonal", "Возвращение вечерней публики", "Рестарт программы после лета, новое сезонное меню", 10, True),
    (10, 1, "Международный день музыки", "music", "Профильный музыкальный повод", "Живой концерт, новый резидент-музыкант", 10, True),
    (10, 31, "Хэллоуин", "cultural", "Атмосферный праздник — идеален для нуара", "Нуар-детектив, мистерия, тёмные коктейли, дресс-код", 14, True),
    (11, 4, "День народного единства", "civic", "Длинные выходные", "Ноябрьский вечерний формат", 7, True),
    (11, 1, "Тёмные вечера — пик нуара", "seasonal", "Самый «нуарный» сезон года", "Серия камерных вечеров: джаз, детектив, кино", 7, True),
    (11, 15, "Старт корпоративного сезона", "seasonal", "Ноябрь–декабрь — бронирования", "Пакеты для компаний, закрытые вечера", 21, True),
    (12, 28, "Годовщина рождения кино", "cinema", "Первый сеанс братьев Люмьер (1895)", "Кинонуар-вечер с коктейлями по фильмам", 10, True),
    (12, 31, "Новый год", "civic", "Главная ночь года", "Новогодняя программа, депозит, живая музыка", 21, True),
]


def _friday_13ths(year: int, month: int) -> list[Occasion]:
    try:
        d = date(year, month, 13)
    except ValueError:
        return []
    if d.weekday() == 4:  # пятница
        return [Occasion("Пятница, 13-е", d.isoformat(), "cultural",
                         "Суеверный повод — идеален для нуар/мистики",
                         "Нуар-детектив, «13 улик», мрачные коктейли", lead_days=10)]
    return []


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date | None:
    """n-й (1-based) день недели месяца, например 3-я суббота мая."""
    days = [date(year, month, d) for d in range(1, _cal.monthrange(year, month)[1] + 1)]
    matches = [d for d in days if d.weekday() == weekday]
    return matches[n - 1] if len(matches) >= n else None


def _first_friday_jam(year: int, month: int) -> Occasion:
    d = _nth_weekday(year, month, 4, 1)
    return Occasion("Джем-сейшен — первая пятница месяца", d.isoformat(), "music",
                    "Регулярный музыкальный якорь", "Открытый джем: резиденты + гости за инструментами",
                    lead_days=5)


def _last_friday(year: int, month: int) -> Occasion:
    last_day = _cal.monthrange(year, month)[1]
    d = date(year, month, last_day)
    while d.weekday() != 4:
        d -= timedelta(days=1)
    return Occasion("Afterwork — последняя пятница месяца", d.isoformat(), "bar",
                    "Регулярный якорный вечер", "Живой сет, спецы на коктейли до определённого часа",
                    lead_days=5)


def _world_whisky_day(year: int, month: int) -> list[Occasion]:
    """Третья суббота мая."""
    if month != 5:
        return []
    d = _nth_weekday(year, 5, 5, 3)
    if not d:
        return []
    return [Occasion("World Whisky Day", d.isoformat(), "bar",
                     "Мировой день виски", "Виски-дегустация, коллаб с локальной винокурней",
                     lead_days=10)]


def _world_gin_day(year: int, month: int) -> list[Occasion]:
    """Вторая суббота июня."""
    if month != 6:
        return []
    d = _nth_weekday(year, 6, 5, 2)
    if not d:
        return []
    return [Occasion("World Gin Day", d.isoformat(), "bar",
                     "Мировой день джина", "Джин-тоник бар, коллаб с крафтовой винокурней",
                     lead_days=10)]


def _valid(y: int, m: int, d: int) -> bool:
    try:
        date(y, m, d)
        return True
    except ValueError:
        return False


def occasions_for(year: int, month: int) -> list[Occasion]:
    """Все поводы месяца, отсортированные по дате."""
    out: list[Occasion] = []
    for mo, day, title, kind, note, fit, lead, festive in FIXED:
        if mo == month and _valid(year, month, day):
            out.append(Occasion(title, date(year, month, day).isoformat(),
                                 kind, note, fit, lead, festive))
    out += _friday_13ths(year, month)
    out += _world_whisky_day(year, month)
    out += _world_gin_day(year, month)
    out.append(_first_friday_jam(year, month))
    out.append(_last_friday(year, month))
    return sorted(out, key=lambda o: o.date)
