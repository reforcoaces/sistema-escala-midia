const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

let areas = [];
let volunteers = [];
let currentYear = new Date().getFullYear();
let currentMonth = new Date().getMonth() + 1;
let events = [];
let extras = [];
let availability = {};
let assignments = {};
/** Oficina de comunicação (domingos 7h30–9h30) na pré-visualização / PDF / PNG. */
let includeTraining = false;

const TRAINING_NOTE_HTML =
  "Oficina de comunicação · Todos os Domingos · 7h30 às 9h30.";

/** Texto suave nas células sem voluntário (falta de pessoas no culto). */
const EMPTY_SCHEDULE_PLACEHOLDER = "Responsável do dia";

async function api(path, opts = {}) {
  const r = await fetch(path, {
    headers: { "Content-Type": "application/json", ...opts.headers },
    ...opts,
  });
  const text = await r.text();
  let data;
  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    data = { error: text };
  }
  if (!r.ok) throw new Error(data.error || r.statusText || "Erro na API");
  return data;
}

function showMsg(el, text, ok = true) {
  if (!el) return;
  el.textContent = text;
  el.className = "message " + (ok ? "ok" : "err");
  el.classList.remove("hidden");
}

function tab(name) {
  $$(".tab-panel").forEach((p) => p.classList.add("hidden"));
  $$("nav.tabs button").forEach((b) => b.classList.remove("active"));
  const panel = $("#tab-" + name);
  if (panel) panel.classList.remove("hidden");
  const btn = $(`nav.tabs button[data-tab="${name}"]`);
  if (btn) btn.classList.add("active");
}

async function loadAreas() {
  areas = await api("/api/areas");
}

function populateAvailVolunteer() {
  const sel = $("#avail-volunteer");
  if (!sel) return;
  const cur = sel.value;
  sel.innerHTML =
    '<option value="">— selecione —</option>' +
    volunteers
      .map(
        (v) =>
          `<option value="${v.id}">${escapeHtml(v.name)}</option>`
      )
      .join("");
  if (cur) sel.value = cur;
}

async function loadVolunteers() {
  volunteers = await api("/api/volunteers");
  renderVolunteers();
  renderVolunteerSummary();
  populateAvailVolunteer();
}

/** Resumo: total cadastrado e quantos por área (usa lista global `areas`). */
function renderVolunteerSummary() {
  const el = $("#vol-summary");
  if (!el) return;
  const total = volunteers.length;
  const list = (areas || []).map((a) => ({
    area: a,
    n: volunteers.filter((v) => (v.areas || []).includes(a)).length,
  }));
  const semArea = volunteers.filter((v) => !(v.areas || []).length).length;
  const chips = list
    .map(
      ({ area, n }) => `
      <div class="vol-summary-chip">
        <span class="vol-summary-area">${escapeHtml(area)}</span>
        <span class="vol-summary-n" title="Voluntários aptos nesta área">${n}</span>
      </div>`
    )
    .join("");
  el.innerHTML = `
    <div class="vol-summary-head">
      <span class="vol-summary-total"><strong>${total}</strong> voluntário(s) no cadastro</span>
    </div>
    <div class="vol-summary-grid">${chips}</div>
    ${
      semArea
        ? `<p class="vol-summary-foot muted">${semArea} sem nenhuma área marcada (edite o voluntário para incluir).</p>`
        : ""
    }`;
}

/** Tons distintos para barras do dashboard de escalas. */
const STATS_BAR_HUES = [200, 280, 145, 32, 310, 172, 24, 265, 355, 125, 48, 220];

function statsBarStyle(i, count, max) {
  const pct = max > 0 && count > 0 ? Math.max(8, Math.round((count / max) * 100)) : 0;
  const h = STATS_BAR_HUES[i % STATS_BAR_HUES.length];
  return `--stats-pct: ${pct}%; --stats-bar: hsl(${h}, 62%, 48%); --stats-bar-end: hsl(${h}, 55%, 58%);`;
}

function volunteersListFromImportJson(parsed) {
  if (Array.isArray(parsed)) return parsed;
  if (parsed && Array.isArray(parsed.volunteers)) return parsed.volunteers;
  throw new Error(
    "Arquivo inválido: use o JSON exportado aqui (campo «volunteers») ou uma lista de objetos com nome, birth_date e areas."
  );
}

async function exportVolunteersJson() {
  const msg = $("#vol-backup-msg");
  if (msg) msg.classList.add("hidden");
  try {
    const r = await fetch("/api/volunteers/export.json");
    const text = await r.text();
    if (!r.ok) {
      let err = text;
      try {
        const j = JSON.parse(text);
        if (j.error) err = j.error;
      } catch {
        /* ignore */
      }
      throw new Error(err || r.statusText);
    }
    const blob = new Blob([text], { type: "application/json;charset=utf-8" });
    const cd = r.headers.get("Content-Disposition");
    let fname = "voluntarios.json";
    const m = cd && cd.match(/filename="([^"]+)"/i);
    if (m) fname = m[1];
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = fname;
    a.click();
    URL.revokeObjectURL(a.href);
    if (msg) showMsg(msg, "Exportação concluída (arquivo baixado).", true);
  } catch (e) {
    if (msg) showMsg(msg, e.message, false);
  }
}

async function onImportVolsFileChange(ev) {
  const msg = $("#vol-backup-msg");
  const input = ev.target;
  const file = input.files && input.files[0];
  if (!file) return;
  input.value = "";
  if (msg) msg.classList.add("hidden");
  try {
    const text = await file.text();
    const parsed = JSON.parse(text);
    const list = volunteersListFromImportJson(parsed);
    const mode = $("#import-vols-mode")?.value || "merge";
    const out = await api("/api/volunteers/import", {
      method: "POST",
      body: JSON.stringify({ volunteers: list, mode }),
    });
    await loadVolunteers();
    let t =
      out.mode === "replace"
        ? `Cadastro substituído: ${out.created} voluntário(s).`
        : `Importação: ${out.created} novo(s), ${out.updated} atualizado(s).`;
    if (msg) showMsg(msg, t, true);
  } catch (e) {
    if (msg) showMsg(msg, e.message, false);
  }
}

