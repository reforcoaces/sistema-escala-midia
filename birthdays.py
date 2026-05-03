"""Próximos aniversários e avisos via webhook do Discord."""
from __future__ import annotations

import datetime as dt
import json
import sqlite3
import urllib.error
import urllib.request
from typing import Any

from logic import WEEKDAY_PT, age_on_date

KEY_DISCORD_WEBHOOK = "discord_webhook_url"


def _birthday_on_year(birth: dt.date, year: int) -> dt.date:
    try:
        return dt.date(year, birth.month, birth.day)
    except ValueError:
        return dt.date(year, 2, 28)


def next_birthday_date(birth: dt.date, from_date: dt.date) -> dt.date:
    """Próxima data de aniversário (dia/mês) a partir de from_date, inclusive."""
    cand = _birthday_on_year(birth, from_date.year)
    if cand < from_date:
        return _birthday_on_year(birth, from_date.year + 1)
    return cand


def discord_birthday_message(name: str) -> str:
    return (
        f"Hoje é aniversário do {name}! Feliz Aniversário! Que seu dia seja excelente! "
        "Declaramos Avanço, Crescimento em todas as áreas da sua vida!"
    )


def post_discord_webhook(webhook_url: str, content: str) -> None:
    payload = json.dumps({"content": content}).encode("utf-8")
    req = urllib.request.Request(
        webhook_url,
        data=payload,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            if resp.status not in (200, 204):
                raise RuntimeError(f"Discord retornou HTTP {resp.status}")
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")[:800]
        raise RuntimeError(f"Discord erro HTTP {e.code}: {body}") from e


def birthdays_upcoming_from_rows(
    rows: list[sqlite3.Row] | list[Any],
    from_date: dt.date,
    window_days: int,
) -> list[dict[str, Any]]:
    end = from_date + dt.timedelta(days=window_days)
    out: list[dict[str, Any]] = []
    for r in rows:
        bd_iso = r["birth_date"]
        if not bd_iso:
            continue
        birth = dt.date.fromisoformat(str(bd_iso)[:10])
        nb = next_birthday_date(birth, from_date)
        if nb > end:
            continue
        days_until = (nb - from_date).days
        turning = age_on_date(birth, nb)
        out.append(
            {
                "id": r["id"],
                "name": r["name"],
                "birth_date": str(bd_iso)[:10],
                "next_birthday": nb.isoformat(),
                "weekday": WEEKDAY_PT[nb.weekday()],
                "turning_age": turning,
                "days_until": days_until,
                "is_today": nb == from_date,
            }
        )
    out.sort(key=lambda x: (x["next_birthday"], x["name"].lower()))
    return out


def notify_birthdays_today(
    conn: sqlite3.Connection,
    today: dt.date | None = None,
    *,
    force: bool = False,
) -> dict[str, Any]:
    """
    Envia mensagem no Discord para cada voluntário com aniversário hoje.
    Evita duplicar no mesmo ano (tabela birthday_notification_sent), salvo se force=True.
    """
    today = today or dt.date.today()
    y = today.year

    row = conn.execute(
        "SELECT value FROM app_setting WHERE key = ?", (KEY_DISCORD_WEBHOOK,)
    ).fetchone()
    url = (row["value"] or "").strip() if row else ""
    if not url:
        raise ValueError(
            "Configure o URL do webhook do Discord na aba Aniversariantes antes de enviar."
        )

    rows = conn.execute(
        """
        SELECT id, name, birth_date FROM volunteer
        WHERE birth_date IS NOT NULL AND trim(birth_date) != ''
        """
    ).fetchall()

    sent: list[str] = []
    skipped_duplicate: list[str] = []

    for r in rows:
        birth = dt.date.fromisoformat(str(r["birth_date"])[:10])
        if birth.month != today.month or birth.day != today.day:
            continue
        vid = r["id"]
        name = r["name"]
        if not force:
            ex = conn.execute(
                """
                SELECT 1 FROM birthday_notification_sent
                WHERE volunteer_id = ? AND year = ?
                """,
                (vid, y),
            ).fetchone()
            if ex:
                skipped_duplicate.append(name)
                continue

        post_discord_webhook(url, discord_birthday_message(name))

        if not force:
            conn.execute(
                """
                INSERT OR IGNORE INTO birthday_notification_sent (volunteer_id, year)
                VALUES (?, ?)
                """,
                (vid, y),
            )
        sent.append(name)

    return {
        "sent": sent,
        "skipped_duplicate": skipped_duplicate,
        "today": today.isoformat(),
        "force": force,
    }
