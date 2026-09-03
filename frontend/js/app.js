/* Zynovix BorderVerity - frontend SPA (vanilla JS, no build step). */
"use strict";

/* =================================================================== *
 * BACKEND API BASE URL  —  ONE configurable override (window.BV_API_URL).
 * =================================================================== *
 * GitHub Pages is STATIC and cannot run FastAPI. This frontend resolves the
 * backend base from a single, user-editable variable:
 *
 *     window.BV_API_URL        // in frontend/index.html (the ONLY thing you edit)
 *
 * Set it to your PUBLIC HTTPS backend. If you expose the local FastAPI via
 * ngrok, use the ROOT ngrok URL — the "/api" path prefix is appended
 * automatically, so you do NOT add it yourself:
 *
 *     window.BV_API_URL = "https://YOUR-NAME.ngrok-free.app"
 *     // -> requests hit https://YOUR-NAME.ngrok-free.app/api/...
 *
 * It ships EMPTY in the repo. With it empty, the deployed GitHub Pages site
 * cannot reach any backend, so the app shows a clear "Backend not reachable"
 * message (it never attempts a dead loopback-address call). Local dev
 * (uvicorn serving the SPA on its own origin) still works via the same-origin
 * "/api" fallback below.
 *
 * Resolution order (the first healthy base that answers GET {base}/health with
 * status "ok" is used):
 *   1. window.BV_API_URL  (normalized so "/api" is present)
 *   2. /api               (same-origin fallback for local dev)
 * =================================================================== */

// Ensure the configured base carries the "/api" path prefix exactly once. The
// backend serves its routes under /api, so a root ngrok URL such as
// "https://x.ngrok-free.app" must become "https://x.ngrok-free.app/api".
function normalizeBase(url) {
  const u = String(url || "").trim().replace(/\/+$/, "");
  if (!u) return u;
  return /\/api$/i.test(u) ? u : u + "/api";
}

const BACKEND_CANDIDATES = [];
if (window.BV_API_URL) BACKEND_CANDIDATES.push(normalizeBase(window.BV_API_URL));
// Same-origin fallback: local dev where uvicorn serves the SPA on its own origin.
// On the deployed GitHub Pages site this resolves to the Page's own origin and
// simply 404s — which is exactly why window.BV_API_URL is the real override.
BACKEND_CANDIDATES.push("/api");

let API = ""; // resolved backend base — set only when a candidate answers /health

function setBackendStatus(msg, cls) {
  const el = document.getElementById("backend-status");
  if (el) { el.textContent = msg; el.className = "login-msg" + (cls ? " " + cls : ""); }
}

// Resolve the candidate base if it answers GET {base}/health with status ok.
function probeBackend(base) {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), 3000);
  return fetch(base + "/health", { cache: "no-store", headers: { Accept: "application/json" }, signal: ctrl.signal })
    .then(async res => {
      if (!res.ok) return null;
      const j = await res.json().catch(() => ({}));
      return j && j.status === "ok" ? base : null;
    })
    .catch(() => null)
    .finally(() => clearTimeout(t));
}

async function discoverBackend() {
  setBackendStatus("Connecting to backend…", "info");
  const seen = [];
  for (const c of BACKEND_CANDIDATES) if (c && seen.indexOf(c) < 0) seen.push(c);
  if (!seen.length) { API = ""; setBackendStatus("Backend not reachable."); return ""; }
  // Probe all candidates concurrently; adopt the first healthy one. When the local
  // backend is running on this machine it answers in ms, so login never hangs; when
  // nothing is reachable (e.g. a phone opening the public page) we resolve fast with
  // a clear message instead of a stuck "Signing in…" button.
  await Promise.all(seen.map(base => probeBackend(base).then(ok => {
    if (ok && !API) { API = ok; setBackendStatus("Backend connected", "success"); }
  })));
  if (!API) {
    API = "";
    setBackendStatus("Backend not reachable. Set window.BV_API_URL in frontend/index.html to your public backend URL (e.g. your ngrok root URL — the /api prefix is added automatically), then refresh.", "");
  }
  return API;
}

const backendReady = discoverBackend().catch(() => "");

// Storage access is wrapped so privacy modes / blocked cookies (where reading or
// writing localStorage throws a SecurityError) never crash the app or blank the
// page. This keeps the site opening normally on phones and locked-down browsers.
function lsGet(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
function lsSet(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* ignore */ } }
function lsRemove(k) { try { localStorage.removeItem(k); } catch (e) { /* ignore */ } }
function lsGetUser() {
  try { return JSON.parse(lsGet("bv_user") || "null"); } catch (e) { return null; }
}

const state = {
  token: lsGet("bv_token"),
  user: lsGetUser(),
  results: {},   // cache: id -> result
  uploads: {},   // name -> url for local display
};

// Key used to remember the CURRENT verification session id on the frontend.
// Only the numeric verification_id is stored (never the document itself); the
// session + document are re-fetched from the backend via /verification/{id}.
const LS_VID = "bv_last_verification_id";

/* ------------------------------------------------------------------ *
 * Helpers
 * ------------------------------------------------------------------ */

function $(sel) { return document.querySelector(sel); }
function show(id) { const n = document.getElementById(id); if (n) n.classList.remove("hidden"); }
function hide(id) { const n = document.getElementById(id); if (n) n.classList.add("hidden"); }
function el(tag, cls, html) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (html !== undefined) n.innerHTML = html;
  return n;
}
function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  }[c]));
}

/* Resolve a backend-served media path (e.g. "/media/uploads/x.png") against the
 * resolved API origin. GitHub Pages is static, so a relative "/media/..." would
 * resolve to the Page's own origin and 404; pointing it at the API origin makes
 * the ORIGINAL uploaded image load no matter where the page is served. Absolute
 * (http/https), blob: and data: URLs are returned unchanged. When the API is
 * same-origin ("/api") the base is empty, so the path stays relative (correct for
 * the local demo where FastAPI serves the whole app on one origin). */
function mediaUrl(p) {
  if (!p) return "";
  if (/^(https?:|blob:|data:)/i.test(p)) return p;
  const base = (API || "").replace(/\/api\/?$/, "").replace(/\/+$/, "");
  if (!base) return p;
  return base + (p.charAt(0) === "/" ? p : "/" + p);
}

/* Inline SVG icon set (stroke-based, consistent with the design system). */
const ICO = {
  shield: '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="M12 8v4"/><path d="M12 16h.01"/>',
  check: '<path d="M20 6 9 17l-5-5"/>',
  alert: '<path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><path d="M12 9v4"/><path d="M12 17h.01"/>',
  upload: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="M17 8l-5-5-5 5"/><path d="M12 3v12"/>',
  doc: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="M16 13H8"/><path d="M16 17H8"/>',
  face: '<circle cx="12" cy="10" r="3"/><path d="M12 2a8 8 0 0 0-8 8c0 1.5.5 3 1.5 4.5L7 20h10l1.5-5.5c1-1.5 1.5-3 1.5-4.5a8 8 0 0 0-8-8z"/>',
  db: '<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/>',
  scan: '<path d="M3 7V5a2 2 0 0 1 2-2h2"/><path d="M17 3h2a2 2 0 0 1 2 2v2"/><path d="M21 17v2a2 2 0 0 1-2 2h-2"/><path d="M7 21H5a2 2 0 0 1-2-2v-2"/><path d="M7 12h10"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 3"/>',
  user: '<path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
  lock: '<rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>',
  list: '<path d="M8 6h13"/><path d="M8 12h13"/><path d="M8 18h13"/><path d="M3 6h.01"/><path d="M3 12h.01"/><path d="M3 18h.01"/>',
  home: '<path d="M3 9.5 12 3l9 6.5"/><path d="M5 10v10h14V10"/>',
  arrowR: '<path d="M5 12h14"/><path d="M12 5l7 7-7 7"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/>',
  chevDown: '<path d="M6 9l6 6 6-6"/>',
  warning: '<circle cx="12" cy="12" r="10"/><path d="M12 8v4"/><path d="M12 16h.01"/>',
  info: '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/>',
  cam: '<path d="M3 7a2 2 0 0 1 2-2h2l1.5-2h7L17 5h2a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><circle cx="12" cy="13" r="4"/>',
};
function ic(name, cls) {
  return `<svg class="${cls || ""}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${ICO[name] || ICO.info}</svg>`;
}
function toast(msg, isError) {
  const t = $("#toast");
  t.textContent = msg;
  t.className = "toast" + (isError ? " error" : "");
  t.classList.remove("hidden");
  clearTimeout(toast._t);
  toast._t = setTimeout(() => t.classList.add("hidden"), 3400);
}

// Default abort window for QUICK requests (login, history, dashboard, uploads).
// The only realistic stall here is an unreachable backend, so 15s fails fast and
// the UI never stays stuck on "Signing in…". Heavy verification calls (OCR + ML)
// PASS a much longer timeout explicitly (see /verify/* call sites) so a legitimate
// multi-second verification is never aborted.
const NETWORK_TIMEOUT_MS = 15000;

async function api(path, options = {}) {
  // Wait for backend discovery first (it probes /api/health on every candidate).
  // This prevents a "Signing in…" hang: discovery resolves in ms when the backend
  // is up and rejects fast when none is reachable, instead of fetching a dead URL.
  await backendReady;
  if (!API) {
    throw new Error("Backend not reachable. Set window.BV_API_URL in frontend/index.html to your public backend URL (e.g. your ngrok root URL — the /api prefix is added automatically), then refresh.");
  }
  const headers = options.headers || {};
  if (state.token) headers["Authorization"] = "Bearer " + state.token;
  // Per-call timeout: heavy verification pipelines (OCR + ML) can legitimately
  // take a while, so those callers pass a long timeout. Quick reads (login,
  // history, dashboard) use the short default so an unreachable backend fails
  // fast instead of leaving the UI stuck.
  const timeout = options.timeout || NETWORK_TIMEOUT_MS;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);
  let res;
  try {
    res = await fetch(API + path, { ...options, headers, signal: controller.signal });
  } catch (err) {
    if (err && err.name === "AbortError") {
      throw new Error("Backend unavailable. Please try again.");
    }
    throw new Error("Could not reach the backend. Is it running?");
  } finally {
    clearTimeout(timer);
  }
  if (res.status === 401 && path !== "/auth/login") {
    logout(true);
    throw new Error("Session expired. Please sign in again.");
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = data.detail || (typeof data === "string" ? data : "") || res.statusText || "Request failed";
    const e = new Error(detail);
    e.status = res.status; // carry the status so the caller can log it
    throw e;
  }
  return data;
}

