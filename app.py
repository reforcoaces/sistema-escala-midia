"""Aplicação web: escala de comunicação — cadastro, disponibilidade, geração e exportação."""
from __future__ import annotations

import datetime as dt
import io
import json
import re
import sqlite3
from typing import Any

import pandas as pd
from flask import Flask, Response, jsonify, render_template, request

import birthdays as birthdays_mod
import db
from db import connection
from full_backup import build_full_backup_payload, restore_full_backup
from logic import (
    AREAS,
    assign_greedy_fair,
    build_month_events,
    dates_in_month_with_weekdays,
    teen_sunday_escala_forbidden,
    thursday_sunday_dates,
)
from pdf_export import build_schedule_pdf

app = Flask(__name__, static_folder="static", static_url_path="/static")


def _parse_date_cell(val: Any) -> str | None:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    s = str(val).strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return dt.datetime.strptime(s[:10], fmt).date().isoformat()
        except ValueError:
            continue
    # Excel serial
    try:
        x = float(s.replace(",", "."))
        if 30000 < x < 60000:
            base = dt.date(1899, 12, 30)
            return (base + dt.timedelta(days=int(x))).isoformat()
    except ValueError:
        pass
    return None


def _truthy(val: Any) -> bool | None:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    s = str(val).strip().lower()
    if s in ("sim", "s", "yes", "y", "true", "1", "disponível", "disponivel", "ok", "posso"):
        return True
    if s in ("não", "nao", "n", "no", "false", "0", "-", "não posso", "nao posso", "impedido"):
        return False
    return None


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/areas", methods=["GET"])
def api_areas():
    return jsonify(AREAS)


