// Sieve. — recruiter dashboard (vanilla JS, no build step)
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const state = { me: null, jobs: [], job: null, cands: [], appId: null, filter: "ALL" };

async function api(path, opts = {}) {
  const init = { method: opts.method || (opts.body || opts.form ? "POST" : "GET"), credentials: "same-origin" };
  if (opts.form) init.body = opts.form;
  else if (opts.body) { init.body = JSON.stringify(opts.body); init.headers = { "Content-Type": "application/json" }; }
  const res = await fetch(path, init);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) { const e = new Error(typeof data.detail === "string" ? data.detail : "Something went wrong."); e.status = res.status; throw e; }
  return data;
}
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const band = s => (s >= 70 ? "hi" : s >= 45 ? "md" : "lo");
const nameHtml = (name, id) => `<span class="real-name">${esc(name)}</span><span class="anon">Candidate #${id}</span>`;
function toast(msg, bad = false) {
  const t = document.createElement("div"); t.className = "toast" + (bad ? " bad" : ""); t.textContent = msg;
  $("#toasts").appendChild(t); setTimeout(() => t.remove(), 4500);
}

// ---------- theme + blind mode ----------
const theme = () => document.documentElement.dataset.theme || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
if (!document.documentElement.dataset.theme) document.documentElement.dataset.theme = theme();
$$(".theme-btn").forEach(b => b.addEventListener("click", () => {
  const next = theme() === "dark" ? "light" : "dark";
  document.documentElement.dataset.theme = next;
  try { localStorage.setItem("sieve-theme", next); } catch (e) {}
}));
try { $("#blind").checked = localStorage.getItem("sieve-blind") === "1"; } catch (e) {}
document.body.classList.toggle("blind", $("#blind").checked);
$("#blind").addEventListener("change", e => {
  document.body.classList.toggle("blind", e.target.checked);
  try { localStorage.setItem("sieve-blind", e.target.checked ? "1" : "0"); } catch (err) {}
});

// ---------- login ----------
function showLogin() { $("#app").hidden = true; $("#login").hidden = false; $("#login-form [name=email]").focus(); }
$("#login-form").addEventListener("submit", async e => {
  e.preventDefault(); const f = new FormData(e.target); $("#login-error").textContent = "";
  try { await api("/api/login", { body: { email: f.get("email"), password: f.get("password") } }); e.target.reset(); boot(); }
  catch (err) { $("#login-error").textContent = err.message; }
});
$("#logout").addEventListener("click", async () => { await api("/api/logout", { body: {} }); state.job = null; state.appId = null; showLogin(); });

// ---------- boot ----------
async function boot() {
  try { state.me = await api("/api/me"); } catch (e) { if (e.status === 401) return showLogin(); throw e; }
  $("#login").hidden = true; $("#app").hidden = false;
  $("#org").textContent = state.me.org; $("#who").textContent = state.me.name;
  await loadJobs();
  if (!state.job && state.jobs.length) selectJob(state.jobs[0].code);
  loadInbox().catch(() => {});
}

async function loadJobs() {
  state.jobs = await api("/api/jobs");
  $("#jobs").innerHTML = state.jobs.map(j => `
    <button class="job ${state.job === j.code ? "on" : ""}" data-code="${j.code}">
      <span class="code">${esc(j.code)}</span><span class="t">${esc(j.title)}</span>
      <span class="counts"><span><b>${j.total}</b> applied</span><span><b>${j.new}</b> new</span><span><b>${j.shortlisted}</b> shortlisted</span></span>
    </button>`).join("");
  $$(".job").forEach(b => b.addEventListener("click", () => { selectJob(b.dataset.code); showTab("cands"); }));
}

async function selectJob(code) {
  state.job = code; state.appId = null;
  $$(".job").forEach(b => b.classList.toggle("on", b.dataset.code === code));
  const j = state.jobs.find(x => x.code === code);
  $("#job-title").textContent = j.title;
  const must = j.must_have.map(g => g.join(" / ")).join(", ");
  $("#job-meta").innerHTML = `${esc(j.code)} · ${j.min_years}+ yrs · must have: ${esc(must)}`;
  $("#card").innerHTML = '<p class="empty">Select a candidate to see the scorecard.</p>';
  await loadCands();
}