/* ------------------------------------------------------------------ *
 * Auth
 * ------------------------------------------------------------------ */

async function login(username, password) {
  const body = new URLSearchParams({ username, password });
  const data = await api("/auth/login", { method: "POST", body });
  state.token = data.access_token;
  state.user = { username: data.username, role: data.role };
  lsSet("bv_token", state.token);
  lsSet("bv_user", JSON.stringify(state.user));
  const av = $("#officer-avatar");
  if (av) av.textContent = (data.username || "O").charAt(0).toUpperCase();
  $("#officer-name").textContent = data.username + "  ·  " + (data.role === "admin" ? "ADMIN" : "OFFICER");
}

function logout(expired) {
  state.token = null; state.user = null;
  lsRemove("bv_token");
  lsRemove("bv_user");
  show("login-view");
  hide("app-view");
  if (expired) toast("Session expired", true);
}

/* ------------------------------------------------------------------ *
 * Router
 * ------------------------------------------------------------------ */

function route() {
  const hash = location.hash || "#/dashboard";
  const parts = hash.replace("#/", "").split("/");
  const page = parts[0] || "dashboard";
  if (!state.token) { show("login-view"); hide("app-view"); return; }
  show("app-view"); hide("login-view");

  // Release the camera stream when navigating away from the verify page.
  if (page !== "verify") stopCamera();

  const nav = document.querySelectorAll(".nav-item");
  nav.forEach(n => n.classList.toggle("active", n.dataset.route === page));

  const titles = {
    dashboard: "Dashboard", verify: "New Verification",
    history: "Verification History", alerts: "Alerts", result: "Verification Result",
    database: "Demo Database"
  };
  $("#page-title").textContent = titles[page] || "Dashboard";

  if (page === "dashboard") renderDashboard();
  else if (page === "verify") renderVerify();
  else if (page === "history") renderHistory();
  else if (page === "alerts") renderAlerts();
  else if (page === "database") renderDatabase();
  else if (page === "result") renderResult(parts[1]);
}

function go(hash) { location.hash = hash; }

/* ------------------------------------------------------------------ *
 * Dashboard
 * ------------------------------------------------------------------ */

async function renderDashboard() {
  const c = $("#page-content");
  c.innerHTML = "<p class='muted'>Loading...</p>";
  try {
    const [stats, history] = await Promise.all([
      api("/dashboard/statistics"), api("/verification/history?limit=12")
    ]);
    const statRow = (label, value, sub, accent, icon) => `
      <div class="stat-card ${accent}">
        <div class="stat-top"><div class="stat-label">${label}</div><span class="stat-ico">${ic(icon)}</span></div>
        <div class="stat-value">${value}</div><div class="stat-sub">${sub}</div>
      </div>`;
    const empty = history.length ? "" : `
      <tr><td colspan="8" class="muted" style="text-align:center;padding:28px">
        No verifications yet. Run a <a href="#/verify">demo case</a> or verify a document.
      </td></tr>`;
    c.innerHTML = `
      <div class="grid stats-grid">
        ${statRow("Total Verifications", stats.total_verifications, "All sessions", "", "list")}
        ${statRow("Verified", stats.verified, "Low risk · safe", "stat-green", "check")}
        ${statRow("Review Required", stats.review_required, "Medium risk", "stat-yellow", "clock")}
        ${statRow("High Risk", stats.high_risk, "Suspicious", "stat-red", "alert")}
        ${statRow("Fraud Detected", stats.fraud_detected, "Flagged", "stat-red", "warning")}
        ${statRow("Avg. Time", stats.average_verification_time_seconds + "s", "Per verification", "", "clock")}
      </div>
      <div class="card">
        <div class="flex mb" style="justify-content:space-between">
          <div class="card-title" style="margin:0">${ic("list", "tt-ico")} Recent Verifications</div>
          <button class="btn btn-ghost btn-sm" onclick="go('#/verify')">${ic("upload")} New Verification</button>
        </div>
        <div class="table-wrap"><table>
          <thead><tr><th>No.</th><th>Image</th><th>Passenger</th><th>Document</th><th>Nationality</th><th>Score</th><th>Decision</th><th>Time</th></tr></thead>
          <tbody>${history.length ? history.map(row).join("") : empty}</tbody>
        </table></div>
      </div>`;
    wireHistoryRows();
  } catch (e) { c.innerHTML = `<div class="card"><p class="muted">Error loading dashboard: ${esc(e.message)}</p></div>`; }
}

function row(r) {
  const cls = r.risk_level === "HIGH" ? "badge-red" : r.risk_level === "MEDIUM" ? "badge-yellow" : "badge-green";
  const status = r.verification_status || r.decision || "";
  return `<tr data-id="${r.id}">
    <td>#${r.id}</td>
    <td>${r.image_url ? `<img class="doc-image-sm" src="${esc(mediaUrl(r.image_url))}" alt="document">` : `<span class="muted">-</span>`}</td>
    <td>${esc(r.passenger_name) || "-"}</td>
    <td>${esc(r.document_number) || "-"} <span class="muted">(${esc(r.document_type)})</span> ${methodChip(r.method)}</td>
    <td>${esc(r.nationality)}</td>
    <td><span class="badge ${cls}">${r.risk_score}</span></td>
    <td>${verdictBadge(status)}</td>
    <td class="muted">${fmtTime(r.created_at)}</td></tr>`;
}
function methodChip(m) {
  if (!m) return "";
  const label = m === "live_camera" ? "Cam" : m === "demo" ? "Demo" : m === "synthetic" ? "Synth" : "Upload";
  const cls = m === "live_camera" ? "badge-blue" : "badge-gray";
  return `<span class="badge ${cls}" title="${esc(m)}">${esc(label)}</span>`;
}
function wireHistoryRows() {
  document.querySelectorAll("tbody tr[data-id]").forEach(tr => {
    tr.style.cursor = "pointer";
    tr.onclick = () => go("#/result/" + tr.dataset.id);
  });
}

function verdictBadge(decision) {
  const d = (decision || "").toUpperCase();
  const cls = d === "VERIFIED" ? "badge-green"
    : (d === "NOT_VERIFIED" || d === "NOT VERIFIED" || d === "HIGH RISK") ? "badge-red"
    : "badge-yellow";
  return `<span class="badge ${cls}">${esc(decision)}</span>`;
}
function fmtTime(iso) { try { return new Date(iso).toLocaleString(); } catch (e) { return iso || "-"; } }

/* ------------------------------------------------------------------ *
 * New Verification
 * ------------------------------------------------------------------ */

/* In-memory state for the New Verification page.
   Survives SPA navigation (hash changes) so an uploaded document, its preview
   and any completed / in-flight verification are restored when the officer
   returns to this page. The actual document (File object + preview object URL)
   is kept in memory ONLY - it is never written to localStorage/sessionStorage,
   which would risk persisting PII beyond the existing upload flow. */
const verifyState = {
  docFile: null,     // uploaded document File
  docPreview: null,  // object URL for the document preview
  docType: "auto",   // selected document type
  faceFile: null,    // optional applicant photo File
  facePreview: null, // object URL for the face preview
  running: false,    // a verification is currently in flight
  activeId: null,    // verification_id of the last run in this session
  lastResult: null,  // last completed verification result (document flow)
};

// Apply an uploaded document file: persist it in memory and render its preview.
// Render a document preview into the upload zone from any image source
// (an object URL for a freshly picked file, or a backend /media URL when a
// previously persisted session is restored after a refresh).
function renderDocPreviewEl(src, name, sizeLabel) {
  const p = $("#doc-preview");
  if (!p) return;
  p.classList.remove("hidden");
  p.innerHTML = `<img src="${esc(mediaUrl(src))}" alt="preview"><div><div class="muted">${esc(name)}</div>` +
    (sizeLabel ? `<div class="muted" style="font-size:12px">${sizeLabel}</div>` : "") + `</div>`;
}

// Apply an uploaded document file: persist it in memory and render its preview.
function setDocFile(f) {
  verifyState.docFile = f || null;
  if (verifyState.docPreview) { URL.revokeObjectURL(verifyState.docPreview); verifyState.docPreview = null; }
  if (f) {
    verifyState.docPreview = URL.createObjectURL(f);
    renderDocPreviewEl(verifyState.docPreview, f.name, (f.size / 1024).toFixed(1) + " KB");
  } else {
    verifyState.docPreview = null;
    const p = $("#doc-preview");
    if (p) { p.classList.add("hidden"); p.innerHTML = ""; }
  }
}

// Apply an optional applicant photo: persist it in memory and render its preview.
function setFaceFile(f) {
  verifyState.faceFile = f || null;
  if (verifyState.facePreview) { URL.revokeObjectURL(verifyState.facePreview); verifyState.facePreview = null; }
  if (f) verifyState.facePreview = URL.createObjectURL(f);
  const p = $("#face-preview");
  if (p) {
    if (f) {
      p.classList.remove("hidden");
      p.innerHTML = `<img src="${verifyState.facePreview}" alt="preview"><div><div class="muted">${esc(f.name)}</div>
        <div class="muted" style="font-size:12px">${(f.size / 1024).toFixed(1)} KB</div></div>`;
    } else {
      p.classList.add("hidden");
      p.innerHTML = "";
    }
  }
}