@app.route("/api/volunteers", methods=["GET"])
def list_volunteers():
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT v.id, v.name, v.birth_date,
                   GROUP_CONCAT(va.area) AS areas
            FROM volunteer v
            LEFT JOIN volunteer_area va ON va.volunteer_id = v.id
            GROUP BY v.id
            ORDER BY v.name COLLATE NOCASE
            """
        ).fetchall()
    out = []
    for r in rows:
        areas = [a for a in (r["areas"] or "").split(",") if a]
        out.append(
            {
                "id": r["id"],
                "name": r["name"],
                "areas": areas,
                "birth_date": r["birth_date"],
            }
        )
    return jsonify(out)


@app.route("/api/volunteers", methods=["POST"])
def create_volunteer():
    data = request.get_json(force=True, silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Nome obrigatório"}), 400
    areas = [a for a in data.get("areas") or [] if a in AREAS]
    birth_raw = (data.get("birth_date") or "").strip() or None
    birth_date: str | None = None
    if birth_raw:
        birth_date = birth_raw[:10]
        try:
            dt.date.fromisoformat(birth_date)
        except ValueError:
            return jsonify({"error": "Data de nascimento inválida (use AAAA-MM-DD)."}), 400
    try:
        with connection() as conn:
            cur = conn.execute(
                "INSERT INTO volunteer (name, birth_date) VALUES (?, ?)",
                (name, birth_date),
            )
            vid = cur.lastrowid
            for a in areas:
                conn.execute(
                    "INSERT INTO volunteer_area (volunteer_id, area) VALUES (?, ?)",
                    (vid, a),
                )
    except sqlite3.IntegrityError:
        return jsonify({"error": "Já existe um voluntário com esse nome."}), 409
    return (
        jsonify(
            {"id": vid, "name": name, "areas": areas, "birth_date": birth_date}
        ),
        201,
    )


@app.route("/api/volunteers/<int:vid>", methods=["PATCH"])
def patch_volunteer(vid: int):
    data = request.get_json(force=True, silent=True) or {}
    if "birth_date" in data:
        bd0 = data.get("birth_date")
        if bd0 is not None and str(bd0).strip() != "":
            try:
                dt.date.fromisoformat(str(bd0).strip()[:10])
            except ValueError:
                return jsonify({"error": "Data de nascimento inválida."}), 400

    with connection() as conn:
        row = conn.execute("SELECT id FROM volunteer WHERE id = ?", (vid,)).fetchone()
        if not row:
            return jsonify({"error": "Voluntário não encontrado"}), 404
        if "name" in data:
            n = (data.get("name") or "").strip()
            if n:
                conn.execute("UPDATE volunteer SET name = ? WHERE id = ?", (n, vid))
        if "areas" in data:
            areas = [a for a in data.get("areas") or [] if a in AREAS]
            conn.execute("DELETE FROM volunteer_area WHERE volunteer_id = ?", (vid,))
            for a in areas:
                conn.execute(
                    "INSERT INTO volunteer_area (volunteer_id, area) VALUES (?, ?)",
                    (vid, a),
                )
        if "birth_date" in data:
            bd = data.get("birth_date")
            if bd is None or str(bd).strip() == "":
                conn.execute(
                    "UPDATE volunteer SET birth_date = NULL WHERE id = ?", (vid,)
                )
            else:
                s = str(bd).strip()[:10]
                conn.execute(
                    "UPDATE volunteer SET birth_date = ? WHERE id = ?", (s, vid)
                )
    return jsonify({"ok": True})


@app.route("/api/volunteers/<int:vid>", methods=["DELETE"])
def delete_volunteer(vid: int):
    with connection() as conn:
        conn.execute("DELETE FROM volunteer WHERE id = ?", (vid,))
    return jsonify({"ok": True})


@app.route("/api/volunteers/export.json", methods=["GET"])
def export_volunteers_json():
    """Backup: nomes, datas de nascimento e áreas (JSON para importar depois)."""
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT v.id, v.name, v.birth_date,
                   GROUP_CONCAT(va.area) AS areas
            FROM volunteer v
            LEFT JOIN volunteer_area va ON va.volunteer_id = v.id
            GROUP BY v.id
            ORDER BY v.name COLLATE NOCASE
            """
        ).fetchall()
    volunteers = []
    for r in rows:
        areas = [a for a in (r["areas"] or "").split(",") if a]
        volunteers.append(
            {
                "name": r["name"],
                "birth_date": r["birth_date"],
                "areas": areas,
            }
        )
    payload = {
        "format": "sistema-escala-midia-volunteers",
        "version": 1,
        "exported_at": dt.datetime.now(dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat(),
        "volunteers": volunteers,
    }
    raw = json.dumps(payload, ensure_ascii=False, indent=2)
    fname = f"voluntarios_{dt.date.today().isoformat()}.json"
    return Response(
        raw.encode("utf-8"),
        mimetype="application/json; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{fname}"',
            "Content-Type": "application/json; charset=utf-8",
        },
    )