async function loadCands() {
  state.cands = await api(`/api/jobs/${state.job}/applications`);
  const counts = state.cands.reduce((m, c) => (m[c.decision] = (m[c.decision] || 0) + 1, m), {});
  const f = ["ALL", "NEW", "SHORTLISTED", "NEED_INFO", "REJECTED"];
  $("#filters").innerHTML = f.map(x => `<button data-f="${x}" class="${state.filter === x ? "on" : ""}">${x === "ALL" ? "All" : x.replace("_", " ").toLowerCase()} ${x === "ALL" ? state.cands.length : counts[x] || 0}</button>`).join("");
  $$("#filters button").forEach(b => b.addEventListener("click", () => { state.filter = b.dataset.f; loadCands(); }));
  const list = state.cands.filter(c => state.filter === "ALL" || c.decision === state.filter);
  $("#cands").innerHTML = list.length ? list.map(c => `
    <button class="cand ${state.appId === c.id ? "on" : ""}" data-id="${c.id}">
      <span class="score-pill ${band(c.score)}">${c.score}</span>
      <span><span class="nm">${nameHtml(c.name, c.id)}</span>
        <span class="line">${esc(c.one_line || (c.missing.length ? "Missing: " + c.missing.join(", ") : `${c.experience_years} yrs relevant experience`))}</span>
        <span class="mini">${c.criteria.map(k => `<i title="${esc(k.name)} ${k.points}/${k.max}"><b style="width:${k.points / k.max * 100}%"></b></i>`).join("")}</span></span>
      <span class="badges"><span class="tag ${c.decision}">${c.decision.replace("_", " ")}</span>
        ${c.flags.includes("possible_prompt_injection") ? '<span class="tag warn" title="Resume tries to instruct the AI">injection</span>' : ""}</span>
    </button>`).join("") : '<p class="empty">No candidates here yet. Upload resumes above.</p>';
  $$(".cand").forEach(b => b.addEventListener("click", () => { openCard(+b.dataset.id); showTab("card"); }));
}

// ---------- scorecard ----------
function dial(score) {
  const r = 46, c = 2 * Math.PI * r, frac = score / 100;
  const color = score >= 70 ? "var(--good)" : score >= 45 ? "var(--mid)" : "var(--low)";
  return `<svg class="dial" viewBox="0 0 110 110" aria-label="Score ${score} of 100">
    <circle cx="55" cy="55" r="${r}" fill="none" stroke="var(--paper-2)" stroke-width="9"/>
    <circle cx="55" cy="55" r="${r}" fill="none" stroke="${color}" stroke-width="9" stroke-linecap="round"
      stroke-dasharray="${c * frac} ${c}" transform="rotate(-90 55 55)"/>
    <text x="55" y="60" text-anchor="middle" class="v">${score}</text><text x="55" y="78" text-anchor="middle" class="m">/ 100</text></svg>`;
}

async function openCard(id) {
  state.appId = id;
  $$(".cand").forEach(b => b.classList.toggle("on", +b.dataset.id === id));
  const a = await api(`/api/applications/${id}`);
  const s = a.summary || {};
  const flags = (a.flag_details || []).map(f => `<div class="flag"><b>${f.type === "possible_prompt_injection" ? "Possible prompt injection" : "Missing requirement"}</b> — ${esc(f.message)}
    ${(f.examples || []).slice(0, 2).map(x => `<q>${esc(x)}</q>`).join("")}</div>`).join("");
  const crits = a.breakdown.criteria.map(c => `
    <div class="crit"><div class="crit-top"><span>${esc(c.name)}</span><span class="pts">${c.points} / ${c.max_points}</span></div>
      <div class="bar"><b style="width:${c.points / c.max_points * 100}%"></b></div>
      <div class="detail">${esc(c.detail)}</div>
      ${c.evidence.length ? `<details><summary>Evidence (${c.evidence.length})</summary><ul class="ev">${c.evidence.map(e =>
        `<li class="${(e.credit || "").startsWith("listed") ? "half" : ""}"><b>${esc(e.skill)}</b>${e.credit ? ` · ${esc(e.credit)}` : ""}<br><span>“${esc(e.quote)}”</span></li>`).join("")}</ul></details>` : ""}
    </div>`).join("");
  const list = xs => (xs && xs.length ? `<ul>${xs.map(x => `<li>${esc(x)}</li>`).join("")}</ul>` : '<p class="empty">Summary not generated yet.</p>');
  $("#card").innerHTML = `
    <div class="sc-head">${dial(a.score)}<div>
      <h3>${nameHtml(a.name, a.id)}</h3>
      <div class="sub">${esc(a.job.code)} · ${esc(a.job.title)} · ${a.breakdown.experience_years} yrs relevant (${a.breakdown.total_experience_years ?? "?"} total) · via ${esc(a.source)}</div>
      ${s.one_line ? `<p class="one-line">${esc(s.one_line)}</p>` : ""}</div></div>
    ${flags}
    <div class="crits">${crits}</div>
    <div class="cols">
      <div class="box"><h4>Strengths</h4>${list(s.strengths)}</div>
      <div class="box"><h4>Gaps</h4>${list(s.gaps)}</div>
      <div class="box full"><h4>Ask in the interview</h4>${s.interview_questions && s.interview_questions.length ? `<ol>${s.interview_questions.map(q => `<li>${esc(q)}</li>`).join("")}</ol>` : '<p class="empty">Summary not generated yet.</p>'}</div>
    </div>
    ${a.emails && a.emails.length ? `<div class="box full mails"><h4>Emails to the candidate</h4>${a.emails.map(m =>
      `<div class="mail-row"><span>${esc(m.subject)}<br><span class="sub">${esc(m.to)} · ${esc(m.at)}${m.error ? " · " + esc(m.error) : ""}</span></span><span class="st ${m.status}">${m.status}</span></div>`).join("")}</div>` : ""}
    <div class="decide"><span class="meta">Score is computed by code; the AI only writes the summary. You decide.</span>
      <button class="btn ghost small" id="view-resume">View resume</button>
      ${["SHORTLISTED", "NEED_INFO", "REJECTED"].map(d => `<button class="btn small ${a.decision === d ? "on" : ""}" data-d="${d}">${{ SHORTLISTED: "Shortlist", NEED_INFO: "Need info", REJECTED: "Reject" }[d]}</button>`).join("")}
    </div>`;
  $("#view-resume").addEventListener("click", () => {
    $("#resume-title").innerHTML = nameHtml(a.name, a.id) + ` · ${esc(a.file_name)}`;
    $("#resume-text").textContent = $("body").classList.contains("blind") ? a.resume_text.replace(a.name, "[name hidden]") : a.resume_text;
    $("#resume-dialog").showModal();
  });
  $$(".decide [data-d]").forEach(b => b.addEventListener("click", () => decide(id, b.dataset.d)));
}

