"""Datas de culto (quinta e domingo), mesclagem com eventos extras e algoritmo de escala."""
from __future__ import annotations

import calendar
import datetime as dt
from collections import defaultdict
from typing import Any, Iterable

# Ordem = prioridade na geração automática quando faltam pessoas no mesmo culto
# (cada voluntário no máximo uma função por data): 1 Responsável … 8 Filmagem.
AREAS = [
    "RESPONSAVEL",
    "SONOPLASTIA",
    "ILUMINAÇÃO",
    "PROJEÇÃO",
    "INSTAGRAM",
    "FOTOGRAFIA",
    "OBS",
    "FILMAGEM",
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


def _candidates_for_slot(
    event_date: str,
    area: str,
    volunteer_areas: dict[int, set[str]],
    availability: dict[int, dict[str, bool]],
    births: dict[int, str | None],
    already: set[int],
) -> list[int]:
    """Voluntários aptos, disponíveis nesta data, ainda não usados neste culto, sem bloqueio de idade."""
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
    return candidates


def _pick_fairest(candidates: list[int], counts: dict[int, int]) -> int | None:
    if not candidates:
        return None
    candidates.sort(key=lambda v: (counts[v], v))
    return candidates[0]


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
    A ordem dos itens em `areas` define a prioridade de cobertura por culto
    (áreas no início da lista competem primeiro pelos voluntários do dia).

    Se RESPONSAVEL ficar vazio mas existir alguém apto a RESPONSAVEL já escalado
    noutra função (área de menor prioridade), promove essa pessoa a RESPONSAVEL
    e tenta repreencher a vaga libertada (prioridade ao desfazer da área menos importante).

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
            candidates = _candidates_for_slot(
                event_date,
                area,
                volunteer_areas,
                availability,
                births,
                already,
            )
            chosen = _pick_fairest(candidates, counts)
            result[(event_date, area)] = chosen
            if chosen is not None:
                counts[chosen] += 1
                already.add(chosen)

    # Garantir RESPONSAVEL (prioridade 1) se ainda houver apto escalado só mais abaixo
    if not areas:
        return result
    resp_area = areas[0]
    if resp_area != "RESPONSAVEL":
        return result

    lower = areas[1:]
    for event_date in event_dates:
        if result.get((event_date, resp_area)) is not None:
            continue

        promoted_vid: int | None = None
        promoted_from: str | None = None
        for area in reversed(lower):
            vid = result.get((event_date, area))
            if vid is None:
                continue
            if resp_area not in volunteer_areas.get(vid, set()):
                continue
            promoted_vid = vid
            promoted_from = area
            break

        if promoted_vid is None or promoted_from is None:
            continue

        result[(event_date, resp_area)] = promoted_vid
        result[(event_date, promoted_from)] = None

        already_on_day = {
            v
            for a in areas
            for v in [result.get((event_date, a))]
            if v is not None
        }
        refill = _pick_fairest(
            _candidates_for_slot(
                event_date,
                promoted_from,
                volunteer_areas,
                availability,
                births,
                already_on_day,
            ),
            counts,
        )
        result[(event_date, promoted_from)] = refill
        if refill is not None:
            counts[refill] += 1

    return result


def detect_no_worship_day_alerts(
    event_dates: list[str],
    areas: list[str],
    assignments: dict[str, dict[str, int | None]],
    availability: dict[int, dict[str, bool]],
    volunteer_names: dict[int, str],
) -> list[dict[str, Any]]:
    """
    Voluntários que, na escala do mês, não ficam com nenhum culto só para cultuar.

    - ``all_events``: escalada em todos os cultos do mês (qualquer função conta).
    - ``all_available``: escalada em todo dia em que marcou disponibilidade explícita
      (ex.: só domingo disponível e escalada em todos os domingos).

    Apenas informativo; não deve bloquear escalação automática ou manual.
    """
    if not event_dates:
        return []
    event_set = frozenset(event_dates)

    assigned_by: dict[int, set[str]] = defaultdict(set)
    for ed in event_dates:
        row = assignments.get(ed) or {}
        for area in areas:
            vid = row.get(area)
            if vid is not None:
                assigned_by[int(vid)].add(ed)

    alerts: list[dict[str, Any]] = []
    for vid, assigned_dates in assigned_by.items():
        name = volunteer_names.get(vid) or f"#{vid}"
        if assigned_dates >= event_set:
            n = len(event_dates)
            alerts.append(
                {
                    "volunteer_id": vid,
                    "name": name,
                    "kind": "all_events",
                    "detail": (
                        f"Escalada em todos os {n} cultos do mês — "
                        "nenhum dia só para cultuar nesta escala."
                    ),
                }
            )
            continue
        avail_dates = {
            d for d in event_dates if availability.get(vid, {}).get(d) is True
        }
        if avail_dates and avail_dates <= assigned_dates:
            n = len(avail_dates)
            alerts.append(
                {
                    "volunteer_id": vid,
                    "name": name,
                    "kind": "all_available",
                    "detail": (
                        f"Escalada em todos os {n} dia(s) em que marcou disponibilidade — "
                        "vale garantir outro dia para cultuar."
                    ),
                }
            )

    alerts.sort(key=lambda x: (x["name"] or "").lower())
    return alerts


# Status de presença no culto (acompanhamento — separado da escala).
ATTENDANCE_STATUSES = (
    "cultou",
    "servindo",
    "ausencia_justificada",
    "ausente",
)

ATTENDANCE_STATUS_LABELS = {
    "cultou": "Cultou",
    "servindo": "Servindo",
    "ausencia_justificada": "Ausência justificada",
    "ausente": "Ausente",
}


def summarize_attendance_statuses(statuses: Iterable[str]) -> dict[str, int]:
    """Contagens por status; chaves alinhadas a ATTENDANCE_STATUSES."""
    out = {s: 0 for s in ATTENDANCE_STATUSES}
    for st in statuses:
        if st in out:
            out[st] += 1
    return out


def detect_attendance_fitness_alerts(
    volunteers: list[dict[str, Any]],
    attendance_rows: list[dict[str, Any]],
    *,
    as_of: dt.date | None = None,
) -> list[dict[str, Any]]:
    """
    Avalia se cada voluntário tem histórico de cultuar (status ``cultou``).

    Registros em ``attendance_rows``: volunteer_id, event_date (ISO), status.

    Retorna alertas informativos (não bloqueiam):
    - ``no_worship_2m``: nos últimos ~60 dias não cultuou nenhum dia (mas há registros).
    - ``no_worship_1m``: nos últimos ~30 dias não cultuou.
    - ``no_records``: sem nenhum registro de acompanhamento no período de 60 dias
      (só se o acompanhamento já estiver em uso).
    """
    today = as_of or dt.date.today()
    d30 = (today - dt.timedelta(days=30)).isoformat()
    d60 = (today - dt.timedelta(days=60)).isoformat()
    today_iso = today.isoformat()

    by_vol: dict[int, list[dict[str, Any]]] = defaultdict(list)
    any_in_window = False
    for r in attendance_rows:
        ed = r.get("event_date") or ""
        if d60 <= ed <= today_iso:
            any_in_window = True
            by_vol[int(r["volunteer_id"])].append(r)

    alerts: list[dict[str, Any]] = []
    for v in volunteers:
        vid = int(v["id"])
        name = v.get("name") or f"#{vid}"
        rows = by_vol.get(vid, [])
        if not rows:
            if any_in_window:
                alerts.append(
                    {
                        "volunteer_id": vid,
                        "name": name,
                        "kind": "no_records",
                        "window_days": 60,
                        "cultou_count": 0,
                        "detail": (
                            "Sem registro de acompanhamento nos últimos 2 meses — "
                            "confirma se a pessoa está cultuando antes de escalar."
                        ),
                    }
                )
            continue

        cultou_60 = sum(1 for r in rows if r.get("status") == "cultou")
        rows_30 = [r for r in rows if (r.get("event_date") or "") >= d30]
        cultou_30 = sum(1 for r in rows_30 if r.get("status") == "cultou")

        if cultou_60 == 0:
            alerts.append(
                {
                    "volunteer_id": vid,
                    "name": name,
                    "kind": "no_worship_2m",
                    "window_days": 60,
                    "cultou_count": 0,
                    "detail": (
                        "Nos últimos 2 meses não cultuou nenhum dia "
                        "(só servindo e/ou ausências) — revise antes de escalar."
                    ),
                }
            )
        elif cultou_30 == 0 and rows_30:
            alerts.append(
                {
                    "volunteer_id": vid,
                    "name": name,
                    "kind": "no_worship_1m",
                    "window_days": 30,
                    "cultou_count": 0,
                    "detail": (
                        "No último mês não cultuou nenhum dia — "
                        "vale priorizar quem está cultuando."
                    ),
                }
            )

    alerts.sort(
        key=lambda x: (
            {"no_worship_2m": 0, "no_worship_1m": 1, "no_records": 2}.get(x["kind"], 9),
            (x["name"] or "").lower(),
        )
    )
    return alerts
