// Owner: P3. The run view, identity pill and keyboard shortcuts (plan 7.3).
// Contract hooks (plan section 6): memory.js (P2) and voice.js (P1) talk to this file ONLY through
//   window.traceback.renderMemoryCard(memory, context)   <- implemented by memory.js
//   window.traceback.currentKey()                         -> the API key the page acts as
//   window.traceback.showRun(runId)                       -> make the screen follow a run
//
// Until P1's run endpoints exist (they return 501), key 0 replays contracts/sample_run_events.json
// so the screen can be built and rehearsed. Live runs need POST /incidents to accept a caseId and
// load cases/<id>/manifest.json on the server.
(function () {
  // Fake, local-only demo keys (see DEMO_PRINCIPALS in .env.example). Not real authentication.
  const DEMO_KEYS = [
    { key: "key-payments-eng", label: "Payments engineer", team: "payments" },
    { key: "key-payments-admin", label: "Payments admin", team: "payments" },
    { key: "key-platform-eng", label: "Platform engineer", team: "platform" },
    { key: "key-platform-admin", label: "Platform admin", team: "platform" },
  ];
  const TEAM_NAMES = { "team-payments": "Payments", "team-platform": "Platform" };
  const CASES = {
    A: { title: "Duplicate webhook crashes payments", repo: "payments-webhooks", key: "key-payments-eng" },
    B: { title: "Notification endpoint failing during a provider retry storm", repo: "payments-webhooks", key: "key-payments-eng" },
    C: { title: "Two different payments from one customer collide", repo: "payments-webhooks", key: "key-payments-eng" },
    D: { title: "Duplicate webhook crashes Platform billing", repo: "platform-webhooks", key: "key-platform-eng" },
    P: { title: "Duplicate webhook, with a suspicious log line", repo: "payments-webhooks", key: "key-payments-eng" },
  };
  const POLL_MS = 1000;
  const SAMPLE_STEP_MS = 700;

  let currentKey = DEMO_KEYS[0].key;
  let followToken = 0; // cancels an older run being followed when a new one starts
  let lastRunByCase = {};
  const runs = {}; // runId -> { caseId, events: [] }, kept for the compare view
  let state = freshState();

  function freshState() {
    return { memoryRef: null, preconditions: [], decision: null, attempt: null };
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

  // One patch line: Prism-highlighted Python (escaped text if Prism is missing) plus our "from memory" tag.
  const escapeHtml = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  function highlightLines(code) {
    const html = window.Prism && Prism.languages.python ? Prism.highlight(code, Prism.languages.python, "python") : escapeHtml(code);
    return html.split("\n");
  }
  function codeLine(html, isMemory) {
    const line = el("span", { class: isMemory ? "line from-memory" : "line" });
    line.innerHTML = html || " ";
    if (isMemory) line.appendChild(el("span", { class: "tag" }, icon("brain"), "from memory"));
    return line;
  }

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

  function addStep(iconName, text, { tone = "", sub = null, extra = null } = {}) {
    const li = el("li", { class: tone }, el("span", { class: "icon" }, icon(iconName)), el("div", {}, text, sub ? el("span", { class: "sub" }, sub) : null, extra));
    $("timeline").appendChild(li);
    drawIcons(li);
    li.scrollIntoView({ block: "nearest", behavior: "smooth" });
    return li;
  }

  function resetView(caseId) {
    $("timeline").innerHTML = "";
    $("memory-slot").innerHTML = "";
    setOutcome("");
    setAnswer("Investigating…", "idle");
    state = freshState();
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
      .catch((err) => setStatus(`Identity check failed (${err.status || err.message}). Is DEMO_PRINCIPALS set in .env?`));
  }

  function setupIdentity() {
    const select = $("identity");
    for (const k of DEMO_KEYS) select.appendChild(el("option", { value: k.key }, `Acting as: ${k.label}`));
    select.addEventListener("change", () => applyIdentity(select.value));
    applyIdentity(currentKey);
  }

  // ------------------------------------------------------------------ memory card

  async function showMemory(ref) {
    if (!ref) return;
    state.memoryRef = ref;
    let card = null;
    try {
      card = await api(`/memories/${encodeURIComponent(ref.memoryId)}`);
    } catch (_) {
      card = null; // P2's endpoint not ready, or not readable: fall back to the reference
    }
    const memory = card || {
      memoryId: ref.memoryId, version: ref.version, ownerTeamId: ref.ownerTeamId, match: ref.match,
      title: "Replayed webhook: record the replay, credit once",
    };
    const context = { currentKey, preconditions: state.preconditions, decision: state.decision };
    let node = null;
    try {
      node = window.traceback.renderMemoryCard(memory, context);
    } catch (_) {
      node = null;
    }
    // memory.js's stub returns a bare text div; treat that like "not implemented yet" too.
    if (!node || node.textContent.includes("TODO") || !node.firstElementChild) node = fallbackCard(memory);
    const slot = $("memory-slot");
    slot.innerHTML = "";
    slot.appendChild(node);
    drawIcons(slot);
  }

  function fallbackCard(memory) {
    const owner = teamName(memory.ownerTeamId);
    const conditions = state.preconditions.length
      ? el("ul", { class: "conditions" }, ...state.preconditions.map((r) => el("li", { class: r.held ? "ok" : "bad" },
        el("span", { class: "mark" }, icon(r.held ? "check" : "x")),
        el("span", {}, r.check.replaceAll("_", " ")),
        el("code", {}, String(r.actual ?? "unknown")))))
      : null;
    const teamClass = TEAM_NAMES[memory.ownerTeamId] ? memory.ownerTeamId : "";
    return el("div", { class: `memory-fallback ${teamClass}` },
      el("div", { class: "memory-head" },
        el("span", { class: "chip owner" }, icon("users"), `Owner: ${owner}`),
        memory.match ? el("span", { class: `chip match ${memory.match}` }, `Match: ${memory.match}`) : null),
      el("div", { class: "memory-body" },
        el("h3", {}, memory.title || "Memory"),
        el("p", { class: "visible" }, icon("lock"), `Visible to: ${owner} only`),
        conditions));
  }

  // ------------------------------------------------------------------ rendering one event

  function renderEvent(event) {
    const p = event.payload || {};
    switch (event.type) {
      case "run_started": {
        if (p.caseId && CASES[p.caseId]) $("incident-title").textContent = CASES[p.caseId].title;
        const mode = p.memoryMode && p.memoryMode !== "real" ? ` · memory ${p.memoryMode}` : "";
        addStep("play", `Run started for ${teamName(p.teamId)}${mode}`, { tone: "minor" });
        break;
      }
      case "observation": {
        const o = p.observations || {};
        const what = o.errorCode === "11000"
          ? `Observed duplicate key error (E11000) on ${o.dupKeyField || "a unique index"}`
          : `Observed ${o.exceptionType || "an error"}`;
        addStep("scan-search", what, { sub: o.summary || null });
        break;
      }
      case "recall": {
        if (!p.count) {
          addStep("search-x", "No memories available to your team", { tone: "memory", sub: "Investigating from scratch." });
          setAnswer("Not seen before by your team. Investigating from scratch.", "idle");
        } else {
          const ref = p.memories[0];
          addStep("brain", `Recalled ${p.count} ${p.count === 1 ? "memory" : "memories"}`, {
            tone: "memory",
            sub: `Owned by ${teamName(ref.ownerTeamId)} · match: ${ref.match || "n/a"}`,
          });
          showMemory(ref);
        }
        break;
      }
      case "precondition_check": {
        state.preconditions = p.results || [];
        const owner = teamName(p.memory && p.memory.ownerTeamId);
        if (p.held === p.total) {
          addStep("shield-check", `Conditions ${p.held}/${p.total} hold`, { tone: "ok", sub: state.preconditions.map((r) => r.check.replaceAll("_", " ")).join(" · ") });
          setAnswer(`Seen before: ${owner} fixed this, and its conditions ${p.held}/${p.total} hold.`, "ok");
          state.decision = "used";
        } else {
          addStep("shield-x", p.notAppliedReason || `Conditions ${p.held}/${p.total} hold: memory not applied`, { tone: "bad" });
          setAnswer(p.notAppliedReason || "A similar memory exists, but it doesn't apply here.", "warn");
          state.decision = "rejected";
        }
        if (state.memoryRef) showMemory(state.memoryRef);
        break;
      }
      case "tool_call":
        break; // shown together with its result
      case "tool_result":
        addStep("terminal", `${p.tool.replaceAll("_", " ")}: ${p.summary}`, { tone: "minor" });
        break;
      case "patch_proposed": {
        state.attempt = p.attempt;
        const highlight = new Set(p.fromMemoryLines || []);
        const lines = highlightLines(((p.patch && p.patch.newContent) || "").replace(/\n$/, ""));
        const pre = el("pre", { class: "patch" }, ...lines.map((html, i) => codeLine(html, highlight.has(i + 1))));
        const sub = p.fromMemory ? `Uses ${teamName(p.fromMemory.ownerTeamId)}'s proven fix` : null;
        addStep("file-pen-line", `Fix proposed for ${(p.patch && p.patch.path) || "a file"} (attempt ${p.attempt})`, { sub, extra: pre });
        break;
      }
      case "verification": {
        const r = p.result || {};
        const tests = r.tests || [];
        const passed = tests.filter((t) => t.passed).length;
        if (r.status === "passed") {
          addStep("flask-conical", `Tests ${passed}/${tests.length} pass`, { tone: "ok", sub: "Failed before the fix, passes after. Only the runner's results count." });
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
        const tone = p.outcome === "refused" || p.outcome === "disputed" ? "bad" : "memory";
        addStep(tone === "bad" ? "ban" : "receipt", p.message || `Memory ${p.outcome}`, { tone });
        if (p.memory) showMemory(p.memory);
        break;
      }
      case "run_finished": {
        if (p.outcome === "verified") {
          setOutcome(`Verified on attempt ${p.attempt || 1}`, p.attempt && p.attempt > 1 ? "warn" : "ok");
          setAnswer(p.summary || "Fix verified.", p.attempt && p.attempt > 1 ? "warn" : "ok");
        } else if (p.outcome === "escalated") {
          setOutcome("Escalated to a human, with evidence", "warn", "user-round");
          if (p.summary) setAnswer(p.summary, "warn");
        } else {
          setOutcome("Unresolved within budget", "bad", "circle-x");
          if (p.summary) setAnswer(p.summary, "bad");
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

  const FINAL = new Set(["run_finished", "error"]);

  function remember(runId, caseId, event) {
    if (!runs[runId]) runs[runId] = { caseId, events: [] };
    if (!runs[runId].events.some((e) => e.seq === event.seq)) runs[runId].events.push(event);
  }

  async function followRun(runId, caseId) {
    const token = ++followToken;
    resetView(caseId);
    hideCompare();
    let after = 0;
    setStatus(`Following run ${runId}`);
    while (token === followToken) {
      let events = [];
      try {
        events = await api(`/runs/${encodeURIComponent(runId)}/events?after=${after}`);
      } catch (err) {
        setStatus(`Lost the run (${err.status || err.message}). Retrying…`);
      }
      for (const event of events) {
        if (token !== followToken) return;
        remember(runId, caseId, event);
        renderEvent(event);
        after = Math.max(after, event.seq);
        if (FINAL.has(event.type)) {
          setStatus(`Run ${runId} finished`);
          return;
        }
      }
      await new Promise((r) => setTimeout(r, POLL_MS));
    }
  }

  async function replaySample() {
    const token = ++followToken;
    resetView("B");
    setStatus("Replaying contracts/sample_run_events.json (no live agent)");
    let events = [];
    try {
      events = await (await fetch("/dev/sample-run-events")).json();
    } catch (err) {
      setStatus(`Sample events not available: ${err}`);
      return;
    }
    for (const event of events) {
      if (token !== followToken) return;
      remember(event.runId, "B", event);
      renderEvent(event);
      await new Promise((r) => setTimeout(r, SAMPLE_STEP_MS));
    }
    setStatus("Sample replay finished");
  }

  // ------------------------------------------------------------------ compare view (P3-8)
  // Two finished runs of the same case side by side: the latest one that used a memory and the
  // latest one that didn't (for example, the rerun after Forget). Facts only, taken from events.

  function summarize(events) {
    const out = { seenBefore: false, outcome: null, summary: "", attempts: [], memoryLines: [], steps: events.length };
    for (const e of events) {
      const p = e.payload || {};
      if (e.type === "patch_proposed") {
        const lines = ((p.patch && p.patch.newContent) || "").split("\n");
        out.memoryLines.push(...(p.fromMemoryLines || []).map((n) => lines[n - 1]).filter(Boolean));
      } else if (e.type === "verification") {
        const tests = (p.result && p.result.tests) || [];
        out.attempts.push({
          attempt: p.attempt,
          passed: tests.filter((t) => t.passed).length,
          total: tests.length,
          failing: tests.filter((t) => !t.passed).map((t) => t.name),
        });
      } else if (e.type === "run_finished") {
        out.seenBefore = !!p.seenBefore;
        out.outcome = p.outcome;
        out.summary = p.summary || "";
      }
    }
    return out;
  }

  function compareColumn(heading, s, variant) {
    const finalAttempt = s.attempts[s.attempts.length - 1];
    const tone = s.outcome === "verified" ? (s.attempts.length > 1 ? "warn" : "ok") : "bad";
    return el("article", { class: `compare-col ${variant}` },
      el("h3", {}, icon(variant === "with" ? "brain" : "circle-dashed"), heading),
      el("ol", {}, ...s.attempts.map((a) => el("li", { class: a.failing.length ? "bad" : "ok" },
        icon(a.failing.length ? "circle-x" : "circle-check"),
        `Attempt ${a.attempt}: tests ${a.passed}/${a.total}`,
        a.failing.length ? el("span", { class: "sub" }, `Failed: ${a.failing.join(", ")}`) : null))),
      s.memoryLines.length
        ? el("pre", { class: "patch" }, ...s.memoryLines.map((t) => codeLine(highlightLines(t.trim())[0], true)))
        : null,
      el("div", { class: `badge ${tone}` }, finalAttempt ? `${s.outcome} on attempt ${finalAttempt.attempt}` : s.outcome || "no result"),
      el("p", { class: "sub" }, `${s.steps} steps · ${s.summary}`));
  }

  function showCompare(caseId) {
    const finished = Object.values(runs)
      .filter((r) => r.caseId === caseId && r.events.some((e) => e.type === "run_finished"))
      .map((r) => summarize(r.events));
    const withMemory = finished.filter((s) => s.seenBefore).pop();
    const withoutMemory = finished.filter((s) => !s.seenBefore).pop();
    const box = $("compare");
    box.innerHTML = "";
    if (!withMemory || !withoutMemory) {
      box.appendChild(el("p", { class: "sub" }, `Compare needs two finished runs of case ${caseId}: one with memory and one without (rerun it after Forget).`));
    } else {
      box.appendChild(compareColumn("With memory", withMemory, "with"));
      box.appendChild(compareColumn("Without memory", withoutMemory, "without"));
    }
    drawIcons(box);
    box.hidden = false;
    box.scrollIntoView({ behavior: "smooth" });
  }

  function hideCompare() {
    $("compare").hidden = true;
  }

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
      lastRunByCase[caseId] = run.runId;
      followRun(run.runId, caseId);
    } catch (err) {
      if (err.status === 501) {
        setAnswer("The live agent isn't wired up yet (P1-4). Press 0 to replay the sample run.", "idle");
        setStatus("POST /incidents returned 501 Not Implemented");
      } else {
        setAnswer(`Couldn't start case ${caseId}: ${err.message}`, "bad");
      }
    }
  }

  // ------------------------------------------------------------------ keyboard: the five beats

  const BEATS = {
    "1": () => (lastRunByCase.A ? followRun(lastRunByCase.A, "A") : startCase("A")), // Earn
    "2": () => startCase("B"), // Reuse
    "3": () => startCase("C"), // Refuse
    "4": () => startCase("D"), // Fence: switches to the Platform engineer
    "5": () => { applyIdentity("key-payments-admin"); $("memory-panel").scrollIntoView({ behavior: "smooth" }); }, // Forget
    "0": () => replaySample(),
    c: () => ($("compare").hidden ? showCompare("B") : hideCompare()), // compare with vs without memory
  };

  document.addEventListener("keydown", (e) => {
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    const tag = (e.target && e.target.tagName) || "";
    if (["INPUT", "TEXTAREA", "SELECT"].includes(tag) || (e.target && e.target.isContentEditable)) return;
    const action = BEATS[e.key];
    if (action) {
      e.preventDefault();
      action();
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
    drawIcons(document.body); // the static icons in index.html
    setupIdentity();
    try {
      const health = await (await fetch("/health")).json();
      setStatus(`API ${health.status}`);
    } catch (err) {
      setStatus(`API not reachable: ${err}`);
    }
  });
})();