async function exportFullBackupJson() {
  const msg = $("#full-backup-msg");
  if (msg) msg.classList.add("hidden");
  try {
    const r = await fetch("/api/backup/full.json");
    const text = await r.text();
    if (!r.ok) {
      let err = text;
      try {
        const j = JSON.parse(text);
        if (j.error) err = j.error;
      } catch {
        /* ignore */
      }
      throw new Error(err || r.statusText);
    }
    const blob = new Blob([text], { type: "application/json;charset=utf-8" });
    const cd = r.headers.get("Content-Disposition");
    let fname = "escala_backup_completo.json";
    const m = cd && cd.match(/filename="([^"]+)"/i);
    if (m) fname = m[1];
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = fname;
    a.click();
    URL.revokeObjectURL(a.href);
    if (msg) showMsg(msg, "Backup completo baixado.", true);
  } catch (e) {
    if (msg) showMsg(msg, e.message, false);
  }
}

async function onImportFullBackupFileChange(ev) {
  const msg = $("#full-backup-msg");
  const input = ev.target;
  const file = input.files && input.files[0];
  if (!file) return;
  input.value = "";
  if (msg) msg.classList.add("hidden");
  try {
    const text = await file.text();
    const parsed = JSON.parse(text);
    if (parsed.format !== "sistema-escala-midia-full") {
      throw new Error(
        "Este ficheiro não é um backup completo (use «Baixar backup completo» desta ou de outra instância)."
      );
    }
    const ok = window.confirm(
      "Isto apaga TODO o estado atual nesta base (voluntários, escalas, disponibilidades, eventos extra, definições, etc.) e substitui pelo conteúdo deste ficheiro. Continuar?"
    );
    if (!ok) return;
    const out = await api("/api/backup/restore", {
      method: "POST",
      body: JSON.stringify(parsed),
    });
    await loadVolunteers();
    populateAvailVolunteer();
    await loadMonthData();
    await loadBirthdaysTab();
    const parts = [
      `${out.volunteers} voluntário(s)`,
      `${out.assignment} células de escala`,
      `${out.availability} disponibilidades`,
      `${out.extra_event} evento(s) extra`,
    ];
    if (msg) showMsg(msg, `Base restaurada: ${parts.join(", ")}.`, true);
  } catch (e) {
    if (msg) showMsg(msg, e.message, false);
  }
}

function renderVolunteers() {
  const ul = $("#volunteer-list");
  if (!ul) return;
  ul.innerHTML = "";
  for (const v of volunteers) {
    const li = document.createElement("li");
    const tags = (v.areas || [])
      .map((a) => `<span>${escapeHtml(a)}</span>`)
      .join("");
    const birthInfo = v.birth_date
      ? `<span class="muted"> · Nasc. ${escapeHtml(fmtBR(v.birth_date))}</span>`
      : `<span class="muted"> · sem data de nascimento</span>`;
    li.innerHTML = `
      <strong>${escapeHtml(v.name)}</strong>${birthInfo}
      <span class="area-tags">${tags || "<span class='muted'>sem áreas</span>"}</span>
      <button type="button" class="small secondary" data-edit="${v.id}">Editar</button>
      <button type="button" class="small danger" data-del="${v.id}">Excluir</button>
    `;
    ul.appendChild(li);
  }
  ul.querySelectorAll("[data-del]").forEach((b) =>
    b.addEventListener("click", () => delVolunteer(+b.dataset.del))
  );
  ul.querySelectorAll("[data-edit]").forEach((b) =>
    b.addEventListener("click", () => openEditVolunteer(+b.dataset.edit))
  );
}

function escapeHtml(s) {
  const d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
}

async function addVolunteer() {
  const name = $("#new-vol-name").value.trim();
  const msg = $("#vol-msg");
  if (!name) {
    showMsg(msg, "Informe o nome.", false);
    return;
  }
  const sel = $$("#new-vol-areas input:checked").map((i) => i.value);
  const birthEl = $("#new-vol-birth");
  const birth_date = birthEl && birthEl.value ? birthEl.value : null;
  try {
    await api("/api/volunteers", {
      method: "POST",
      body: JSON.stringify({ name, areas: sel, birth_date }),
    });
    $("#new-vol-name").value = "";
    if (birthEl) birthEl.value = "";
    $$("#new-vol-areas input").forEach((i) => (i.checked = false));
    showMsg(msg, "Voluntário cadastrado.", true);
    await loadVolunteers();
  } catch (e) {
    showMsg(msg, e.message, false);
  }
}

function openEditVolunteer(id) {
  const v = volunteers.find((x) => x.id === id);
  if (!v) return;
  $("#edit-vol-id").value = id;
  $("#edit-vol-name").value = v.name;
  const eb = $("#edit-vol-birth");
  if (eb) eb.value = v.birth_date || "";
  $$("#edit-vol-areas input").forEach((i) => {
    i.checked = (v.areas || []).includes(i.value);
  });
  $("#edit-modal").classList.remove("hidden");
}

function closeEdit() {
  $("#edit-modal").classList.add("hidden");
}

