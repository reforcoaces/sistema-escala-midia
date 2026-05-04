"""Backup e restauração completos (SQLite → JSON e vice-versa)."""
from __future__ import annotations

import datetime as dt
import sqlite3
from typing import Any

from logic import AREAS

FORMAT = "sistema-escala-midia-full"
VERSION = 1

_DELETE_ORDER = (
    "birthday_notification_sent",
    "assignment",
    "availability",
    "volunteer_area",
    "volunteer",
    "extra_event",
    "month_options",
    "app_setting",
)


def _row_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {k: row[k] for k in row.keys()}


def build_full_backup_payload(conn: sqlite3.Connection) -> dict[str, Any]:
    volunteers = [
        _row_dict(r)
        for r in conn.execute(
            "SELECT id, name, birth_date FROM volunteer ORDER BY id"
        ).fetchall()
    ]
    volunteer_area = [
        _row_dict(r)
        for r in conn.execute(
            "SELECT volunteer_id, area FROM volunteer_area ORDER BY volunteer_id, area"
        ).fetchall()
    ]
    extra_event = [
        _row_dict(r)
        for r in conn.execute(
            """
            SELECT year, month, event_date, label, event_time
            FROM extra_event
            ORDER BY year, month, event_date
            """
        ).fetchall()
    ]
    availability = [
        _row_dict(r)
        for r in conn.execute(
            "SELECT volunteer_id, event_date, available FROM availability ORDER BY volunteer_id, event_date"
        ).fetchall()
    ]
    assignment = [
        _row_dict(r)
        for r in conn.execute(
            """
            SELECT year, month, event_date, area, volunteer_id
            FROM assignment
            ORDER BY year, month, event_date, area
            """
        ).fetchall()
    ]
    month_options = [
        _row_dict(r)
        for r in conn.execute(
            "SELECT year, month, include_training FROM month_options ORDER BY year, month"
        ).fetchall()
    ]
    app_setting = [
        _row_dict(r)
        for r in conn.execute("SELECT key, value FROM app_setting ORDER BY key").fetchall()
    ]
    birthday_notification_sent = [
        _row_dict(r)
        for r in conn.execute(
            """
            SELECT volunteer_id, year FROM birthday_notification_sent
            ORDER BY volunteer_id, year
            """
        ).fetchall()
    ]
    return {
        "format": FORMAT,
        "version": VERSION,
        "exported_at": dt.datetime.now(dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat(),
        "volunteer": volunteers,
        "volunteer_area": volunteer_area,
        "extra_event": extra_event,
        "availability": availability,
        "assignment": assignment,
        "month_options": month_options,
        "app_setting": app_setting,
        "birthday_notification_sent": birthday_notification_sent,
    }


def _as_int(v: Any, field: str) -> int:
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, int) and not isinstance(v, bool):
        return v
    if isinstance(v, float) and v == int(v):
        return int(v)
    if isinstance(v, str) and v.strip().lstrip("-").isdigit():
        return int(v.strip())
    raise ValueError(f"Campo «{field}» precisa ser número inteiro.")


def _as_opt_int(v: Any) -> int | None:
    if v is None or v == "":
        return None
    return _as_int(v, "volunteer_id")


def _as_bool_int(v: Any, field: str) -> int:
    if isinstance(v, bool):
        return 1 if v else 0
    x = _as_int(v, field)
    if x not in (0, 1):
        raise ValueError(f"Campo «{field}» deve ser 0 ou 1.")
    return x


def _validate_iso_date(s: str, field: str) -> str:
    t = (s or "").strip()[:10]
    if len(t) != 10:
        raise ValueError(f"Campo «{field}» com data inválida (use AAAA-MM-DD).")
    dt.date.fromisoformat(t)
    return t


