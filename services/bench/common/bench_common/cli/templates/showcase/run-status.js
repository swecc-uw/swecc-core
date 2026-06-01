/**
 * Live run status UI for Mesocosm showcase/ folder.
 * Polls GET /v1/runs/status and GET /v1/runs/{id}/episodes.
 */

const REASON_LABELS = {
  user_cancelled: "Cancelled by user",
  task_cancelled: "Run task cancelled",
  domain_missing: "Domain no longer exists",
  no_episodes: "No episodes recorded",
  insufficient_scoreable_episodes: "Too few episodes finished successfully",
  execute_run_error: "Run execution error",
  stale_run_timeout: "Run timed out (stale)",
  bench_api_restart: "Interrupted by platform restart",
  manual_reap: "Marked failed by operator",
  stale_orphan: "Stranded run cleaned up",
  unknown_failure: "Run failed (reason unknown)",
  run_cancelled: "Cancelled while running",
  episode_error: "Episode error",
  no_env_url: "No environment URL configured",
  step_limit: "Step limit reached",
  wall_time_limit: "Wall-clock time limit reached",
  token_budget_exceeded: "Token budget exceeded",
};

const TERMINAL = new Set(["completed", "failed", "cancelled"]);

function reasonLabel(code) {
  if (!code) return "Unknown";
  return REASON_LABELS[code] || code.replace(/_/g, " ");
}

function qs(name) {
  return new URLSearchParams(window.location.search).get(name);
}

function loadConfig() {
  const runId = qs("run_id") || localStorage.getItem("mesocosm.run_id") || "";
  const apiBase =
    qs("api") || localStorage.getItem("mesocosm.api_base") || "https://api.swecc.org/bench";
  const token = localStorage.getItem("mesocosm.auth_token") || "";
  document.getElementById("run-id").value = runId;
  document.getElementById("api-base").value = apiBase.replace(/\/$/, "");
  document.getElementById("auth-token").value = token;
}

function saveConfig() {
  localStorage.setItem("mesocosm.run_id", document.getElementById("run-id").value.trim());
  localStorage.setItem("mesocosm.api_base", document.getElementById("api-base").value.trim());
  localStorage.setItem("mesocosm.auth_token", document.getElementById("auth-token").value.trim());
}

function headers() {
  const token = document.getElementById("auth-token").value.trim();
  const h = { Accept: "application/json" };
  if (token) h.Authorization = `Bearer ${token}`;
  return h;
}

function apiBase() {
  return document.getElementById("api-base").value.trim().replace(/\/$/, "");
}

function showError(msg) {
  const el = document.getElementById("error");
  el.hidden = !msg;
  el.textContent = msg || "";
}

function setBadge(el, status) {
  el.textContent = status;
  el.className = "badge " + (status || "").toLowerCase();
}

function renderRun(row) {
  document.getElementById("run-panel").hidden = false;
  setBadge(document.getElementById("run-status"), row.status);
  document.getElementById("run-id-display").textContent = row.id;

  const reasonEl = document.getElementById("run-reason");
  if (row.status_reason) {
    reasonEl.hidden = false;
    reasonEl.textContent = reasonLabel(row.status_reason);
  } else {
    reasonEl.hidden = true;
  }

  const outcomesEl = document.getElementById("run-outcomes");
  outcomesEl.innerHTML = "";
  const detail = row.status_detail || {};
  const outcomes = detail.episode_outcomes;
  let hasOutcomes = false;
  if (outcomes && typeof outcomes === "object") {
    for (const [key, val] of Object.entries(outcomes)) {
      if (!val) continue;
      hasOutcomes = true;
      const dt = document.createElement("dt");
      dt.textContent = key;
      const dd = document.createElement("dd");
      dd.textContent = String(val);
      outcomesEl.appendChild(dt);
      outcomesEl.appendChild(dd);
    }
  }
  for (const key of ["failure_reasons", "truncation_reasons", "cancellation_reasons"]) {
    const vals = detail[key];
    if (!Array.isArray(vals) || !vals.length) continue;
    hasOutcomes = true;
    const dt = document.createElement("dt");
    dt.textContent = key.replace(/_/g, " ");
    const dd = document.createElement("dd");
    dd.textContent = vals.map(reasonLabel).join(", ");
    outcomesEl.appendChild(dt);
    outcomesEl.appendChild(dd);
  }
  outcomesEl.hidden = !hasOutcomes;

  const scoresEl = document.getElementById("run-scores");
  const scores = row.scores || {};
  const keys = Object.keys(scores);
  if (keys.length) {
    scoresEl.hidden = false;
    scoresEl.textContent = "Scores: " + keys.map((k) => `${k}=${scores[k]}`).join(", ");
  } else {
    scoresEl.hidden = true;
  }
}