async function saveEditVolunteer() {
  const id = +$("#edit-vol-id").value;
  const name = $("#edit-vol-name").value.trim();
  const areasSel = $$("#edit-vol-areas input:checked").map((i) => i.value);
  const eb = $("#edit-vol-birth");
  const birth_date = eb && eb.value ? eb.value : null;
  const msg = $("#edit-msg");
  try {
    await api(`/api/volunteers/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ name, areas: areasSel, birth_date }),
    });
    showMsg(msg, "Salvo.", true);
    closeEdit();
    await loadVolunteers();
  } catch (e) {
    showMsg(msg, e.message, false);
  }
}

async function delVolunteer(id) {
  if (!confirm("Remover este voluntário?")) return;
  await api(`/api/volunteers/${id}`, { method: "DELETE" });
  await loadVolunteers();
}

function renderAreaCheckboxes(containerId) {
  const c = $(containerId);
  if (!c || !areas.length) return;
  c.innerHTML = areas
    .map(
      (a) => `
    <label class="chk"><input type="checkbox" value="${escapeHtml(a)}"/> ${escapeHtml(a)}</label>
  `
    )
    .join("");
}

function ymFromInputs() {
  const ym = $("#month-picker").value;
  if (!ym) return null;
  const [y, m] = ym.split("-").map(Number);
  return { year: y, month: m };
}

async function loadMonthData() {
  const ym = ymFromInputs();
  if (!ym) return;
  currentYear = ym.year;
  currentMonth = ym.month;
  await loadVolunteers();
  events = await api(`/api/month/${ym.year}/${ym.month}/events`);
  extras = await api(`/api/month/${ym.year}/${ym.month}/extras`);
  availability = await api(`/api/month/${ym.year}/${ym.month}/availability`);
  assignments = await api(`/api/month/${ym.year}/${ym.month}/assignments`);
  const opts = await api(`/api/month/${ym.year}/${ym.month}/options`);
  includeTraining = !!opts.include_training;
  const chkTr = $("#chk-include-training");
  if (chkTr) chkTr.checked = includeTraining;
  renderExtras();
  renderAvailabilityEditor();
  renderScheduleTable();
  await loadStats();
}

/** Texto "Nx ÁREA" para estatísticas por função (áreas já escapadas no HTML). */
function statsByAreaPartsHtml(byArea) {
  if (!byArea || !byArea.length) return "";
  return byArea
    .map(({ area, count }) => `${count}x ${escapeHtml(area)}`)
    .join(", ");
}

async function loadStats() {
  const ym = ymFromInputs();
  if (!ym) return;
  const chartEl = $("#stats-chart");
  const numEl = $("#stats-body");
  const neverWrap = $("#stats-never-wrap");
  const neverEl = $("#stats-never");
  const allAssignedEl = $("#stats-all-assigned");
  if (!chartEl || !numEl) return;

  const resetNeverUi = () => {
    if (neverWrap) neverWrap.classList.add("hidden");
    if (neverEl) neverEl.innerHTML = "";
    if (allAssignedEl) {
      allAssignedEl.classList.add("hidden");
      allAssignedEl.textContent = "";
    }
    renderWorshipAlertsInStats([]);
  };

  try {
    const raw = await api(`/api/stats/${ym.year}/${ym.month}`);
    const rows = Array.isArray(raw) ? raw : raw.assigned || [];
    const never = Array.isArray(raw) ? [] : raw.never_assigned || [];
    const worshipAlerts = Array.isArray(raw)
      ? computeWorshipAlerts()
      : raw.worship_alerts || [];
    const max = rows.reduce((m, r) => Math.max(m, r.count || 0), 0);

    resetNeverUi();

    if (!rows.length && !never.length) {
      chartEl.innerHTML =
        '<p class="muted stats-empty">Não há voluntários cadastrados ou ninguém entrou na escala neste mês.</p>';
      numEl.innerHTML = "";
      return;
    }

    if (!rows.length) {
      chartEl.innerHTML =
        '<p class="muted stats-empty">Ninguém foi escalado neste mês (cargos vazios ou escala não gerada).</p>';
    } else {
      chartEl.innerHTML = rows
        .map((r, i) => {
          const st = statsBarStyle(i, r.count, max);
          const parts = statsByAreaPartsHtml(r.by_area);
          const sub = parts
            ? `<div class="stats-chart-breakdown muted">${parts}</div>`
            : "";
          return `<div class="stats-chart-row" style="${st}">
          <div class="stats-chart-head">
            <div class="stats-chart-namecol">
              <span class="stats-chart-name">${escapeHtml(r.name)}</span>
              ${sub}
            </div>
            <span class="stats-chart-count">${r.count}</span>
          </div>
          <div class="stats-chart-track" role="presentation">
            <div class="stats-chart-fill"></div>
          </div>
        </div>`;
        })
        .join("");
    }

    numEl.innerHTML = rows.length
      ? rows
          .map((r) => {
            const parts = statsByAreaPartsHtml(r.by_area);
            const tail = parts ? ` <span class="stats-by-area-detail">(${parts})</span>` : "";
            return `<div class="stats-num-row"><span class="stats-num-name">${escapeHtml(
              r.name
            )}</span> — <strong class="stats-num-val">${r.count}</strong>${tail}</div>`;
          })
          .join("")
      : "";

    if (never.length && neverEl && neverWrap) {
      neverWrap.classList.remove("hidden");
      neverEl.innerHTML = `<ul class="stats-never-ul">${never
        .map((n) => `<li>${escapeHtml(n.name)}</li>`)
        .join("")}</ul>`;
    } else if (rows.length && allAssignedEl) {
      allAssignedEl.textContent =
        "Todos os voluntários cadastrados entram na escala pelo menos uma vez neste mês.";
      allAssignedEl.classList.remove("hidden");
    }

    renderWorshipAlertsInStats(
      worshipAlerts.length ? worshipAlerts : computeWorshipAlerts()
    );
  } catch {
    chartEl.innerHTML = "";
    numEl.innerHTML = "";
    resetNeverUi();
  }
}

function renderExtras() {
  const ul = $("#extras-list");
  if (!ul) return;
  ul.innerHTML = "";
  for (const ex of extras) {
    const li = document.createElement("li");
    li.className = "extra-row";
    li.innerHTML = `
      <span class="extra-row-date">${escapeHtml(ex.event_date)}</span>
      <input type="text" class="extra-row-lbl" data-eid="${ex.id}" value="${escapeHtml(ex.label || "")}" placeholder="Descrição" />
      <input type="text" class="extra-row-time" data-eid="${ex.id}" value="${escapeHtml(ex.event_time || "")}" placeholder="Horário" />
      <button type="button" class="small secondary" data-save="${ex.id}">Salvar</button>
      <button type="button" class="small danger" data-xid="${ex.id}">Remover</button>
    `;
    li.querySelector("[data-xid]").addEventListener("click", async () => {
      const ym = ymFromInputs();
      await api(`/api/month/${ym.year}/${ym.month}/extra-event/${ex.id}`, {
        method: "DELETE",
      });
      await loadMonthData();
    });
    li.querySelector("[data-save]").addEventListener("click", async () => {
      const ym = ymFromInputs();
      const lbl = li.querySelector(".extra-row-lbl").value.trim();
      const tim = li.querySelector(".extra-row-time").value.trim();
      if (!lbl) {
        alert("A descrição não pode ficar vazia.");
        return;
      }
      await api(`/api/month/${ym.year}/${ym.month}/extra-event/${ex.id}`, {
        method: "PATCH",
        body: JSON.stringify({ label: lbl, event_time: tim || null }),
      });
      await loadMonthData();
    });
    ul.appendChild(li);
  }
}

async function addExtraEvent() {
  const ym = ymFromInputs();
  const date = $("#extra-date").value;
  const label = $("#extra-label").value.trim();
  const msg = $("#month-msg");
  if (!ym || !date) {
    showMsg(msg, "Selecione o mês e a data do evento extra.", false);
    return;
  }
  if (!label) {
    showMsg(msg, "Informe a descrição do evento.", false);
    return;
  }
  try {
    const event_time = ($("#extra-time") && $("#extra-time").value.trim()) || "";
    await api(`/api/month/${ym.year}/${ym.month}/extra-event`, {
      method: "POST",
      body: JSON.stringify({ date, label, event_time: event_time || null }),
    });
    $("#extra-date").value = "";
    $("#extra-label").value = "";
    if ($("#extra-time")) $("#extra-time").value = "";
    showMsg(msg, "Evento adicionado.", true);
    await loadMonthData();
  } catch (e) {
    showMsg(msg, e.message, false);
  }
}

function renderAvailabilityEditor() {
  const wrap = $("#avail-editor");
  if (!wrap) return;
  const vid = +$("#avail-volunteer").value;
  if (!vid) {
    wrap.innerHTML = "<p class='muted'>Selecione um voluntário.</p>";
    return;
  }
  const av = availability[vid] || {};
  wrap.innerHTML = `
    <div class="avail-grid">
      ${events
        .map((ev) => {
          const checked = av[ev.date] === true ? "checked" : "";
          const br = fmtBR(ev.date);
          const wd = weekdayTimeBlockHtml(ev);
          return `<label class="chk avail-day-chk"><span class="avail-day-row"><input type="checkbox" data-d="${ev.date}" ${checked}/><span class="avail-day-text"><span class="avail-day-date">${br}</span><span class="avail-day-wd">${wd}</span></span></span></label>`;
        })
        .join("")}
    </div>
    <p style="margin-top:0.5rem;font-size:0.8rem;color:var(--muted)">
      Marque apenas os dias em que a pessoa pode servir. Em branco = não disponível para a montagem automática.
    </p>
  `;
  wrap.querySelectorAll("input[type=checkbox]").forEach((cb) => {
    cb.addEventListener("change", () => saveAvailabilityBatch(vid));
  });
}

function fmtBR(iso) {
  const [y, m, d] = iso.split("-").map(Number);
  return `${String(d).padStart(2, "0")}/${String(m).padStart(2, "0")}`;
}

/** Primeiro domingo do mês (AAAA-MM-DD), local. */
function firstSundayIsoInMonth(y, m) {
  for (let day = 1; day <= 7; day++) {
    const d = new Date(y, m - 1, day);
    if (d.getDay() === 0) {
      return `${y}-${String(m).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
    }
  }
  return null;
}

/**
 * Bloqueio: até 15 anos não vai a domingos (exceto 1º domingo — Santa Ceia).
 * Sem data de nascimento → não bloqueia.
 */
function teenSundayForbiddenVol(birthIso, eventIso) {
  if (!birthIso) return false;
  const [y, mo, da] = eventIso.split("-").map(Number);
  const ev = new Date(y, mo - 1, da);
  if (ev.getDay() !== 0) return false;
  const fs = firstSundayIsoInMonth(y, mo);
  if (eventIso === fs) return false;
  const [by, bm, bd] = birthIso.split("-").map(Number);
  const b = new Date(by, bm - 1, bd);
  let age = ev.getFullYear() - b.getFullYear();
  const md = ev.getMonth() - b.getMonth();
  if (md < 0 || (md === 0 && ev.getDate() < b.getDate())) age--;
  return age <= 15;
}

/** Dia da semana em português (data local a partir de AAAA-MM-DD). */
function isSundayIso(iso) {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d).getDay() === 0;
}