async function renderVerify() {
  const c = $("#page-content");
  c.innerHTML = `
    <div class="pipeline">
      <span class="pl-step"><span class="num">1</span> Upload</span><span class="pl-arrow">${ic("arrowR")}</span>
      <span class="pl-step"><span class="num">2</span> OCR / MRZ</span><span class="pl-arrow">${ic("arrowR")}</span>
      <span class="pl-step"><span class="num">3</span> Database</span><span class="pl-arrow">${ic("arrowR")}</span>
      <span class="pl-step"><span class="num">4</span> Risk</span><span class="pl-arrow">${ic("arrowR")}</span>
      <span class="pl-step"><span class="num">5</span> Decision</span>
    </div>

    <div class="grid" style="grid-template-columns: 1fr 1fr; gap:20px">
      <div class="card">
        <div class="card-title">${ic("doc", "tt-ico")} Upload Travel Document</div>
        <div id="doc-zone" class="upload-zone">
          <span class="up-ico">${ic("upload")}</span>
          <div><b>Click or drag</b> a passport / visa image</div>
          <div style="font-size:12px">PNG · JPG · WEBP up to 5 MB</div>
        </div>
        <input id="doc-input" type="file" accept="image/*" class="hidden">
        <div id="doc-preview" class="upload-preview hidden"></div>
        <div class="form-row mt">
          <label class="fld" for="doc-type">Document type</label>
          <select id="doc-type" class="fld">
            <option value="auto">Auto-detect</option>
            <option value="passport">Passport</option>
            <option value="visa">Visa</option>
          </select>
        </div>
        <button id="run-verify" class="btn btn-primary btn-block">${ic("scan")} Run Verification</button>
      </div>

      <div class="card">
        <div class="card-title">${ic("face", "tt-ico")} Face Verification <span class="badge badge-gray">optional</span></div>
        <div id="face-zone" class="upload-zone" style="padding:28px 20px">
          <span class="up-ico">${ic("face")}</span>
          <div><b>Click or drag</b> a live / applicant photo</div>
        </div>
        <input id="face-input" type="file" accept="image/*" class="hidden">
        <div id="face-preview" class="upload-preview hidden"></div>
        <div class="muted mt" style="font-size:12px">If no photo is uploaded, face verification is skipped (shown as not performed).</div>
      </div>
    </div>

    <div class="card mt">
      <div class="card-title">${ic("cam", "tt-ico")} Live Camera Verification <span class="badge badge-blue">real-time</span></div>
      <p class="muted mb">Upload the document above first. Then start the camera, point it at the applicant's live face, and select <b>Capture Face &amp; Verify</b>. The face is verified against the uploaded document through the <b>same OCR + database pipeline</b> as an upload.</p>
      <div class="cam-wrap">
        <div id="cam-stage" class="cam-stage">
          <video id="cam-video" autoplay playsinline muted></video>
          <div id="cam-frame" class="cam-frame">
            <div class="cam-corner tl"></div><div class="cam-corner tr"></div>
            <div class="cam-corner bl"></div><div class="cam-corner br"></div>
            <div class="cam-hint">FACE<br>IN<br>FRAME</div>
          </div>
        </div>
        <div class="cam-status" id="cam-status">Camera is off. Start the camera to begin.</div>
        <div class="cam-actions">
          <button id="cam-start" class="btn btn-primary">${ic("cam")} Start Camera</button>
          <button id="cam-face" class="btn btn-primary" disabled>${ic("face")} Capture Face &amp; Verify</button>
          <button id="cam-stop" class="btn btn-ghost" disabled>${ic("close")} Stop</button>
        </div>
        <div id="cam-error" class="muted" style="font-size:12px;color:var(--red);margin-top:8px"></div>
      </div>
    </div>

    <div class="card mt">
      <div class="card-title">${ic("list", "tt-ico")} Quick Demo Cases <span class="badge badge-gray">SIH scenarios</span></div>
      <p class="muted mb">Run a predefined scenario end-to-end with synthetic data. No upload required.</p>
      <div class="demo-cases">
        <button class="demo-btn green" data-demo="valid"><span class="demo-synth-tag">valid</span> ${ic("check")} VERIFIED</button>
        <button class="demo-btn red" data-demo="expired"><span class="demo-synth-tag">expired</span> ${ic("alert")} REVIEW</button>
        <button class="demo-btn red" data-demo="mrz_mismatch"><span class="demo-synth-tag">MRZ</span> ${ic("alert")} HIGH</button>
        <button class="demo-btn red" data-demo="tamper"><span class="demo-synth-tag">tamper</span> ${ic("alert")} HIGH</button>
        <button class="demo-btn red" data-demo="watchlist"><span class="demo-synth-tag">watchlist</span> ${ic("alert")} HIGH</button>
        <button class="demo-btn yellow" data-demo="face_mismatch"><span class="demo-synth-tag">face</span> ${ic("warning")} HIGH</button>
        <button class="demo-btn yellow" data-demo="duplicate"><span class="demo-synth-tag">duplicate</span> ${ic("warning")} REVIEW</button>
        <button class="demo-btn yellow" data-demo="not_found"><span class="demo-synth-tag">not found</span> ${ic("info")} REVIEW</button>
      </div>
    </div>

    <div class="card mt">
      <div class="card-title">${ic("shield", "tt-ico")} Synthetic Document Tampering <span class="badge badge-blue">Aadhaar · PAN · College ID</span></div>
      <p class="muted mb">Run the document-authenticity demonstrator on <b>fictional</b> demo cards. No real identity document is generated or used. Original → VERIFIED · LOW RISK; edited → HIGH RISK.</p>
      <div class="demo-cases">
        <button class="demo-btn green" data-synth="aadhaar_valid"><span class="demo-synth-tag">aadhaar</span> original ${ic("check")} VERIFIED</button>
        <button class="demo-btn red" data-synth="aadhaar_tampered"><span class="demo-synth-tag">aadhaar</span> edited ${ic("alert")} HIGH</button>
        <button class="demo-btn green" data-synth="pan_valid"><span class="demo-synth-tag">PAN</span> original ${ic("check")} VERIFIED</button>
        <button class="demo-btn red" data-synth="pan_tampered"><span class="demo-synth-tag">PAN</span> edited ${ic("alert")} HIGH</button>
        <button class="demo-btn green" data-synth="college_valid"><span class="demo-synth-tag">college</span> original ${ic("check")} VERIFIED</button>
        <button class="demo-btn red" data-synth="college_tampered"><span class="demo-synth-tag">college</span> edited ${ic("alert")} HIGH</button>
      </div>
    </div>

    <div class="card mt hidden" id="verify-progress">
      <div class="loading-block"><span class="spinner"></span> Running verification pipeline… OCR → MRZ → Face → Risk → Decision</div>
    </div>
    `;

  // attach upload handlers
  wireUpload("doc-zone", "doc-input", "doc-preview", f => setDocFile(f));
  wireUpload("face-zone", "face-input", "face-preview", f => setFaceFile(f));

  $("#doc-input").addEventListener("change", e => handlePick(e, "doc"));
  $("#face-input").addEventListener("change", e => handlePick(e, "face"));

  $("#run-verify").onclick = runImageVerify;
  document.querySelectorAll(".demo-btn[data-demo]").forEach(b => b.onclick = () => runDemo(b.dataset.demo));
  document.querySelectorAll(".demo-btn[data-synth]").forEach(b => b.onclick = () => runSynthetic(b.dataset.synth));
  const cs = $("#cam-start"); if (cs) cs.onclick = startCamera;
  const cf = $("#cam-face"); if (cf) cf.onclick = captureFaceAndVerify;
  const cp = $("#cam-stop"); if (cp) cp.onclick = stopCamera;

  // Rehydrate any in-memory state (uploaded document, doc type, running flag)
  // so navigating away and back to this page does not lose the current work.
  const dtSel = $("#doc-type");
  if (dtSel) {
    dtSel.value = verifyState.docType;
    dtSel.addEventListener("change", e => { verifyState.docType = e.target.value; });
  }
  if (verifyState.docFile) setDocFile(verifyState.docFile);
  else if (verifyState.docPreview) renderDocPreviewEl(verifyState.docPreview, "Restored document", "");
  if (verifyState.faceFile) setFaceFile(verifyState.faceFile);
  if (verifyState.running) {
    const prog = $("#verify-progress");
    if (prog) prog.classList.remove("hidden");
  }

  // Restore the latest persisted verification session from the backend so the
  // New Verification page survives a full browser refresh (not just navigation).
  // Only the verification_id is kept on the frontend (localStorage); the actual
  // document image and all results are re-fetched from the existing DB record.
  if (!verifyState.lastResult && !verifyState.running) {
    const vid = parseInt(lsGet(LS_VID) || "", 10);
    if (vid) {
      c.insertAdjacentHTML("beforeend",
        `<div class="card mt" id="verify-restoring"><div class="loading-block"><span class="spinner"></span> Restoring previous verification session…</div></div>`);
      try {
        const result = await api("/verification/" + vid);
        state.results[vid] = result;
        verifyState.activeId = vid;
        verifyState.lastResult = result;
        verifyState.docType = result.document_type || verifyState.docType;
        if (dtSel && result.document_type) dtSel.value = verifyState.docType;
        if (result.image_url) {
          verifyState.docPreview = mediaUrl(result.image_url);
          renderDocPreviewEl(result.image_url, "Restored document", "");
        }
      } catch (e) {
        lsRemove(LS_VID);  // stale id -> show empty upload screen
      } finally {
        const l = $("#verify-restoring"); if (l) l.remove();
      }
    }
  }

  // Render the restored session's full results in the UI: OCR/MRZ, extracted
  // fields, database match, risk score/result, tamper, face, and final decision.
  if (verifyState.lastResult && verifyState.activeId) {
    c.insertAdjacentHTML("beforeend", restoredSessionHtml(verifyState.lastResult, verifyState.activeId));
  }
}

function wireUpload(zoneId, inputId, previewId, onPick) {
  const zone = $("#" + zoneId), input = $("#" + inputId);
  zone.onclick = () => input.click();
  zone.ondragover = e => { e.preventDefault(); zone.classList.add("drag"); };
  zone.ondragleave = () => zone.classList.remove("drag");
  zone.ondrop = e => { e.preventDefault(); zone.classList.remove("drag");
    const f = e.dataTransfer.files[0]; if (f) { setInput(input, f); input.dispatchEvent(new Event("change")); } };
}
function setInput(input, file) {
  try { const dt = new DataTransfer(); dt.items.add(file); input.files = dt.files; } catch (e) {}
}
function handlePick(e, kind) {
  const f = e.target.files[0]; if (!f) return;
  if (kind === "doc") setDocFile(f); else setFaceFile(f);
}

