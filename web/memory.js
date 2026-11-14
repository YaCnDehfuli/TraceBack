// Owner: P2. The memory card, Fence split view and admin drawer (plan 7.3, P2-4 / P2-5 / P2-7).
// Implements window.traceback.renderMemoryCard(memory, context): memory is a MemoryCard (contracts/models.py,
// camelCase JSON), context is optional:
//   { preconditions: [PreconditionResult] }   condition results for the current incident, during a run
// Show "match: strong/weak", never a raw score; IDs, versions and hashes go behind "details".
// Also fills #memory-panel with the caller's team's memories and refreshes it when the identity changes.
// Everything is built with textContent (never innerHTML): memory text can come from an LLM.
(function () {
  if (!window.traceback) return;

  const TEAMS = {
    "team-payments": { name: "Payments", color: "#0b7a75" },
    "team-platform": { name: "Platform", color: "#6b4fbb" },
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
    const f = memory.forgotten;
    return el("article", "tb-card tb-forgotten",
      el("div", "tb-title", memory.title || "Memory"),
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
    if (memory.stale) chips.appendChild(el("span", "tb-chip tb-warn", "Stale: code changed since this was proven"));
    if (memory.match) chips.appendChild(el("span", "tb-chip tb-plain", `match: ${memory.match}`));
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

    const card = el("article", "tb-card",
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
    updateExpiry(expiry);
    return card;
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
  }

  // ---------------------------------------------------------------- the panel
  async function refreshMemories() {
    const panel = document.getElementById("memory-panel");
    if (!panel) return;
    let body = panel.querySelector(".tb-panel-body");
    if (!body) {
      body = el("div", "tb-panel-body");
      panel.appendChild(body);
    }
    try {
      const memories = await window.traceback.api("/memories");
      body.replaceChildren();
      if (!memories.length) {
        body.appendChild(el("p", "tb-muted", "Your team has no memories yet."));
        return;
      }
      for (const m of memories.slice(0, 3)) body.appendChild(renderMemoryCard(m, {}));
    } catch (err) {
      body.replaceChildren(el("p", "tb-muted", `Memories unavailable: ${err.message}`));
    }
  }

  // ---------------------------------------------------------------- styles (kept here so P3's page stays untouched)
  function injectStyles() {
    const css = `
      .tb-card { background:#fff; border:1px solid #dde1e6; border-top:5px solid #5b6670; border-radius:10px;
                 padding:14px 16px; margin:0 0 14px; font-size:15px; line-height:1.4; }
      .tb-card.tb-expired { opacity:.55; filter:grayscale(1); }
      .tb-forgotten { background:transparent; border:2px dashed #9aa4ad; border-top-width:2px; color:#5b6670; }
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
      .tb-cond { margin:3px 0; }
      .tb-icon { display:inline-block; width:1.4em; font-weight:700; }
      .tb-ok .tb-icon { color:#1a7f37; } .tb-bad .tb-icon { color:#b42318; } .tb-unknown .tb-icon { color:#8a5a00; }
      .tb-expiry { margin-top:10px; }
      .tb-bar { height:8px; background:#e6e9ed; border-radius:999px; overflow:hidden; }
      .tb-bar-fill { height:100%; width:100%; transition:width .9s linear; }
      .tb-details { margin-top:8px; font-size:13px; color:#5b6670; }
      .tb-details dl { display:grid; grid-template-columns:max-content 1fr; gap:2px 12px; margin:6px 0 0; }
      .tb-details dt { font-weight:600; } .tb-details dd { margin:0; word-break:break-all; }
    `;
    document.head.appendChild(el("style", null, css));
  }

  // ---------------------------------------------------------------- wire up
  window.traceback.renderMemoryCard = renderMemoryCard;
  window.traceback.refreshMemories = refreshMemories;

  injectStyles();
  setInterval(tick, 1000);
  document.addEventListener("DOMContentLoaded", () => {
    // Registered after app.js's own listener, so currentKey() is already the new identity.
    const identity = document.getElementById("identity");
    if (identity) identity.addEventListener("change", refreshMemories);
    refreshMemories();
  });
})();