function isThursdayIso(iso) {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d).getDay() === 4;
}

/** Dia + horário para coluna Data: quinta em duas linhas para não quebrar no meio do horário. */
function weekdayTimeBlockHtml(ev) {
  const wd = weekdayLongPt(ev.date);
  const tr = ev.time_range;
  if (!tr) return escapeHtml(wd);
  if (isThursdayIso(ev.date)) {
    return `${escapeHtml(wd)}<br><span class="col-date-time">${escapeHtml(
      "(" + tr + ")"
    )}</span>`;
  }
  return escapeHtml(`${wd} (${tr})`);
}

function whenLineForManual(ev) {
  const wdM = weekdayLongPt(ev.date);
  if (!ev.time_range) return escapeHtml(wdM);
  if (isThursdayIso(ev.date)) {
    return `${escapeHtml(wdM)}<br><span class="manual-when-time">${escapeHtml(
      "(" + ev.time_range + ")"
    )}</span>`;
  }
  return escapeHtml(`${wdM} (${ev.time_range})`);
}

function weekdayLongPt(iso) {
  const [y, m, d] = iso.split("-").map(Number);
  const dt = new Date(y, m - 1, d);
  const names = [
    "Domingo",
    "Segunda-feira",
    "Terça-feira",
    "Quarta-feira",
    "Quinta-feira",
    "Sexta-feira",
    "Sábado",
  ];
  return names[dt.getDay()];
}