async function runImageVerify() {
  if (!verifyState.docFile) { toast("Please upload a document image", true); return; }
  const prog = $("#verify-progress"); if (prog) prog.classList.remove("hidden");
  verifyState.running = true;
  // A new run invalidates any previously restored result for this document.
  verifyState.lastResult = null; verifyState.activeId = null;
  try {
    toast("Uploading document…");
    const fd = new FormData(); fd.append("file", verifyState.docFile);
    const upload = await api("/upload-document", { method: "POST", body: fd });
    let prov = null;
    if (verifyState.faceFile) {
      const ff = new FormData(); ff.append("file", verifyState.faceFile);
      const up = await api("/upload-photo", { method: "POST", body: ff });
      prov = up.filename;
    }
    toast("Verifying document…");
    const docType = $("#doc-type").value;
    verifyState.docType = docType;
    const result = await api("/verify/document", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ image_filename: upload.filename, reference_photo_filename: null, provided_photo_filename: prov, live_photo_filename: prov, document_type: docType, method: "upload", original_filename: upload.original_filename || "" }),
      timeout: 90000
    });
    cacheResult(result);
    verifyState.running = false;
    verifyState.activeId = result.verification_id;
    verifyState.lastResult = result;
    lsSet(LS_VID, String(result.verification_id));
    // Only auto-navigate if the officer is still on this page; otherwise the
    // completed result is preserved and restored when they return.
    if ((location.hash || "").includes("verify")) go("#/result/" + result.verification_id);
  } catch (e) {
    verifyState.running = false;
    const p = $("#verify-progress"); if (p) p.classList.add("hidden");
    toast("Verification failed: " + e.message, true);
  }
}

async function runDemo(scenario) {
  const prog = $("#verify-progress"); if (prog) prog.classList.remove("hidden");
  verifyState.running = true;
  try {
    const result = await api("/verify/demo", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ scenario }),
      timeout: 90000
    });
    cacheResult(result);
    verifyState.running = false;
    lsSet(LS_VID, String(result.verification_id));
    if ((location.hash || "").includes("verify")) go("#/result/" + result.verification_id);
  } catch (e) {
    verifyState.running = false;
    toast("Demo failed: " + e.message, true);
  }
}

async function runSynthetic(syntheticId) {
  const prog = $("#verify-progress"); if (prog) prog.classList.remove("hidden");
  verifyState.running = true;
  try {
    const result = await api("/verify/synthetic", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ synthetic_id: syntheticId }),
      timeout: 90000
    });
    cacheResult(result);
    verifyState.running = false;
    lsSet(LS_VID, String(result.verification_id));
    if ((location.hash || "").includes("verify")) go("#/result/" + result.verification_id);
  } catch (e) {
    verifyState.running = false;
    toast("Synthetic demo failed: " + e.message, true);
  }
}

/* ------------------------------------------------------------------ *
 * Live Camera Verification
 * ------------------------------------------------------------------ */
const camState = { stream: null, active: false };

function setCamStatus(msg, cls) {
  const s = $("#cam-status");
  if (s) { s.textContent = msg; s.className = "cam-status" + (cls ? " " + cls : ""); }
}
function setCamError(msg) {
  const e = $("#cam-error");
  if (e) e.textContent = msg || "";
}
function setCamButtons(running, streamOn) {
  const st = $("#cam-start"), sp = $("#cam-stop"), cf = $("#cam-face");
  if (st) st.disabled = streamOn;
  if (cf) cf.disabled = !streamOn || running;
  if (sp) sp.disabled = !streamOn;
}
function stopCamera() {
  if (camState.stream) { camState.stream.getTracks().forEach(t => t.stop()); camState.stream = null; }
  camState.active = false;
  const v = $("#cam-video"); if (v) v.srcObject = null;
  const fr = $("#cam-frame"); if (fr) fr.classList.remove("detected");
  setCamStatus("Camera is off. Start the camera to begin.");
  setCamButtons(false, false);
}
async function startCamera() {
  setCamError("");
  const video = $("#cam-video");
  if (!video) return;
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    setCamStatus("Camera unavailable in this browser. You can verify by uploading a document instead.", "err");
    setCamError("Camera unavailable. You can verify by uploading a document instead.");
    toast("Camera not supported — use upload instead.", true);
    return;
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" }, audio: false });
    camState.stream = stream;
    camState.active = true;
    video.srcObject = stream;
    setCamStatus("Position the applicant's face inside the frame", "live");
    setCamButtons(false, true);
  } catch (err) {
    const name = (err && err.name) || "";
    if (name === "NotAllowedError" || name === "PermissionDeniedError") {
      setCamStatus("Camera permission denied.", "err");
      setCamError("Camera access was denied. You can verify by uploading a document instead.");
      toast("Camera permission denied", true);
    } else if (name === "NotFoundError" || name === "DevicesNotFoundError") {
      setCamStatus("No camera found.", "err");
      setCamError("Camera unavailable. You can verify by uploading a document instead.");
      toast("No camera found", true);
    } else {
      setCamStatus("Camera could not be opened.", "err");
      setCamError("Camera unavailable (" + name + "). You can verify by uploading a document instead.");
      toast("Camera error: " + name, true);
    }
    setCamButtons(false, false);
  }
}

// Reject a clearly empty/blurry/tiny frame instead of submitting garbage to the
// real verification pipeline. Camera detection is only the capture stage; the
// verdict still comes from OCR + the reference database look-up.
async function frameQualityCheck(canvas) {
  try {
    const ctx = canvas.getContext("2d");
    const data = ctx.getImageData(0, 0, canvas.width, canvas.height).data;
    let sum = 0, sumSq = 0;
    const n = data.length / 4;
    for (let i = 0; i < data.length; i += 4) {
      const g = data[i] * 0.299 + data[i + 1] * 0.587 + data[i + 2] * 0.114;
      sum += g; sumSq += g * g;
    }
    const mean = sum / n;
    const variance = (sumSq / n) - mean * mean;
    return { ok: variance > 200, variance, mean };
  } catch (e) { return { ok: true }; }
}

async function captureFaceAndVerify() {
  const video = $("#cam-video");
  if (!video || !camState.stream) return;
  if (!verifyState.docFile) {
    setCamStatus("Upload a travel document first.", "err");
    setCamError("Upload a travel document above before capturing the face.");
    toast("Please upload a travel document first", true);
    return;
  }
  setCamStatus("Capturing live photo…", "scanning");
  setCamButtons(true, true);
  try {
    // The document ALWAYS comes from the external file upload - never from the
    // camera. Only the applicant's live face is captured here.
    const df = new FormData(); df.append("file", verifyState.docFile);
    const upDoc = await api("/upload-document", { method: "POST", body: df });

    const W = video.videoWidth, H = video.videoHeight;
    if (!W || !H) throw new Error("No video frame");
    const canvas = document.createElement("canvas");
    canvas.width = W; canvas.height = H;
    canvas.getContext("2d").drawImage(video, 0, 0, W, H);
    const q = await frameQualityCheck(canvas);
    if (!q.ok) {
      setCamStatus("Live photo unclear — reposition and hold steady", "err");
      setCamButtons(false, true);
      toast("Live photo too unclear — try again", true);
      return;
    }
    const blob = await new Promise(res => canvas.toBlob(res, "image/jpeg", 0.9));
    if (!blob) throw new Error("Could not encode face frame");
    const file = new File([blob], "camera_face_" + Date.now() + ".jpg", { type: "image/jpeg" });
    const fd = new FormData(); fd.append("file", file);
    const upFace = await api("/upload-photo", { method: "POST", body: fd });

    const docType = $("#doc-type").value || "auto";
    verifyState.docType = docType;
    const result = await api("/verify/document", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ image_filename: upDoc.filename, reference_photo_filename: null, provided_photo_filename: upFace.filename, live_photo_filename: upFace.filename, document_type: docType, method: "live_camera" }),
      timeout: 90000
    });
    stopCamera();
    cacheResult(result);
    verifyState.activeId = result.verification_id;
    verifyState.lastResult = result;
    lsSet(LS_VID, String(result.verification_id));
    setCamStatus("Verification complete", "done");
    go("#/result/" + result.verification_id);
  } catch (e) {
    setCamStatus("Capture failed: " + e.message, "err");
    setCamButtons(false, true);
    toast("Camera verification failed: " + e.message, true);
  }
}

function cacheResult(result) {
  state.results[result.verification_id] = result;
}

/* Render the two image cards side by side: the uploaded/captured document image
 * and the live-captured applicant photo. The live photo is optional - when a
 * verification has no live photo it shows a clean empty state instead of a
 * placeholder/fake image. */
function imageCards(result) {
  const docImg = result.image_url || "";
  const liveImg = result.live_photo_url || "";
  const method = result.method || "upload";
  const isDemo = method === "demo" || result.backend === "synthetic-image" || method === "synthetic";
  const docCap = isDemo ? "Synthetic demo document (fictional)." : "Uploaded document.";
  const liveCap = liveImg ? "Photo captured by camera / applicant." : "No live photo captured.";
  return `<div class="img-grid">
    <div class="card mb">
      <div class="card-title">${ic("doc", "tt-ico")} Document Image</div>
      ${docImg ? `<img class="doc-image" src="${esc(mediaUrl(docImg))}" alt="document">` : `<div class="img-empty"><div class="es-ico">${ic("doc")}</div><div>No document image</div></div>`}
      <div class="muted mt" style="font-size:11.5px">${docCap}</div>
    </div>
    <div class="card mb">
      <div class="card-title">${ic("cam", "tt-ico")} Live Captured Photo</div>
      ${liveImg ? `<img class="doc-image" src="${esc(mediaUrl(liveImg))}" alt="live photo">` : `<div class="img-empty"><div class="es-ico">${ic("cam")}</div><div>No live photo captured</div></div>`}
      <div class="muted mt" style="font-size:11.5px">${liveCap}</div>
    </div>
  </div>`;
}

