// Owner: P3. The run view, identity pill and keyboard shortcuts (plan 7.3).
// Contract hooks (plan section 6): memory.js (P2) and voice.js (P1) talk to this file ONLY through
//   window.traceback.renderMemoryCard(memory, context)   <- implemented by memory.js
//   window.traceback.currentKey()                         -> the API key the page acts as
//   window.traceback.showRun(runId)                       -> make the screen follow a run
//
// Key 0 replays contracts/sample_run_events.json (always labelled "Replay", never passed off as live).
// Live runs need POST /incidents to accept a caseId and load cases/<id>/manifest.json on the server.
(function () {
  // Fake, local-only demo keys (see DEMO_PRINCIPALS in .env.example). Not real authentication.
  const DEMO_KEYS = [
    { key: "key-payments-eng", label: "Payments engineer", team: "payments" },
    { key: "key-payments-admin", label: "Payments admin", team: "payments" },
    { key: "key-platform-eng", label: "Platform engineer", team: "platform" },
    { key: "key-platform-admin", label: "Platform admin", team: "platform" },
  ];
  const TEAM_NAMES = { "team-payments": "Payments", "team-platform": "Platform" };
  // provenBy: the trusted test that fails without the memory's line (trusted_tests/test_webhooks.py).
  const REPLAY_TEST = "test_replay_recorded_for_reconciliation";
  const CASES = {
    A: { title: "Duplicate webhook crashes payments", repo: "payments-webhooks", key: "key-payments-eng", provenBy: REPLAY_TEST },
    B: { title: "Webhook retries are crashing Payments", repo: "payments-webhooks", key: "key-payments-eng", provenBy: REPLAY_TEST },
    C: { title: "Two different payments from one customer collide", repo: "payments-webhooks", key: "key-payments-eng" },
    D: { title: "Duplicate webhook crashes Platform billing", repo: "platform-webhooks", key: "key-platform-eng", provenBy: REPLAY_TEST },
    P: { title: "Duplicate webhook, with a suspicious log line", repo: "payments-webhooks", key: "key-payments-eng", provenBy: REPLAY_TEST },
  };
  const IDLE_TEXT = "3:04 a.m. The duplicate-webhook alert is back.";
  // The five steps every run takes, shown greyed until the run reaches them.
  const PHASES = [
    { id: "observe", icon: "scan-search", name: "Observe", sub: "Read the error and the logs" },
    { id: "recall", icon: "brain", name: "Recall", sub: "Find a memory your team may see" },
    { id: "check", icon: "shield-check", name: "Check", sub: "Does that memory still hold here?" },
    { id: "fix", icon: "file-pen-line", name: "Fix", sub: "Patch the code, marking lines from memory" },
    { id: "test", icon: "flask-conical", name: "Test", sub: "Prove it: failed before, passes after" },
  ];
  const POLL_MS = 1000;
  const SAMPLE_STEP_MS = 700;
  const RECENT_MS = 10 * 60 * 1000; // keys 2-4 re-follow a run of the same case started this recently
  const STORE = "traceback.runs.v1";
  const smooth = matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth";

  let currentKey = DEMO_KEYS[0].key;
  let followToken = 0; // cancels an older run being followed when a new one starts
  const lastRunByCase = {}; // caseId -> { runId, startedAt }
  const runs = {}; // runId -> { caseId, replay, events: [] }, kept for the compare view
  let state = freshState();
  let clock = null;

  function freshState() {
    return { memoryRef: null, preconditions: [], checks: [], checkStep: null, decision: null, attempt: null, proof: null,
      stamp: null, stampShown: false, printed: null, caseId: null, query: null, now: null, startedAt: Date.now() };
  }

  // Live runs survive a reload (e.g. before Forget), so Compare still has both runs. Replays are not kept.
  function loadRuns() {
    try {
      const saved = JSON.parse(localStorage.getItem(STORE)) || {};
      Object.assign(runs, saved.runs);
      Object.assign(lastRunByCase, saved.lastRunByCase);
    } catch (_) { /* nothing saved, or storage blocked */ }
  }
  function saveRuns() {
    const live = Object.fromEntries(Object.entries(runs).filter(([, r]) => !r.replay));
    try { localStorage.setItem(STORE, JSON.stringify({ runs: live, lastRunByCase })); } catch (_) { /* storage full or blocked */ }
  }

  // ------------------------------------------------------------------ API

  async function api(path, options = {}) {
    const headers = Object.assign({ "X-API-Key": currentKey }, options.headers || {});
    if (options.body && !headers["Content-Type"]) headers["Content-Type"] = "application/json";
    const res = await fetch(path, Object.assign({}, options, { headers }));
    if (!res.ok) {
      const err = new Error(`${res.status} ${await res.text()}`);
      err.status = res.status;
      throw err;
    }
    return res.status === 204 ? null : res.json();
  }

  // ------------------------------------------------------------------ small DOM helpers

  const $ = (id) => document.getElementById(id);
  function el(tag, attrs = {}, ...children) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (k === "class") node.className = v;
      else node.setAttribute(k, v);
    }
    for (const child of children) {
      if (child == null) continue;
      node.appendChild(typeof child === "string" ? document.createTextNode(child) : child);
    }
    return node;
  }
  const teamName = (teamId) => TEAM_NAMES[teamId] || teamId || "another team";
  const setStatus = (text) => { $("status").textContent = text; };

  // ------------------------------------------------------------------ fit to the window
  // Everything is in rem, so the root font size scales the whole page. Pick the largest size (16-48px) at which
  // nothing scrolls. While a run is on screen the page only shrinks, so a landing step never makes it jump;
  // it grows back when the run ends, the view resets or the window resizes. The CSS clamp is the no-JS start.
  const ROOT = document.documentElement;
  const FIT_MIN = 16, FIT_MAX = 48;
  let fitTimer = null, fitGrow = false;
  const running = () => ["live", "replay"].includes($("run-panel").dataset.live);
  const setRoot = (px) => ROOT.style.setProperty("--pico-font-size", `${px}px`);

  function overflowing() {
    const boxes = $("compare").hidden ? [$("run-panel"), $("memory-panel")] : [$("compare")];
    // A top bar that wrapped (the pill on a second row) counts too: it fits vertically but looks broken.
    const wrapped = $("identity").getBoundingClientRect().top >= document.querySelector(".brand").getBoundingClientRect().bottom;
    return wrapped || ROOT.scrollHeight > innerHeight || ROOT.scrollWidth > innerWidth
      || boxes.some((b) => b.scrollHeight > b.clientHeight + 1);
  }

  function fit(grow) {
    if (innerWidth < 901) return ROOT.style.removeProperty("--pico-font-size"); // one column: the page scrolls
    const from = parseFloat(getComputedStyle(ROOT).fontSize);
    ROOT.style.transition = "none"; // measure at the target sizes, not mid-transition
    let lo = FIT_MIN, hi = grow ? FIT_MAX : from;
    setRoot(hi);
    if (!overflowing()) lo = hi;
    for (let i = 0; i < 8 && hi - lo > 0.25; i++) {
      const mid = (lo + hi) / 2;
      setRoot(mid);
      if (overflowing()) hi = mid;
      else lo = mid;
    }
    setRoot(from);
    void ROOT.offsetWidth; // commit `from`, so the change below animates
    ROOT.style.transition = "";
    setRoot(Math.floor(lo * 4) / 4);
  }

  // Debounced past the step and stamp animations, so their transforms aren't measured.
  function fitSoon(grow = !running()) {
    fitGrow = fitGrow || grow;
    clearTimeout(fitTimer);
    fitTimer = setTimeout(() => {
      fit(fitGrow);
      fitGrow = false;
    }, 350);
  }

  // Lucide icons: <i data-lucide="name"> placeholders, swapped for SVGs under `root` only.
  const icon = (name) => el("i", { "data-lucide": name });
  const drawIcons = (root) => { if (window.lucide) window.lucide.createIcons({ root }); };

  // Plain-language names for the memory's applicability checks (PreconditionResult.check).
  const CONDITION_LABELS = {
    dup_key_field: (r) => `Same duplicated field: ${r.expected}`,
    same_event_id_on_both_deliveries: () => "Same event delivered twice",
  };
  const conditionLabel = (r) => (CONDITION_LABELS[r.check] ? CONDITION_LABELS[r.check](r) : r.check.replaceAll("_", " "));

  // ------------------------------------------------------------------ code: Prism lines, windowed around the memory's lines

  const escapeHtml = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  function highlightLines(code) {
    const html = window.Prism && Prism.languages.python ? Prism.highlight(code, Prism.languages.python, "python") : escapeHtml(code);
    return html.split("\n");
  }
  function codeLine(n, html, cls = "", tag = null) {
    const line = el("span", { class: `line ${cls}`, "data-n": n });
    line.innerHTML = cls === "empty" ? "" : html || " ";
    if (tag) line.appendChild(el("span", { class: "tag" }, icon("brain"), tag));
    return line;
  }
  const memoryTag = (caseId) => (CASES[caseId] && CASES[caseId].provenBy ? `from memory · proven by ${CASES[caseId].provenBy}` : "from memory");

  // The patch as a <pre>. With memory lines: each one with ±2 lines of dimmed context (none when there are
  // more than two), overlapping windows merged, "⋯" for the lines skipped; the tag once, on the first memory line.
  // `missing` renders the memory lines as empty rows (compare, after Forget).
  function patchBlock(code, memoryLines, { caseId = state.caseId, missing = false } = {}) {
    const lines = highlightLines(code.replace(/\n$/, ""));
    const marked = new Set(memoryLines || []);
    const pad = marked.size > 2 ? 0 : 2;
    const nums = lines.map((_, i) => i + 1).filter((n) => !marked.size || [...marked].some((m) => Math.abs(m - n) <= pad));
    // Dedent what's shown so deep indentation doesn't push lines into wrapping (leading spaces are plain text in Prism's HTML).
    const depth = (h) => h.length - h.trimStart().length;
    const indent = Math.min(...nums.map((n) => lines[n - 1]).filter((h) => h.trim()).map(depth));
    const text = (n) => lines[n - 1].slice(Math.min(indent, depth(lines[n - 1])));
    const rows = [];
    let tag = memoryTag(caseId);
    nums.forEach((n, i) => {
      if (i && n > nums[i - 1] + 1) rows.push(el("span", { class: "line gap" }, "⋯"));
      if (!marked.has(n)) rows.push(codeLine(n, text(n), marked.size ? "near" : ""));
      else if (missing) rows.push(codeLine(n, "", "empty"));
      else {
        rows.push(codeLine(n, text(n), "from-memory", tag));
        tag = null;
      }
    });
    return el("pre", { class: marked.size ? "patch" : "patch full" }, ...rows);
  }

  // ------------------------------------------------------------------ answer, outcome, now line, live chip

  const ANSWER_ICONS = { ok: "circle-check", warn: "triangle-alert", bad: "circle-x" };
  function setAnswer(text, tone) {
    const answer = $("answer");
    answer.replaceChildren(icon(ANSWER_ICONS[tone] || "scan-search"), el("span", {}, text));
    answer.className = tone || "";
    drawIcons(answer);
  }

  function setOutcome(text, tone, iconName = "badge-check") {
    const outcome = $("outcome");
    outcome.replaceChildren(...(text ? [icon(iconName), text] : []));
    outcome.className = text ? tone : "";
    drawIcons(outcome);
  }

  // One line for whatever the agent is doing right now (tool calls and results), with the run's elapsed time.
  function setNow(text) {
    state.now = text;
    renderNow();
  }
  function renderNow() {
    const now = $("now");
    now.hidden = !state.now;
    if (!state.now) return;
    const secs = Math.floor((Date.now() - state.startedAt) / 1000);
    now.replaceChildren(el("span", { class: "dot" }), el("span", { class: "text" }, state.now),
      el("span", { class: "clock" }, `${Math.floor(secs / 60)}:${String(secs % 60).padStart(2, "0")}`));
  }
  const TOOL_VERBS = {
    read_file: (a) => `Reading ${a.path || "a file"}…`,
    search_code: (a) => `Searching the code${a.query ? ` for ${a.query}` : ""}…`,
    run_tests: () => "Running the tests…",
  };

  // mode: "live" | "replay" (being followed) | "done" | null (nothing on screen)
  function setLive(mode, replay = false) {
    const chip = $("live");
    chip.hidden = !mode;
    chip.dataset.mode = replay ? "replay" : mode || "";
    chip.textContent = replay ? "Replay" : mode === "done" ? "Finished" : "Live";
    if (mode) $("run-panel").dataset.live = mode;
    else delete $("run-panel").dataset.live;
    clearInterval(clock);
    if (mode === "live" || mode === "replay") clock = setInterval(renderNow, 1000);
    else setNow(null);
    if (mode === "done") {
      clearGhosts();
      fitSoon(true); // the run is over: the page may grow back
    }
  }

  // ------------------------------------------------------------------ timeline

  const step = (iconName, text, sub, tone = "") =>
    el("li", { class: tone }, el("span", { class: "icon" }, icon(iconName)), el("div", {}, text, sub ? el("span", { class: "sub" }, sub) : null));

  // A step of `phase` lands: the greyed steps up to that phase go, the ones still ahead stay.
  function addStep(iconName, text, { tone = "", sub = null, extra = null, phase = null } = {}) {
    const li = step(iconName, text, sub, tone);
    if (extra) li.lastChild.appendChild(extra);
    $("timeline").appendChild(li);
    if (phase) clearGhosts(PHASES.findIndex((p) => p.id === phase));
    drawIcons(li);
    li.scrollIntoView({ block: "nearest", behavior: smooth });
    return li;
  }

  function showGhosts() {
    const ghosts = $("ghosts");
    ghosts.replaceChildren(...PHASES.map((p) => step(p.icon, p.name, p.sub, "ghost")));
    drawIcons(ghosts);
  }
  function clearGhosts(upTo = PHASES.length - 1) {
    const ghosts = [...$("ghosts").children]; // the last ghosts.length phases
    ghosts.slice(0, Math.max(0, upTo + 1 - (PHASES.length - ghosts.length))).forEach((g) => g.remove());
  }

  function resetView(caseId) {
    $("timeline").innerHTML = "";
    $("handoff")?.remove();
    $("live-link")?.remove();
    showGhosts();
    $("memory-slot").innerHTML = "";
    delete $("memory-slot").dataset.stamp;
    delete $("memory-slot").dataset.empty;
    setOutcome("");
    setLive(null);
    setAnswer("Investigating…", "idle");
    fitSoon(true);
    state = freshState();
    state.caseId = caseId || null;
    if (caseId && CASES[caseId]) $("incident-title").textContent = CASES[caseId].title;
  }

  // ------------------------------------------------------------------ identity pill

  function applyIdentity(key) {
    currentKey = key;
    const entry = DEMO_KEYS.find((k) => k.key === key) || DEMO_KEYS[0];
    document.body.className = `team-${entry.team}`;
    $("identity").value = key;
    api("/whoami")
      .then((p) => setStatus(`Acting as ${teamName(p.teamId)} · ${p.role.replace("memory_", "")}`)) // "admin", as the pill says
      .catch(() => setStatus("Couldn't confirm who you're acting as."));
  }

  function setupIdentity() {
    const select = $("identity");
    for (const k of DEMO_KEYS) select.appendChild(el("option", { value: k.key }, `Acting as: ${k.label}`));
    select.addEventListener("change", () => applyIdentity(select.value));
    applyIdentity(currentKey);
  }

  // ------------------------------------------------------------------ memory receipt and stamps

  async function showMemory(ref) {
    if (!ref) return;
    state.memoryRef = ref;
    let card = null;
    try {
      card = await api(`/memories/${encodeURIComponent(ref.memoryId)}`);
    } catch (_) {
      card = null; // P2's endpoint not ready, or not readable: fall back to the reference
    }
    if (state.memoryRef !== ref) return; // a newer memory took the receipt while we waited
    const context = { currentKey, preconditions: state.preconditions, decision: state.decision };
    let node = null;
    if (card) {
      // memory.js renders a full MemoryCard only; a bare reference would show blank fields.
      try {
        node = window.traceback.renderMemoryCard(card, { ...context, match: ref.match });
      } catch (_) {
        node = null;
      }
    }
    // No card (e.g. sample replay without Atlas), or memory.js's stub: use our own receipt.
    if (!node || node.textContent.includes("TODO") || !node.firstElementChild) {
      node = fallbackCard(card || { memoryId: ref.memoryId, version: ref.version, ownerTeamId: ref.ownerTeamId,
        title: "Replayed webhook: record the replay, credit once" });
    }
    if (state.printed !== ref.memoryId) node.classList.add("print"); // prints in once per run
    state.printed = ref.memoryId;
    const slot = $("memory-slot");
    slot.replaceChildren(node); // replaces memory.js's idle team list (.tb-list) while a run is on screen
    drawIcons(slot);
    placeStamp();
  }

  // The receipt follows the memory the fix actually used (patch_proposed.fromMemory, run_finished.memoryUsed).
  const useMemory = (ref) => {
    if (ref && ref.memoryId !== (state.memoryRef && state.memoryRef.memoryId)) showMemory(ref);
  };

  function relativeExpiry(iso) {
    const ms = Date.parse(iso) - Date.now();
    if (!(ms > 0)) return "expired";
    const h = Math.floor(ms / 3600000);
    return h ? `in ${h} h` : `in ${Math.max(1, Math.round(ms / 60000))} min`;
  }

  // Our receipt, used when memory.js has no card to render. Mono line items, like a printed receipt.
  function fallbackCard(memory) {
    const owner = teamName(memory.ownerTeamId);
    const readers = (memory.readableBy && memory.readableBy.length ? memory.readableBy : [memory.ownerTeamId]).map(teamName);
    const proof = memory.proof && memory.proof.testsTotal
      ? { beforeFailed: memory.proof.beforeFailed, afterPassed: memory.proof.afterPassed, tests: `${memory.proof.testsTotal}/${memory.proof.testsTotal}` }
      : state.proof;
    const mark = (ok) => el("span", { class: ok ? "v ok" : "v bad" }, ok ? "✓" : "✗");
    const row = (k, v) => el("li", {}, el("span", { class: "k" }, k), el("span", { class: "dots" }), typeof v === "string" ? el("span", { class: "v" }, v) : v);
    const rows = [
      row("Owner", owner),
      row("Visible to", `${readers.join(", ")}${readers.length === 1 ? " only" : ""}`),
      proof ? row("Failed before", mark(proof.beforeFailed)) : null,
      proof ? row("Passed after", mark(proof.afterPassed)) : null,
      proof ? row("Trusted tests", proof.tests) : null,
      proof ? el("li", { class: "note" }, "Run by the safe runner. The agent can't edit these tests.") : null,
      state.preconditions.length ? el("li", { class: "note" }, "Taken from the error when the memory was saved · checked in code, not by the model") : null,
      ...state.preconditions.map((r) => row(conditionLabel(r), mark(r.held))),
      memory.expiresAt ? row("Expires", relativeExpiry(memory.expiresAt)) : null,
    ];
    const teamClass = TEAM_NAMES[memory.ownerTeamId] ? memory.ownerTeamId : "";
    return el("div", { class: `memory-fallback ${teamClass}` },
      el("p", { class: "receipt-head" }, "Memory receipt"),
      el("h3", {}, memory.title || "Memory"),
      el("ul", { class: "receipt-items" }, ...rows));
  }

  const STAMPS = { proven: "Proven", refused: "Refused", "not-applied": "Not applied" }; // "Void" is CSS-only, on memory.js's forgotten card
  function stamp(kind) {
    state.stamp = kind;
    state.stampShown = false;
    placeStamp();
  }
  function placeStamp() {
    const slot = $("memory-slot");
    const old = slot.querySelector(":scope > .stamp");
    if (old) old.remove();
    if (!state.stamp || !slot.firstElementChild) return;
    slot.dataset.stamp = state.stamp;
    slot.appendChild(el("div", { class: `stamp ${state.stamp}${state.stampShown ? " still" : ""}` }, STAMPS[state.stamp]));
    state.stampShown = true;
  }

  // Reuse: the memory's line lights up in the patch and the receipt answers with the same glow.
  function echoMemory() {
    const slot = $("memory-slot");
    slot.classList.remove("echo");
    void slot.offsetWidth; // restart the animation
    slot.classList.add("echo");
  }

  // An escalated or unresolved run's plain-text handoff (run_finished.escalation), clamped, with Copy.
  function showHandoff(text) {
    const body = el("p", {}, text);
    const more = el("button", { type: "button" }, "more");
    const copy = el("button", { type: "button" }, icon("copy"), el("span", {}, "Copy"));
    more.addEventListener("click", () => { more.textContent = body.classList.toggle("open") ? "less" : "more"; });
    copy.addEventListener("click", () => navigator.clipboard?.writeText(text).then(() => { copy.lastChild.textContent = "Copied"; }));
    const box = el("div", { id: "handoff" }, body, el("div", {}, more, copy));
    $("outcome").after(box);
    drawIcons(box);
    more.hidden = body.scrollHeight <= body.clientHeight;
  }

  function clearVerdict() {
    setOutcome("");
    $("handoff")?.remove();
    $("live-link")?.remove();
  }

  // A verified run links to the live practice app (scripts/live_app.py, port 8100): the same deliveries
  // against the original code and against this run's verified fix.
  function showLiveLink(caseId, runId) {
    $("live-link")?.remove();
    if (!caseId || !runId) return;
    const href = `http://127.0.0.1:8100/?case=${encodeURIComponent(caseId)}&run=${encodeURIComponent(runId)}`;
    const a = el("a", { id: "live-link", href, target: "_blank", rel: "noopener" }, icon("external-link"), "See it in the practice app");
    $("outcome").after(a);
    drawIcons(a);
  }

  function toast(text, iconName) {
    const t = el("div", { class: "toast", role: "status" }, icon(iconName), text);
    document.body.appendChild(t);
    drawIcons(t);
    setTimeout(() => t.remove(), 4000);
  }

  // ------------------------------------------------------------------ rendering one event

  function renderEvent(event) {
    const p = event.payload || {};
    switch (event.type) {
      case "run_started": {
        if (p.caseId && CASES[p.caseId]) {
          state.caseId = p.caseId;
          $("incident-title").textContent = CASES[p.caseId].title;
        }
        const mode = p.memoryMode && p.memoryMode !== "real" ? ` · memory ${p.memoryMode}` : "";
        setNow(`Run started for ${teamName(p.teamId)}${mode}`);
        break;
      }
      case "observation": {
        const o = p.observations || {};
        const what = o.errorCode === "11000"
          ? `Duplicate key error on ${o.dupKeyField || "a unique index"}`
          : `Observed ${o.exceptionType || "an error"}`;
        state.query = o.summary || what;
        addStep("scan-search", what, { sub: o.summary || null, phase: "observe" });
        break;
      }
      case "recall": {
        if (!p.count) {
          addStep("search-x", "Nothing your team may see", { tone: "memory", sub: "Investigating from scratch.", phase: "check" });
          $("memory-slot").dataset.empty = "Nothing your team may see.";
          // A real child, so memory.js's idle list (refreshed when key 4 flips the pill) can't fill the slot
          // with the team's own memories next to "Nothing your team may see".
          $("memory-slot").replaceChildren(el("p", { class: "slot-empty" }, "Nothing your team may see."));
          setAnswer("Not seen before by your team. Investigating from scratch.", "idle");
        } else {
          const ref = p.memories[0];
          addStep("brain", `Recalled ${p.count} ${p.count === 1 ? "memory" : "memories"}`, { tone: "memory", sub: `Owned by ${teamName(ref.ownerTeamId)}`, phase: "recall" });
          showMemory(ref);
        }
        break;
      }
      case "precondition_check": {
        // The loop checks each recalled memory in turn: one step for all of them, showing the memory that
        // held (or, if none did, the first one's reason), the others counted in its sub-line.
        state.checks.push(p);
        const used = state.checks.find((c) => c.held === c.total);
        const shown = used || state.checks[0];
        const more = state.checks.length - 1;
        const sub = more ? `${more} more similar ${more === 1 ? "memory" : "memories"} checked` : null;
        state.preconditions = shown.results || [];
        let li;
        if (used) {
          const title = used.total === 2 ? "Both conditions still true (2/2)" : `All conditions still true (${used.held}/${used.total})`;
          li = addStep("shield-check", title, { tone: "ok", sub, phase: "check" }); // the receipt lists each condition
          setAnswer(`Seen before: ${teamName(used.memory && used.memory.ownerTeamId)} fixed this, and its conditions still hold.`, "ok");
          state.decision = "used";
          if (state.stamp === "not-applied") {
            state.stamp = null; // an earlier memory didn't apply, this one does
            delete $("memory-slot").dataset.stamp;
          }
        } else {
          // Each broken condition as "memory needs X ≠ here: Y".
          const mismatches = state.preconditions.filter((r) => !r.held).map((r) => el("div", { class: "mismatch" },
            el("span", { class: "need" }, "Memory needs ", el("code", {}, String(r.expected ?? "?"))),
            el("span", { class: "ne", "aria-label": "but" }, "≠"),
            el("span", { class: "have" }, "Here: ", el("code", {}, String(r.actual ?? "unknown")))));
          li = addStep("shield-x", shown.notAppliedReason || `Conditions ${shown.held}/${shown.total} hold: memory not applied`,
            { tone: "bad", sub, extra: el("div", {}, ...mismatches), phase: "check" });
          setAnswer(shown.notAppliedReason || "A similar memory exists, but it doesn't apply here.", "warn");
          state.decision = "rejected";
          if (state.stamp !== "not-applied") stamp("not-applied");
        }
        if (state.checkStep) state.checkStep.replaceWith(li);
        state.checkStep = li;
        showMemory(shown.memory || state.memoryRef);
        break;
      }
      case "tool_call": {
        const verb = TOOL_VERBS[p.tool];
        setNow(verb ? verb(p.args || {}) : `${p.tool.replaceAll("_", " ")}…`);
        break;
      }
      case "tool_result":
        setNow(p.summary || `${p.tool.replaceAll("_", " ")} done`);
        break;
      case "patch_proposed": {
        state.attempt = p.attempt;
        for (const old of $("timeline").querySelectorAll("pre.patch")) old.hidden = true; // only the newest attempt's code
        const code = (p.patch && p.patch.newContent) || "";
        const attempt = p.attempt > 1 ? ` (attempt ${p.attempt})` : "";
        addStep("file-pen-line", `Fix proposed for ${(p.patch && p.patch.path) || "a file"}${attempt}`, { extra: patchBlock(code, p.fromMemoryLines), phase: "fix" });
        useMemory(p.fromMemory);
        if (p.fromMemoryLines && p.fromMemoryLines.length) echoMemory();
        break;
      }
      case "verification": {
        const r = p.result || {};
        const tests = r.tests || [];
        const passed = tests.filter((t) => t.passed).length;
        if (r.status === "passed") {
          state.proof = { beforeFailed: r.beforeFailed, afterPassed: r.afterPassed, tests: `${passed}/${tests.length}` };
          addStep("flask-conical", `Tests ${passed}/${tests.length} pass`, { tone: "ok", phase: "test" }); // failed-before / passed-after is on the receipt
        } else if (r.status === "inconclusive") {
          addStep("circle-help", "Verification inconclusive", { tone: "warn", sub: r.detail || "Our test infrastructure broke, not the fix.", phase: "test" });
        } else {
          const failing = tests.filter((t) => !t.passed);
          addStep("flask-conical", `Tests ${passed}/${tests.length} pass (attempt ${p.attempt})`, {
            tone: "bad",
            phase: "test",
            sub: failing.map((t) => `${t.name}${t.detail ? `: ${t.detail}` : ""}`).join(" · "),
          });
        }
        break;
      }
      case "memory_outcome": {
        // near_miss comes once per recalled memory and repeats the check step's "Not applied" line; it must not
        // swap the receipt either (the check step already chose the memory to show).
        if (p.outcome === "near_miss") break;
        const refused = p.outcome === "refused" || p.outcome === "disputed";
        const text = p.outcome === "renewed" ? "Receipt renewed: proven again today." : p.message || `Memory ${p.outcome}`;
        addStep(refused ? "ban" : "receipt-text", text, { tone: refused ? "bad" : "memory" });
        if (refused) stamp("refused");
        // P2 (R11): Atlas refused the write -> show the refusal receipt (failing test, "Nothing was stored").
        if (p.outcome === "refused" && window.traceback.showRefusal) window.traceback.showRefusal(event.runId);
        if (p.memory) showMemory(p.memory);
        break;
      }
      case "run_finished": {
        useMemory(p.memoryUsed);
        if (p.outcome === "verified") {
          const tone = p.attempt && p.attempt > 1 ? "warn" : "ok";
          setAnswer(p.summary || "Fix verified.", tone);
          setOutcome(`Verified on attempt ${p.attempt || 1}`, tone);
          if (state.memoryRef && !state.stamp) stamp("proven");
          showLiveLink(state.caseId, event.runId);
        } else if (p.outcome === "escalated") {
          if (p.summary) setAnswer(p.summary, "warn");
          setOutcome("Escalated to a human, with evidence", "warn", "user-round");
        } else {
          if (p.summary) setAnswer(p.summary, "bad");
          setOutcome("Unresolved within budget", "bad", "circle-x");
        }
        if (p.outcome !== "verified" && p.escalation) showHandoff(p.escalation);
        break;
      }
      case "error":
        addStep("circle-alert", p.message || "Error", { tone: "bad" });
        break;
      default:
        addStep("dot", event.type, { tone: "minor" });
    }
  }

  // ------------------------------------------------------------------ following a run

  // Only run_finished ends a run: the loop reports non-fatal problems as "error" events and keeps going.
  const FINAL = new Set(["run_finished"]);
  const isFinished = (runId) => !!runs[runId] && runs[runId].events.some((e) => FINAL.has(e.type));

  function remember(runId, caseId, event, replay = false) {
    if (!runs[runId]) runs[runId] = { caseId, replay, events: [] };
    if (!runs[runId].events.some((e) => e.seq === event.seq)) runs[runId].events.push(event);
    if (!replay) saveRuns();
  }

  async function followRun(runId, caseId) {
    const token = ++followToken;
    resetView(caseId);
    hideCompare();
    let after = 0, sawError = false, missing = 0;
    setLive("live");
    setStatus("Following the live run");
    while (token === followToken) {
      let events = [];
      try {
        events = await api(`/runs/${encodeURIComponent(runId)}/events?after=${after}`);
        missing = 0;
      } catch (err) {
        console.warn("Traceback: polling run events failed", err);
        // 404: usually the pill was switched to another team mid-run: say so and keep polling, so the run picks
        // up again when the pill goes back. A run that stays 404 for 2 minutes (e.g. saved before a server
        // restart) is not followed forever.
        if (err.status === 404) {
          missing += 1;
          if (missing * POLL_MS >= 120000 && token === followToken) {
            setLive(null);
            setStatus("Run not found for this identity. Shift + its key starts a new one.");
            return;
          }
          setStatus("Another team's run: switch the pill back.");
        } else {
          setStatus("Connection lost. Retrying…");
        }
      }
      for (const event of events) {
        if (token !== followToken) return;
        remember(runId, caseId, event);
        renderEvent(event);
        after = Math.max(after, event.seq);
        if (FINAL.has(event.type)) {
          setLive("done");
          setStatus("Run finished");
          return;
        }
      }
      // Safety net: a run that died without run_finished must not be followed forever. Keep checking after
      // the error event: the run's status may turn "error" a poll or two later.
      sawError = sawError || events.some((e) => e.type === "error");
      if (sawError && token === followToken) {
        try {
          const view = await api(`/runs/${encodeURIComponent(runId)}`);
          if (token !== followToken) return; // a newer run took the screen while we waited
          if (view.status === "error") {
            setLive("done");
            setStatus("Run stopped");
            return;
          }
        } catch (_) { /* keep polling */ }
      }
      await new Promise((r) => setTimeout(r, POLL_MS));
    }
  }

  async function replaySample() {
    const token = ++followToken;
    resetView("B");
    hideCompare();
    setLive("replay", true);
    setStatus("Replay of a recorded run");
    let events = [];
    try {
      events = await (await fetch("/dev/sample-run-events")).json();
    } catch (err) {
      console.warn("Traceback: sample events unavailable", err);
      setLive(null);
      setStatus("The recorded run isn't available.");
      return;
    }
    for (const event of events) {
      if (token !== followToken) return;
      remember(event.runId, "B", event, true);
      renderEvent(event);
      await new Promise((r) => setTimeout(r, SAMPLE_STEP_MS));
    }
    setLive("done", true);
    setStatus("Replay finished");
  }

  // ------------------------------------------------------------------ compare overlay (P3-8)
  // Two finished runs of the same case side by side: the latest one that used a memory and the
  // latest one that didn't (the rerun after Forget). Facts only, taken from events.

  function summarize(events) {
    const out = { seenBefore: false, outcome: null, attempts: [], patches: [] };
    for (const e of events) {
      const p = e.payload || {};
      if (e.type === "patch_proposed") {
        out.patches.push({ attempt: p.attempt, code: (p.patch && p.patch.newContent) || "", memoryLines: p.fromMemoryLines || [] });
      } else if (e.type === "verification") {
        const tests = (p.result && p.result.tests) || [];
        out.attempts.push({ attempt: p.attempt, ok: !tests.some((t) => !t.passed), failing: tests.filter((t) => !t.passed).map((t) => t.name) });
      } else if (e.type === "run_finished") {
        out.seenBefore = !!p.seenBefore;
        out.outcome = p.outcome;
      }
    }
    return out;
  }

  // `code` is the with-memory patch; on the "after Forget" side its memory lines show as empty rows.
  function compareColumn(heading, s, variant, code) {
    const final = s.attempts[s.attempts.length - 1];
    const verified = s.outcome === "verified" && final;
    const failing = [...new Set(s.attempts.flatMap((a) => a.failing))];
    return el("article", { class: `compare-col ${variant}` },
      el("h3", {}, icon(variant === "with" ? "brain" : "circle-dashed"), heading),
      el("p", { class: "numeral" }, el("strong", {}, verified ? String(final.attempt) : "–"),
        verified ? `${final.attempt === 1 ? "attempt" : "attempts"} to a verified fix` : s.outcome || "no result"),
      code ? patchBlock(code.code, code.memoryLines, { caseId: "B", missing: variant !== "with" }) : null,
      failing.length ? el("p", { class: "failing" }, ...failing.map((name) => el("code", {}, `${name} ✗`))) : null,
      el("p", { class: "attempts" }, ...s.attempts.flatMap((a, i) => [
        i ? el("span", { class: "arrow" }, "→") : null,
        el("span", { class: a.ok ? "ok" : "bad" }, `Attempt ${a.attempt} ${a.ok ? "✓" : "✗"}`)])));
  }

  function showCompare(caseId) {
    document.querySelectorAll(".toast").forEach((t) => t.remove()); // never over the overlay
    const finished = Object.values(runs)
      .filter((r) => r.caseId === caseId && r.events.some((e) => e.type === "run_finished"))
      .map((r) => summarize(r.events));
    const withMemory = finished.filter((s) => s.seenBefore).pop();
    const withoutMemory = finished.filter((s) => !s.seenBefore).pop();
    const box = $("compare");
    const head = el("header", {}, el("h2", {}, "Same incident, with and without memory"),
      el("button", { type: "button", class: "close" }, el("kbd", {}, "Esc"), "Close"));
    head.querySelector("button").addEventListener("click", hideCompare);
    if (!withMemory || !withoutMemory) {
      box.replaceChildren(head, el("p", { class: "empty" }, "Compare needs two finished runs of this case: one with memory, and one after Forget."));
    } else {
      const code = withMemory.patches.find((p) => p.memoryLines.length);
      box.replaceChildren(head, el("div", { class: "columns" },
        compareColumn("With memory", withMemory, "with", code),
        compareColumn("After Forget", withoutMemory, "without", code)));
    }
    drawIcons(box);
    box.hidden = false;
    setPressed("c", true);
    fitSoon(true);
  }

  function hideCompare() {
    $("compare").hidden = true;
    setPressed("c", false);
    fitSoon(true);
  }

  // ------------------------------------------------------------------ starting cases

  async function startCase(caseId) {
    const c = CASES[caseId];
    if (!c) return;
    if (c.key.split("-")[1] !== currentKey.split("-")[1]) applyIdentity(c.key);
    resetView(caseId);
    try {
      const incident = await api("/incidents", {
        method: "POST",
        body: JSON.stringify({ repositoryId: c.repo, caseId, logs: "", request: {} }),
      });
      const run = await api(`/incidents/${encodeURIComponent(incident.incidentId)}/runs`, { method: "POST" });
      lastRunByCase[caseId] = { runId: run.runId, startedAt: Date.now() };
      saveRuns();
      followRun(run.runId, caseId);
    } catch (err) {
      console.warn(`Traceback: couldn't start case ${caseId}`, err);
      if (err.status === 501) {
        setAnswer("The live agent isn't available right now. Press 0 to replay a recorded run.", "idle");
        setStatus("Live runs unavailable");
      } else {
        setAnswer("Couldn't start this case. Try again in a moment.", "bad");
      }
    }
  }

  // Keys 2-4: show the run already in flight (or started in the last few minutes) instead of starting another.
  // Shift forces a fresh run.
  function openCase(caseId, force) {
    const last = lastRunByCase[caseId];
    const c = CASES[caseId];
    if (!force && last && (!isFinished(last.runId) || Date.now() - last.startedAt < RECENT_MS)) {
      if (c.key.split("-")[1] !== currentKey.split("-")[1]) applyIdentity(c.key);
      followRun(last.runId, caseId);
    } else {
      startCase(caseId);
    }
  }

  // ------------------------------------------------------------------ keys and the key-chip bar: the five beats

  const BEATS = {
    // Earn: shows the last Earn run; a new one only with Shift, so a stray 1 can't create a memory mid-demo.
    "1": (force) => {
      if (force) startCase("A");
      else if (lastRunByCase.A) {
        if (currentKey.split("-")[1] !== "payments") applyIdentity(CASES.A.key);
        followRun(lastRunByCase.A.runId, "A");
      }
      else setAnswer("No Earn run on record yet. Shift+1 starts one.", "idle");
    },
    "2": (force) => openCase("B", force), // Reuse
    "3": (force) => openCase("C", force), // Refuse
    "4": (force) => openCase("D", force), // Fence: switches to the Platform engineer
    // Forget: memory.js only redraws a slot it owns, so clear a Fence/refusal view first, then redraw the list.
    // Forget leaves the run: a finished run's data-live="done" would make memory.js keep its hands off the slot (#73).
    "5": () => { if ($("run-panel").dataset.live !== "live") setLive(null); $("memory-slot").replaceChildren(); applyIdentity("key-payments-admin"); window.traceback.refreshMemories?.(); $("memory-panel").scrollIntoView({ behavior: smooth }); scrollToForget(Date.now()); },
    "6": (force) => openCase("P", force), // Earn's poisoned log: Atlas refuses an unproven memory
    "0": () => replaySample(),
    c: () => ($("compare").hidden ? showCompare("B") : hideCompare()), // compare with vs without memory
    // P2 views (web/memory.js), into the memory panel:
    // F and R swap the receipt column to a P2 view: clear the run's verdict so a green "Verified" never sits
    // under a red refusal, and the Fence card has the column to itself (fits at 1280x720).
    f: () => { clearVerdict(); window.traceback.showFence && window.traceback.showFence(); }, // "Payments sees 1 / Platform sees 0" + filter
    r: () => { clearVerdict(); window.traceback.showRefusal && window.traceback.showRefusal(); }, // latest "Memory refused: no proof." (R11)
  };

  // Key 5: memory.js adds the admin drawer once /whoami answers; bring its reason box and Forget button into view
  // (at 1280x720 they sit below the card, inside the receipt column's scroll).
  function scrollToForget(since) {
    const reason = document.querySelector("#memory-slot .tb-admin .tb-reason");
    if (reason) reason.scrollIntoView({ block: "center", behavior: smooth });
    else if (Date.now() - since < 5000) setTimeout(() => scrollToForget(since), 200);
  }

  const chip = (key) => document.querySelector(`#keys button[data-key="${key}"]`);
  function setPressed(key, on) {
    const button = chip(key);
    if (button) button.setAttribute("aria-pressed", String(on));
  }

  function runBeat(key, force) {
    if (key !== "c" && !$("compare").hidden) hideCompare(); // F, R, 5... would otherwise draw under the overlay
    BEATS[key](force);
    const button = chip(key);
    if (!button) return;
    button.classList.remove("pressed");
    void button.offsetWidth; // restart the press animation
    button.classList.add("pressed");
    if (key !== "c") {
      for (const b of document.querySelectorAll("#keys button.current")) b.classList.remove("current");
      button.classList.add("current");
    }
  }

  document.addEventListener("keydown", (e) => {
    if (e.ctrlKey || e.metaKey || e.altKey || e.repeat) return; // a held Shift+1 must not start a run per repeat
    const tag = (e.target && e.target.tagName) || "";
    if (["INPUT", "TEXTAREA", "SELECT"].includes(tag) || (e.target && e.target.isContentEditable)) return;
    if (e.key === "Escape" && !$("compare").hidden) {
      hideCompare();
      return;
    }
    // e.code, so Shift+2 still reads as "2" (e.key would be "@").
    const digit = /^(?:Digit|Numpad)(\d)$/.exec(e.code);
    const key = digit ? digit[1] : e.key.toLowerCase();
    if (BEATS[key]) {
      e.preventDefault();
      runBeat(key, e.shiftKey);
    }
  });

  // ------------------------------------------------------------------ public hooks

  window.traceback = {
    api,
    currentKey: () => currentKey,
    showRun: (runId, caseId) => followRun(runId, caseId),
    startCase,
    showCompare,
    renderMemoryCard: (memory, context) => fallbackCard(memory), // replaced by web/memory.js (P2-4)
  };

  document.addEventListener("DOMContentLoaded", async () => {
    loadRuns();
    drawIcons(document.body); // the static icons in index.html
    setAnswer(IDLE_TEXT, "idle");
    showGhosts();
    // Anything that changes size (a step, the receipt, memory.js's list, the window) refits the page.
    const watch = new ResizeObserver(() => fitSoon());
    for (const id of ["answer", "timeline", "now", "ghosts", "memory-slot", "outcome", "compare"]) watch.observe($(id));
    addEventListener("resize", () => fitSoon(true));
    // Forget (key 5, then the admin's button): memory.js turns the receipt into a tombstone and tells us.
    document.addEventListener("traceback:memory-forgotten", () => toast("Forgotten: recall now finds 0 candidates", "eraser"));
    $("keys").addEventListener("click", (e) => {
      const button = e.target.closest("button[data-key]");
      if (button) runBeat(button.dataset.key, e.shiftKey);
    });
    setupIdentity();
    try {
      const health = await (await fetch("/health")).json();
      setStatus(health.status === "ok" ? "Connected" : `Server: ${health.status}`);
    } catch (err) {
      setStatus("Server not reachable");
    }
  });
})();