/**
 * Alertas: sem dia só para cultuar (espelha logic.detect_no_worship_day_alerts).
 * Não bloqueia escalação — apenas informa para revisão futura.
 */
function computeWorshipAlerts() {
  const eventDates = events.map((e) => e.date);
  if (!eventDates.length) return [];

  const eventSet = new Set(eventDates);
  const assignedBy = {};

  for (const ed of eventDates) {
    for (const a of areas) {
      const cell = assignments[ed] && assignments[ed][a];
      const vid = cell && cell.volunteer_id;
      if (vid != null && vid !== "") {
        const id = +vid;
        if (!assignedBy[id]) assignedBy[id] = new Set();
        assignedBy[id].add(ed);
      }
    }
  }

  const alerts = [];
  for (const [vidStr, assignedDates] of Object.entries(assignedBy)) {
    const vid = +vidStr;
    const v = volunteers.find((x) => x.id === vid);
    const name = (v && v.name) || `#${vid}`;

    if (assignedDates.size >= eventSet.size) {
      const n = eventDates.length;
      alerts.push({
        volunteer_id: vid,
        name,
        kind: "all_events",
        detail: `Escalada em todos os ${n} cultos do mês — nenhum dia só para cultuar nesta escala.`,
      });
      continue;
    }

    const availDates = eventDates.filter(
      (d) => (availability[vid] || {})[d] === true
    );
    if (
      availDates.length &&
      availDates.every((d) => assignedDates.has(d))
    ) {
      const n = availDates.length;
      alerts.push({
        volunteer_id: vid,
        name,
        kind: "all_available",
        detail: `Escalada em todos os ${n} dia(s) em que marcou disponibilidade — vale garantir outro dia para cultuar.`,
      });
    }
  }

  alerts.sort((a, b) => (a.name || "").localeCompare(b.name || "", "pt"));
  return alerts;
}

function worshipAlertsBannerHtml(alerts) {
  if (!alerts.length) return "";
  const items = alerts
    .map(
      (a) =>
        `<li><strong>${escapeHtml(a.name)}</strong> — ${escapeHtml(a.detail)}</li>`
    )
    .join("");
  return `<div class="schedule-worship-banner" role="status">
    <p><strong>Alerta (tempo para cultuar):</strong> estas pessoas ficaram sem nenhum culto só para cultuar nesta escala. Isso não impede a escalação — use como lembrete para ajustar nos próximos meses quando houver mais gente.</p>
    <ul class="schedule-worship-list">${items}</ul>
  </div>`;
}

function renderWorshipAlertsInStats(alerts) {
  const wrap = $("#stats-worship-wrap");
  const list = $("#stats-worship-list");
  if (!wrap || !list) return;
  if (!alerts.length) {
    wrap.classList.add("hidden");
    list.innerHTML = "";
    return;
  }
  wrap.classList.remove("hidden");
  list.innerHTML = alerts
    .map(
      (a) =>
        `<li><strong>${escapeHtml(a.name)}</strong> — ${escapeHtml(a.detail)}</li>`
    )
    .join("");
}

/** Voluntários escalados mais de uma vez no mesmo culto (mesma data). */
function volunteerIdsDuplicatedOnDate(eventDate) {
  const counts = {};
  for (const a of areas) {
    const cell = assignments[eventDate] && assignments[eventDate][a];
    const vid = cell && cell.volunteer_id;
    if (vid != null && vid !== "") {
      const id = +vid;
      counts[id] = (counts[id] || 0) + 1;
    }
  }
  const dup = new Set();
  for (const [vid, n] of Object.entries(counts)) {
    if (n > 1) dup.add(+vid);
  }
  return dup;
}

/** Problemas na célula (disponibilidade, aptidão, duplicidade no culto). */
function assignmentCellIssues(eventDate, area, volunteerId) {
  const issues = [];
  if (volunteerId == null || volunteerId === "") return issues;
  const id = +volunteerId;
  if (Number.isNaN(id)) return issues;

  const v = volunteers.find((x) => x.id === id);
  if (!v) {
    issues.push("Voluntário não encontrado no cadastro");
    return issues;
  }

  const apt = v.areas || [];
  if (!apt.includes(area)) {
    issues.push("Sem aptidão nesta área");
  }

  const avMap = availability[id] || {};
  if (avMap[eventDate] !== true) {
    issues.push("Sem disponibilidade marcada neste dia");
  }

  const dups = volunteerIdsDuplicatedOnDate(eventDate);
  if (dups.has(id)) {
    issues.push("Mesma pessoa em mais de uma função neste culto");
  }

  if (teenSundayForbiddenVol(v.birth_date, eventDate)) {
    issues.push(
      "Até 15 anos: não escalar aos domingos (exceto 1º domingo — Santa Ceia)"
    );
  }

  return issues;
}