function episodeReason(ep) {
  const info = ep.terminal_info || {};
  if (info.reason) return info.reason;
  if (ep.status === "failed" && info.error) return "episode_error";
  return null;
}

function renderEpisodes(episodes) {
  const panel = document.getElementById("episodes-panel");
  const list = document.getElementById("episode-list");
  list.innerHTML = "";
  if (!episodes || !episodes.length) {
    panel.hidden = true;
    return;
  }
  panel.hidden = false;
  for (const ep of episodes) {
    const li = document.createElement("li");
    const meta = document.createElement("div");
    meta.className = "episode-meta";
    const badge = document.createElement("span");
    setBadge(badge, ep.status);
    meta.appendChild(badge);
    const id = document.createElement("span");
    id.className = "run-id";
    id.textContent = ep.id + (ep.seed != null ? ` · seed ${ep.seed}` : "");
    meta.appendChild(id);
    li.appendChild(meta);

    const reason = episodeReason(ep);
    const info = ep.terminal_info || {};
    const bits = [];
    if (reason) bits.push(reasonLabel(reason));
    if (info.error) bits.push(String(info.error));
    if (info.max_steps && reason === "step_limit") bits.push(`max_steps=${info.max_steps}`);
    if (ep.total_reward != null && ep.status !== "pending") bits.push(`reward=${ep.total_reward}`);
    if (bits.length) {
      const detail = document.createElement("p");
      detail.className = "episode-detail";
      detail.textContent = bits.join(" · ");
      li.appendChild(detail);
    }
    list.appendChild(li);
  }
}

async function fetchJson(path) {
  const res = await fetch(`${apiBase()}${path}`, { headers: headers() });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || JSON.stringify(body);
    } catch (_) {
      /* ignore */
    }
    throw new Error(`${res.status}: ${detail}`);
  }
  return res.json();
}

let pollTimer = null;

async function pollOnce(runId) {
  const batch = await fetchJson(`/v1/runs/status?ids=${encodeURIComponent(runId)}`);
  const row = (batch.runs || {})[runId];
  if (!row) throw new Error("Run not found or not accessible with this token.");
  renderRun(row);
  if (TERMINAL.has(row.status)) {
    const episodes = await fetchJson(`/v1/runs/${encodeURIComponent(runId)}/episodes`);
    renderEpisodes(episodes);
    stopPoll();
  }
}

function stopPoll() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
  document.getElementById("stop-btn").disabled = true;
  document.getElementById("start-btn").disabled = false;
}

async function startPoll() {
  saveConfig();
  showError("");
  const runId = document.getElementById("run-id").value.trim();
  if (!runId) {
    showError("Enter a run ID.");
    return;
  }
  document.getElementById("start-btn").disabled = true;
  document.getElementById("stop-btn").disabled = false;
  try {
    await pollOnce(runId);
    if (!pollTimer) {
      pollTimer = setInterval(() => pollOnce(runId).catch(onPollError), 2000);
    }
  } catch (err) {
    onPollError(err);
  }
}

function onPollError(err) {
  stopPoll();
  showError(err.message || String(err));
}

document.getElementById("start-btn").addEventListener("click", () => startPoll());
document.getElementById("stop-btn").addEventListener("click", () => stopPoll());
loadConfig();
if (qs("run_id")) startPoll();
