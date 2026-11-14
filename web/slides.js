/* Traceback demo deck: navigation, fullscreen, and the results slide (reads evals/results/results.md if it can).
   Keys: Right / Space / PageDown next, Left / PageUp back, Home / End, 1-6 jump, F fullscreen. */
(function () {
  "use strict";

  const slides = Array.from(document.querySelectorAll(".slide"));
  const counter = document.getElementById("counter");
  const dots = document.getElementById("dots");
  let index = 0;

  slides.forEach((s, i) => {
    const b = document.createElement("button");
    b.type = "button";
    b.setAttribute("aria-label", `Slide ${i + 1}: ${s.dataset.title}`);
    b.addEventListener("click", () => go(i));
    dots.appendChild(b);
  });

  function go(n) {
    n = Math.max(0, Math.min(slides.length - 1, n));
    const first = !slides.some((s) => s.classList.contains("active"));
    if (n === index && !first) return;
    slides.forEach((s, i) => {
      s.classList.toggle("active", i === n);
      s.classList.toggle("before", i < n);
      s.setAttribute("aria-hidden", i === n ? "false" : "true");
    });
    index = n;
    counter.textContent = `${n + 1} / ${slides.length}`;
    Array.from(dots.children).forEach((d, i) => d.setAttribute("aria-current", i === n ? "true" : "false"));
    if (history.replaceState) history.replaceState(null, "", "#" + (n + 1));
    if (slides[n].classList.contains("s-results")) loadResults();
  }

  function toggleFullscreen() {
    if (document.fullscreenElement) document.exitFullscreen();
    else if (document.documentElement.requestFullscreen) document.documentElement.requestFullscreen().catch(() => {});
  }

  document.addEventListener("keydown", (e) => {
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    const k = e.key;
    if (k === "ArrowRight" || k === " " || k === "PageDown" || k === "Enter") go(index + 1);
    else if (k === "ArrowLeft" || k === "PageUp" || k === "Backspace") go(index - 1);
    else if (k === "Home") go(0);
    else if (k === "End") go(slides.length - 1);
    else if (k === "f" || k === "F") toggleFullscreen();
    else if (/^[1-9]$/.test(k) && +k <= slides.length) go(+k - 1);
    else return;
    e.preventDefault();
  });

  // Hide the mouse cursor on the projector after a moment of stillness.
  let idleTimer;
  function wake() {
    document.body.classList.remove("idle");
    clearTimeout(idleTimer);
    idleTimer = setTimeout(() => document.body.classList.add("idle"), 2500);
  }
  document.addEventListener("mousemove", wake);
  wake();

  /* ---------------------------------------------------------------- results slide
     The deck is served from web/, so evals/results/results.md is only reachable if the server exposes it or
     a copy sits at web/results.md. Anything else (or a file that is not a markdown table) shows the placeholder.
     We never fill in numbers ourselves: we only render what the file says. */

  const RESULT_URLS = ["evals/results/results.md", "results.md"];
  let loadedText = null;

  async function fetchResults() {
    for (const url of RESULT_URLS) {
      try {
        const r = await fetch(url, { cache: "no-store" });
        if (!r.ok) continue;
        const t = await r.text();
        if (/^\s*</.test(t) || !/^\s*\|.*\|\s*$/m.test(t)) continue; // HTML fallback page, or no table in it
        return { text: t, url };
      } catch (e) { /* offline, file://: placeholder */ }
    }
    return null;
  }

  async function loadResults() {
    const got = await fetchResults();
    if (!got || got.text === loadedText) return;
    loadedText = got.text;
    document.getElementById("results-md").innerHTML = markdown(got.text);
    document.getElementById("results-src").textContent = got.url === "results.md" ? "evals/results/results.md (copy)" : got.url;
    document.getElementById("results-live").hidden = false;
    document.getElementById("results-placeholder").hidden = true;
    if (window.lucide) window.lucide.createIcons();
  }

  const esc = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const inline = (s) => esc(s).replace(/`([^`]+)`/g, "<code>$1</code>").replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>");
  const cells = (row) => row.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((c) => c.trim());

  function markdown(src) {
    const lines = src.replace(/\r/g, "").split("\n");
    const out = [];
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      if (!line.trim()) continue;
      const h = line.match(/^(#{1,3})\s+(.*)/);
      if (h) { out.push(`<h${h[1].length}>${inline(h[2])}</h${h[1].length}>`); continue; }
      if (/^\s*\|/.test(line)) {
        const rows = [];
        while (i < lines.length && /^\s*\|/.test(lines[i])) rows.push(lines[i++]);
        i--;
        const body = rows.filter((r) => !/^\s*\|[\s:|-]+\|\s*$/.test(r)).map(cells);
        const head = body.shift() || [];
        out.push("<table><thead><tr>" + head.map((c) => `<th>${inline(c)}</th>`).join("") + "</tr></thead><tbody>" +
          body.map((r) => "<tr>" + r.map((c) => `<td>${inline(c)}</td>`).join("") + "</tr>").join("") + "</tbody></table>");
        continue;
      }
      if (/^\s*[-*]\s+/.test(line)) {
        const items = [];
        while (i < lines.length && /^\s*[-*]\s+/.test(lines[i])) items.push(lines[i++].replace(/^\s*[-*]\s+/, ""));
        i--;
        out.push("<ul>" + items.map((t) => `<li>${inline(t)}</li>`).join("") + "</ul>");
        continue;
      }
      out.push(`<p>${inline(line)}</p>`);
    }
    return out.join("");
  }

  if (window.lucide) window.lucide.createIcons();
  const start = parseInt((location.hash || "").slice(1), 10);
  go(start >= 1 && start <= slides.length ? start - 1 : 0);
  loadResults(); // preload, so the slide is ready when we get there
})();
