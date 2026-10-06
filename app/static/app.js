/* Job Classifier dashboard — vanilla JS, no build step. */

const $ = (sel) => document.querySelector(sel);

// Pydantic validation errors arrive as `detail: [{msg, loc}, …]`; a plain
// handler would fall back to `res.statusText` ("Unprocessable Content").
function detailMessage(body, res) {
  const detail = body.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => (item && item.msg ? String(item.msg) : ""))
      .filter(Boolean);
    if (messages.length) return messages.join(" · ");
  }
  return res.statusText || `HTTP ${res.status}`;
}

async function getJSON(url, options) {
  const res = await fetch(url, options);
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(detailMessage(body, res));
  return body;
}

// Job data is untrusted (scraped text): everything goes through esc() before HTML.
function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
  );
}

function safeUrl(url) {
  return /^https?:\/\//i.test(String(url || "")) ? url : "";
}

// posted_at arrives in three shapes: `YYYY-MM-DD` (GeekHunter detail, Indeed),
// a full ISO timestamp (Gupy) and relative text (`Publicada há 5 dias`).
// Only the ISO timestamp is normalized — anything else is shown as-is.
function formatPostedAt(value) {
  const raw = String(value ?? "").trim();
  const isoDate = raw.match(/^\d{4}-\d{2}-\d{2}T/);
  return isoDate ? raw.slice(0, 10) : raw;
}

async function loadHealth() {
  const badge = $("#backend");
  try {
    const health = await getJSON("/health");
    const classifier = health.classifier || {};
    let label = classifier.backend || "?";
    if (classifier.backend === "laya") {
      label = classifier.laya_ready
        ? `Laya · ${classifier.device}`
        : "Laya · carregando modelo…";
    }
    const sources = (health.sources || []).join(", ");
    const state = `backend ativa: ${label}`;
    badge.textContent = sources ? `${state} · ${sources}` : state;
    badge.title =
      "Configuração do processo em execução. O rodapé de cada card mostra a " +
      "backend que classificou aquele job — podem diferir." +
      (sources ? ` Fontes: ${sources}.` : "");
    badge.className = "badge " + (classifier.backend === "heuristic" ? "warn" : "ok");
  } catch (err) {
    badge.textContent = "API offline";
    badge.className = "badge bad";
  }
}

function filterQuery() {
  const params = new URLSearchParams({ limit: "100" });
  const source = $("#f-source").value;
  const match = $("#f-match").value;
  const remote = $("#f-remote").value;
  const location = $("#f-location").value.trim();
  const score = $("#f-score").value;
  const query = $("#f-query").value.trim();
  if (source) params.set("source", source);
  if (match) params.set("match", match);
  if (remote) params.set("remote", remote);
  if (location) params.set("location", location);
  if (score !== "") params.set("min_score", score);
  if (query) params.set("query", query);
  return params.toString();
}

function probabilityRow(probabilities) {
  const order = ["high", "medium", "low"];
  const chips = order
    .filter((key) => probabilities[key] !== undefined)
    .map(
      (key) =>
        `<span class="prob ${key}">${key} ${(probabilities[key] * 100).toFixed(0)}%</span>`
    )
    .join("");
  return `<div class="probs">${chips}</div>`;
}