async function saveAvailabilityBatch(vid) {
  const ym = ymFromInputs();
  const wrap = $("#avail-editor");
  const dates = {};
  wrap.querySelectorAll("input[data-d]").forEach((cb) => {
    dates[cb.dataset.d] = cb.checked;
  });
  await api(`/api/month/${ym.year}/${ym.month}/availability`, {
    method: "POST",
    body: JSON.stringify({ volunteer_id: vid, dates }),
  });
  availability = await api(`/api/month/${ym.year}/${ym.month}/availability`);
}

async function fillRegularByWhich(which, available = true) {
  const ym = ymFromInputs();
  const vid = +$("#avail-volunteer").value;
  if (!vid) {
    alert("Selecione um voluntário.");
    return;
  }
  await api(`/api/month/${ym.year}/${ym.month}/availability/fill-regular`, {
    method: "POST",
    body: JSON.stringify({ volunteer_id: vid, available, which }),
  });
  await loadMonthData();
}

async function importCsv(e) {
  const f = e.target.files?.[0];
  if (!f) return;
  const ym = ymFromInputs();
  const fd = new FormData();
  fd.append("file", f);
  const msg = $("#import-msg");
  try {
    const r = await fetch(`/api/month/${ym.year}/${ym.month}/import-csv`, {
      method: "POST",
      body: fd,
    });
    const data = await r.json();
    if (!r.ok) throw new Error(data.error || r.statusText);
    const errTxt = (data.errors || []).slice(0, 5).join(" ");
    showMsg(
      msg,
      `Importadas ${data.imported} linhas. Ignoradas: ${data.skipped}. ${errTxt}`,
      true
    );
    await loadMonthData();
  } catch (err) {
    showMsg(msg, err.message, false);
  }
  e.target.value = "";
}

async function generateSchedule() {
  const ym = ymFromInputs();
  const msg = $("#month-msg");
  try {
    await api(`/api/month/${ym.year}/${ym.month}/generate`, { method: "POST" });
    showMsg(msg, "Escala gerada. Revise e ajuste manualmente se precisar.", true);
    await loadMonthData();
  } catch (e) {
    showMsg(msg, e.message, false);
  }
}

function renderScheduleTable() {
  const host = $("#schedule-preview");
  if (!host) return;
  const ym = ymFromInputs();
  const title = ym
    ? `Escala de comunicação — ${String(ym.month).padStart(2, "0")}/${ym.year}`
    : "Escala";

  let invalidCount = 0;

  let html = `<h3 style="margin:0 0 8px;font-size:14px">${escapeHtml(title)}</h3>`;
  if (includeTraining) {
    html += `<p class="schedule-training-banner">${escapeHtml(TRAINING_NOTE_HTML)}</p>`;
  }
  html += "<table><thead><tr>";
  html += '<th class="col-date">Data</th><th class="col-event">Evento</th>';
  for (const a of areas) {
    const cls = a === "RESPONSAVEL" ? " area-resp" : "";
    html += `<th class="${cls.trim()}">${escapeHtml(a)}</th>`;
  }
  html += "</tr></thead><tbody>";

  for (const ev of events) {
    html += "<tr>";
    html += `<td class="col-date">${escapeHtml(fmtBR(ev.date))}<br><span class="col-date-wd">${weekdayTimeBlockHtml(ev)}</span></td>`;
    const trainExtra =
      includeTraining && isSundayIso(ev.date)
        ? `<span class="training-note">${escapeHtml(TRAINING_NOTE_HTML)}</span>`
        : "";
    html += `<td class="col-event">${escapeHtml(ev.label)}${trainExtra}</td>`;
    for (const a of areas) {
      const cell = (assignments[ev.date] && assignments[ev.date][a]) || {};
      const vid = cell.volunteer_id;
      const empty = vid == null || vid === "";
      const inner = empty
        ? `<span class="schedule-cell-placeholder">${escapeHtml(
            EMPTY_SCHEDULE_PLACEHOLDER
          )}</span>`
        : escapeHtml(cell.name || "—");
      const issues = assignmentCellIssues(ev.date, a, vid);
      const inv = issues.length > 0;
      if (inv) invalidCount += 1;
      const baseCls = a === "RESPONSAVEL" ? "area-resp" : "";
      const cls = [baseCls, inv ? "cell-invalid" : ""].filter(Boolean).join(" ");
      const tip = inv ? escapeHtml(issues.join(" · ")) : "";
      html += `<td class="${cls}" ${tip ? `title="${tip}"` : ""}>${inner}</td>`;
    }
    html += "</tr>";
  }
  html += "</tbody></table>";
  if (invalidCount > 0) {
    html += `<p class="schedule-invalid-banner" role="alert"><strong>${invalidCount} célula(s) com problema.</strong> Passe o mouse na célula vermelha para ver o motivo (disponibilidade, aptidão ou duas funções no mesmo culto).</p>`;
  }
  const worshipAlerts = computeWorshipAlerts();
  if (worshipAlerts.length) {
    html += worshipAlertsBannerHtml(worshipAlerts);
  }
  host.innerHTML = html;
  renderManualEditor();
}

