// The practice company's "Payments · webhook receiver" page: the provider's deliveries against the
// code in production (before), then against the agent's verified fix (after).
// URL: live.html?case=B&run=run_xxx   Dev without the backend: add &mock=1.
// Backend: POST /api/replay {case, mode: "before"|"after", runId} (409 when the run has no verified fix).
(() => {
  "use strict";

  const params = new URLSearchParams(location.search);
  const CASE = (params.get("case") || "B").toUpperCase();
  const MOCK = params.get("mock") === "1";
  const RUN = params.get("run") || (MOCK ? "run_mock01" : null);
  const ROW_MS = 500;

  const REPORTS = {
    A: "Duplicate webhook crashes payments",
    B: "Notification endpoint returning 500s during a provider retry storm",
    B2: "Payment callbacks erroring after the provider re-sent an event",
    B3: "Posted payments rejected when the provider repeats a notification",
    C: "Second payment from the same customer fails with HTTP 500",
    D: "Gateway notification crashes on a redelivered event",
    P: "Duplicate webhook crashes payments",
  };

  const $ = (id) => document.getElementById(id);
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  const money = (cents) => (typeof cents === "number" ? "$" + (cents / 100).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : "—");
  const icons = () => { if (window.lucide) window.lucide.createIcons(); };

  const STATUS = { 200: "OK", 201: "Created", 202: "Accepted", 400: "Bad Request", 409: "Conflict", 422: "Unprocessable Entity", 500: "Internal Server Error", 502: "Bad Gateway", 503: "Service Unavailable" };

  // ---------- Mock data (?mock=1) ----------
  const MOCK_FILE = `"""Inbound payment notifications."""

from fastapi import APIRouter
from pydantic import BaseModel
from pymongo.errors import DuplicateKeyError

from . import ledger
from .db import get_db

router = APIRouter()


class PaymentNotification(BaseModel):
    id: str
    customer_id: str
    amount: int


@router.post("/webhooks/provider")
def handle_provider_event(notification: PaymentNotification) -> dict:
    payments = get_db().payments
    try:
        payments.insert_one(
            {
                "provider_event_id": notification.id,
                "customer_id": notification.customer_id,
                "amount": notification.amount,
            }
        )
    except DuplicateKeyError:
        # Already processed: don't credit again, record the replay for reconciliation.
        ledger.mark_replayed(notification.id)
        return {"ok": True, "duplicate": True}
    ledger.credit(notification.customer_id, notification.amount, notification.id)
    return {"ok": True}
`;
  const E11000 = 'E11000 duplicate key error collection: payments.payments index: provider_event_id_1 dup key: { provider_event_id: "evt_2001" }';
  const mockReply = (mode) => {
    const before = mode === "before";
    return {
      case: CASE, mode,
      code: before
        ? { source: "original", runId: null, attempt: null, verified: true, path: "app/webhooks.py", newContent: null, fromMemoryLines: [] }
        : { source: "agent-fix", runId: RUN, attempt: 1, verified: true, path: "app/webhooks.py", newContent: MOCK_FILE, fromMemoryLines: [30, 31, 32, 33] },
      deliveries: [
        { n: 1, eventId: "evt_2001", customerId: "cus_77", amount: 4000, status: 200, body: '{"ok":true}', error: null },
        before
          ? { n: 2, eventId: "evt_2001", customerId: "cus_77", amount: 4000, status: 500, body: "Internal Server Error", error: E11000 }
          : { n: 2, eventId: "evt_2001", customerId: "cus_77", amount: 4000, status: 200, body: '{"ok":true,"duplicate":true}', error: null },
      ],
      ledger: { customerId: "cus_77", credited: 4000, expectedCredit: 4000, paymentRows: 1, replaysRecorded: before ? 0 : 1 },
      verdict: before ? "crashed" : "ok",
      summary: before
        ? "The retried delivery hit the unique index and returned 500, so the provider keeps retrying."
        : "The retry was acknowledged with 200, the customer was credited once and the replay was recorded.",
    };
  };

  // ---------- API ----------
  async function replay(mode) {
    if (MOCK) { await sleep(350); return { ok: true, data: mockReply(mode) }; }
    let res;
    try {
      res = await fetch("/api/replay", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ case: CASE, mode, runId: mode === "after" ? RUN : null }),
      });
    } catch (e) {
      return { ok: false, kind: "network", message: "Could not reach the replay server (" + (e && e.message ? e.message : "network error") + ")." };
    }
    let body = null;
    try { body = await res.json(); } catch (_) { /* not JSON */ }
    if (res.status === 409) return { ok: false, kind: "nofix", message: (body && body.detail) || "This run has no verified fix." };
    if (!res.ok || !body) {
      const detail = body && body.detail ? (typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail)) : res.statusText;
      return { ok: false, kind: "http", message: "The replay server answered " + res.status + (detail ? ": " + detail : "") + "." };
    }
    if (!Array.isArray(body.deliveries)) return { ok: false, kind: "http", message: "The replay server sent an unexpected answer (no deliveries)." };
    return { ok: true, data: body };
  }

  // ---------- Rendering ----------
  function notice(el, icon, title, text, cls) {
    el.innerHTML = `<div class="notice ${cls || ""}"><i data-lucide="${icon}"></i><strong>${esc(title)}</strong>${text ? `<span>${text}</span>` : ""}</div>`;
    icons();
  }

  function shortError(err) {
    const s = String(err);
    if (/E11000/.test(s)) {
      const key = (s.match(/index:\s*([A-Za-z0-9_]+?)(?:_-?\d+)?\s+dup key/) || [])[1] || (s.match(/provider_event_id/) || [])[0];
      return "E11000 duplicate key error" + (key ? " … " + key : "");
    }
    return s.length > 90 ? s.slice(0, 88) + " …" : s;
  }

  function deliveryRow(d) {
    const li = document.createElement("li");
    li.innerHTML = `<div class="req"><span class="n">#${esc(d.n)}</span>→ POST /webhooks/provider · ${esc(d.eventId)} · ${money(d.amount)}</div>
      <div class="res pending">… waiting</div>`;
    return li;
  }
  function settleRow(li, d) {
    const good = d.status >= 200 && d.status < 300;
    const res = li.querySelector(".res");
    res.className = "res " + (good ? "ok" : "bad");
    res.textContent = `← ${d.status} ${STATUS[d.status] || ""}`.trim();
    if (d.error) {
      const e = document.createElement("div");
      e.className = "err"; e.title = d.error; e.textContent = shortError(d.error);
      li.appendChild(e);
    }
  }

  function codeView(code) {
    const text = code && code.newContent;
    if (!text) return null;
    const lines = text.replace(/\n$/, "").split("\n");
    let marks = (code.fromMemoryLines || []).map((x) => {
      if (typeof x === "number") return x;
      const want = String(x).trim();
      const i = lines.findIndex((l) => l.trim() === want && want);
      return i >= 0 ? i + 1 : null;
    }).filter((x) => Number.isInteger(x) && x >= 1 && x <= lines.length);
    const set = new Set(marks);
    let from, to;
    if (marks.length) { from = Math.max(1, Math.min(...marks) - 3); to = Math.min(lines.length, Math.max(...marks) + 3); }
    else { from = 1; to = Math.min(lines.length, 12); }
    const box = document.createElement("div");
    box.className = "code";
    const hl = (s) => (window.Prism && Prism.languages.python ? Prism.highlight(s, Prism.languages.python, "python") : esc(s));
    let rows = "";
    for (let n = from; n <= to; n++) {
      rows += `<div class="code-line${set.has(n) ? " mem" : ""}"><span class="ln">${n}</span><span class="src">${hl(lines[n - 1]) || " "}</span></div>`;
    }
    box.innerHTML = `<div class="code-head"><span>${esc(code.path || "patched file")}</span>${set.size ? '<span class="mem-tag">from memory</span>' : ""}</div><div class="code-lines">${rows}</div>`;
    return box;
  }

  function ledgerCard(l) {
    const credited = l.credited, expected = l.expectedCredit;
    const right = typeof credited === "number" && credited === expected;
    const replays = typeof l.replaysRecorded === "number" && l.replaysRecorded > 0;
    const div = document.createElement("div");
    div.className = "ledger";
    div.innerHTML = `
      <div>Customer ${esc(l.customerId)} credited <b class="${right ? "good" : "bad"}">${money(credited)}</b> (expected ${money(expected)})</div>
      <div>Payment rows <b>${esc(l.paymentRows ?? "—")}</b><span class="sep">·</span>Replay recorded for month-end: <b class="${replays ? "good" : "bad"}">${replays ? "yes" : "no"}</b></div>`;
    return div;
  }

  const VERDICTS = {
    crashed: { cls: "bad", icon: "octagon-x", text: "Crashed: the provider will keep retrying" },
    "double-credited": { cls: "warn", icon: "copy-x", text: "Double-credited: the customer was paid twice" },
    ok: { cls: "ok", icon: "circle-check-big", text: "Credited once" },
  };
  function verdictBanner(v, summary) {
    const m = VERDICTS[v] || { cls: "warn", icon: "circle-help", text: String(v || "Unknown result") };
    const div = document.createElement("div");
    div.className = "verdict " + m.cls;
    div.innerHTML = `<i data-lucide="${m.icon}"></i><div><div class="vt">${esc(m.text)}</div>${summary ? `<div class="vs">${esc(summary)}</div>` : ""}</div>`;
    return div;
  }

  async function play(el, data) {
    el.innerHTML = "";
    const code = codeView(data.code);
    if (code) el.appendChild(code);
    const log = document.createElement("ol");
    log.className = "log";
    el.insertBefore(log, el.firstChild);
    for (const d of data.deliveries) {
      const li = deliveryRow(d);
      log.appendChild(li);
      fitCode(el);
      await sleep(ROW_MS);
      settleRow(li, d);
      fitCode(el);
      await sleep(ROW_MS / 2);
    }
    { const sp = document.createElement("div"); sp.className = "spacer"; el.appendChild(sp); }
    if (data.ledger) { el.appendChild(ledgerCard(data.ledger)); fitCode(el); await sleep(ROW_MS); }
    el.appendChild(verdictBanner(data.verdict, data.summary));
    icons();
    fitCode(el);
  }

  function setAfterTitle(code) {
    const parts = [];
    if (RUN) parts.push(RUN);
    if (code && code.attempt != null) parts.push("attempt " + code.attempt);
    $("after-sub").textContent = parts.length ? parts.join(" · ") : "no run selected";
  }

  // Hide context lines (furthest from the memory lines first) until the code view fits its column.
  function fitCode(el) {
    const box = el.querySelector(".code-lines");
    if (!box) return;
    const rows = [...box.querySelectorAll(".code-line")];
    rows.forEach((r) => r.classList.remove("hid"));
    const memIdx = rows.map((r, i) => (r.classList.contains("mem") ? i : -1)).filter((i) => i >= 0);
    const lo = memIdx.length ? Math.min(...memIdx) : 0, hi = memIdx.length ? Math.max(...memIdx) : rows.length - 1;
    let top = 0, bottom = rows.length - 1, fromTop = memIdx.length ? true : false;
    while (box.scrollHeight > box.clientHeight + 1) {
      const canTop = top < lo, canBottom = bottom > hi;
      if (!canTop && !canBottom) break;
      if ((fromTop && canTop) || !canBottom) rows[top++].classList.add("hid");
      else rows[bottom--].classList.add("hid");
      fromTop = !fromTop;
    }
  }
  window.addEventListener("resize", () => { fitCode($("after-body")); fitCode($("before-body")); });

  function idle() {
    notice($("before-body"), "send", "Ready", "Press <b>Replay</b> (or Space) to send the provider's deliveries to the code in production.");
    if (!RUN) {
      notice($("after-body"), "play-circle", "Run Traceback first", "Run Traceback first (Shift+2 in the run view), then open this page from the run's link.");
    } else {
      notice($("after-body"), "shield-check", "Waiting for the before replay", "Then the same deliveries go to the agent's verified fix.");
    }
  }

  function failed(el, r) {
    if (r.kind === "nofix") notice(el, "shield-off", "This run has no verified fix", esc(r.message), "error");
    else notice(el, "wifi-off", "Replay failed", esc(r.message), "error");
  }

  let running = false;
  async function go() {
    if (running) return;
    running = true;
    const btn = $("replay");
    btn.disabled = true;
    try {
      const b = $("before-body"), a = $("after-body");
      notice(b, "loader", "Sending deliveries…", "");
      if (RUN) notice(a, "hourglass", "Next: the same deliveries against the fix", "");
      const rb = await replay("before");
      if (rb.ok) await play(b, rb.data); else failed(b, rb);
      if (!RUN) {
        notice(a, "play-circle", "Run Traceback first", "Run Traceback first (Shift+2 in the run view), then open this page from the run's link.");
        return;
      }
      await sleep(ROW_MS);
      notice(a, "loader", "Sending deliveries…", "");
      const ra = await replay("after");
      if (ra.ok) { setAfterTitle(ra.data.code); await play(a, ra.data); } else failed(a, ra);
    } catch (e) {
      notice($("after-body"), "triangle-alert", "Something went wrong", esc(e && e.message ? e.message : String(e)), "error");
    } finally {
      running = false;
      btn.disabled = false;
    }
  }

  // ---------- Boot ----------
  $("case-label").textContent = "Incident " + CASE + (MOCK ? " · mock" : "");
  $("case-report").textContent = REPORTS[CASE] || "Incident " + CASE;
  setAfterTitle(null);
  idle();
  $("replay").addEventListener("click", (e) => { e.currentTarget.blur(); go(); });
  document.addEventListener("keydown", (e) => {
    if ((e.key === " " || e.key === "Enter") && !e.repeat && !e.ctrlKey && !e.metaKey && !e.altKey) {
      e.preventDefault();
      go();
    }
  });
  icons();
})();