function card(job) {
  const decision = job.decision || {};
  const probabilities = (decision.choice && decision.choice.probabilities) || null;
  const laya = decision.laya || null;
  const url = safeUrl(job.url);
  const reasons = (job.reasons || [])
    .map((reason) => `<li>${esc(reason)}</li>`)
    .join("");
  const gapList = job.gaps || [];
  const gaps = gapList.map((gap) => `<li>${esc(gap)}</li>`).join("");
  const score = Number(job.score);
  const scoreLabel = Number.isFinite(score) ? score.toFixed(1) : "—";

  // Low match: show prominent indicator with reason
  const isLow = job.match === "low";
  const lowReason = isLow && gapList.length > 0
    ? `<div class="low-indicator">⚠️ ${esc(gapList[0])}</div>`
    : "";

  return `
  <article class="card${isLow ? " low-match" : ""}" data-source="${esc(job.source || "linkedin")}" data-source-id="${esc(job.source_id || "")}">
    <div class="card-head">
      <h2>${
        url
          ? `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(job.title)}</a>`
          : esc(job.title)
      }</h2>
      <span class="match ${esc(job.match || "unknown")}">${esc(job.match || "?")}</span>
    </div>
    <div class="meta"><span class="source-chip" data-source="${esc(job.source || "linkedin")}">${esc(job.source || "linkedin")}</span> ${esc(job.company || "—")} · ${esc(job.location || "—")}${
    job.remote ? " · remoto" : ""
  }${job.posted_at ? " · " + esc(formatPostedAt(job.posted_at)) : ""}</div>
    <div class="score-row">
      <div class="score-bar"><span style="width:${Math.max(0, Math.min(100, score || 0))}%"></span></div>
      <b>${scoreLabel}</b>
    </div>
    ${probabilities ? probabilityRow(probabilities) : ""}
    ${lowReason}
    <button type="button" class="add-btn" data-source="${esc(job.source || "linkedin")}" data-source-id="${esc(job.source_id || "")}">+ Add</button>
    <details>
      <summary>Detalhes</summary>
      ${reasons ? `<h3>Motivos</h3><ul class="reasons">${reasons}</ul>` : ""}
      ${gaps ? `<h3>Gaps</h3><ul class="gaps">${gaps}</ul>` : ""}
      ${
        laya
          ? `<p class="laya">backend ${esc(laya.backend)} · modelo ${esc(laya.model)} · ${esc(laya.latency_ms)} ms</p>`
          : ""
      }
    </details>
  </article>`;
}

async function loadJobs() {
  const box = $("#jobs");
  box.innerHTML = "<p class='empty'>Carregando…</p>";
  try {
    const data = await getJSON(`/jobs?${filterQuery()}`);
    $("#total").textContent = `${data.total} vaga(s)`;
    if (!data.items.length) {
      box.innerHTML =
        "<p class='empty'>Nenhuma vaga. Use <b>Buscar e classificar</b> acima.</p>";
      return;
    }
    box.innerHTML = data.items.map(card).join("");
  } catch (err) {
    box.innerHTML = `<p class="empty">Erro ao carregar: ${esc(err.message)}</p>`;
  }
}

async function runSync(event) {
  event.preventDefault();
  const button = $("#sync-btn");
  const status = $("#sync-status");
  const source = $("#source").value;
  const keywords = $("#keywords").value
    .split(",")
    .map((word) => word.trim())
    .filter(Boolean);
  const sourceLabel = $("#source").selectedOptions[0].textContent;

  button.disabled = true;
  status.textContent = `Buscando em ${sourceLabel}… (coleta + classificação)`;
  try {
    const result = await getJSON("/jobs/sync", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        source,
        keywords,
        location: $("#location").value || "Brazil",
        limit: Number($("#limit").value) || 10,
        hours_old: Number($("#hours-old").value),
        fetch_details: true,
      }),
    });
    const failed = Object.entries(result.errors || {});
    status.textContent =
      `${result.synced} vaga(s) sincronizada(s)` +
      (failed.length
        ? ` · falha em ${failed.map(([name]) => name).join(", ")}`
        : "");
    await loadJobs();
  } catch (err) {
    status.textContent = `Erro: ${err.message}`;
  } finally {
    button.disabled = false;
  }
}

// ── Hash router ──────────────────────────────────────────────────────────────

// Páginas de primeiro nível. Perfil e Dados deixaram de ser páginas: são abas
// dentro de Configurações (`#/configuracoes/<tab>`). Rotas antigas (`#/perfil`,
// `#/dados`) e hashes desconhecidos caem em "vagas" (CA10).
const PAGES = ["vagas", "kanban", "configuracoes"];
const TABS = ["perfil", "dados"];