/* A PASS / FAIL / REVIEW / N/A pill used by the per-check summary. */
function statePill(state, label) {
  const map = {
    pass:    { c: "#1f9d55", t: "PASS" },
    fail:    { c: "#c5282f", t: "FAIL" },
    review:  { c: "#d59000", t: "REVIEW" },
    na:      { c: "#8a93a3", t: "N/A" },
    unknown: { c: "#8a93a3", t: "UNKNOWN" },
  };
  const m = map[state] || map.na;
  return `<span class="check-pill"><span class="dot" style="background:${m.c}"></span>${esc(label)} <b style="font-size:11px">${m.t}</b></span>`;
}

function summaryRow(name, pill) {
  return `<div class="summary-row"><span class="k">${esc(name)}</span>${pill}</div>`;
}

/* One compact summary strip: OCR · MRZ · Database · Face · Liveness · Tamper. */
function checksStrip(result) {
  const ocr = result.ocr || {};
  const fl = result.extracted_fields || {};
  const hasFields = Object.values(fl).some(v => v && v.value);
  const conf = parseFloat(ocr.confidence) || 0;
  const ocrState = !hasFields ? "fail" : (conf < 0.5 ? "review" : "pass");

  const mrz = result.mrz;
  const mrzOk = result.mrz_checksum_valid;
  const mrzState = !mrz ? "na" : (mrzOk ? "pass" : "fail");

  const dm = result.database_match || {};
  const dbState = dm.status === "MATCH" ? "pass" : (dm.status === "CONFLICT" ? "fail" : "review");

  const face = result.face || {};
  const faceState = face.status === "match" ? "pass" : (face.status === "mismatch" ? "fail" : (face.status === "review" ? "review" : "na"));

  const live = result.liveness || {};
  const liveState = live.status === "live" ? "pass" : (live.status === "spoof_suspected" ? "fail" : (live.status === "not_applicable" ? "na" : "review"));

  const tamper = result.tamper || {};
  const tamperState = tamper.risk_level === "high" ? "fail" : (tamper.risk_level === "medium" ? "review" : (tamper.risk_level ? "pass" : "na"));

  return `<div class="card mb">
    <div class="card-title">${ic("shield", "tt-ico")} Verification Checks</div>
    ${summaryRow("OCR", statePill(ocrState, "conf " + conf.toFixed(2)))}
    ${summaryRow("MRZ", statePill(mrzState, mrz ? (mrzOk ? "checksum valid" : "checksum invalid") : "no MRZ zone"))}
    ${summaryRow("Database", statePill(dbState, (dm.status || "NOT_FOUND").toLowerCase()))}
    ${summaryRow("Face", statePill(faceState, face.status === "no_face" ? "no face" : (Math.round((face.score || 0) * 100) + "% similarity")))}
    ${summaryRow("Liveness", statePill(liveState, (live.status || "unknown").replace(/_/g, " ")))}
    ${summaryRow("Tamper", statePill(tamperState, (tamper.risk_level || "na") + " risk"))}
  </div>`;
}

/* Document-image quality + supported-document check card. */
function docQCard(result) {
  const da = result.document_analysis;
  if (!da) return `<div class="card"><div class="card-title">${ic("doc", "tt-ico")} Document Analysis</div><p class="muted">Not performed for this record.</p></div>`;
  const grade = da.quality_grade || "poor";
  const gcls = grade === "good" ? "badge-green" : grade === "moderate" ? "badge-yellow" : "badge-red";
  const sup = da.supported;
  const scls = sup ? "badge-green" : "badge-red";
  const rows = Object.entries(da.scores || {}).map(([k, v]) => detail(esc(k.replace(/_/g, " ")), (Number(v) || 0).toFixed(0) + "/100")).join("");
  const reasons = (da.support_reasons || []).map(r => `<li>${esc(r)}</li>`).join("");
  return `<div class="card"><div class="card-title">${ic("doc", "tt-ico")} Document Analysis <span class="badge ${gcls}">${esc(grade.toUpperCase())}</span></div>
    ${detail("Supported document", sup ? "YES" : "NO")}
    ${detail("Document type", esc(da.doc_type || "-"))}
    ${detail("Quality score", (Number(da.quality_score) || 0).toFixed(0) + "/100")}
    ${detail("Readable", da.readability ? "YES" : "NO")}
    ${rows}
    ${reasons ? `<div class="mt"><span class="badge ${scls}">${sup ? "LAYOUT FOUND" : "NO SUPPORTED DOC"}</span></div>
      <div class="mt"><div class="pre-line muted" style="font-size:11.5px">${reasons}</div></div>` : ""}
  </div>`;
}

/* Liveness (passive anti-spoof) card. */
function livenessCard(result) {
  const lv = result.liveness;
  if (!lv) return `<div class="card"><div class="card-title">${ic("cam", "tt-ico")} Liveness</div><p class="muted">Not performed for this record.</p></div>`;
  const s = (lv.status || "unknown").toLowerCase();
  const bcls = s === "live" ? "badge-green" : s === "spoof_suspected" ? "badge-red" : s === "not_applicable" ? "badge-gray" : "badge-yellow";
  const label = s.replace(/_/g, " ").toUpperCase();
  const scores = Object.entries(lv.scores || {}).map(([k, v]) => detail(esc(k.replace(/_/g, " ")), (Number(v) || 0).toFixed(1) + "/100")).join("");
  return `<div class="card"><div class="card-title">${ic("cam", "tt-ico")} Liveness <span class="badge ${bcls}">${esc(label)}</span></div>
    ${detail("Confidence", (Number(lv.confidence) || 0).toFixed(2))}
    ${scores}
    ${lv.note ? `<div class="pre-line muted" style="font-size:11.5px;margin-top:8px">${esc(lv.note)}</div>` : ""}
  </div>`;
}

/* ------------------------------------------------------------------ *
 * Result page
 * ------------------------------------------------------------------ */

async function renderResult(id) {
  const c = $("#page-content");
  c.innerHTML = "<p class='muted'>Loading result…</p>";
  let result = state.results[id];
  if (!result) {
    try { result = await api("/verification/" + id); state.results[id] = result; }
    catch (e) { c.innerHTML = `<div class="card"><p class="muted">Result not found.</p></div>`; return; }
  }
  const risk = result.risk || {};
  const decision = risk.decision || "REVIEW REQUIRED";
  const vstatus = result.verification_status || (decision === "VERIFIED" ? "VERIFIED" : decision === "HIGH RISK" ? "NOT_VERIFIED" : "UNVERIFIED");
  const vreason = result.verification_reason || "";
  const method = result.method || "upload";
  const methodLabel = method === "live_camera" ? "Live Camera" : method === "demo" ? "Quick Demo" : method === "synthetic" ? "Synthetic Demo" : "Document Upload";
  const docImg = result.image_url || "";
  const rcls = risk.level === "HIGH" ? "badge-red" : risk.level === "MEDIUM" ? "badge-yellow" : "badge-green";
  const vcls = vstatus === "VERIFIED" ? "v-verified" : (vstatus === "NOT_VERIFIED" || vstatus === "NOT VERIFIED") ? "v-high" : "v-review";
  const meterColor = risk.level === "HIGH" ? "var(--red)" : risk.level === "MEDIUM" ? "var(--yellow)" : "var(--green)";
  const docTypeLabel = (result.synthetic_label || (result.document_type || "passport").toUpperCase());

  c.innerHTML = `
    <div class="result-head">
      <div style="min-width:0">
        <div class="flex"><span class="badge ${rcls}">RISK ${risk.score} / 100</span>
          <span class="badge badge-blue">${esc(docTypeLabel)}</span>
          ${result.backend === "mongodb" ? `<span class="badge badge-green" title="Result driven by a lookup in the MongoDB reference database">DATABASE VERIFICATION</span>` : ""}
          ${result.backend === "synthetic-image" ? `<span class="badge badge-blue" title="Heuristic image-based document authenticity analysis">SYNTHETIC DOC DEMO</span>` : ""}
          <span class="badge badge-gray" title="Verification method">${esc(methodLabel)}</span>
          ${method === "live_camera" ? `<span class="badge badge-blue">LIVE CAMERA</span>` : ""}</div>
        <h2 style="margin-top:12px">Verification #${id}</h2>
        <p class="crumb mt">${esc(result.passenger?.full_name || "Unknown passenger")} · ${esc(result.passenger?.document_number||"-")}</p>
      </div>
      <div class="result-verdict">
        <div class="verdict-badge ${vcls}">${esc(vstatus)}</div>
        <div class="risk-big" style="justify-content:center"><span class="score-num" style="color:${meterColor}">${risk.score}</span><span class="score-max">/100</span></div>
        <div class="muted">${risk.level} risk</div>
      </div>
    </div>

    ${vreason ? `<div class="card mb" style="border:1px solid ${meterColor}33;padding:12px 16px"><b>Verification outcome:</b> ${esc(vstatus)} — ${esc(vreason)}</div>` : ""}

    <div class="result-layout">
      <div>
        ${imageCards(result)}
      </div>
      <div>
        ${whyCard(result)}
        <div class="section-grid">
          ${riskCard(result)}
          ${passengerCard(result.passenger)}
          ${dbMatchCard(result)}
          ${sourceCard(result)}
          ${tamperCard(result)}
          ${ocrCard(result)}
          ${mrzCard(result)}
          ${crossCard(result)}
          ${faceCard(result)}
          ${livenessCard(result)}
          ${docQCard(result)}
          ${checksStrip(result)}
          ${expiryCard(result)}
          ${watchCard(result)}
          ${dupCard(result)}
        </div>
      </div>
    </div>
    <div class="mt" style="text-align:center"><button class="btn btn-ghost" onclick="go('#/verify')">+ New Verification</button>
      <button class="btn btn-ghost" onclick="go('#/history')">History</button></div>
    `;
}

