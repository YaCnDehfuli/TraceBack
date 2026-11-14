// Owner: P3. The run view, identity pill and keyboard shortcuts (plan 7.3).
// Contract hooks (plan section 6): memory.js (P2) and voice.js (P1) talk to this file ONLY through
//   window.traceback.renderMemoryCard(memory, context)   <- implemented by memory.js
//   window.traceback.currentKey()                         -> the API key the page acts as
//   window.traceback.showRun(runId)                       -> make the screen follow a run
(function () {
  // Fake, local-only demo keys (see DEMO_PRINCIPALS in .env.example). Not real authentication.
  const DEMO_KEYS = [
    { key: "key-payments-eng", label: "Payments engineer" },
    { key: "key-payments-admin", label: "Payments admin" },
    { key: "key-platform-eng", label: "Platform engineer" },
    { key: "key-platform-admin", label: "Platform admin" },
  ];
  let currentKey = DEMO_KEYS[0].key;

  async function api(path, options = {}) {
    const headers = Object.assign({ "X-API-Key": currentKey }, options.headers || {});
    if (options.body && !headers["Content-Type"]) headers["Content-Type"] = "application/json";
    const res = await fetch(path, Object.assign({}, options, { headers }));
    if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
    return res.json();
  }

  function renderEvents(events) {
    const list = document.getElementById("timeline");
    list.innerHTML = "";
    for (const e of events) {
      const li = document.createElement("li");
      li.textContent = `${e.seq}. ${e.type}`;
      list.appendChild(li);
    }
  }

  function setupIdentity() {
    const select = document.getElementById("identity");
    for (const k of DEMO_KEYS) {
      const opt = document.createElement("option");
      opt.value = k.key;
      opt.textContent = `Acting as: ${k.label}`;
      select.appendChild(opt);
    }
    select.addEventListener("change", () => { currentKey = select.value; });
  }

  window.traceback = {
    api,
    currentKey: () => currentKey,
    showRun: (runId) => { console.log("TODO(P3-5): follow run", runId); },
    renderMemoryCard: (memory, context) => {
      // Replaced by web/memory.js (P2-4).
      const div = document.createElement("div");
      div.textContent = memory && memory.title ? memory.title : "(memory card)";
      return div;
    },
  };

  document.addEventListener("DOMContentLoaded", async () => {
    setupIdentity();
    const status = document.getElementById("status");
    try {
      const health = await (await fetch("/health")).json();
      const events = await (await fetch("/dev/sample-run-events")).json();
      renderEvents(events);
      status.textContent = `API ${health.status} · showing contracts/sample_run_events.json`;
    } catch (err) {
      status.textContent = `API not reachable: ${err}`;
    }
  });
})();