@app.route("/api/volunteers/import", methods=["POST"])
def import_volunteers_json():
    """
    Restauração: aceita o JSON exportado ou só uma lista em «volunteers».
    mode=merge: cria novos ou atualiza quem tem o mesmo nome.
    mode=replace: apaga todos os voluntários e recria (apaga disponibilidade; escala fica sem nome).
    """
    data = request.get_json(force=True, silent=True) or {}
    vols = data.get("volunteers")
    if not isinstance(vols, list):
        return jsonify({"error": 'JSON inválido: é necessário o campo «volunteers» (lista).'}), 400
    mode = (data.get("mode") or "merge").strip().lower()
    if mode not in ("merge", "replace"):
        return jsonify({"error": "mode deve ser merge ou replace."}), 400

    by_name: dict[str, dict[str, Any]] = {}
    for raw in vols:
        if not isinstance(raw, dict):
            continue
        name = (raw.get("name") or "").strip()
        if not name:
            continue
        birth_date: str | None = None
        bd_raw = raw.get("birth_date")
        if bd_raw is not None and str(bd_raw).strip() != "":
            birth_date = str(bd_raw).strip()[:10]
            try:
                dt.date.fromisoformat(birth_date)
            except ValueError:
                return jsonify(
                    {
                        "error": (
                            f'Data de nascimento inválida para «{name}» '
                            f"(use AAAA-MM-DD)."
                        )
                    }
                ), 400
        areas = [a for a in (raw.get("areas") or []) if a in AREAS]
        by_name[name] = {"name": name, "birth_date": birth_date, "areas": areas}

    entries = list(by_name.values())
    if not entries:
        return jsonify({"error": "Nenhum voluntário com nome válido no arquivo."}), 400

    created = 0
    updated = 0
    try:
        with connection() as conn:
            if mode == "replace":
                conn.execute("DELETE FROM volunteer")
            for e in entries:
                name = e["name"]
                birth_date = e["birth_date"]
                areas = e["areas"]
                if mode == "replace":
                    cur = conn.execute(
                        "INSERT INTO volunteer (name, birth_date) VALUES (?, ?)",
                        (name, birth_date),
                    )
                    vid = int(cur.lastrowid)
                    for a in areas:
                        conn.execute(
                            "INSERT INTO volunteer_area (volunteer_id, area) VALUES (?, ?)",
                            (vid, a),
                        )
                    created += 1
                else:
                    row = conn.execute(
                        "SELECT id FROM volunteer WHERE name = ?", (name,)
                    ).fetchone()
                    if row:
                        vid = int(row["id"])
                        conn.execute(
                            "UPDATE volunteer SET birth_date = ? WHERE id = ?",
                            (birth_date, vid),
                        )
                        conn.execute(
                            "DELETE FROM volunteer_area WHERE volunteer_id = ?", (vid,)
                        )
                        for a in areas:
                            conn.execute(
                                "INSERT INTO volunteer_area (volunteer_id, area) VALUES (?, ?)",
                                (vid, a),
                            )
                        updated += 1
                    else:
                        cur = conn.execute(
                            "INSERT INTO volunteer (name, birth_date) VALUES (?, ?)",
                            (name, birth_date),
                        )
                        vid = int(cur.lastrowid)
                        for a in areas:
                            conn.execute(
                                "INSERT INTO volunteer_area (volunteer_id, area) VALUES (?, ?)",
                                (vid, a),
                            )
                        created += 1
    except sqlite3.IntegrityError as e:
        return jsonify({"error": f"Conflito ao importar: {e}."}), 409

    out: dict[str, Any] = {
        "mode": mode,
        "created": created,
        "updated": updated,
        "total": len(entries),
    }
    return jsonify(out)


@app.route("/api/backup/full.json", methods=["GET"])
def export_full_backup():
    """Backup global: voluntários (com ids), áreas, extras, disponibilidade, escalas, opções, definições."""
    with connection() as conn:
        payload = build_full_backup_payload(conn)
    raw = json.dumps(payload, ensure_ascii=False, indent=2)
    fname = f"escala_backup_completo_{dt.date.today().isoformat()}.json"
    return Response(
        raw.encode("utf-8"),
        mimetype="application/json; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{fname}"',
            "Content-Type": "application/json; charset=utf-8",
        },
    )


@app.route("/api/backup/restore", methods=["POST"])
def restore_full_backup_route():
    """Substitui toda a base pelo conteúdo do backup (irreversível sem novo arquivo)."""
    data = request.get_json(force=True, silent=True) or {}
    try:
        with connection() as conn:
            stats = restore_full_backup(conn, data)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except sqlite3.IntegrityError as e:
        return jsonify({"error": f"Conflito ao restaurar: {e}."}), 409
    return jsonify({"ok": True, **stats})


def _extras_for_month(
    conn, year: int, month: int
) -> list[tuple[str, str | None, str | None]]:
    rows = conn.execute(
        "SELECT event_date, label, event_time FROM extra_event WHERE year = ? AND month = ?",
        (year, month),
    ).fetchall()
    return [(r["event_date"], r["label"], r["event_time"]) for r in rows]