/* "WHY THIS RESULT?" — contributions + reasons, judge-friendly. */
function whyCard(result) {
  const risk = result.risk || {};
  const contribs = (risk.contributions || []).filter(c => c.applied);
  const rows = contribs.length ? contribs.map(c =>
    `<div class="contrib-row"><span class="c-signal">${esc(c.signal.replace(/_/g," "))}</span><span class="c-weight pos">+${c.weight}</span></div>`).join("")
    : `<div class="contrib-row"><span class="c-signal">No active risk signals</span><span class="c-weight none">0</span></div>`;
  const reasonsHtml = (risk.reasons && risk.reasons.length)
    ? `<ul class="reasons mt">${risk.reasons.map(x => `<li class="${x.toLowerCase().includes("no significant") || x.toLowerCase().includes("no negative") ? "ok" : ""}">${esc(x)}</li>`).join("")}</ul>`
    : "";
  const note = result.notes && result.notes.length
    ? `<p class="muted mt" style="font-size:11.5px;background:var(--panel-2);padding:10px;border-radius:8px">${result.notes.map(esc).join("<br>")}</p>` : "";
  const score = risk.score || 0;
  const level = risk.level || "LOW";
  const color = level === "HIGH" ? "var(--red)" : level === "MEDIUM" ? "var(--yellow)" : "var(--green)";
  return `<div class="card mb" style="border:1px solid ${color}33">
    <div class="card-title">${ic("shield", "tt-ico")} Why this result?</div>
    <div class="risk-label-row"><span>Risk score</span><span>${score} / 100</span></div>
    <div class="risk-meter"><div class="risk-fill" style="width:${score}%;background:${color}"></div></div>
    <div class="contrib-rows">${rows}</div>
    ${reasonsHtml}
    ${note}
  </div>`;
}

function detail(k, v, cls) {
  return `<div class="detail"><span class="k">${k}</span><span class="v ${cls||""}">${v}</span></div>`;
}
function ci(ok, label) {
  const cls = ok ? "check-pill" : "check-pill";
  const c = ok ? "#1f9d55" : "#c5282f";
  const dot = ok ? "dot-green" : "dot";
  return `<span class="${cls}"><span class="dot" style="background:${c}"></span>${label}</span>`;
}

function passengerCard(p) {
  p = p || {};
  const yyyymmdd = s => s ? (s.length === 6 ? `20${s.slice(0,2)}-${s.slice(2,4)}-${s.slice(4,6)}` : s) : "-";
  return `<div class="card"><div class="card-title">${ic("user", "tt-ico")} Passenger / Holder</div>
    ${detail("Full name", esc(p.full_name||"-"))}
    ${detail("Date of birth", esc(yyyymmdd(p.date_of_birth))||"-")}
    ${detail("Nationality", esc(p.nationality||"-"))}
    ${detail("Sex", esc(p.sex||"-"))}
    ${detail("Document No.", esc(p.document_number||"-"))}
    ${detail("Date of expiry", esc(yyyymmdd(p.date_of_expiry)))}
    ${detail("Date of issue", esc(p.date_of_issue||"-"))}
    ${detail("Issuing country", esc(p.issuing_country||"-"))}
  </div>`;
}

function riskCard(result) {
  const r = result.risk || {};
  const color = r.level === "HIGH" ? "var(--red)" : r.level === "MEDIUM" ? "var(--yellow)" : "var(--green)";
  return `<div class="card"><div class="card-title">${ic("shield", "tt-ico")} Risk Score</div>
    <div class="risk-big"><span class="score-num" style="color:${color}">${r.score||0}</span><span class="score-max">/100</span></div>
    <div class="risk-label-row"><span>LOW 0</span><span>MEDIUM 31</span><span>HIGH 61+</span></div>
    <div class="risk-meter"><div class="risk-fill" style="width:${r.score||0}%;background:${color}"></div></div>
    <div class="flex mb"><span class="badge ${r.level==="HIGH"?"badge-red":r.level==="MEDIUM"?"badge-yellow":"badge-green"}">${esc(r.level||"")} RISK</span><span class="badge ${r.decision==="VERIFIED"?"badge-green":r.decision==="HIGH RISK"?"badge-red":"badge-yellow"}">${esc(r.decision||"")}</span></div>
  </div>`;
}

function ocrCard(result) {
  const ocr = result.ocr || {};
  const fl = result.extracted_fields || {};
  const rows = Object.entries(fl).filter(([,v]) => v && v.value).map(([k,v]) =>
      detail(esc(k.replace(/_/g," ")), esc(v.value))).join("");
  const conf = (ocr.confidence||0).toFixed(2);
  const raw = (ocr.text||"").trim();
  return `<div class="card"><div class="card-title">${ic("scan", "tt-ico")} OCR Extraction <span class="badge badge-gray">conf ${conf}</span></div>
    ${rows || "<p class='muted'>No fields extracted.</p>"}
    ${raw ? `<div class="collapsible mt">
      <button type="button">${ic("scan")} Raw OCR text <span class="ch-caret">${ic("chevDown")}</span></button>
      <div class="ch-body hidden"><div class="pre-line muted" style="font-size:12px;background:var(--panel-2);padding:10px;border-radius:8px">${esc(raw)}</div></div>
    </div>` : ""}
  </div>`;
}

function mrzCard(result) {
  const m = result.mrz;
  if (!m) return `<div class="card"><div class="card-title">${ic("scan", "tt-ico")} MRZ Zone</div><p class="muted">No MRZ detected.</p></div>`;
  const ok = result.mrz_checksum_valid;
  const checks = (m.checks||[]).map(ch => ci(ch.ok, `${ch.field} ${ch.ok?"OK":"FAIL"}`)).join(" ");
  const lines = (m.raw_lines||[]).map(l => `<div class="mono">${esc(l)}</div>`).join("");
  return `<div class="card"><div class="card-title">${ic("scan", "tt-ico")} MRZ Zone <span class="badge ${ok?"badge-green":"badge-red"}">${ok ? "VALID" : "INVALID"}</span></div>
    ${detail("Document number", esc(m.document_number||"-"))}
    ${detail("Nationality", esc(m.nationality||"-"))}
    ${detail("Date of birth", esc(m.date_of_birth||"-"))}
    ${detail("Date of expiry", esc(m.date_of_expiry||"-"))}
    ${detail("Sex", esc(m.sex||"-"))}
    <div class="mt">${checks || "<span class='muted'>No check digits.</span>"}</div>
    ${lines ? `<div class="collapsible mt">
      <button type="button">${ic("scan")} MRZ text <span class="ch-caret">${ic("chevDown")}</span></button>
      <div class="ch-body hidden"><div class="mrz-text">${lines}</div></div>
    </div>` : ""}
  </div>`;
}

function crossCard(result) {
  const cc = result.cross_check || {};
  const checks = (cc.checks||[]).map(c => detail(c.field, c.status === "match" ? "MATCH" : c.status === "mismatch" ? "MISMATCH" : "n/a",
      c.status === "mismatch" ? "bad" : "ok")).join("");
  const ok = cc.overall_consistent;
  return `<div class="card"><div class="card-title">${ic("scan", "tt-ico")} OCR vs MRZ Cross-Validation <span class="badge ${ok?"badge-green":"badge-red"}" style="margin-left:6px">${ok?"CONSISTENT":"INCONSISTENT"}</span></div>
    ${checks || "<p class='muted'>No fields to compare.</p>"}
    ${(cc.mismatches||[]).length ? `<ul class="reasons mt">${cc.mismatches.map(x=>`<li>${esc(x)}</li>`).join("")}</ul>` : ""}
  </div>`;
}

function faceCard(result) {
  const f = result.face || {};
  const score = (f.score||0);
  const pct = Math.round(score*100);
  const status = f.status;
  const cls = status === "match" ? "badge-green" : status === "mismatch" ? "badge-red" : status === "review" ? "badge-yellow" : "badge-gray";
  return `<div class="card"><div class="card-title">${ic("face", "tt-ico")} Face Verification</div>
    <div class="risk-big"><span class="score-num" style="color:${status==="mismatch"?"var(--red)":"var(--green)"}">${pct}%</span>
      <span class="badge ${cls}">${esc((status||"n/a").toUpperCase())}</span></div>
    <div class="risk-meter"><div class="risk-fill" style="width:${pct}%;background:${status==="mismatch"?"var(--red)":"var(--green)"}"></div></div>
    <p class="muted">${esc(f.message||"")}</p>
  </div>`;
}

function tamperCard(result) {
  const t = result.tamper || {};
  const level = t.risk_level || "low";
  const cls = level === "high" ? "badge-red" : level === "medium" ? "badge-yellow" : "badge-green";
  const sigs = (t.signals||[]).map(s => detail(esc(s.name.replace(/_/g," ")), `${Math.round(s.score)} · ${s.label}`,
      s.label === "high" ? "bad" : s.label === "suspicious" ? "" : "ok")).join("");
  const col = level === "high" ? "var(--red)" : level === "medium" ? "var(--yellow)" : "var(--green)";
  return `<div class="card"><div class="card-title">${ic("shield", "tt-ico")} Document Authenticity</div>
    <div class="risk-big"><span class="score-num" style="color:${col}">${Math.round(t.overall_score||0)}</span><span class="score-max">/100</span>
      <span class="badge ${cls}">${esc((level||"low").toUpperCase())}</span></div>
    <div class="risk-meter"><div class="risk-fill" style="width:${t.overall_score||0}%;background:${col}"></div></div>
    ${sigs || "<p class='muted'>No anomaly signals.</p>"}
    <p class="muted mt" style="font-size:11.5px">Heuristic image analysis — not forensic-grade.</p>
  </div>`;
}

function expiryCard(result) {
  const e = result.expiry || {};
  const status = e.status || "unknown";
  const cls = status === "valid" ? "badge-green" : status === "expired" ? "badge-red" : "badge-yellow";
  const label = status === "valid" ? "VALID" : status === "expired" ? "EXPIRED" : "EXPIRING SOON";
  return `<div class="card"><div class="card-title">${ic("clock", "tt-ico")} Expiry Status</div>
    <div class="flex"><span class="badge ${cls}">${label}</span>
      ${e.days_left!=null ? `<span class="muted">${e.days_left} day(s)</span>` : ""}</div>
    <p class="muted mt">${esc(e.explanation||"")}</p>
  </div>`;
}