// ---------- decisions (shortlist / reject open an email preview first) ----------
async function decide(id, decision) {
  if (decision === "NEED_INFO") return saveDecision(id, { decision });
  const p = await api(`/api/applications/${id}/email-preview?decision=${decision}`);
  $("#mail-title").textContent = decision === "SHORTLISTED" ? "Shortlist and invite the candidate" : "Reject and notify the candidate";
  $("#mail-to").value = p.to || "(no email address on the resume)";
  $("#mail-subject").value = p.subject;
  $("#mail-text").value = p.body;
  const send = $("#mail-send");
  send.checked = p.valid_to && !p.already_sent;
  send.disabled = !p.valid_to;
  const notes = [];
  if (!p.valid_to) notes.push("No valid email address was found, so only the decision will be saved.");
  if (p.already_sent) notes.push("This email was already sent once for this candidate; it is unticked to avoid a duplicate.");
  if (p.valid_to && !p.smtp) notes.push("Email sending is not configured yet: the message will be stored in the outbox as LOGGED, not delivered.");
  if (!notes.length) notes.push("Review and edit the message. It is sent only when you confirm.");
  $("#mail-note").textContent = notes.join(" ");
  $("#mail-note").classList.toggle("warn", notes.length > 1 || !p.valid_to || !p.smtp);
  $("#mail-confirm").textContent = decision === "SHORTLISTED" ? "Shortlist" : "Reject";
  $("#mail-dialog").dataset.id = id;
  $("#mail-dialog").dataset.decision = decision;
  $("#mail-dialog").showModal();
}

$("#mail-form").addEventListener("submit", async e => {
  e.preventDefault();
  const d = $("#mail-dialog");
  const body = { decision: d.dataset.decision,
                 email: { send: $("#mail-send").checked, subject: $("#mail-subject").value, body: $("#mail-text").value } };
  d.close();
  await saveDecision(+d.dataset.id, body);
});
$("#mail-cancel").addEventListener("click", () => $("#mail-dialog").close());
$("#mail-close").addEventListener("click", () => $("#mail-dialog").close());

async function saveDecision(id, body) {
  try {
    const r = await api(`/api/applications/${id}/decision`, { body });
    let msg = `Marked as ${r.decision.replace("_", " ").toLowerCase()}.`;
    if (r.email) msg += { SENT: " Email sent.", LOGGED: " Email saved to the outbox (sending not configured).",
                          FAILED: ` Email failed: ${r.email.error}` }[r.email.status];
    toast(msg, r.email && r.email.status === "FAILED");
    await Promise.all([loadJobs(), loadCands()]);
    openCard(id);
  } catch (err) { toast(err.message, true); }
}
$("#close-resume").addEventListener("click", () => $("#resume-dialog").close());