function renderManualEditor() {
  const ed = $("#manual-editor");
  if (!ed) return;
  let h =
    "<p style='font-size:0.85rem;color:var(--muted)'>Ajuste manual por célula (opcional):</p>";
  for (const ev of events) {
    const trainManual =
      includeTraining && isSundayIso(ev.date)
        ? `<p class="manual-training-hint">${escapeHtml(TRAINING_NOTE_HTML)}</p>`
        : "";
    h += `<div class="panel" style="padding:0.6rem"><strong>${escapeHtml(fmtBR(ev.date))}</strong> <span style="color:var(--muted);font-weight:500">${whenLineForManual(ev)}</span> — ${escapeHtml(ev.label)}${trainManual}<div class="row" style="margin-top:0.5rem;align-items:flex-start">`;
    for (const a of areas) {
      const cell = (assignments[ev.date] && assignments[ev.date][a]) || {};
      const issues = assignmentCellIssues(ev.date, a, cell.volunteer_id);
      const inv = issues.length > 0;
      const tip = inv ? escapeHtml(issues.join(" · ")) : "";
      const lblCls = inv ? " select-invalid" : "";
      const opts =
        '<option value="">— vazio —</option>' +
        volunteers
          .map((v) => {
            const dis =
              teenSundayForbiddenVol(v.birth_date, ev.date) &&
              cell.volunteer_id !== v.id
                ? " disabled"
                : "";
            const sel = cell.volunteer_id === v.id ? "selected" : "";
            const title = teenSundayForbiddenVol(v.birth_date, ev.date)
              ? ' title="Até 15 anos: não neste domingo (exceto 1º domingo)"'
              : "";
            return `<option value="${v.id}" ${sel}${dis}${title}>${escapeHtml(v.name)}</option>`;
          })
          .join("");
      h += `<label class="${lblCls.trim()}" ${tip ? `title="${tip}"` : ""}><span>${escapeHtml(a)}</span><select data-d="${escapeHtml(ev.date)}" data-a="${escapeHtml(a)}">${opts}</select></label>`;
    }
    h += "</div></div>";
  }
  ed.innerHTML = h;
  ed.querySelectorAll("select").forEach((sel) => {
    sel.addEventListener("change", async () => {
      const ym = ymFromInputs();
      const volunteer_id = sel.value ? +sel.value : null;
      try {
        await api(`/api/month/${ym.year}/${ym.month}/assignment`, {
          method: "PATCH",
          body: JSON.stringify({
            event_date: sel.dataset.d,
            area: sel.dataset.a,
            volunteer_id,
          }),
        });
        assignments = await api(`/api/month/${ym.year}/${ym.month}/assignments`);
        renderScheduleTable();
        await loadStats();
      } catch (e) {
        alert(e.message);
        await loadMonthData();
      }
    });
  });
}

function downloadPdf() {
  const ym = ymFromInputs();
  window.open(`/api/month/${ym.year}/${ym.month}/export.pdf`, "_blank");
}

async function downloadPng() {
  if (typeof window.html2canvas !== "function") {
    alert("Biblioteca de imagem não carregou. Verifique a internet e recarregue a página.");
    return;
  }
  const canvas = await window.html2canvas($("#schedule-preview"), {
    scale: 2,
    backgroundColor: "#ffffff",
    logging: false,
  });
  const a = document.createElement("a");
  a.href = canvas.toDataURL("image/png");
  a.download = `escala_${currentYear}_${String(currentMonth).padStart(2, "0")}.png`;
  a.click();
}

async function downloadJpg() {
  if (typeof window.html2canvas !== "function") {
    alert("Biblioteca de imagem não carregou. Verifique a internet e recarregue a página.");
    return;
  }
  const canvas = await window.html2canvas($("#schedule-preview"), {
    scale: 2,
    backgroundColor: "#ffffff",
    logging: false,
  });
  const a = document.createElement("a");
  a.href = canvas.toDataURL("image/jpeg", 0.92);
  a.download = `escala_${currentYear}_${String(currentMonth).padStart(2, "0")}.jpg`;
  a.click();
}