function watchCard(result) {
  const w = result.watchlist || {};
  return `<div class="card"><div class="card-title">${ic("alert", "tt-ico")} Watchlist Check <span class="badge ${w.matched?"badge-red":"badge-green"}">${w.matched?"MATCH":"CLEAR"}</span></div>
    <p class="muted">${esc(w.reason || (w.matched ? "Demo watchlist match." : "No watchlist match."))}</p>
    <p class="muted mt" style="font-size:11px">Source: ${esc(w.source||"DEMO")} (synthetic data - not a real government watchlist)</p>
  </div>`;
}

function dupCard(result) {
  const d = result.duplicate || {};
  const sigs = (d.signals||[]).map(s => detail(s.field, Math.round(s.similarity*100)+"%")).join("");
  return `<div class="card"><div class="card-title">${ic("user", "tt-ico")} Duplicate Identity <span class="badge ${d.is_duplicate?"badge-red":"badge-yellow"}">${d.is_duplicate?"ALERT":"CHECK"}</span></div>
    <div class="detail"><span class="k">Confidence</span><span class="v">${Math.round((d.confidence||0)*100)}%</span></div>
    ${sigs}
    <p class="muted mt">${esc(d.explanation||"")}</p>
  </div>`;
}

/* Reference-database match card: shows the matched record from the reference DB
 * and (when present) exactly which identity fields conflict with it. */
function dbMatchCard(result) {
  const dm = result.database_match;
  if (!dm) return "";
  const status = dm.status || "NOT_FOUND";
  const rec = dm.record || {};
  const mism = dm.mismatched_fields || [];
  const isMatch = status === "MATCH";
  const isConflict = status === "CONFLICT";
  const badge = isMatch ? "badge-green" : isConflict ? "badge-red" : "badge-yellow";
  const statusText = isMatch ? "MATCH" : isConflict ? "CONFLICT" : "NOT FOUND";
  const fancyDate = s => {
    const t = String(s || "").replace(/[^0-9]/g, "");
    if (t.length === 8) return `${t.slice(0,4)}-${t.slice(4,6)}-${t.slice(6,8)}`;
    if (t.length === 6) return `20${t.slice(0,2)}-${t.slice(2,4)}-${t.slice(4,6)}`;
    return s || "-";
  };
  const recKeys = ["surname", "given_names", "nationality", "date_of_birth",
                   "date_of_expiry", "issuing_country", "status"];
  const recRows = recKeys.filter(k => {
    const v = rec[k];
    return v !== "" && v !== null && v !== undefined && v !== false;
  }).map(k => detail(esc(k.replace(/_/g, " ")),
                     k.includes("date") ? esc(fancyDate(rec[k])) : esc(String(rec[k])))).join("");
  const mismRows = mism.length
    ? mism.map(m => `<div class="detail"><span class="k">${esc(m.field.replace(/_/g," "))}</span><span class="v">extracted: ${esc(String(m.extracted))} · DB: ${esc(String(m.reference))}</span></div>`).join("")
    : "";
  return `<div class="card"><div class="card-title">${ic("db","tt-ico")} Reference Database Match <span class="badge ${badge}">${statusText}</span></div>
    <div class="detail"><span class="k">Document No.</span><span class="v">${esc(dm.document_number || "-")}</span></div>
    ${isConflict ? `<div class="muted" style="font-size:11.5px">Matched a database record but the extracted identity fields conflict:</div>` : ""}
    ${recRows}
    ${mism.length ? `${mismRows}` : `<div class="mt"><span class="check-pill"><span class="dot" style="background:#1f9d55"></span>${isMatch ? "Identity fields aligned with the database record" : "No database record matched"}</span></div>`}
    <p class="muted mt" style="font-size:11px">Matched record retrieved from reference database · simulated data, not a real government database</p>
  </div>`;
}

function sourceCard(result) {
  const ds = result.data_source || "SIH SYNTHETIC DEMO DATABASE";
  const env = result.environment || "DEMO / MOCK";
  const backend = result.backend || result.source_provenance?.backend || "";
  const checks = (result.source_provenance && result.source_provenance.checks) || [];
  const rows = checks.map(c =>
    `<div class="detail"><span class="k">${esc(c.check.replace(/_/g," "))}</span>
       <span class="v ${c.matched?"":"muted"}">${esc(c.table)} · ${c.matched?"match":"none"}</span>
     </div>`).join("");
  const body = `<div class="detail"><span class="k">DATA SOURCE</span><span class="v">${esc(ds)}</span></div>
    <div class="detail"><span class="k">Environment</span><span class="v">${esc(env)}</span></div>
    ${rows}`;
  return `<div class="card"><div class="card-title">${ic("db", "tt-ico")} Database Verification <span class="badge ${backend === "mongodb" ? "badge-blue" : "badge-gray"}">${backend === "mongodb" ? "MongoDB" : "DEMO"}</span></div>
    ${body}
    <p class="muted mt" style="font-size:11px">Simulated data - not a real government database.</p>
  </div>`;
}

/* Full rendered results for a restored verification session. Reuses the same
 * card components as the Result page so OCR/MRZ, extracted fields, database
 * match, risk, tamper, face and the final decision are all shown in the UI. */
function restoredSessionHtml(result, id) {
  const risk = result.risk || {};
  const decision = risk.decision || "REVIEW REQUIRED";
  const vstatus = result.verification_status || (decision === "VERIFIED" ? "VERIFIED" : decision === "HIGH RISK" ? "NOT_VERIFIED" : "UNVERIFIED");
  const vreason = result.verification_reason || "";
  const method = result.method || "upload";
  const methodLabel = method === "live_camera" ? "Live Camera" : method === "demo" ? "Quick Demo" : method === "synthetic" ? "Synthetic Demo" : "Document Upload";
  const docImg = result.image_url || "";
  const rcls = risk.level === "HIGH" ? "badge-red" : risk.level === "MEDIUM" ? "badge-yellow" : "badge-green";
  const vcls = vstatus === "VERIFIED" ? "v-verified" : (vstatus === "NOT_VERIFIED" || vstatus === "NOT VERIFIED") ? "v-high" : "v-review";
  const meterColor = risk.level === "HIGH" ? "var(--red)" : risk.level === "MEDIUM" ? "var(--yellow)" : "var(--green)";
  const docTypeLabel = (result.synthetic_label || (result.document_type || "passport").toUpperCase());
  return `
  <div class="card mt" id="verify-restored">
    <div class="flex" style="justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px">
      <div class="card-title" style="margin:0">${ic("list", "tt-ico")} Restored Verification Session <span class="badge badge-blue">#${id}</span></div>
      <button class="btn btn-primary btn-sm" onclick="go('#/result/${id}')">${ic("arrowR")} Open Full Result</button>
    </div>
    <div class="result-head">
      <div style="min-width:0">
        <div class="flex"><span class="badge ${rcls}">RISK ${risk.score} / 100</span>
          <span class="badge badge-blue">${esc(docTypeLabel)}</span>
          ${result.backend === "mongodb" ? `<span class="badge badge-green" title="Result driven by a lookup in the MongoDB reference database">DATABASE VERIFICATION</span>` : ""}
          ${result.backend === "synthetic-image" ? `<span class="badge badge-blue" title="Heuristic image-based document authenticity analysis">SYNTHETIC DOC DEMO</span>` : ""}
          <span class="badge badge-gray" title="Verification method">${esc(methodLabel)}</span>
          ${method === "live_camera" ? `<span class="badge badge-blue">LIVE CAMERA</span>` : ""}</div>
        <h2 style="margin-top:12px">Verification #${id}</h2>
        <p class="crumb mt">${esc(result.passenger?.full_name || "Unknown passenger")} · ${esc(result.passenger?.document_number||"-")}</p>
      </div>
      <div class="result-verdict">
        <div class="verdict-badge ${vcls}">${esc(vstatus)}</div>
        <div class="risk-big" style="justify-content:center"><span class="score-num" style="color:${meterColor}">${risk.score}</span><span class="score-max">/100</span></div>
        <div class="muted">${risk.level} risk</div>
      </div>
    </div>
    ${vreason ? `<div class="card mb" style="border:1px solid ${meterColor}33;padding:12px 16px"><b>Verification outcome:</b> ${esc(vstatus)} — ${esc(vreason)}</div>` : ""}
    <div class="result-layout">
      <div>
        ${imageCards(result)}
      </div>
      <div>
        ${whyCard(result)}
        <div class="section-grid">
          ${riskCard(result)}
          ${passengerCard(result.passenger)}
          ${dbMatchCard(result)}
          ${sourceCard(result)}
          ${tamperCard(result)}
          ${ocrCard(result)}
          ${mrzCard(result)}
          ${crossCard(result)}
          ${faceCard(result)}
          ${livenessCard(result)}
          ${docQCard(result)}
          ${checksStrip(result)}
          ${expiryCard(result)}
          ${watchCard(result)}
          ${dupCard(result)}
        </div>
      </div>
    </div>
  </div>`;
}

/* ------------------------------------------------------------------ *
 * History & Alerts
 * ------------------------------------------------------------------ */

async function renderHistory() {
  const c = $("#page-content");
  try {
    const history = await api("/verification/history?limit=100");
    const body = history.length ? history.map(row).join("")
      : `<tr><td colspan="8" class="muted" style="text-align:center;padding:28px">No verifications yet. Run a <a href="#/verify">demo case</a>.</td></tr>`;
    c.innerHTML = `
      <div class="card">
        <div class="flex mb" style="justify-content:space-between">
          <div class="card-title" style="margin:0">${ic("list", "tt-ico")} Verification History <span class="badge badge-gray">${history.length}</span></div>
          <button class="btn btn-ghost btn-sm" onclick="go('#/verify')">${ic("upload")} New Verification</button>
        </div>
        <div class="table-wrap"><table>
        <thead><tr><th>No.</th><th>Image</th><th>Passenger</th><th>Document</th><th>Nationality</th><th>Score</th><th>Decision</th><th>Time</th></tr></thead>
        <tbody>${body}</tbody>
        </table></div>
      </div>`;
    wireHistoryRows();
  } catch (e) { c.innerHTML = `<div class="card"><p class="muted">Error: ${esc(e.message)}</p></div>`; }
}