@app.route("/api/month/<int:year>/<int:month>/events", methods=["GET"])
def month_events(year: int, month: int):
    if not 1 <= month <= 12:
        return jsonify({"error": "Mês inválido"}), 400
    with connection() as conn:
        extras = _extras_for_month(conn, year, month)
    events = build_month_events(year, month, extras)
    return jsonify(events)


@app.route("/api/month/<int:year>/<int:month>/extra-event", methods=["POST"])
def add_extra_event(year: int, month: int):
    data = request.get_json(force=True, silent=True) or {}
    date_iso = _parse_date_cell(data.get("date") or data.get("event_date"))
    if not date_iso:
        return jsonify({"error": "Data inválida (use AAAA-MM-DD ou DD/MM/AAAA)"}), 400
    d = dt.date.fromisoformat(date_iso)
    if d.year != year or d.month != month:
        return jsonify({"error": "A data precisa estar no mês selecionado"}), 400
    label = (data.get("label") or "").strip() or None
    if not label:
        return jsonify({"error": "Informe a descrição do evento"}), 400
    event_time = (data.get("event_time") or "").strip() or None
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO extra_event (year, month, event_date, label, event_time)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(year, month, event_date) DO UPDATE SET
                label = excluded.label,
                event_time = excluded.event_time
            """,
            (year, month, date_iso, label, event_time),
        )
    return jsonify({"ok": True, "date": date_iso, "label": label, "event_time": event_time})


@app.route("/api/month/<int:year>/<int:month>/extra-event/<int:eid>", methods=["DELETE", "PATCH"])
def extra_event_item(year: int, month: int, eid: int):
    if request.method == "DELETE":
        with connection() as conn:
            conn.execute(
                "DELETE FROM extra_event WHERE id = ? AND year = ? AND month = ?",
                (eid, year, month),
            )
        return jsonify({"ok": True})

    data = request.get_json(force=True, silent=True) or {}
    sets: list[str] = []
    vals: list[Any] = []
    if "label" in data:
        sets.append("label = ?")
        vals.append((data.get("label") or "").strip() or None)
    if "event_time" in data:
        sets.append("event_time = ?")
        vals.append((data.get("event_time") or "").strip() or None)
    if not sets:
        return jsonify({"error": "Envie label e/ou event_time"}), 400
    vals.extend([eid, year, month])
    with connection() as conn:
        cur = conn.execute(
            f"UPDATE extra_event SET {', '.join(sets)} WHERE id = ? AND year = ? AND month = ?",
            vals,
        )
        if cur.rowcount == 0:
            return jsonify({"error": "Evento não encontrado"}), 404
    return jsonify({"ok": True})


@app.route("/api/month/<int:year>/<int:month>/extras", methods=["GET"])
def list_extras(year: int, month: int):
    with connection() as conn:
        rows = conn.execute(
            "SELECT id, event_date, label, event_time FROM extra_event WHERE year = ? AND month = ? ORDER BY event_date",
            (year, month),
        ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/month/<int:year>/<int:month>/options", methods=["GET", "PATCH"])
def month_options(year: int, month: int):
    """Opções de exibição do mês (ex.: oficina / treinamento nos domingos)."""
    if request.method == "GET":
        with connection() as conn:
            row = conn.execute(
                "SELECT include_training FROM month_options WHERE year = ? AND month = ?",
                (year, month),
            ).fetchone()
        return jsonify(
            {"include_training": bool(row["include_training"]) if row else False}
        )

    data = request.get_json(force=True, silent=True) or {}
    inc = bool(data.get("include_training"))
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO month_options (year, month, include_training)
            VALUES (?, ?, ?)
            ON CONFLICT(year, month) DO UPDATE SET
                include_training = excluded.include_training
            """,
            (year, month, 1 if inc else 0),
        )
    return jsonify({"ok": True, "include_training": inc})