def restore_full_backup(conn: sqlite3.Connection, data: dict[str, Any]) -> dict[str, Any]:
    if data.get("format") != FORMAT:
        raise ValueError(
            "Este arquivo não é um backup completo deste sistema "
            f'(esperado format «{FORMAT}»).'
        )
    if int(data.get("version") or 0) != VERSION:
        raise ValueError("Versão de backup não suportada (só versão 1).")

    vols_raw = data.get("volunteer")
    if not isinstance(vols_raw, list):
        raise ValueError('O backup precisa do campo «volunteer» (lista).')

    volunteers: list[tuple[int, str, str | None]] = []
    seen_ids: set[int] = set()
    seen_names: set[str] = set()
    for i, raw in enumerate(vols_raw):
        if not isinstance(raw, dict):
            raise ValueError(f"Voluntário #{i + 1}: objeto inválido.")
        vid = _as_int(raw.get("id"), "id")
        if vid <= 0:
            raise ValueError(f"Voluntário #{i + 1}: id deve ser positivo.")
        if vid in seen_ids:
            raise ValueError(f"Voluntário: id {vid} repetido.")
        seen_ids.add(vid)
        name = (raw.get("name") or "").strip()
        if not name:
            raise ValueError(f"Voluntário id {vid}: nome vazio.")
        key = name.casefold()
        if key in seen_names:
            raise ValueError(f"Voluntário: nome duplicado «{name}».")
        seen_names.add(key)
        bd = raw.get("birth_date")
        birth: str | None = None
        if bd is not None and str(bd).strip() != "":
            birth = _validate_iso_date(str(bd), "birth_date")
        volunteers.append((vid, name, birth))

    areas_set = frozenset(AREAS)
    va_list: list[tuple[int, str]] = []
    seen_va: set[tuple[int, str]] = set()
    for i, raw in enumerate(data.get("volunteer_area") or []):
        if not isinstance(raw, dict):
            raise ValueError(f"volunteer_area #{i + 1}: objeto inválido.")
        vid = _as_int(raw.get("volunteer_id"), "volunteer_id")
        area = (raw.get("area") or "").strip()
        if area not in areas_set:
            raise ValueError(f"Área inválida em volunteer_area: «{area}».")
        if vid not in seen_ids:
            raise ValueError(f"volunteer_area: voluntário id {vid} não existe no backup.")
        vk = (vid, area)
        if vk in seen_va:
            raise ValueError(f"volunteer_area duplicado: voluntário {vid}, área «{area}».")
        seen_va.add(vk)
        va_list.append((vid, area))

    extras: list[tuple[int, int, str, str | None, str | None]] = []
    seen_ex: set[tuple[int, int, str]] = set()
    for i, raw in enumerate(data.get("extra_event") or []):
        if not isinstance(raw, dict):
            raise ValueError(f"extra_event #{i + 1}: objeto inválido.")
        y = _as_int(raw.get("year"), "year")
        m = _as_int(raw.get("month"), "month")
        if not 1 <= m <= 12:
            raise ValueError(f"extra_event: mês inválido ({m}).")
        ed = _validate_iso_date(str(raw.get("event_date") or ""), "event_date")
        ek = (y, m, ed)
        if ek in seen_ex:
            raise ValueError(f"extra_event duplicado: {y}-{m:02d} {ed}.")
        seen_ex.add(ek)
        label = raw.get("label")
        lbl = (str(label).strip() if label is not None else "") or None
        et = raw.get("event_time")
        et_s = (str(et).strip() if et is not None else "") or None
        extras.append((y, m, ed, lbl, et_s))

    avail: list[tuple[int, str, int]] = []
    seen_av: set[tuple[int, str]] = set()
    for i, raw in enumerate(data.get("availability") or []):
        if not isinstance(raw, dict):
            raise ValueError(f"availability #{i + 1}: objeto inválido.")
        vid = _as_int(raw.get("volunteer_id"), "volunteer_id")
        if vid not in seen_ids:
            raise ValueError(f"availability: voluntário id {vid} não existe.")
        ed = _validate_iso_date(str(raw.get("event_date") or ""), "event_date")
        ak = (vid, ed)
        if ak in seen_av:
            raise ValueError(f"availability duplicada: voluntário {vid}, data {ed}.")
        seen_av.add(ak)
        av = _as_bool_int(raw.get("available"), "available")
        avail.append((vid, ed, av))

    assigns: list[tuple[int, int, str, str, int | None]] = []
    seen_as: set[tuple[int, int, str, str]] = set()
    for i, raw in enumerate(data.get("assignment") or []):
        if not isinstance(raw, dict):
            raise ValueError(f"assignment #{i + 1}: objeto inválido.")
        y = _as_int(raw.get("year"), "year")
        m = _as_int(raw.get("month"), "month")
        if not 1 <= m <= 12:
            raise ValueError(f"assignment: mês inválido ({m}).")
        ed = _validate_iso_date(str(raw.get("event_date") or ""), "event_date")
        area = (raw.get("area") or "").strip()
        if area not in areas_set:
            raise ValueError(f"assignment: área inválida «{area}».")
        sk = (y, m, ed, area)
        if sk in seen_as:
            raise ValueError(f"assignment duplicado: {y}-{m:02d} {ed} «{area}».")
        seen_as.add(sk)
        vid_opt = _as_opt_int(raw.get("volunteer_id"))
        if vid_opt is not None and vid_opt not in seen_ids:
            raise ValueError(
                f"assignment ({ed}, {area}): voluntário id {vid_opt} não existe."
            )
        assigns.append((y, m, ed, area, vid_opt))

    mopts: list[tuple[int, int, int]] = []
    seen_mo: set[tuple[int, int]] = set()
    for i, raw in enumerate(data.get("month_options") or []):
        if not isinstance(raw, dict):
            raise ValueError(f"month_options #{i + 1}: objeto inválido.")
        y = _as_int(raw.get("year"), "year")
        m = _as_int(raw.get("month"), "month")
        if not 1 <= m <= 12:
            raise ValueError(f"month_options: mês inválido ({m}).")
        mk = (y, m)
        if mk in seen_mo:
            raise ValueError(f"month_options duplicado: {y}-{m:02d}.")
        seen_mo.add(mk)
        it = _as_bool_int(raw.get("include_training"), "include_training")
        mopts.append((y, m, it))

    settings: list[tuple[str, str | None]] = []
    seen_sk: set[str] = set()
    for i, raw in enumerate(data.get("app_setting") or []):
        if not isinstance(raw, dict):
            raise ValueError(f"app_setting #{i + 1}: objeto inválido.")
        k = (raw.get("key") or "").strip()
        if not k:
            raise ValueError("app_setting: chave vazia.")
        if k in seen_sk:
            raise ValueError(f"app_setting: chave duplicada «{k}».")
        seen_sk.add(k)
        val = raw.get("value")
        val_s = None if val is None else str(val)
        settings.append((k, val_s))

    bdays: list[tuple[int, int]] = []
    seen_bd: set[tuple[int, int]] = set()
    for i, raw in enumerate(data.get("birthday_notification_sent") or []):
        if not isinstance(raw, dict):
            raise ValueError(f"birthday_notification_sent #{i + 1}: objeto inválido.")
        vid = _as_int(raw.get("volunteer_id"), "volunteer_id")
        if vid not in seen_ids:
            raise ValueError(f"birthday_notification_sent: voluntário id {vid} não existe.")
        yr = _as_int(raw.get("year"), "year")
        bk = (vid, yr)
        if bk in seen_bd:
            raise ValueError(
                f"birthday_notification_sent duplicado: voluntário {vid}, ano {yr}."
            )
        seen_bd.add(bk)
        bdays.append((vid, yr))

    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        for table in _DELETE_ORDER:
            conn.execute(f"DELETE FROM {table}")

        conn.executemany(
            "INSERT INTO volunteer (id, name, birth_date) VALUES (?, ?, ?)",
            volunteers,
        )
        conn.executemany(
            "INSERT INTO volunteer_area (volunteer_id, area) VALUES (?, ?)",
            va_list,
        )
        conn.executemany(
            """
            INSERT INTO extra_event (year, month, event_date, label, event_time)
            VALUES (?, ?, ?, ?, ?)
            """,
            extras,
        )
        conn.executemany(
            """
            INSERT INTO availability (volunteer_id, event_date, available)
            VALUES (?, ?, ?)
            """,
            avail,
        )
        conn.executemany(
            """
            INSERT INTO assignment (year, month, event_date, area, volunteer_id)
            VALUES (?, ?, ?, ?, ?)
            """,
            assigns,
        )
        conn.executemany(
            """
            INSERT INTO month_options (year, month, include_training)
            VALUES (?, ?, ?)
            """,
            mopts,
        )
        conn.executemany(
            "INSERT INTO app_setting (key, value) VALUES (?, ?)",
            settings,
        )
        conn.executemany(
            """
            INSERT INTO birthday_notification_sent (volunteer_id, year)
            VALUES (?, ?)
            """,
            bdays,
        )

        max_vid_row = conn.execute("SELECT MAX(id) AS m FROM volunteer").fetchone()
        max_vid = max_vid_row["m"] if max_vid_row else None
        try:
            conn.execute("DELETE FROM sqlite_sequence WHERE name = 'volunteer'")
            if max_vid:
                conn.execute(
                    "INSERT INTO sqlite_sequence (name, seq) VALUES ('volunteer', ?)",
                    (max_vid,),
                )
        except sqlite3.OperationalError:
            # sqlite_sequence só existe após o primeiro INSERT AUTOINCREMENT em volunteer
            pass
    finally:
        conn.execute("PRAGMA foreign_keys = ON")

    return {
        "volunteers": len(volunteers),
        "volunteer_area": len(va_list),
        "extra_event": len(extras),
        "availability": len(avail),
        "assignment": len(assigns),
        "month_options": len(mopts),
        "app_setting": len(settings),
        "birthday_notification_sent": len(bdays),
    }