// ---------- upload ----------
async function uploadFiles(files) {
  if (!files.length || !state.job) return;
  const form = new FormData(); [...files].forEach(f => form.append("files", f));
  toast(`Screening ${files.length} resume${files.length > 1 ? "s" : ""}… this takes a few seconds each.`);
  try {
    const res = await api(`/api/jobs/${state.job}/upload`, { form });
    res.forEach(r => r.error ? toast(`${r.file}: ${r.error}`, true) : toast(`${r.name}: scored ${r.score}`));
    await Promise.all([loadJobs(), loadCands()]);
    const first = res.find(r => r.id); if (first) openCard(first.id);
  } catch (err) { toast(err.message, true); }
}
$("#file").addEventListener("change", e => { uploadFiles(e.target.files); e.target.value = ""; });
const drop = $("#drop");
["dragenter", "dragover"].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.add("over"); }));
["dragleave", "drop"].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.remove("over"); }));
drop.addEventListener("drop", e => uploadFiles(e.dataTransfer.files));

// ---------- careers inbox ----------
const ROUTE_LABEL = { job_code: "job code in email", title: "job title in email", ai_match: "AI match",
                      manual: "routed by you", needs_routing: "needs routing" };
async function loadInbox() {
  const d = await api("/api/inbox");
  const waiting = d.items.filter(i => i.status === "NEEDS_ROUTING").length;
  $("#inbox-badge").hidden = !waiting; $("#inbox-badge").textContent = waiting;
  $("#inbox-status").textContent = d.connected ? "Gmail connected." : "Gmail is not connected (run scripts/gmail_auth.py).";
  $("#inbox-check").disabled = !d.connected;
  const jobOptions = state.jobs.map(j => `<option value="${j.code}">${esc(j.code)} · ${esc(j.title)}</option>`).join("");
  $("#inbox-list").innerHTML = d.items.length ? d.items.map(i => {
    const r = i.routing || {};
    const how = r.method ? `${ROUTE_LABEL[r.method] || r.method}${r.job_codes && r.job_codes.length ? " → " + r.job_codes.join(", ") : ""}` +
      (r.confidence !== undefined && r.method === "ai_match" ? ` (${Math.round(r.confidence * 100)}%)` : "") : "";
    return `<div class="mail-item"><div class="top"><span class="subj">${esc(i.subject)}</span><span class="st ${i.status}">${i.status.replace("_", " ")}</span></div>
      <span class="sub">${esc(i.from)} · ${esc(i.at)}${i.file ? " · " + esc(i.file) : ""}</span>
      <span>${esc(i.outcome)}${how ? ` <span class="sub">(${esc(how)}${r.reason ? ": " + esc(r.reason) : ""})</span>` : ""}</span>
      ${i.status === "NEEDS_ROUTING" ? `<div class="route"><select data-id="${i.id}">${r.suggested ? `<option value="${r.suggested}">Suggested: ${esc(r.suggested)}</option>` : ""}${jobOptions}</select>
        <button class="btn ink small" data-route="${i.id}">Screen for this role</button></div>` : ""}</div>`;
  }).join("") : '<p class="empty">No emails processed yet.</p>';
  $$("[data-route]").forEach(b => b.addEventListener("click", async () => {
    const code = $(`select[data-id="${b.dataset.route}"]`).value;
    b.disabled = true; b.textContent = "Screening…";
    try { const r = await api(`/api/inbox/${b.dataset.route}/route`, { body: { job_code: code } });
          toast(`Screened for ${code}.`); await Promise.all([loadInbox(), loadJobs()]);
          if (state.job === code) loadCands(); }
    catch (err) { toast(err.message, true); b.disabled = false; b.textContent = "Screen for this role"; }
  }));
}
$("#inbox-btn").addEventListener("click", async () => { await loadInbox(); $("#inbox-dialog").showModal(); });
$("#inbox-close").addEventListener("click", () => $("#inbox-dialog").close());
$("#inbox-check").addEventListener("click", async () => {
  const b = $("#inbox-check"); b.disabled = true; b.textContent = "Checking…";
  try {
    const s = await api("/api/inbox/check", { body: {} });
    toast(`Checked ${s.checked} new email(s): ${s.screened} screened, ${s.needs_routing} need routing, ${s.skipped} skipped` +
          (s.quota_reached ? ". AI quota reached: remaining emails will be retried later" : s.errors ? `, ${s.errors} errors (will retry)` : "") + ".", s.errors > 0);
    await Promise.all([loadInbox(), loadJobs()]); if (state.job) loadCands();
  } catch (err) { toast(err.message, true); }
  finally { b.disabled = false; b.textContent = "Check inbox now"; }
});

// ---------- mobile tabs ----------
function showTab(t) {
  $$("#tabs button").forEach(b => b.classList.toggle("on", b.dataset.tab === t));
  $$(".layout > .panel").forEach(p => p.classList.toggle("show", p.dataset.pane === t));
}
$$("#tabs button").forEach(b => b.addEventListener("click", () => showTab(b.dataset.tab)));
showTab("jobs");

boot().catch(e => toast(e.message, true));