@app.route("/api/month/<int:year>/<int:month>/availability", methods=["GET"])
def get_availability(year: int, month: int):
    if month == 12:
        end = dt.date(year, 12, 31)
    else:
        end = dt.date(year, month + 1, 1) - dt.timedelta(days=1)
    start_iso = dt.date(year, month, 1).isoformat()
    end_iso = end.isoformat()
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT volunteer_id, event_date, available
            FROM availability
            WHERE event_date >= ? AND event_date <= ?
            """,
            (start_iso, end_iso),
        ).fetchall()
    by_vol: dict[int, dict[str, bool]] = {}
    for r in rows:
        by_vol.setdefault(r["volunteer_id"], {})[r["event_date"]] = bool(r["available"])
    return jsonify(by_vol)


@app.route("/api/month/<int:year>/<int:month>/availability", methods=["POST"])
def set_availability(year: int, month: int):
    data = request.get_json(force=True, silent=True) or {}
    vid = int(data.get("volunteer_id", 0))
    updates = data.get("dates") or {}
    if not vid:
        return jsonify({"error": "volunteer_id obrigatório"}), 400
    with connection() as conn:
        row = conn.execute("SELECT id FROM volunteer WHERE id = ?", (vid,)).fetchone()
        if not row:
            return jsonify({"error": "Voluntário não encontrado"}), 404
        for date_iso, flag in updates.items():
            if not re.match(r"^\d{4}-\d{2}-\d{2}$", str(date_iso)):
                continue
            d = dt.date.fromisoformat(str(date_iso))
            if d.year != year or d.month != month:
                continue
            conn.execute(
                """
                INSERT INTO availability (volunteer_id, event_date, available)
                VALUES (?, ?, ?)
                ON CONFLICT(volunteer_id, event_date) DO UPDATE SET available = excluded.available
                """,
                (vid, str(date_iso), 1 if flag else 0),
            )
    return jsonify({"ok": True})


@app.route("/api/month/<int:year>/<int:month>/availability/fill-regular", methods=["POST"])
def fill_regular_availability(year: int, month: int):
    """
    Marca ou desmarca disponibilidade no mês para cultos regulares.
    `available` (padrão true): true = disponível, false = não disponível (checkbox desligado).
    `which`: sunday | thursday | both (padrão both, compatível com clientes antigos).
    """
    data = request.get_json(force=True, silent=True) or {}
    vid = int(data.get("volunteer_id", 0))
    flag = bool(data.get("available", True))
    if not vid:
        return jsonify({"error": "volunteer_id obrigatório"}), 400
    which = (data.get("which") or "both").strip().lower()
    if which == "sunday":
        raw_dates = dates_in_month_with_weekdays(year, month, (6,))
    elif which == "thursday":
        raw_dates = dates_in_month_with_weekdays(year, month, (3,))
    elif which == "both":
        raw_dates = thursday_sunday_dates(year, month)
    else:
        return jsonify(
            {"error": "which deve ser sunday, thursday ou both."}
        ), 400
    dates = [d.isoformat() for d in raw_dates]
    with connection() as conn:
        if not conn.execute("SELECT id FROM volunteer WHERE id = ?", (vid,)).fetchone():
            return jsonify({"error": "Voluntário não encontrado"}), 404
        for date_iso in dates:
            conn.execute(
                """
                INSERT INTO availability (volunteer_id, event_date, available)
                VALUES (?, ?, ?)
                ON CONFLICT(volunteer_id, event_date) DO UPDATE SET available = excluded.available
                """,
                (vid, date_iso, 1 if flag else 0),
            )
    return jsonify({"ok": True, "dates": dates})


@app.route("/api/month/<int:year>/<int:month>/import-csv", methods=["POST"])
def import_csv(year: int, month: int):
    """
    CSV flexível: tenta detectar colunas de nome, data e disponibilidade.
    Também aceita formato longo: nome, data, disponivel
    """
    if "file" not in request.files:
        return jsonify({"error": "Envie o arquivo no campo 'file'"}), 400
    f = request.files["file"]
    raw = f.read()
    text: str | None = None
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        return jsonify({"error": "Não foi possível decodificar o arquivo"}), 400

    df = pd.read_csv(io.StringIO(text), sep=None, engine="python")
    df.columns = [str(c).strip().lower() for c in df.columns]

    def pick_col(candidates: list[str]) -> str | None:
        for c in df.columns:
            for cand in candidates:
                if cand in c:
                    return c
        return None

    col_name = pick_col(["nome", "name", "voluntário", "voluntario", "quem"])
    col_date = pick_col(["data", "date", "dia"])
    col_ok = pick_col(["disp", "dispon", "pode", "available", "vai", "comparecer"])

    if not col_name or not col_date:
        return (
            jsonify(
                {
                    "error": "CSV precisa ter colunas reconhecíveis de nome e data "
                    "(ex.: nome, data ou name, date).",
                    "columns_found": list(df.columns),
                }
            ),
            400,
        )

    with connection() as conn:
        vol_rows = conn.execute("SELECT id, name FROM volunteer").fetchall()
    name_to_id = {r["name"].strip().lower(): r["id"] for r in vol_rows}

    imported = 0
    skipped = 0
    errors: list[str] = []
    pending_rows: list[tuple[int, str, int]] = []

    for _, row in df.iterrows():
        nm = str(row.get(col_name, "")).strip()
        if not nm or nm.lower() == "nan":
            skipped += 1
            continue
        vid = name_to_id.get(nm.lower())
        if not vid:
            for k, i in name_to_id.items():
                if k in nm.lower() or nm.lower() in k:
                    vid = i
                    break
        if not vid:
            errors.append(f"Voluntário não cadastrado: {nm}")
            skipped += 1
            continue

        date_iso = _parse_date_cell(row.get(col_date))
        if not date_iso:
            skipped += 1
            continue
        try:
            d = dt.date.fromisoformat(date_iso)
        except ValueError:
            skipped += 1
            continue
        if d.year != year or d.month != month:
            continue

        if col_ok:
            t = _truthy(row.get(col_ok))
            if t is None:
                avail = True
            else:
                avail = t
        else:
            avail = True

        pending_rows.append((vid, date_iso, 1 if avail else 0))
        imported += 1

    with connection() as conn:
        for vid, date_iso, av in pending_rows:
            conn.execute(
                """
                INSERT INTO availability (volunteer_id, event_date, available)
                VALUES (?, ?, ?)
                ON CONFLICT(volunteer_id, event_date) DO UPDATE SET available = excluded.available
                """,
                (vid, date_iso, av),
            )

    return jsonify({"imported": imported, "skipped": skipped, "errors": errors[:30]})


@app.route("/api/month/<int:year>/<int:month>/generate", methods=["POST"])
def generate_schedule(year: int, month: int):
    with connection() as conn:
        extras = _extras_for_month(conn, year, month)
        events = build_month_events(year, month, extras)
        event_dates = [e["date"] for e in events]

        vols = conn.execute("SELECT id, name, birth_date FROM volunteer").fetchall()
        volunteer_birth = {r["id"]: r["birth_date"] for r in vols}
        va = conn.execute("SELECT volunteer_id, area FROM volunteer_area").fetchall()
        volunteer_areas: dict[int, set[str]] = {}
        for r in va:
            volunteer_areas.setdefault(r["volunteer_id"], set()).add(r["area"])

        av_rows = conn.execute(
            """
            SELECT volunteer_id, event_date, available
            FROM availability
            WHERE substr(event_date, 1, 7) = ?
            """,
            (f"{year:04d}-{month:02d}",),
        ).fetchall()
        availability: dict[int, dict[str, bool]] = {}
        for r in av_rows:
            availability.setdefault(r["volunteer_id"], {})[r["event_date"]] = bool(
                r["available"]
            )

        # só quem tem pelo menos uma aptidão entra na fila
        for v in vols:
            volunteer_areas.setdefault(v["id"], set())

        result = assign_greedy_fair(
            event_dates,
            AREAS,
            volunteer_areas,
            availability,
            volunteer_birth,
        )

        conn.execute(
            "DELETE FROM assignment WHERE year = ? AND month = ?",
            (year, month),
        )
        for (ed, area), vid in result.items():
            conn.execute(
                """
                INSERT INTO assignment (year, month, event_date, area, volunteer_id)
                VALUES (?, ?, ?, ?, ?)
                """,
                (year, month, ed, area, vid),
            )

    return jsonify({"ok": True, "cells": len(result)})


@app.route("/api/month/<int:year>/<int:month>/assignments", methods=["GET"])
def get_assignments(year: int, month: int):
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT a.event_date, a.area, a.volunteer_id, v.name
            FROM assignment a
            LEFT JOIN volunteer v ON v.id = a.volunteer_id
            WHERE a.year = ? AND a.month = ?
            """,
            (year, month),
        ).fetchall()
    cells: dict[str, dict[str, Any]] = {}
    for r in rows:
        cells.setdefault(r["event_date"], {})[r["area"]] = {
            "volunteer_id": r["volunteer_id"],
            "name": r["name"] or None,
        }
    return jsonify(cells)