function initMonthPicker() {
  const mp = $("#month-picker");
  if (!mp) return;
  const d = new Date();
  mp.value = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

async function loadBirthdaysTab() {
  const setMsg = $("#birthdays-settings-msg");
  const notifyMsg = $("#birthdays-notify-msg");
  if (setMsg) setMsg.classList.add("hidden");
  if (notifyMsg) notifyMsg.classList.add("hidden");
  try {
    const s = await api("/api/settings");
    const inp = $("#discord-webhook");
    const hint = $("#discord-webhook-env-hint");
    if (inp) {
      inp.value = s.discord_webhook_url || "";
      inp.disabled = s.discord_webhook_source === "env";
    }
    if (hint) hint.classList.toggle("hidden", s.discord_webhook_source !== "env");
  } catch (e) {
    if (setMsg) showMsg(setMsg, e.message, false);
  }
  await refreshBirthdaysTable();
}

async function refreshBirthdaysTable() {
  const wrap = $("#birthdays-table-wrap");
  if (!wrap) return;
  const days = +($("#birthdays-window")?.value || 365);
  wrap.innerHTML = '<p class="muted">Carregando…</p>';
  try {
    const data = await api(`/api/birthdays/upcoming?days=${days}`);
    const items = data.items || [];
    if (!items.length) {
      wrap.innerHTML =
        '<p class="muted">Nenhum aniversário nesta janela. Cadastre datas de nascimento em Voluntários.</p>';
      return;
    }
    const rows = items
      .map((it) => {
        const tag = it.is_today
          ? ' <span class="birthday-today-badge">hoje</span>'
          : "";
        const when =
          it.days_until === 0
            ? "hoje"
            : it.days_until === 1
              ? "amanhã"
              : `em ${it.days_until} dias`;
        return `<tr class="${it.is_today ? "birthday-today-row" : ""}">
          <td><strong>${escapeHtml(it.name)}</strong>${tag}</td>
          <td>${escapeHtml(fmtBR(it.next_birthday))} · ${escapeHtml(it.weekday)}</td>
          <td>${it.turning_age}</td>
          <td>${when}</td>
        </tr>`;
      })
      .join("");
    wrap.innerHTML = `
      <table class="birthdays-table">
        <thead>
          <tr><th>Nome</th><th>Próximo aniversário</th><th>Completa (anos)</th><th>Quando</th></tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>`;
  } catch (e) {
    wrap.innerHTML = `<p class="message err">${escapeHtml(e.message)}</p>`;
  }
}

async function saveDiscordWebhook() {
  const inp = $("#discord-webhook");
  const msg = $("#birthdays-settings-msg");
  if (!inp || !msg) return;
  if (inp.disabled) {
    showMsg(
      msg,
      "O webhook está definido pela variável DISCORD_WEBHOOK_URL no servidor. Remova-a no painel (ex.: Render) para editar aqui.",
      false
    );
    return;
  }
  try {
    await api("/api/settings", {
      method: "PATCH",
      body: JSON.stringify({ discord_webhook_url: inp.value.trim() }),
    });
    showMsg(msg, "Webhook salvo.", true);
  } catch (e) {
    showMsg(msg, e.message, false);
  }
}

async function notifyBirthdaysDiscord(force) {
  const msg = $("#birthdays-notify-msg");
  if (!msg) return;
  msg.classList.add("hidden");
  try {
    const out = await api("/api/birthdays/notify-today", {
      method: "POST",
      body: JSON.stringify({ force: !!force }),
    });
    const sent = (out.sent || []).length;
    const skip = (out.skipped_duplicate || []).length;
    let t = "";
    if (sent) t += `Enviado para: ${out.sent.join(", ")}. `;
    if (skip && !force) t += `Já enviado antes neste ano (ignorado): ${out.skipped_duplicate.join(", ")}. `;
    if (!sent && !skip) t = "Ninguém faz aniversário hoje (ou não há data cadastrada).";
    showMsg(msg, t.trim(), true);
  } catch (e) {
    showMsg(msg, e.message, false);
  }
}

function initThemeToggle() {
  const btn = document.getElementById("theme-toggle");
  if (!btn) return;
  btn.addEventListener("click", () => {
    const html = document.documentElement;
    const cur = html.getAttribute("data-theme") === "light" ? "light" : "dark";
    const next = cur === "light" ? "dark" : "light";
    html.setAttribute("data-theme", next);
    try {
      localStorage.setItem("theme", next);
    } catch {
      /* ignore */
    }
  });
}

document.addEventListener("DOMContentLoaded", async () => {
  initThemeToggle();
  initMonthPicker();
  await loadAreas();
  renderAreaCheckboxes("#new-vol-areas");
  renderAreaCheckboxes("#edit-vol-areas");
  await loadVolunteers();

  $("#btn-add-vol")?.addEventListener("click", addVolunteer);
  $("#btn-export-vols")?.addEventListener("click", exportVolunteersJson);
  $("#btn-import-vols")?.addEventListener("click", () => $("#import-vols-file")?.click());
  $("#import-vols-file")?.addEventListener("change", onImportVolsFileChange);
  $("#btn-full-backup-download")?.addEventListener("click", exportFullBackupJson);
  $("#btn-full-backup-restore")?.addEventListener("click", () =>
    $("#import-full-backup-file")?.click()
  );
  $("#import-full-backup-file")?.addEventListener("change", onImportFullBackupFileChange);
  $("#btn-save-edit")?.addEventListener("click", saveEditVolunteer);
  $("#btn-close-edit")?.addEventListener("click", closeEdit);
  $("#month-picker")?.addEventListener("change", loadMonthData);
  $("#btn-refresh-month")?.addEventListener("click", loadMonthData);
  $("#chk-include-training")?.addEventListener("change", async (e) => {
    const ym = ymFromInputs();
    if (!ym) return;
    const v = e.target.checked;
    try {
      await api(`/api/month/${ym.year}/${ym.month}/options`, {
        method: "PATCH",
        body: JSON.stringify({ include_training: v }),
      });
      includeTraining = v;
      renderScheduleTable();
    } catch (err) {
      e.target.checked = !v;
      alert(err.message);
    }
  });
  $("#btn-add-extra")?.addEventListener("click", addExtraEvent);
  $("#btn-gen")?.addEventListener("click", generateSchedule);
  $("#btn-fill-sundays")?.addEventListener("click", () => fillRegularByWhich("sunday", true));
  $("#btn-fill-thursdays")?.addEventListener("click", () => fillRegularByWhich("thursday", true));
  $("#btn-clear-sundays")?.addEventListener("click", () => fillRegularByWhich("sunday", false));
  $("#btn-clear-thursdays")?.addEventListener("click", () => fillRegularByWhich("thursday", false));
  $("#avail-volunteer")?.addEventListener("change", renderAvailabilityEditor);
  $("#csv-file")?.addEventListener("change", importCsv);
  $("#btn-pdf")?.addEventListener("click", downloadPdf);
  $("#btn-png")?.addEventListener("click", downloadPng);
  $("#btn-jpg")?.addEventListener("click", downloadJpg);

  $$("nav.tabs button").forEach((b) =>
    b.addEventListener("click", () => {
      tab(b.dataset.tab);
      if (b.dataset.tab === "birthdays") loadBirthdaysTab();
    })
  );

  $("#btn-save-webhook")?.addEventListener("click", saveDiscordWebhook);
  $("#btn-birthdays-refresh")?.addEventListener("click", refreshBirthdaysTable);
  $("#birthdays-window")?.addEventListener("change", refreshBirthdaysTable);
  $("#btn-birthdays-notify")?.addEventListener("click", () => notifyBirthdaysDiscord(false));
  $("#btn-birthdays-notify-force")?.addEventListener("click", () => notifyBirthdaysDiscord(true));

  await loadMonthData();
});