async function renderAlerts() {
  const c = $("#page-content");
  try {
    const alerts = await api("/alerts");
    const sevCls = s => s === "high" ? "a-high" : s === "medium" ? "a-medium" : "a-low";
    const sevBadge = s => s === "high" ? "badge-red" : s === "medium" ? "badge-yellow" : "badge-green";
    const sevIcon = s => s === "high" ? "alert" : s === "medium" ? "warning" : "info";
    const items = alerts.length ? alerts.map(a => `
      <div class="alert-card ${sevCls(a.severity)}">
        <span class="a-ico">${ic(sevIcon(a.severity))}</span>
        <div style="flex:1">
          <div class="flex" style="justify-content:space-between;flex-wrap:wrap;gap:6px">
            <div class="flex"><span class="badge ${sevBadge(a.severity)}">${esc(a.severity.toUpperCase())}</span><b>${esc(a.title)}</b></div>
            <span class="muted" style="font-size:12px">${fmtTime(a.created_at)}</span>
          </div>
          <p class="muted mt" style="margin-top:8px">${esc(a.message)}</p>
        </div>
      </div>`).join("")
      : `<div class="empty-state"><div class="es-ico">${ic("check")}</div><div>No alerts. All clear.</div></div>`;
    c.innerHTML = `<div class="card"><div class="card-title">${ic("alert", "tt-ico")} Alerts <span class="badge badge-gray">${alerts.length}</span></div>${items}</div>`;
  } catch (e) { c.innerHTML = `<div class="card"><p class="muted">Error: ${esc(e.message)}</p></div>`; }
}

/* ------------------------------------------------------------------ *
 * Demo Database (MongoDB reference data)
 * ------------------------------------------------------------------ */

async function renderDatabase() {
  const c = $("#page-content");
  c.innerHTML = "<p class='muted'>Loading database overview…</p>";
  try {
    const [ov, cols] = await Promise.all([api("/database/overview"), api("/database/collections")]);
    const isMongo = ov.storage === "MongoDB";
    const storage = isMongo ? `<span class="badge badge-green">${ic("db")} MongoDB · ${esc(ov.database)}</span>`
                            : `<span class="badge badge-red">${esc(ov.storage)}</span>`;
    const countsHtml = Object.entries(ov.counts || {}).map(([k, v]) =>
      `<div class="stat-card"><div class="stat-label">${esc(k.replace(/_/g, " "))}</div><div class="stat-value">${v}</div></div>`
    ).join("");

    const colIcon = n => n.includes("verification") ? "list" : n.includes("passport") ? "doc"
      : n.includes("visa") ? "doc" : n.includes("watchlist") ? "alert" : n.includes("identity") ? "user"
      : n.includes("passenger") ? "user" : n.includes("audit") ? "list" : "db";
    const colCards = (cols.collections || []).map(col => `
      <div class="card">
        <div class="flex"><span class="stat-ico">${ic(colIcon(col.name))}</span>
          <div class="card-title" style="margin:0;flex:1">${esc(col.name.replace(/_/g, " "))}</div>
          <span class="badge badge-blue">${col.count} docs</span></div>
        <p class="muted mb" style="font-size:12px">${esc(col.description || "")}</p>
        <div class="collapsible">
          <button type="button">${ic("db")} Sample records <span class="ch-caret">${ic("chevDown")}</span></button>
          <div class="ch-body hidden"><div style="font-size:12px;background:var(--panel-2);padding:10px;border-radius:8px;overflow:auto;max-height:200px">
            ${formatJson(col.sample_records || [])}
          </div></div>
        </div>
      </div>`).join("");

    c.innerHTML = `
      <div class="card mb">
        <div class="flex" style="justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px">
          <div class="card-title" style="margin:0">${ic("db", "tt-ico")} Reference Database</div>
          ${storage}
        </div>
        <div class="grid stats-grid" style="margin:14px 0 0">${countsHtml}</div>
      </div>

      <div class="card mb">
        <div class="card-title">${ic("info", "tt-ico")} Data Source Identity</div>
        <div class="detail"><span class="k">DATA SOURCE</span><span class="v">${esc(ov.label)}</span></div>
        <div class="detail"><span class="k">Environment</span><span class="v">${esc(ov.environment)}</span></div>
        <div class="detail"><span class="k">Government integration</span><span class="v">${esc(ov.government_integration || "NOT CONNECTED")}</span></div>
        <div class="detail"><span class="k">Planned future</span><span class="v">${esc(ov.future_integration || "")}</span></div>
        <p class="muted mt" style="font-size:11.5px">${esc(ov.disclaimer || "")}</p>
        <p class="mt" style="font-size:11.5px;background:var(--yellow-bg);color:var(--yellow);padding:10px;border-radius:8px">
          <b>${esc(ov.label || "SIH SYNTHETIC DEMO DATABASE")}</b> — NOT a real government database.
        </p>
        <div class="mt" style="display:flex;gap:8px">
          <input id="db-lookup" class="fld" placeholder="Enter document no. e.g. P1234567" style="flex:1;min-width:0">
          <button id="db-lookup-btn" class="btn btn-primary">${ic("search")} Lookup</button>
        </div>
        <div id="db-lookup-out" class="mt"></div>
      </div>

      <div class="card-title mt">${ic("list", "tt-ico")} Collections</div>
      <div class="section-grid mt">${colCards}</div>
    `;

    $("#db-lookup-btn").onclick = dbLookup;
    $("#db-lookup").addEventListener("keydown", e => { if (e.key === "Enter") dbLookup(); });
  } catch (e) {
    c.innerHTML = `<div class="card"><p class="muted">Error loading database: ${esc(e.message)}</p></div>`;
  }
}

async function dbLookup() {
  const input = $("#db-lookup");
  const out = $("#db-lookup-out");
  const doc = (input.value || "").trim().toUpperCase();
  if (!doc) { toast("Enter a document number", true); return; }
  out.innerHTML = "<p class='muted'>Looking up…</p>";
  try {
    const res = await api("/database/lookup/" + encodeURIComponent(doc));
    const rows = Object.entries(res.results || {}).map(([k, v]) =>
      `<div class="detail"><span class="k">${esc(k.replace(/_/g," "))}</span>
         <span class="v ${v ? "ok" : "muted"}">${v ? "MATCH" : "none"}</span></div>`).join("");
    const n = (res.matched_sources && res.matched_sources.length) || 0;
    out.innerHTML = `
      <div class="card" style="border:1px solid ${n ? "var(--yellow)" : "var(--green)"}33">
        <div class="card-title">${ic("search", "tt-ico")} Look-up: <span class="mono">${esc(doc)}</span>
          ${n ? `<span class="badge badge-yellow">${n} source(s)</span>` : `<span class="badge badge-green">NO MATCH</span>`}</div>
        <div class="muted">${esc(res.summary || "")}</div>
        <div class="mt">${rows}</div>
      </div>`;
  } catch (e) { out.innerHTML = `<p class="muted">Lookup failed: ${esc(e.message)}</p>`; }
}

function formatJson(obj) {
  const s = obj === undefined ? "" : JSON.stringify(obj, null, 2);
  return s ? `<pre class="mono" style="margin:0;white-space:pre-wrap;font-size:11px">${esc(s)}</pre>` : "<pre class='mono' style='margin:0'>[]</pre>";
}

/* ------------------------------------------------------------------ *
 * Boot
 * ------------------------------------------------------------------ */

/* Global safety net: any uncaught runtime error renders a visible message
 * instead of leaving a blank page. */
function showFatal(err) {
  const c = $("#page-content");
  if (c) c.innerHTML = `<div class="card"><h3 style="color:var(--red)">Something went wrong</h3>
    <p class="muted">${esc(err && err.message ? err.message : "Unknown error")}</p>
    <button class="btn btn-primary mt" onclick="location.reload()">Reload</button></div>`;
}
window.addEventListener("error", e => { showFatal(e.error || e.message); });
window.addEventListener("unhandledrejection", e => { showFatal(e.reason); });

window.addEventListener("hashchange", route);

/* Global toggle for collapsible detail sections (event delegation). */
document.addEventListener("click", (e) => {
  const btn = e.target.closest(".collapsible > button");
  if (btn) {
    const box = btn.parentElement;
    box.classList.toggle("open");
    const body = box.querySelector(".ch-body");
    if (body) body.classList.toggle("hidden");
  }
});
window.addEventListener("load", () => {
  $("#login-form").addEventListener("submit", async e => {
    e.preventDefault();
    const msg = $("#login-msg");
    const user = $("#login-user").value.trim();
    const pass = $("#login-pass").value;
    msg.className = "login-msg info"; msg.textContent = "Signing in…";
    // Ensure backend discovery has finished so the request URL + outcome are accurate.
    await backendReady;
    console.log("[LOGIN] REQUEST URL:", API + "/auth/login");
    console.log("[LOGIN] REQUEST METHOD: POST");
    console.log("[LOGIN] REQUEST STARTED", new Date().toISOString());
    try {
      await login(user, pass);
      console.log("[LOGIN] RESPONSE STATUS: 200");
      console.log("[LOGIN] RESPONSE BODY: ok (token stored, username=" + state.user.username + ", role=" + state.user.role + ")");
      msg.textContent = "";
      toast("Welcome, officer");
      if (!location.hash || location.hash === "#/" || location.hash === "#/login") location.hash = "#/dashboard";
      route();
    } catch (err) {
      const status = (err && err.status) || "N/A";
      console.log("[LOGIN] RESPONSE STATUS:", status);
      console.log("[LOGIN] ERROR:", (err && err.message) || err);
      msg.className = "login-msg";
      msg.textContent = (err && err.message) || "Login failed. Please try again.";
    }
  });
  $("#logout-btn").onclick = () => logout(false);
  // The backend connection status (Connecting / Connected / Not reachable) is set
  // by discoverBackend() on the dedicated #backend-status element, so the login
  // card never shows a misleading "backend required" banner before the runtime
  // probe has actually finished.
  try {
    route();
  } catch (err) { showFatal(err); }
});