@app.route("/api/month/<int:year>/<int:month>/assignment", methods=["PATCH"])
def patch_assignment(year: int, month: int):
    data = request.get_json(force=True, silent=True) or {}
    date_iso = data.get("event_date")
    area = data.get("area")
    volunteer_id = data.get("volunteer_id")
    if not date_iso or area not in AREAS:
        return jsonify({"error": "event_date e area válidos são obrigatórios"}), 400
    if volunteer_id is not None:
        volunteer_id = int(volunteer_id) if volunteer_id else None
    with connection() as conn:
        if volunteer_id:
            brow = conn.execute(
                "SELECT birth_date FROM volunteer WHERE id = ?", (volunteer_id,)
            ).fetchone()
            bd = brow["birth_date"] if brow else None
            if teen_sunday_escala_forbidden(bd, str(date_iso)):
                return (
                    jsonify(
                        {
                            "error": (
                                "Menores de 16 anos não podem ser escalados neste domingo "
                                "(exceto no 1º domingo do mês — Santa Ceia)."
                            )
                        }
                    ),
                    400,
                )
        conn.execute(
            """
            INSERT INTO assignment (year, month, event_date, area, volunteer_id)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(year, month, event_date, area)
            DO UPDATE SET volunteer_id = excluded.volunteer_id
            """,
            (year, month, date_iso, area, volunteer_id),
        )
    return jsonify({"ok": True})


