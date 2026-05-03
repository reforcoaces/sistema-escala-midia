"""Datas de culto (quinta e domingo), mesclagem com eventos extras e algoritmo de escala."""
from __future__ import annotations

import calendar
import datetime as dt
from collections import defaultdict
from typing import Any, Iterable

AREAS = [
    "PROJEÇÃO",
    "OBS",
    "FILMAGEM",
    "INSTAGRAM",
    "FOTOGRAFIA",
    "ILUMINAÇÃO",
    "SONOPLASTIA",
    "RESPONSAVEL",
]

WEEKDAY_PT = (
    "Segunda-feira",
    "Terça-feira",
    "Quarta-feira",
    "Quinta-feira",
    "Sexta-feira",
    "Sábado",
    "Domingo",
)


def regular_time_range_for_date(d: dt.date) -> str | None:
    """Horários fixos dos cultos regulares (quinta = 3, domingo = 6; segunda = 0)."""
    wd = d.weekday()
    if wd == 3:
        return "20h às 21h30"
    if wd == 6:
        return "18h às 20h"
    return None


def default_label_for_date(d: dt.date) -> str:
    wd = d.weekday()
    if wd == 3:
        return "Quinta-feira — culto"
    if wd == 6:
        return "Domingo — culto"
    return f"{WEEKDAY_PT[wd]} — evento"


def first_sunday_of_month(year: int, month: int) -> dt.date:
    """Primeiro domingo do mês (Santa Ceia): regra de idade não se aplica neste culto."""
    for day in range(1, 8):
        d = dt.date(year, month, day)
        if d.weekday() == 6:
            return d
    raise ValueError("mês sem domingo nos primeiros 7 dias (impossível)")


def age_on_date(birth: dt.date, on: dt.date) -> int:
    """Idade em anos completos na data `on`."""
    y = on.year - birth.year
    if (on.month, on.day) < (birth.month, birth.day):
        y -= 1
    return y


def teen_sunday_escala_forbidden(birth_iso: str | None, event_iso: str) -> bool:
    """
    True se o voluntário (≤15 anos) não pode ser escalado nesta data:
    domingo que não é o 1º do mês (1º = Santa Ceia, exceção).
    Sem data de nascimento cadastrada → não bloqueia.
    """
    if not birth_iso:
        return False
    birth = dt.date.fromisoformat(birth_iso)
    on = dt.date.fromisoformat(event_iso)
    if on.weekday() != 6:
        return False
    if on == first_sunday_of_month(on.year, on.month):
        return False
    return age_on_date(birth, on) <= 15


def dates_in_month_with_weekdays(
    year: int, month: int, weekdays: tuple[int, ...]
) -> list[dt.date]:
    """Datas do mês cujo weekday está em `weekdays` (0=seg … 6=dom, como date.weekday())."""
    want = frozenset(weekdays)
    _, last = calendar.monthrange(year, month)
    out: list[dt.date] = []
    for day in range(1, last + 1):
        d = dt.date(year, month, day)
        if d.weekday() in want:
            out.append(d)
    return out


def thursday_sunday_dates(year: int, month: int) -> list[dt.date]:
    return dates_in_month_with_weekdays(year, month, (3, 6))


def build_month_events(
    year: int,
    month: int,
    extras: Iterable[tuple[str, str | None, str | None]],
) -> list[dict[str, Any]]:
    """
    Retorna lista ordenada de dicts: date, label, time_range (str | None), is_regular.

    extras: (event_date_iso, label, event_time) — event_time texto livre (ex.: 19h às 21h).
    """
    reg_dates = {x.isoformat() for x in thursday_sunday_dates(year, month)}
    base: dict[str, dict[str, Any]] = {}

    for d in thursday_sunday_dates(year, month):
        iso = d.isoformat()
        base[iso] = {
            "date": iso,
            "label": default_label_for_date(d),
            "time_range": regular_time_range_for_date(d),
            "is_regular": True,
        }

    for event_date_iso, label, event_time in extras:
        d = dt.date.fromisoformat(event_date_iso)
        reg_tr = regular_time_range_for_date(d)
        et = (event_time or "").strip() or None

        if label:
            prev = base.get(event_date_iso)
            tr = et or (prev.get("time_range") if prev else None) or reg_tr
            base[event_date_iso] = {
                "date": event_date_iso,
                "label": label,
                "time_range": tr,
                "is_regular": event_date_iso in reg_dates,
            }
        elif event_date_iso not in base:
            base[event_date_iso] = {
                "date": event_date_iso,
                "label": default_label_for_date(d),
                "time_range": et or reg_tr,
                "is_regular": False,
            }

    out = sorted(base.values(), key=lambda x: x["date"])
    for item in out:
        item["is_regular"] = item["date"] in reg_dates
    return out


def assign_greedy_fair(
    event_dates: list[str],
    areas: list[str],
    volunteer_areas: dict[int, set[str]],
    availability: dict[int, dict[str, bool]],
    volunteer_birth: dict[int, str | None] | None = None,
) -> dict[tuple[str, str], int | None]:
    """
    Para cada (data, área), escolhe um voluntário apto, disponível,
    ainda não escalado nesse culto, priorizando quem tem menos escalas no mês.

    volunteer_birth: id -> data de nascimento ISO (opcional). Menores de 16 não entram
    em domingos exceto o 1º domingo do mês (Santa Ceia).
    """
    births = volunteer_birth or {}
    counts: dict[int, int] = defaultdict(int)
    assigned_same_day: dict[str, set[int]] = defaultdict(set)
    result: dict[tuple[str, str], int | None] = {}

    for event_date in event_dates:
        already = assigned_same_day[event_date]
        for area in areas:
            candidates: list[int] = []
            for vid, apt in volunteer_areas.items():
                if area not in apt:
                    continue
                av = availability.get(vid, {}).get(event_date)
                if av is False:
                    continue
                if av is None:
                    continue
                if vid in already:
                    continue
                if teen_sunday_escala_forbidden(births.get(vid), event_date):
                    continue
                candidates.append(vid)

            candidates.sort(key=lambda v: (counts[v], v))
            chosen = candidates[0] if candidates else None
            result[(event_date, area)] = chosen
            if chosen is not None:
                counts[chosen] += 1
                already.add(chosen)

    return result
