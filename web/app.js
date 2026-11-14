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
    return { memoryRef: null, preconditions: [], decision: null, attempt: null, proof: null,
      stamp: null, stampShown: false, printed: null, caseId: null, now: null, startedAt: Date.now() };
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
  function codeLine(html, cls = "", tag = null) {
    const line = el("span", { class: `line ${cls}` });
    line.innerHTML = cls === "empty" ? "" : html || " ";
    if (tag) line.appendChild(el("span", { class: "tag" }, icon("brain"), tag));
    return line;
  }
  const memoryTag = (caseId) => (CASES[caseId] && CASES[caseId].provenBy ? `from memory · proven by ${CASES[caseId].provenBy}` : "from memory");

  // The patch as a <pre>: with memory lines, only those ±2 neighbours (dimmed); `missing` renders them as empty rows.
  function patchBlock(code, memoryLines, { caseId = state.caseId, missing = false } = {}) {
    const lines = highlightLines(code.replace(/\n$/, ""));
    const marked = new Set(memoryLines || []);
    let first = 1, last = lines.length;
    if (marked.size) {
      first = Math.max(1, Math.min(...marked) - 2);
      last = Math.min(lines.length, Math.max(...marked) + 2);
    }
    // Dedent the window so deep indentation doesn't push lines into wrapping (leading spaces are plain text in Prism's HTML).
    const shown = lines.slice(first - 1, last).filter((h) => h.trim());
    const indent = Math.min(...shown.map((h) => h.length - h.trimStart().length));
    const text = (n) => lines[n - 1].slice(Math.min(indent, lines[n - 1].length - lines[n - 1].trimStart().length));
    const rows = [];
    for (let n = first; n <= last; n++) {
      if (!marked.has(n)) rows.push(codeLine(text(n), marked.size ? "near" : ""));
      else if (missing) rows.push(codeLine("", "empty"));
      else rows.push(codeLine(text(n), "from-memory", memoryTag(caseId)));
    }
    const pre = el("pre", { class: marked.size ? "patch" : "patch full" }, ...rows);
    pre.style.counterReset = `line ${first - 1}`;
    return pre;
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
  }

  // ------------------------------------------------------------------ timeline

  function addStep(iconName, text, { tone = "", sub = null, extra = null } = {}) {
    const li = el("li", { class: tone }, el("span", { class: "icon" }, icon(iconName)), el("div", {}, text, sub ? el("span", { class: "sub" }, sub) : null, extra));
    $("timeline").appendChild(li);
    drawIcons(li);
    li.scrollIntoView({ block: "nearest", behavior: smooth });
    return li;
  }

  function resetView(caseId) {
    $("timeline").innerHTML = "";
    $("memory-slot").innerHTML = "";
    delete $("memory-slot").dataset.stamp;
    delete $("memory-slot").dataset.empty;
    setOutcome("");
    setLive(null);
    setAnswer("Investigating…", "idle");
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
      .then((p) => setStatus(`Acting as ${teamName(p.teamId)} · ${p.role}`))
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
      proof ? row("Tests", proof.tests) : null,
      ...state.preconditions.map((r) => row(conditionLabel(r), mark(r.held))),
      memory.expiresAt ? row("Expires", relativeExpiry(memory.expiresAt)) : null,
    ];
    const teamClass = TEAM_NAMES[memory.ownerTeamId] ? memory.ownerTeamId : "";
    return el("div", { class: `memory-fallback ${teamClass}` },
      el("p", { class: "receipt-head" }, "Traceback · memory receipt"),
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
        addStep("scan-search", what, { sub: o.summary || null });
        break;
      }
      case "recall": {
        if (!p.count) {
          addStep("search-x", "Nothing your team may see", { tone: "memory", sub: "Investigating from scratch." });
          $("memory-slot").dataset.empty = "Nothing your team may see.";
          setAnswer("Not seen before by your team. Investigating from scratch.", "idle");
        } else {
          const ref = p.memories[0];
          addStep("brain", `Recalled ${p.count} ${p.count === 1 ? "memory" : "memories"}`, { tone: "memory", sub: `Owned by ${teamName(ref.ownerTeamId)}` });
          showMemory(ref);
        }
        break;
      }
      case "precondition_check": {
        state.preconditions = p.results || [];
        const owner = teamName(p.memory && p.memory.ownerTeamId);
        if (p.held === p.total) {
          const title = p.total === 2 ? "Both conditions still true (2/2)" : `All conditions still true (${p.held}/${p.total})`;
          addStep("shield-check", title, { tone: "ok" }); // the receipt lists each condition
          setAnswer(`Seen before: ${owner} fixed this, and its conditions still hold.`, "ok");
          state.decision = "used";
        } else {
          // Each broken condition as "memory requires X ≠ this incident: Y".
          const mismatches = state.preconditions.filter((r) => !r.held).map((r) => el("div", { class: "mismatch" },
            el("span", { class: "need" }, "Memory requires ", el("code", {}, String(r.expected ?? "?"))),
            el("span", { class: "ne", "aria-label": "but" }, "≠"),
            el("span", { class: "have" }, "This incident: ", el("code", {}, String(r.actual ?? "unknown")))));
          addStep("shield-x", p.notAppliedReason || `Conditions ${p.held}/${p.total} hold: memory not applied`, { tone: "bad", extra: el("div", {}, ...mismatches) });
          setAnswer(p.notAppliedReason || "A similar memory exists, but it doesn't apply here.", "warn");
          state.decision = "rejected";
          stamp("not-applied");
        }
        if (state.memoryRef) showMemory(state.memoryRef);
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
        addStep("file-pen-line", `Fix proposed for ${(p.patch && p.patch.path) || "a file"}${attempt}`, { extra: patchBlock(code, p.fromMemoryLines) });
        break;
      }
      case "verification": {
        const r = p.result || {};
        const tests = r.tests || [];
        const passed = tests.filter((t) => t.passed).length;
        if (r.status === "passed") {
          state.proof = { beforeFailed: r.beforeFailed, afterPassed: r.afterPassed, tests: `${passed}/${tests.length}` };
          addStep("flask-conical", `Tests ${passed}/${tests.length} pass`, { tone: "ok" }); // failed-before / passed-after is on the receipt
        } else if (r.status === "inconclusive") {
          addStep("circle-help", "Verification inconclusive", { tone: "warn", sub: r.detail || "Our test infrastructure broke, not the fix." });
        } else {
          const failing = tests.filter((t) => !t.passed);
          addStep("flask-conical", `Tests ${passed}/${tests.length} pass (attempt ${p.attempt})`, {
            tone: "bad",
            sub: failing.map((t) => `${t.name}${t.detail ? `: ${t.detail}` : ""}`).join(" · "),
          });
        }
        break;
      }
      case "memory_outcome": {
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
        if (p.outcome === "verified") {
          const tone = p.attempt && p.attempt > 1 ? "warn" : "ok";
          setAnswer(p.summary || "Fix verified.", tone);
          setOutcome(`Verified on attempt ${p.attempt || 1}`, tone);
          if (state.memoryRef && !state.stamp) stamp("proven");
        } else if (p.outcome === "escalated") {
          if (p.summary) setAnswer(p.summary, "warn");
          setOutcome("Escalated to a human, with evidence", "warn", "user-round");
        } else {
          if (p.summary) setAnswer(p.summary, "bad");
          setOutcome("Unresolved within budget", "bad", "circle-x");
        }
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
    let after = 0;
    setLive("live");
    setStatus("Following the live run");
    while (token === followToken) {
      let events = [];
      try {
        events = await api(`/runs/${encodeURIComponent(runId)}/events?after=${after}`);
      } catch (err) {
        console.warn("Traceback: polling run events failed", err);
        setStatus("Connection lost. Retrying…");
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
      // Safety net: a run that died without run_finished must not be followed forever.
      if (events.some((e) => e.type === "error")) {
        try {
          if ((await api(`/runs/${encodeURIComponent(runId)}`)).status === "error") {
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
    const tone = s.outcome === "verified" ? (s.attempts.length > 1 ? "warn" : "ok") : "bad";
    const failing = [...new Set(s.attempts.flatMap((a) => a.failing))];
    return el("article", { class: `compare-col ${variant}` },
      el("div", { class: "numeral" }, s.outcome === "verified" && final ? String(final.attempt) : "–"),
      el("p", { class: "numeral-label" }, "attempts to a verified fix"),
      el("h3", {}, icon(variant === "with" ? "brain" : "circle-dashed"), heading),
      code ? patchBlock(code.code, code.memoryLines, { caseId: "B", missing: variant !== "with" }) : null,
      failing.length ? el("p", { class: "failing" }, ...failing.map((name) => el("code", {}, `${name} ✗`))) : null,
      el("p", { class: "attempts" }, ...s.attempts.flatMap((a, i) => [
        i ? el("span", { class: "arrow" }, "→") : null,
        el("span", { class: a.ok ? "ok" : "bad" }, `Attempt ${a.attempt} ${a.ok ? "✓" : "✗"}`)])),
      el("div", { class: `badge ${tone}` }, final ? `${s.outcome} on attempt ${final.attempt}` : s.outcome || "no result"));
  }

  function showCompare(caseId) {
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
  }

  function hideCompare() {
    $("compare").hidden = true;
    setPressed("c", false);
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
      else if (lastRunByCase.A) followRun(lastRunByCase.A.runId, "A");
      else setAnswer("No Earn run on record yet. Shift+1 starts one.", "idle");
    },
    "2": (force) => openCase("B", force), // Reuse
    "3": (force) => openCase("C", force), // Refuse
    "4": (force) => openCase("D", force), // Fence: switches to the Platform engineer
    "5": () => { applyIdentity("key-payments-admin"); $("memory-panel").scrollIntoView({ behavior: smooth }); }, // Forget
    "0": () => replaySample(),
    c: () => ($("compare").hidden ? showCompare("B") : hideCompare()), // compare with vs without memory
    // P2 views (web/memory.js), into the memory panel:
    f: () => window.traceback.showFence && window.traceback.showFence(), // "Payments sees 1 / Platform sees 0" + filter
    r: () => window.traceback.showRefusal && window.traceback.showRefusal(), // latest "Memory refused: no proof." (R11)
  };

  const chip = (key) => document.querySelector(`#keys button[data-key="${key}"]`);
  function setPressed(key, on) {
    const button = chip(key);
    if (button) button.setAttribute("aria-pressed", String(on));
  }

  function runBeat(key, force) {
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
    if (e.ctrlKey || e.metaKey || e.altKey) return;
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