@app.route("/api/month/<int:year>/<int:month>/export.pdf", methods=["GET"])
def export_pdf(year: int, month: int):
    with connection() as conn:
        extras = _extras_for_month(conn, year, month)
        events = build_month_events(year, month, extras)
        row_opt = conn.execute(
            "SELECT include_training FROM month_options WHERE year = ? AND month = ?",
            (year, month),
        ).fetchone()
        include_training = bool(row_opt and row_opt["include_training"])
        rows = conn.execute(
            """
            SELECT a.event_date, a.area, v.name
            FROM assignment a
            LEFT JOIN volunteer v ON v.id = a.volunteer_id
            WHERE a.year = ? AND a.month = ?
            """,
            (year, month),
        ).fetchall()
    names: dict[tuple[str, str], str] = {}
    for r in rows:
        names[(r["event_date"], r["area"])] = (r["name"] or "-").strip() or "-"
    for ev in events:
        d = ev["date"]
        for a in AREAS:
            names.setdefault((d, a), "-")

    title = f"Escala de comunicação — {month:02d}/{year}"
    try:
        pdf_bytes = build_schedule_pdf(
            title, events, names, include_training=include_training
        )
    except (FileNotFoundError, RuntimeError) as e:
        return jsonify({"error": str(e)}), 503
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=escala_{year}_{month:02d}.pdf"
        },
    )