// Caminho cru do hash sem "#/" — usado para o deep-link da tab e para marcar
// a sidebar pelo prefixo da rota ("#/configuracoes/perfil" também é
// Configurações).
function hashPath() {
  return window.location.hash.replace(/^#\/?/, "");
}

function currentRoute() {
  // "configuracoes/dados" → "configuracoes"; sub-rotas colapsam na página.
  const route = hashPath().split("/")[0];
  return PAGES.includes(route) ? route : "vagas";
}

// Segmento após "#/configuracoes/"; default "perfil" (hash sem sub-rota,
// barra final ou tab desconhecida).
function currentTab() {
  const match = hashPath().match(/^configuracoes\/([^/?#]*)/);
  return TABS.includes(match ? match[1] : "") ? match[1] : "perfil";
}

// Aba visível dentro de #page-configuracoes (painéis + aria-selected).
function showTab(tab) {
  for (const name of TABS) {
    const panel = $(`#tab-${name}`);
    if (panel) panel.hidden = name !== tab;
    const btn = document.querySelector(`.tab-btn[data-tab="${name}"]`);
    if (btn) btn.setAttribute("aria-selected", String(name === tab));
  }
}

function showPage(route) {
  for (const page of PAGES) {
    const el = $(`#page-${page}`);
    if (el) el.hidden = page !== route;
  }
  const path = hashPath();
  document.querySelectorAll(".sidebar-link").forEach((link) => {
    const target = (link.getAttribute("href") || "").replace(/^#\/?/, "");
    // Prefixo, não igualdade exata: "#/configuracoes/perfil" e
    // "#/configuracoes/dados" também marcam Configurações. Hash vazio,
    // desconhecido ou rota antiga já colapsou em "vagas".
    const isActive =
      target === route &&
      (route === "vagas" || path === target || path.startsWith(`${target}/`));
    link.classList.toggle("active", isActive);
    if (isActive) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  });
  if (route === "configuracoes") showTab(currentTab());
}

function navigate() {
  const route = currentRoute();
  showPage(route); // showPage já aplica a tab visível em Configurações
  if (route === "configuracoes") {
    if (currentTab() === "dados") loadDataCounts();
    else loadProfile();
  }
  if (route === "kanban") loadKanban();
}

// Troca de tab: só mexe no hash — quem recarrega é o hashchange → navigate().
// Tab já visível com hash já alvo: retorna sem nada (sem loop, sem re-fetch).
function selectTab(tab) {
  if (!TABS.includes(tab)) return;
  if (currentRoute() === "configuracoes" && currentTab() === tab) return;
  window.location.hash = `#/configuracoes/${tab}`;
}

// ── Profile page ─────────────────────────────────────────────────────────────

function textareaToList(el) {
  return el.value
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
}

function listToTextarea(items) {
  return (items || []).join("\n");
}

async function loadProfile() {
  // A aba Perfil abre aqui (navigate → loadProfile): o currículo segue o
  // mesmo gatilho, sem mexer no roteador de hash (item 11).
  loadCurriculum();
  const status = $("#profile-status");
  status.textContent = "";
  try {
    const profile = await getJSON("/profile");
    $("#p-name").value = profile.name || "";
    $("#p-titles").value = listToTextarea(profile.titles);
    $("#p-seniority").value = listToTextarea(profile.seniority);
    $("#p-locations").value = listToTextarea(profile.locations);
    $("#p-skills").value = listToTextarea(profile.skills);
    $("#p-focus").value = listToTextarea(profile.focus);
    $("#p-exclusions").value = listToTextarea(profile.exclusions);
    $("#p-remote").checked = Boolean(profile.remote_required);
  } catch (err) {
    status.textContent = `Erro ao carregar perfil: ${err.message}`;
    status.className = "form-status error";
  }
}

async function saveProfile(event) {
  event.preventDefault();
  const status = $("#profile-status");
  status.className = "form-status";
  status.textContent = "Salvando…";
  const payload = {
    name: $("#p-name").value.trim(),
    titles: textareaToList($("#p-titles")),
    seniority: textareaToList($("#p-seniority")),
    locations: textareaToList($("#p-locations")),
    remote_required: $("#p-remote").checked,
    skills: textareaToList($("#p-skills")),
    focus: textareaToList($("#p-focus")),
    exclusions: textareaToList($("#p-exclusions")),
  };
  try {
    await getJSON("/profile", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    status.textContent = "Perfil salvo com sucesso.";
    status.className = "form-status ok";
  } catch (err) {
    status.textContent = `Erro: ${err.message}`;
    status.className = "form-status error";
  }
}

// ── Curriculum (Configurações → aba Perfil) ────────────────────────────────

async function loadCurriculum() {
  const status = $("#curriculum-status");
  status.textContent = "";
  try {
    const data = await getJSON("/curriculum");
    $("#curriculum-md").value = data.content || "";
  } catch (err) {
    status.textContent = `Erro ao carregar currículo: ${err.message}`;
    status.className = "form-status error";
  }
}

async function saveCurriculum(event) {
  event.preventDefault();
  const status = $("#curriculum-status");
  status.className = "form-status";
  status.textContent = "Salvando…";
  try {
    await getJSON("/curriculum", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content: $("#curriculum-md").value }),
    });
    status.textContent = "Currículo salvo com sucesso.";
    status.className = "form-status ok";
  } catch (err) {
    status.textContent = `Erro: ${err.message}`;
    status.className = "form-status error";
  }
}

// ── Data page ────────────────────────────────────────────────────────────────

const SOURCES = ["linkedin", "geekhunter", "gupy", "indeed", "glassdoor"];

async function loadDataCounts() {
  const totalEl = $("#data-total");
  const countsEl = $("#source-counts");
  totalEl.textContent = "…";
  countsEl.innerHTML = "";
  try {
    const totalData = await getJSON("/jobs?limit=1");
    totalEl.textContent = String(totalData.total);
  } catch (err) {
    totalEl.textContent = "erro";
  }
  for (const source of SOURCES) {
    try {
      const data = await getJSON(`/jobs?source=${source}&limit=1`);
      const row = document.createElement("div");
      row.className = "source-count";
      row.innerHTML = `<span class="source-label">${esc(source)}</span><span class="source-value">${data.total}</span>`;
      countsEl.appendChild(row);
    } catch {
      const row = document.createElement("div");
      row.className = "source-count";
      row.innerHTML = `<span class="source-label">${esc(source)}</span><span class="source-value">erro</span>`;
      countsEl.appendChild(row);
    }
  }
}

async function cleanJobs() {
  if (!window.confirm("Apagar todas as vagas do banco?")) return;
  try {
    await getJSON("/jobs", { method: "DELETE" });
    await loadDataCounts();
    await loadJobs();
  } catch (err) {
    alert(`Erro ao limpar vagas: ${err.message}`);
  }
}

// ── Kanban page ──────────────────────────────────────────────────────────────

const KANBAN_STATUSES = ["CHECK", "RUNNING", "DONE"];

function kanbanCard(item) {
  const url = safeUrl(item.url);
  const title = url
    ? `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(item.title || "—")}</a>`
    : esc(item.title || "—");
  const company = esc(item.company || "—");
  const location = esc(item.location || "—");
  const created = esc(item.created_at ? item.created_at.slice(0, 10) : "—");
  const prevStatus = KANBAN_STATUSES[KANBAN_STATUSES.indexOf(item.status) - 1];
  const nextStatus = KANBAN_STATUSES[KANBAN_STATUSES.indexOf(item.status) + 1];
  const prevBtn = prevStatus
    ? `<button type="button" class="kanban-move" data-id="${item.id}" data-status="${prevStatus}" aria-label="Mover para ${prevStatus}">←</button>`
    : "";
  const nextBtn = nextStatus
    ? `<button type="button" class="kanban-move" data-id="${item.id}" data-status="${nextStatus}" aria-label="Mover para ${nextStatus}">→</button>`
    : "";
  const options = KANBAN_STATUSES.map(
    (s) => `<option value="${s}"${s === item.status ? " selected" : ""}>${s}</option>`
  ).join("");
  return `
  <div class="kanban-card" data-id="${item.id}">
    <div class="kanban-card-title">${title}</div>
    <div class="kanban-card-meta">${company} · ${location} · ${created}</div>
    <div class="kanban-card-controls">
      ${prevBtn}
      <select class="kanban-status-select" aria-label="alterar status" data-id="${item.id}">${options}</select>
      ${nextBtn}
    </div>
  </div>`;
}

async function loadKanban() {
  for (const status of KANBAN_STATUSES) {
    const body = $(`#kanban-body-${status}`);
    if (body) body.innerHTML = "<p class='kanban-empty'>Carregando…</p>";
  }
  try {
    const data = await getJSON("/kanban");
    for (const status of KANBAN_STATUSES) {
      const body = $(`#kanban-body-${status}`);
      if (!body) continue;
      const items = data.items.filter((item) => item.status === status);
      body.innerHTML = items.length
        ? items.map(kanbanCard).join("")
        : "<p class='kanban-empty'>Nenhuma candidatura.</p>";
    }
  } catch (err) {
    for (const status of KANBAN_STATUSES) {
      const body = $(`#kanban-body-${status}`);
      if (body) body.innerHTML = `<p class="kanban-empty">Erro: ${esc(err.message)}</p>`;
    }
  }
}

async function moveKanbanCard(id, status) {
  try {
    await getJSON(`/kanban/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status }),
    });
    await loadKanban();
  } catch (err) {
    alert(`Erro ao mover card: ${err.message}`);
  }
}

async function addToKanban(button) {
  const source = button.dataset.source;
  const sourceId = button.dataset.sourceId;
  button.disabled = true;
  try {
    await getJSON("/kanban", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ source, source_id: sourceId }),
    });
    button.textContent = "✓ Adicionada ao CHECK";
    const cardEl = button.closest(".card");
    if (cardEl) {
      cardEl.style.opacity = "0.3";
      cardEl.style.pointerEvents = "none";
      // O contador reflete a listagem: sem esta checagem ele ficaria
      // exibindo um número que a API já não devolve.
      const totalEl = $("#total");
      const shown = Number.parseInt(totalEl.textContent, 10);
      if (Number.isFinite(shown) && shown > 0) totalEl.textContent = `${shown - 1} vaga(s)`;
      setTimeout(() => cardEl.remove(), 300);
    }
  } catch (err) {
    button.disabled = false;
    button.textContent = `Erro: ${err.message}`;
  }
}

// ── Event listeners ──────────────────────────────────────────────────────────

$("#sync-form").addEventListener("submit", runSync);
$("#f-apply").addEventListener("click", loadJobs);
$("#f-source").addEventListener("change", loadJobs);
$("#f-match").addEventListener("change", loadJobs);
$("#f-remote").addEventListener("change", loadJobs);
$("#f-location").addEventListener("change", loadJobs);
$("#f-score").addEventListener("change", loadJobs);
$("#f-query").addEventListener("keydown", (event) => {
  if (event.key === "Enter") loadJobs();
});
$("#profile-form").addEventListener("submit", saveProfile);
$("#curriculum-form").addEventListener("submit", saveCurriculum);
$("#clean-btn").addEventListener("click", cleanJobs);
window.addEventListener("hashchange", navigate);

// Kanban: + Add buttons (delegated from #jobs)
$("#jobs").addEventListener("click", (event) => {
  const btn = event.target.closest(".add-btn");
  if (btn) addToKanban(btn);
});

// Abas de Configurações: delegação em #page-configuracoes — um listener
// único registrado uma vez; nenhum render ou hashchange o duplica.
const configPage = $("#page-configuracoes");
if (configPage) {
  configPage.addEventListener("click", (event) => {
    const btn = event.target.closest("[data-tab]");
    if (btn) selectTab(btn.dataset.tab);
  });
}

// Kanban: move buttons + status select (delegated from kanban page)
$("#page-kanban").addEventListener("click", (event) => {
  const btn = event.target.closest(".kanban-move");
  if (btn) moveKanbanCard(btn.dataset.id, btn.dataset.status);
});
$("#page-kanban").addEventListener("change", (event) => {
  const select = event.target.closest(".kanban-status-select");
  if (select) moveKanbanCard(select.dataset.id, select.value);
});

// ── Init ─────────────────────────────────────────────────────────────────────

loadHealth();
loadJobs();
setInterval(loadHealth, 30000);
navigate();
