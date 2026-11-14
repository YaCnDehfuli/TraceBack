// Owner: P2. The memory card, Fence split view and admin drawer (plan 7.3, P2-4 / P2-5 / P2-7).
// Implements window.traceback.renderMemoryCard(memory, context): memory is a MemoryCard (contracts/models.py,
// camelCase JSON), context is optional:
//   { preconditions: [PreconditionResult] }   condition results for the current incident, during a run
// Show "match: strong/weak", never a raw score; IDs, versions and hashes go behind "details".
// When no run is on screen, also lists the caller's team's memories in #memory-slot (refreshed on identity change).
// Everything is built with textContent (never innerHTML): memory text can come from an LLM.
(function () {
  if (!window.traceback) return;

  const TEAMS = {
    // Same colours as web/styles.css (.team-payments / .team-platform --team). Payments is cyan, not
    // teal, so it doesn't read as the green "tests passed" on a projector (issue #15).
    "team-payments": { name: "Payments", color: "#0e7490" },
    "team-platform": { name: "Platform", color: "#6d28d9" },
  };
  const team = (id) => TEAMS[id] || { name: String(id || "").replace(/^team-/, ""), color: "#5b6670" };

  // Contract: Conditions (camelCase in JSON) and PreconditionResult.check (snake_case names).
  const CONDITIONS = {
    dupKeyField: { check: "dup_key_field", label: (v) => `Duplicate key is ${v}` },
    sameEventIdOnBothDeliveries: {
      check: "same_event_id_on_both_deliveries",
      label: (v) => (v ? "Same event ID on both deliveries" : "Different event IDs on the deliveries"),
    },
  };
  const STATUS_LABEL = { disputed: "Disputed", superseded: "Superseded", revoked: "Revoked" };

  // ---------------------------------------------------------------- tiny DOM helper
  function el(tag, cls, ...children) {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    for (const c of children) {
      if (c === null || c === undefined || c === false) continue;
      node.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
    }
    return node;
  }

  function actorLabel(actor) {
    // "memory_admin@team-payments" -> "Payments admin"
    const m = /^(\w+)@(.+)$/.exec(actor || "");
    if (!m) return actor || "an admin";
    return `${team(m[2]).name} ${m[1] === "memory_admin" ? "admin" : "engineer"}`;
  }

  function timeLeft(ms) {
    if (ms <= 0) return "Expired";
    const s = Math.floor(ms / 1000);
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    if (h > 0) return `Expires in ${h} h ${m} min`;
    if (m > 0) return `Expires in ${m} min ${s % 60} s`;
    return `Expires in ${s} s`;
  }

  // ---------------------------------------------------------------- the card
  function forgottenCard(memory) {
    // Content is gone, so the receipt lines are blacked out (issue #17); P3's CSS adds the VOID stamp.
    const f = memory.forgotten;
    const bars = [78, 52, 66, 40].map((w) => {
      const bar = el("span", "tb-redacted");
      bar.style.width = `${w}%`;
      return bar;
    });
    return el("div", "tb-card tb-forgotten",
      el("div", "tb-redactions", ...bars),
      el("p", "tb-line", `Forgotten by ${actorLabel(f.forgottenBy)} · ${f.reason} · content erased`),
      el("p", "tb-muted", new Date(f.at).toLocaleString()));
  }

  function conditionRows(memory, context) {
    const conds = (memory.applicability && memory.applicability.conditions) || {};
    const results = {};
    for (const r of (context && context.preconditions) || []) results[r.check] = r;

    const rows = [];
    let held = 0;
    for (const [key, spec] of Object.entries(CONDITIONS)) {
      const value = conds[key];
      if (value === null || value === undefined) continue;
      const r = results[spec.check];
      let icon = "•", cls = "tb-cond";
      let extra = null;
      if (r) {
        if (r.held === true) { icon = "✓"; cls += " tb-ok"; held++; }
        else if (r.held === false) { icon = "✗"; cls += " tb-bad"; extra = r.actual != null ? ` (here: ${r.actual})` : null; }
        else { icon = "?"; cls += " tb-unknown"; }
      }
      rows.push(el("li", cls, el("span", "tb-icon", icon), spec.label(value), extra));
    }
    if (!rows.length) return null;
    const heading = context && context.preconditions
      ? `Conditions ${held}/${rows.length} hold for this incident`
      : "Applies only when";
    return el("div", "tb-block", el("div", "tb-label", heading), el("ul", "tb-conds", ...rows));
  }

  function renderMemoryCard(memory, context) {
    if (!memory) return el("div", "tb-muted", "No memory.");
    if (memory.forgotten) return forgottenCard(memory);

    const owner = team(memory.ownerTeamId);
    const readers = (memory.readableBy || []).map((t) => team(t).name);
    const created = Date.parse(memory.createdAt);
    const expires = Date.parse(memory.expiresAt);

    const chips = el("div", "tb-chips");
    const ownerChip = el("span", "tb-chip tb-owner", owner.name);
    ownerChip.style.background = owner.color;
    chips.appendChild(ownerChip);
    if (STATUS_LABEL[memory.status]) chips.appendChild(el("span", "tb-chip tb-warn", STATUS_LABEL[memory.status]));
    if (memory.stale) chips.appendChild(staleChip());
    // GET /memories/{id} has no match; during a run app.js passes the recall's match in context.
    const match = memory.match || (context && context.match);
    if (match) chips.appendChild(el("span", "tb-chip tb-plain", `match: ${match}`));
    if (memory.seeded) chips.appendChild(el("span", "tb-chip tb-plain", "seeded"));

    const p = memory.proof || {};
    const proven = p.beforeFailed && p.afterPassed;
    const proofText = !proven ? "No proof"
      : memory.seeded ? "Seeded example, not from a real run"
      : `Proven: failed before, passed after · ${p.testsTotal} tests`;

    // Expiry bar: the share of its lifetime left. Updated every second by tick().
    const fill = el("div", "tb-bar-fill");
    fill.style.background = owner.color;
    const bar = el("div", "tb-bar", fill);
    const left = el("div", "tb-muted tb-left", "");
    const expiry = el("div", "tb-expiry", bar, left);
    expiry.dataset.created = created;
    expiry.dataset.expires = expires;

    const excludes = (memory.applicability && memory.applicability.excludes) || [];
    const details = el("details", "tb-details",
      el("summary", null, "details"),
      el("dl", null,
        el("dt", null, "Memory"), el("dd", null, `${memory.memoryId} · version ${memory.version}`),
        el("dt", null, "Proof run"), el("dd", null, p.verificationRunId || "none"),
        el("dt", null, "Deleted for good"), el("dd", null, new Date(memory.purgeAt).toLocaleString()),
        el("dt", null, "Created"), el("dd", null, new Date(memory.createdAt).toLocaleString())));

    const card = el("div", "tb-card",
      chips,
      el("div", "tb-title", memory.title || "Untitled memory"),
      el("p", "tb-line", `Visible to: ${readers.join(", ")}${readers.length === 1 ? " only" : ""}`),
      el("p", "tb-line " + (proven ? "tb-proof" : "tb-bad"), (proven ? "✓ " : "✗ ") + proofText),
      conditionRows(memory, context),
      excludes.length ? el("div", "tb-block", el("div", "tb-label", "Does not apply when"),
        el("ul", "tb-conds", ...excludes.map((x) => el("li", "tb-cond", el("span", "tb-icon", "–"), x)))) : null,
      expiry,
      details);
    card.style.borderTopColor = owner.color;
    card.dataset.memoryId = memory.memoryId;
    card._memory = memory;
    updateExpiry(expiry);
    attachAdmin(card); // async: only shows for an admin of the owner team
    return card;
  }

  // ---------------------------------------------------------------- admin drawer (P2-6)
  // Forget and Expire now, only under an admin key of the owner team. Forget is always a person
  // clicking a button with a typed reason (plan 6.4: never by voice, never by the agent).
  const whoCache = {};
  function whoami() {
    const key = window.traceback.currentKey ? window.traceback.currentKey() : "";
    if (!whoCache[key]) whoCache[key] = window.traceback.api("/whoami").catch(() => null);
    return whoCache[key];
  }

  async function attachAdmin(card) {
    const memory = card._memory;
    card.querySelector(":scope > .tb-admin")?.remove();
    const me = await whoami();
    if (!me || me.role !== "memory_admin" || me.teamId !== memory.ownerTeamId) return;
    card.querySelector(":scope > .tb-admin")?.remove(); // in case two checks raced

    const reason = el("input", "tb-reason");
    reason.type = "text";
    reason.placeholder = "Reason (required)";
    reason.setAttribute("aria-label", "Reason");
    const expire = el("button", "tb-btn", "Expire now");
    const forget = el("button", "tb-btn tb-danger", "Forget");
    // Correction (P2-7): add an exclusion -> a new version supersedes this one.
    const exclude = el("input", "tb-reason");
    exclude.type = "text";
    exclude.placeholder = "Does not apply when… (correction)";
    exclude.setAttribute("aria-label", "Exclusion to add");
    const correct = el("button", "tb-btn", `Correct → v${memory.version + 1}`);
    const historyBtn = el("button", "tb-btn tb-plain-btn", "History");
    const history = el("ol", "tb-history");
    const msg = el("p", "tb-muted", "");
    const canCorrect = memory.status === "active";
    for (const b of [expire, forget, correct, historyBtn]) b.type = "button";
    function sync() {
      const r = !!reason.value.trim();
      expire.disabled = forget.disabled = !r;
      correct.disabled = !r || !exclude.value.trim();
    }
    reason.addEventListener("input", sync);
    exclude.addEventListener("input", sync);
    sync();

    async function act(method, path, then, extra = {}) {
      expire.disabled = forget.disabled = correct.disabled = true;
      msg.textContent = "Working…";
      try {
        const body = JSON.stringify({ reason: reason.value.trim(), ...extra });
        then(await window.traceback.api(path, { method, body }));
      } catch (err) {
        msg.textContent = `Failed: ${err.message}`;
        sync();
      }
    }
    const id = encodeURIComponent(memory.memoryId);
    correct.addEventListener("click", () => act("POST", `/memories/${id}/correct`, (v2) => {
      card.replaceWith(renderMemoryCard(v2, {}));
    }, { excludes: [exclude.value.trim()] }));
    historyBtn.addEventListener("click", async () => {
      if (history.childElementCount) { history.replaceChildren(); return; }
      try {
        const events = await window.traceback.api(`/memories/${id}/audit`);
        history.replaceChildren(...events.map((e) => el("li", null,
          el("strong", null, e.event.replaceAll("_", " ")),
          ` · ${e.actor ? e.actor.id : ""} · ${new Date(e.at).toLocaleTimeString()}`,
          e.version ? ` · v${e.version}` : "",
          e.reason ? el("span", "tb-muted", ` · ${e.reason}`) : null)));
      } catch (err) {
        history.replaceChildren(el("li", "tb-muted", `History unavailable: ${err.message}`));
      }
    });
    expire.addEventListener("click", () => act("POST", `/memories/${id}/expire`, (updated) => {
      card.replaceWith(renderMemoryCard(updated, {}));
    }));
    forget.addEventListener("click", () => act("DELETE", `/memories/${id}`, (tomb) => {
      const gone = forgottenCard(tomb);
      card.replaceWith(gone);
      probeRecall(gone, memory.memoryId);
      // For the run view (P3): e.g. rerun or show the compare view after Forget.
      document.dispatchEvent(new CustomEvent("traceback:memory-forgotten", { detail: { memoryId: memory.memoryId, card: tomb } }));
    }));

    card.appendChild(el("div", "tb-admin",
      el("div", "tb-label", `Admin · ${team(memory.ownerTeamId).name}`),
      reason, el("div", "tb-admin-btns", expire, forget),
      canCorrect ? exclude : null, canCorrect ? el("div", "tb-admin-btns", correct) : null,
      el("div", "tb-admin-btns", historyBtn), history, msg));
  }

  // After Forget: show that recall really can't find it any more (the store's re-read guard makes
  // this true at once, even while the vector index still lags for a few seconds).
  async function probeRecall(node, memoryId) {
    const line = el("p", "tb-line", "Checking recall…");
    node.appendChild(line);
    try {
      const res = await window.traceback.api(`/memories/search?q=${encodeURIComponent(FENCE_QUERY)}`);
      const still = res.memories.some((m) => m.memoryId === memoryId);
      line.textContent = still ? "Recall still returns it (index lag): retrying…" : "Recall: 0 candidates · unsearchable";
      if (still) setTimeout(() => { line.remove(); probeRecall(node, memoryId); }, 1000);
    } catch (err) {
      line.textContent = `Recall check failed: ${err.message}`;
    }
  }

  // Key 5 switches engineer -> admin without changing the team, so watch the key itself.
  let lastKey = null;
  function refreshAdminDrawers() {
    const key = window.traceback.currentKey ? window.traceback.currentKey() : null;
    if (key === lastKey) return;
    lastKey = key;
    document.querySelectorAll(".tb-card[data-memory-id]").forEach((c) => { if (c._memory) attachAdmin(c); });
  }

  function updateExpiry(node) {
    const created = Number(node.dataset.created);
    const expires = Number(node.dataset.expires);
    const now = Date.now();
    const share = Math.max(0, Math.min(1, (expires - now) / Math.max(1, expires - created)));
    node.querySelector(".tb-bar-fill").style.width = `${(share * 100).toFixed(1)}%`;
    node.querySelector(".tb-left").textContent = timeLeft(expires - now);
    node.closest(".tb-card")?.classList.toggle("tb-expired", expires <= now);
  }

  function tick() {
    document.querySelectorAll(".tb-expiry").forEach(updateExpiry);
    refreshAdminDrawers();
  }

  // ---------------------------------------------------------------- staleness (R12)
  // Every 5 s, ask whether the code each visible memory was proven on has changed, and flip its
  // "Stale" chip live (edit one line of webhooks.py and the card flips). Unaudited endpoint.
  function staleChip() {
    return el("span", "tb-chip tb-warn tb-stale", "Stale: code changed since this was proven");
  }

  async function refreshStaleness() {
    const cards = [...document.querySelectorAll(".tb-card[data-memory-id]")].filter((c) => c.isConnected);
    for (const card of cards) {
      try {
        const r = await window.traceback.api(`/memories/${encodeURIComponent(card.dataset.memoryId)}/stale`);
        const chip = card.querySelector(".tb-stale");
        if (r.stale && !chip) card.querySelector(".tb-chips")?.appendChild(staleChip());
        if (!r.stale && chip) chip.remove();
        if (card._memory) card._memory.stale = r.stale;
      } catch (_) {
        // not readable under the current key, or the API is down: leave the card as it is
      }
    }
  }

  // ---------------------------------------------------------------- the panel
  // Idle state only: when no run is on screen, #memory-slot lists the caller's team's memories.
  // During a run, app.js (P3) owns the slot and calls renderMemoryCard for the run's memory;
  // we never overwrite that (our list is marked with .tb-list).
  async function refreshMemories() {
    const slot = document.getElementById("memory-slot");
    if (!slot) return;
    const ours = () => !slot.firstElementChild || slot.firstElementChild.classList.contains("tb-list");
    if (!ours()) return;
    let list;
    try {
      const memories = await window.traceback.api("/memories");
      list = el("div", "tb-list");
      if (!memories.length) list.appendChild(el("p", "tb-muted", "Your team has no memories yet."));
      for (const m of memories.slice(0, 3)) list.appendChild(renderMemoryCard(m, {}));
    } catch (err) {
      list = el("div", "tb-list", el("p", "tb-muted", `Memories unavailable: ${err.message}`));
    }
    if (ours()) slot.replaceChildren(list); // a run may have claimed the slot while we waited
  }

  // ---------------------------------------------------------------- the Fence view (P2-5)
  // The same search run with each team's demo key, side by side, plus what Platform's search WOULD
  // return without the team filter (struck through; other teams' memories arrive redacted from the API),
  // and the exact $vectorSearch pre-filter printed underneath.
  const FENCE_QUERY = "Duplicate webhook delivery raises E11000 on provider_event_id; " +
    "retry carries the same event identifier.";
  const FENCE_KEYS = { payments: "key-payments-eng", platform: "key-platform-eng", admin: "key-platform-admin" };

  function filterLine(filter) {
    // { tenantId: "demo-org", readableBy: { $in: ["team-platform"] }, ... } on one line
    return JSON.stringify(filter).replace(/"(\$?\w+)":/g, "$1: ").replace(/,/g, ", ").replace(/"now"/g, "now");
  }

  function fenceColumn(teamId, result) {
    const t = team(teamId);
    const head = el("div", "tb-fence-head", `${t.name} sees ${result.count}`);
    head.style.color = t.color;
    const body = result.count
      ? el("ul", "tb-conds", ...result.memories.map((m) =>
        el("li", "tb-cond", el("span", "tb-icon", "✓"), m.title, m.match ? el("span", "tb-muted", ` · ${m.match}`) : null)))
      : el("p", "tb-muted", "Nothing your team may see.");
    return el("div", "tb-fence-col", head, body);
  }

  async function renderFence(q) {
    q = q || FENCE_QUERY;
    const qs = `/memories/search?q=${encodeURIComponent(q)}`;
    const as = (key) => ({ headers: { "X-API-Key": key } });
    const [pay, plat, unscoped] = await Promise.all([
      window.traceback.api(qs, as(FENCE_KEYS.payments)),
      window.traceback.api(qs, as(FENCE_KEYS.platform)),
      window.traceback.api(`/memories/compare-unscoped?q=${encodeURIComponent(q)}`, as(FENCE_KEYS.admin)),
    ]);
    const blocked = unscoped.memories.filter((m) => !(m.readableBy || []).includes("team-platform"));
    const without = el("div", "tb-block",
      el("div", "tb-label", "Without the team filter, Platform's search would return"),
      blocked.length
        ? el("ul", "tb-conds", ...blocked.map((m) => el("li", "tb-cond tb-struck",
          el("span", "tb-icon", "✗"), el("s", null, m.title), el("span", "tb-muted", " · blocked inside the search"))))
        : el("p", "tb-muted", "Nothing (no other team's memory matches)."));
    return el("div", "tb-card tb-fence",
      el("div", "tb-label", "Same search, two teams"),
      el("div", "tb-fence-cols", fenceColumn("team-payments", pay), fenceColumn("team-platform", plat)),
      without,
      el("div", "tb-block", el("div", "tb-label", "$vectorSearch filter for Platform"),
        el("code", "tb-filter", filterLine(plat.filter))));
  }

  async function showFence(q) {
    const slot = document.getElementById("memory-slot");
    if (!slot) return;
    try {
      slot.replaceChildren(await renderFence(q));
    } catch (err) {
      slot.replaceChildren(el("p", "tb-muted", `Fence view unavailable: ${err.message}`));
    }
  }

  // ---------------------------------------------------------------- refusal receipt (R11)
  // "Memory refused: no proof." The fix failed verification, so Atlas's validator refused the write.
  // Nothing was stored: the receipt shows only facts from the audit log (run, case, failing tests).
  function renderRefusal(ev) {
    const d = ev.details || {};
    const failed = d.failedTests || [];
    const card = el("div", "tb-card tb-refused",
      el("div", "tb-label", "Memory write · refused by the database"),
      el("div", "tb-title", "Memory refused: no proof."),
      el("p", "tb-line tb-bad", `✗ Verification ${d.status || "failed"}: ` +
        `${d.testsPassed ?? "?"}/${d.testsTotal ?? "?"} tests pass after the fix`),
      failed.length ? el("div", "tb-block", el("div", "tb-label", "Failing"),
        el("ul", "tb-conds", ...failed.map((t) => el("li", "tb-cond tb-bad", el("span", "tb-icon", "✗"), t)))) : null,
      el("p", "tb-line", "Atlas's schema validator requires failed-before and passed-after. Nothing was stored."),
      el("p", "tb-muted", `${d.caseId ? `Case ${d.caseId} · ` : ""}run ${ev.runId || "?"} · ${new Date(ev.at).toLocaleTimeString()}`));
    card.appendChild(el("div", "stamp refused", "Refused")); // P3's stamp style (styles.css)
    return card;
  }

  async function showRefusal(runId) {
    const slot = document.getElementById("memory-slot");
    if (!slot) return null;
    try {
      const list = await window.traceback.api("/memories/refusals?limit=10");
      // The audit records the runner's verification id, not the agent's run id, so a live run's id
      // usually won't match: fall back to the most recent refusal (the one that just happened).
      const ev = (runId && list.find((e) => e.runId === runId)) || list[0];
      slot.replaceChildren(ev ? renderRefusal(ev) : el("p", "tb-muted", "No refused memory writes for your team."));
      return ev || null;
    } catch (err) {
      slot.replaceChildren(el("p", "tb-muted", `Refusals unavailable: ${err.message}`));
      return null;
    }
  }

  // ---------------------------------------------------------------- styles (kept here so P3's page stays untouched)
  function injectStyles() {
    const css = `
      .tb-card { background:#fff; border:1px solid #dde1e6; border-top:5px solid #5b6670; border-radius:10px;
                 padding:14px 16px; margin:0 0 14px; font-size:15px; line-height:1.4; }
      .tb-card.tb-expired { opacity:.55; filter:grayscale(1); }
      .tb-forgotten { background:transparent; border:2px dashed #9aa4ad; border-top-width:2px; color:#5b6670; }
      .tb-redactions { margin:4px 0 10px; } .tb-redacted { display:block; height:.85em; margin:7px 0; background:#1d232a; border-radius:2px; }
      .tb-title { font-size:18px; font-weight:650; margin:6px 0 8px; }
      .tb-line { margin:4px 0; }
      .tb-proof { color:#1a7f37; font-weight:600; }
      .tb-bad { color:#b42318; }
      .tb-muted { color:#5b6670; font-size:13px; margin:4px 0; }
      .tb-chips { display:flex; flex-wrap:wrap; gap:6px; }
      .tb-chip { font-size:12px; font-weight:600; padding:2px 10px; border-radius:999px; }
      .tb-owner { color:#fff; }
      .tb-warn { background:#fff4d6; color:#8a5a00; border:1px solid #f0c36d; }
      .tb-plain { background:#eef1f4; color:#3b444d; }
      .tb-block { margin:10px 0 4px; }
      .tb-label { font-size:12px; text-transform:uppercase; letter-spacing:.04em; color:#5b6670; }
      .tb-conds { list-style:none; padding:0; margin:4px 0; }
      .tb-card ul li { list-style:none; } .tb-card p { margin-bottom:4px; } .tb-card details { margin-bottom:0; }
      .tb-cond { margin:3px 0; }
      .tb-icon { display:inline-block; width:1.4em; font-weight:700; }
      .tb-ok .tb-icon { color:#1a7f37; } .tb-bad .tb-icon { color:#b42318; } .tb-unknown .tb-icon { color:#8a5a00; }
      .tb-expiry { margin-top:10px; }
      .tb-bar { height:8px; background:#e6e9ed; border-radius:999px; overflow:hidden; }
      .tb-bar-fill { height:100%; width:100%; transition:width .9s linear; }
      .tb-details { margin-top:8px; font-size:13px; color:#5b6670; }
      .tb-details dl { display:grid; grid-template-columns:max-content 1fr; gap:2px 12px; margin:6px 0 0; }
      .tb-details dt { font-weight:600; } .tb-details dd { margin:0; word-break:break-all; }
      .tb-fence-cols { display:grid; grid-template-columns:1fr 1fr; gap:16px; margin:8px 0; }
      .tb-fence-head { font-size:20px; font-weight:700; margin-bottom:4px; }
      .tb-struck s { color:#5b6670; } .tb-struck .tb-icon { color:#b42318; }
      .tb-admin { margin-top:12px; padding-top:10px; border-top:1px dashed #c5ccd3; }
      .tb-admin .tb-reason { width:100%; margin:6px 0; font-size:14px; padding:6px 8px; height:auto; }
      .tb-admin-btns { display:flex; gap:8px; }
      .tb-admin .tb-btn { flex:1; font-size:14px; padding:6px 10px; margin:0; }
      .tb-admin .tb-danger { background:#b42318; border-color:#b42318; color:#fff; }
      .tb-admin .tb-plain-btn { background:transparent; color:inherit; border:1px solid #c5ccd3; }
      .tb-history { font-size:13px; margin:8px 0 0; padding-left:1.2em; } .tb-history li { margin:2px 0; }
      .tb-refused { position:relative; } .tb-refused .tb-title { color:#b42318; }
      .tb-filter { display:block; font-size:12px; white-space:normal; word-break:break-word; padding:6px 8px; }
    `;
    document.head.appendChild(el("style", null, css));
  }

  // ---------------------------------------------------------------- wire up
  window.traceback.renderMemoryCard = renderMemoryCard;
  window.traceback.refreshMemories = refreshMemories;
  window.traceback.renderFence = renderFence; // async (q?) -> node
  window.traceback.showFence = showFence; // async (q?): puts the Fence view in #memory-slot (beat 4)
  // Forget fires document event "traceback:memory-forgotten" with detail {memoryId, card}.
  window.traceback.renderRefusal = renderRefusal; // (auditEvent) -> node
  window.traceback.showRefusal = showRefusal; // async (runId?): latest (or that run's) refusal into #memory-slot

  injectStyles();
  setInterval(tick, 1000);
  setInterval(refreshStaleness, 5000);
  document.addEventListener("DOMContentLoaded", () => {
    // app.js sets <body class="team-…"> on every identity change (the pill AND keys 4/5),
    // so watching the body class catches all of them.
    let team = document.body.className;
    new MutationObserver(() => {
      if (document.body.className !== team) {
        team = document.body.className;
        refreshMemories();
      }
    }).observe(document.body, { attributes: true, attributeFilter: ["class"] });
    refreshMemories();
  });
})();