@app.route("/api/settings", methods=["GET", "PATCH"])
def api_settings():
    """Configurações globais (ex.: webhook do Discord para aniversários)."""
    if request.method == "GET":
        with connection() as conn:
            url, source = birthdays_mod.resolve_discord_webhook_url(conn)
        return jsonify(
            {
                "discord_webhook_url": url if source != "env" else "",
                "discord_webhook_source": source,
            }
        )

    data = request.get_json(force=True, silent=True) or {}
    url = (data.get("discord_webhook_url") or "").strip()
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO app_setting (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (birthdays_mod.KEY_DISCORD_WEBHOOK, url),
        )
    return jsonify({"ok": True, "discord_webhook_url": url})


@app.route("/api/birthdays/upcoming", methods=["GET"])
def api_birthdays_upcoming():
    """Voluntários com próximo aniversário dentro da janela (a partir de hoje)."""
    try:
        days = int(request.args.get("days", "365"))
    except ValueError:
        days = 365
    days = max(1, min(days, 730))
    from_date = dt.date.today()
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT id, name, birth_date FROM volunteer
            WHERE birth_date IS NOT NULL AND trim(birth_date) != ''
            ORDER BY name COLLATE NOCASE
            """
        ).fetchall()
    items = birthdays_mod.birthdays_upcoming_from_rows(rows, from_date, days)
    return jsonify({"from": from_date.isoformat(), "days": days, "items": items})


@app.route("/api/birthdays/notify-today", methods=["POST"])
def api_birthdays_notify_today():
    """
    Envia mensagens no Discord para quem faz aniversário hoje (uma vez por ano por pessoa,
    salvo force=true para reenviar).
    """
    data = request.get_json(force=True, silent=True) or {}
    force = bool(data.get("force"))
    try:
        with connection() as conn:
            result = birthdays_mod.notify_birthdays_today(conn, force=force)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 502
    return jsonify(result)


@app.route("/api/stats/<int:year>/<int:month>", methods=["GET"])
def stats(year: int, month: int):
    """
    Contagem de escalas por voluntário no mês (com detalhe por área) e lista de quem
    não entrou na escala nenhuma vez nesse mês.
    """
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT v.id, v.name, a.area, COUNT(*) AS c
            FROM assignment a
            JOIN volunteer v ON v.id = a.volunteer_id
            WHERE a.year = ? AND a.month = ? AND a.volunteer_id IS NOT NULL
            GROUP BY v.id, a.area
            """,
            (year, month),
        ).fetchall()
        never_rows = conn.execute(
            """
            SELECT v.name
            FROM volunteer v
            WHERE NOT EXISTS (
                SELECT 1 FROM assignment a
                WHERE a.volunteer_id = v.id
                  AND a.year = ?
                  AND a.month = ?
                  AND a.volunteer_id IS NOT NULL
            )
            ORDER BY v.name COLLATE NOCASE
            """,
            (year, month),
        ).fetchall()

    by_vol: dict[int, dict[str, Any]] = {}
    for r in rows:
        vid = int(r["id"])
        if vid not in by_vol:
            by_vol[vid] = {"name": r["name"], "count": 0, "by_area": []}
        c = int(r["c"])
        by_vol[vid]["count"] += c
        by_vol[vid]["by_area"].append({"area": r["area"], "count": c})

    for v in by_vol.values():
        v["by_area"].sort(key=lambda x: (-x["count"], x["area"]))

    assigned = sorted(
        by_vol.values(),
        key=lambda x: (-x["count"], (x["name"] or "").lower()),
    )
    never_assigned = [{"name": r["name"]} for r in never_rows]
    return jsonify({"assigned": assigned, "never_assigned": never_assigned})


def main():
    app.run(host="127.0.0.1", port=5050, debug=True)


db.init_db()

if __name__ == "__main__":
    main()
