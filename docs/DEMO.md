# Traceback: the presenter's runbook

For the live demo (about 3 minutes, from 5:15 PM) and for every rehearsal. Written for a stressed presenter: read the tables, not the paragraphs.

Plan references (PLAN 7.1, 7.2, 7.4) are in `docs/PLAN.md`. Where this file and the plan disagree on a key press, **this file wins** (it was written against `web/app.js`).

**Who:** P1 Yasin (agent, Reuse, Refuse, results) · P2 Elham (memory, Fence, Forget) · P3 Sepehr (Story, Earn, **drives the screen: all key presses are P3's**).

---

## 0. The keys (cut this out and tape it to the desk)

| Key | Beat | What it does |
| --- | --- | --- |
| **1** | Earn | Shows the last Earn run (case A). **Never starts a run** without Shift. |
| **Shift+1** | Earn | Starts a new Earn run (case A). Only before the session. |
| **2** | Reuse | Shows the Reuse run (case B) if one is running or started in the last 10 minutes. Otherwise starts one. |
| **Shift+2** | Reuse | **Always starts a fresh Reuse run.** Use this at 0:00. |
| **3** / **Shift+3** | Refuse | Same, for case C (look-alike bug). |
| **4** / **Shift+4** | Fence | Same, for case D. Switches the pill to **Platform engineer** by itself. |
| **5** | Forget | Switches the pill to **Payments admin** and scrolls to the memory card. The Forget button is on the card (P2's admin drawer). |
| **0** | Sample | Replays a recorded run (contracts/sample_run_events.json). Labelled **Replay**, never passed off as live. |
| **C** | Compare | Opens or closes the with/without memory overlay. **Esc** also closes it. |

Rules of thumb:
- A bare **1 / 2 / 3 / 4 is safe**: it re-shows a run, it can't create a memory by accident.
- **Shift is the "go live" key.** Hold it only when you mean it.
- Keys do nothing while a text box or the identity pill has focus. If a key seems dead, click on empty page space and press again.
- The bottom bar has the same keys as buttons. Clicking works too (Shift+click forces a fresh run).

---

## 1. Before each judging session (do it in this order)

| # | Do this | Done when |
| --- | --- | --- |
| 1 | `uv run python scripts/demo_reset.py` | Prints `Demo reset complete.` Three steps `ok`. If it says `FAILED: fixture database not reachable`, start MongoDB (README_P3: Windows note) and run it again. |
| 2 | `uv run python scripts/demo.py` (leave the window open, don't minimise) | Prints `Traceback: open http://127.0.0.1:8000`. |
| 3 | Open **exactly that address** in the browser. Always the same one: `127.0.0.1` and `localhost` are different sites to the browser and keep separate saved runs. | The page loads. Footer says **Connected**. |
| 4 | Full screen (**F11**). Browser zoom **100%** (**Ctrl+0**). Screen resolution 1920x1080. | Top bar and the bottom key bar are both visible, no scrollbars. |
| 5 | Identity pill reads **Acting as: Payments engineer**. Footer reads "Acting as Payments · engineer". | Pill and footer agree. |
| 6 | Press **0**. A replay plays in about 7 seconds. Then reload (**F5**) to clear it. | The replay works: this proves the page and API are fine even if Wi-Fi dies. |
| 7 | Prepare the saved runs (section 1.1). | Keys **1** and **C** both work. |
| 8 | Headset mic on, set as the default input. Say one test sentence. Speaker volume at a level the judges can hear. | The voice panel hears you (if R9 is merged). |
| 9 | Windows: Focus assist on (no notification pop-ups). Close Slack, Discord, mail. Charger plugged in. | Nothing else on screen. |
| 10 | Put the results slide and the title slide in a second window. | One click or Alt+Tab to reach them. |

**Wi-Fi independence, stated honestly.** The page itself needs no internet: fonts, icons, code highlighting and CSS are all in `web/vendor/` and the page loads nothing from a CDN. So the screen, the replay (**0**) and every saved run keep working with no Wi-Fi. **Live runs do need the network** (Atlas, Voyage embeddings, the LLM, ElevenLabs). Venue Wi-Fi is `TRBOT-Guest`. If it is slow, run the live parts earlier and show saved runs with the bare keys.

### 1.1 Prepare the saved runs (after the reset, about 5 minutes)

The page keeps finished runs in the browser (localStorage), so **Compare (C)** works with two earlier runs. Reload does not lose them. A reset does **not** clear them, so after a reset do this order:

1. **Shift+1**: Earn run (case A). Wait for "Verified on attempt 1" and the **Proven** stamp.
2. **Shift+2**: Reuse run (case B), with memory. Wait until finished.
3. **5**, then **Forget** the memory on the card (as Payments admin), with a reason.
4. **Shift+2** again: Reuse run (case B), now without memory. Wait until finished. (It should earn a new memory, so the Reuse beat finds one later.)
5. **C**: the overlay should show two columns, "With memory" and "After Forget". **Esc**.
6. **1**: shows the Earn run. **2**: shows the latest Reuse run. Put the page on the idle state (reload, F5).

Expect the Earn card (key **1**) to look thinner after this: its memory was forgotten in step 3, so the page falls back to a plain receipt built from the run itself. That is normal.

If Compare says "Compare needs two finished runs of this case", you skipped step 2 or 4.

---

## 2. The three-minute script

All key presses are Sepehr's. **Bold** = say it word for word.

| Time | Beat | Who speaks | Keys | What appears | Key line | If it fails |
| --- | --- | --- | --- | --- | --- | --- |
| **0:00-0:20** | **Story** | P3 | Voice (R9): Sam says *"Payments webhooks are crashing with duplicate key errors."* Without voice: say the line yourself and press **Shift+2** (starts the live Reuse run). | Reuse run starts: "Run started for Payments", steps appear one by one, the "Live" chip. The run keeps going while you talk. | **"Dana fixed this in March and left in June. At 3 a.m. the same alert pages Sam. Memory with receipts."** | Voice silent: press **Shift+2** and go on. The voice agent is a bonus, never a dependency. |
| **0:20-0:40** | **Earn** (already run) | P3 | **1** (shows the Earn run). Optional, R11: the poisoned-log run (see 2.1). | The Earn run: the memory receipt prints in, stamped **Proven**. Poisoned run: step "Memory refused", stamp **Refused**. | **"Only a fix proven by tests becomes memory. Even a log that tells the agent to remember a bad fix gets refused by the database itself."** | Footer or answer says "No Earn run on record yet": press **0** and say **"this is a recording of the same flow."** Say the poisoned-log sentence only if you showed it. |
| **0:40-1:15** | **Reuse** (live since 0:00) | P1 | **2** (re-shows the live run, so the screen is on Reuse for P1's turn). Do not press Shift here. | Within seconds: "Seen before: Payments fixed this, and its conditions still hold." Step "Both conditions still true (2/2)". The patch with the **`ledger.mark_replayed` line highlighted "from memory · proven by test_replay_recorded_for_reconciliation"**. "Tests 6/6 pass" (the trusted suite has 6 tests; the **0** replay shows 7/7). Say "all tests pass", never a number. Badge **Verified on attempt 1**. | **"The model knows the generic fix. Only memory knows our team's rule."** (point at the highlighted line) | Still running at 1:15: keep talking, the screen keeps filling. Run errored or "Live runs unavailable": press **0**, say **"recorded run of the same flow"**. Wrong screen: press **2**. |
| **1:15-1:35** | **Refuse** | P1 | **Shift+3** (or **3** if you ran it in the last 10 minutes) | Steps show "Not applied: duplicate key is `customer_id`; this memory requires `provider_event_id`", the line "Memory requires `provider_event_id` ≠ This incident: `customer_id`", receipt greys out under a **Not applied** stamp. Badge "Escalated to a human, with evidence". | **"Similar isn't enough. Evidence decides."** | Press **3** (re-shows a recent run). Still nothing: press **0** and move on to Fence. Cut this beat if over time. |
| **1:35-2:00** | **Fence** | P2 | **Shift+4**: the pill flips to **Platform engineer** and a Platform run starts. Voice (R9): P2 says *"I'm on Payments, show me their webhook fix."* | Step "Nothing your team may see". Answer: "Not seen before by your team. Investigating from scratch." Memory area: "Nothing your team may see." Voice agent (R9): "Your team has no memories for this." If the Fence view is merged: "Payments sees 1 / Platform sees 0" with the filter line. | **"You can't talk your way past it. The team filter runs inside the database search."** | Press **4** (re-shows a recent run). Or just use the pill: pick **Acting as: Platform engineer**; the memory area shows the Platform team's own list only. |
| **2:00-2:40** | **Forget** | P2 | **5** (pill goes to **Payments admin**, page scrolls to the card). Then **a judge clicks Forget** on the card and types a reason. Then **C**. | The card turns into a grey dashed "Forgotten by Payments admin · reason · content erased" with a **Void** stamp. Compare overlay: **With memory** (attempt 1, the `mark_replayed` line shown) and **After Forget** (the same line missing, empty rows). | **"Forgetting is real, and this shows the memory caused the improvement."** | Forget button not responding: press **C** anyway and say **"forget is one admin call; here is what the rerun looked like after it."** Compare empty: redo section 1.1 after the session. Close with **Esc**. |
| **2:40-3:00** | **Receipts** | P1 | Alt+Tab to the results slide. | The slide: 9 runs, raw counts. | Read the real numbers, whatever they are. | No slide: say **"nine runs, raw counts are in the README"** and stop. Never invent a number. |

**Timing rules:**
- Shift+2 at 0:00, never later: the live run needs 30-90 seconds.
- For Forget, use the compare overlay from the earlier runs (section 1.1). Do not wait for a live rerun.
- If you are 15 seconds behind at 1:15, **drop Refuse**. Cut beats, never words that carry the story.
- Staleness (R12) is for Q&A only. Do not demo it in the 3 minutes.
- After the session, run section 1 again before the next judges.

### 2.1 The poisoned-log run (R11, case P)

There is **no key for case P** in the page. Two ways:
- **Console (rehearsal only):** press F12, type `traceback.startCase("P")`, press Enter, close F12. Fine for testing, too slow and risky on stage.
- **Bookmark (recommended for the demo):** make a bookmark on the bookmarks bar named "Poisoned", with the address `javascript:traceback.startCase('P')`. One click starts the run. Test it at rehearsal; some browsers block `javascript:` bookmarks.

The run starts live and takes about as long as Earn. Start it **just before 0:20** (while P3 tells the story), or leave it out. If it does not work, leave the poisoned log out and say nothing about it.

---

## 3. What to demo for each stopping point (PLAN 7.1, adapted to the keys)

Find the last rung that is merged to `main` and works. Demo that row, nothing more.

| Last rung | What to show (3 minutes) | Keys and fallbacks |
| --- | --- | --- |
| **R1-R2** (no UI yet) | Story. Then a terminal: Earn, Reuse, Fence (Payments finds 1, Platform finds 0). Show the Atlas Data Explorer: the memory and the audit log. | `uv run python scripts/skeleton.py`, then Atlas Data Explorer. Nothing here uses the page. |
| **R3-R4** | Story, Earn, Reuse **on screen**, Fence. | **1**, **Shift+2**, **Shift+4**. Live runs need the agent (P1-2/P1-4). Without it the page says "Press 0 to replay a recorded run": use **0** and say "recorded". |
| **R5** (**minimum complete demo**) | + Forget with the compare view. | Add **5** (Forget button) and **C**. Prepare the saved runs (1.1). |
| **R6-R8** | The full script above. Start Reuse with **Shift+2** (not voice). Do Fence with **Shift+4** or the identity pill. Show Correction (R7) from the admin drawer, or keep it for Q&A. | As the script. Voice lines are said by a person. |
| **R9-R12** | The full script with the voice agent (R9), the results slide (R10), the poisoned log in Earn (R11, section 2.1). Staleness (R12) for Q&A. | As the script. Voice is the first thing to drop if the room is loud. |

---

## 4. Judge Q&A cheat sheet

Two minutes per judge group. Short answers first, then stop. The owner answers; the others stay quiet unless asked.

| Question | Answer (say this) | Who |
| --- | --- | --- |
| **What exactly did you build today?** | Everything in the repo. Every commit is from today, by the three of us. The only thing from before is the open-source tools it stands on: FastAPI, pytest, MongoDB. | P1 |
| **Is this just a dashboard?** | No. There is one run view and no charts. It is a receipt for one investigation. The product is the agent plus governed memory. The screen only shows the proof. | P3 |
| **Why vector search with so few memories?** | The seeded set has about 20 labelled distractors across two teams, plus a score cutoff. In production it is thousands. Vectors find candidates when the wording differs, as with our retry-storm report that never says "duplicate". Conditions then decide in code whether to apply one. | P2 |
| **Why vectors at all, not keywords?** | People describe the same bug differently each time. Case B never uses the words in case A. Vectors find the candidate; plain code checks it applies. | P2 |
| **Isn't the convention test rigged?** | The convention is in the app's own runbook, deep in the reconciliation section. The no-memory agent can find it; it just takes more attempts. That is exactly the knowledge memory saves. | P1 |
| **What stops a poisoned memory?** | Only test-verified fixes can be written, and the database validator enforces it, not our code. You just saw it refuse one. | P2 |
| **Does ElevenLabs end up holding your memories?** | No. The voice agent's tools return run facts and memory metadata only, never memory text. Retention is set to the minimum. | P1 |
| **Can someone talk their way into another team's memory?** | No. Identity comes from the session's key, what you say is ignored, and the team filter runs inside the database search. | P1 |
| **What if the code changes?** | Each memory stores fingerprints of the files it touched. A change marks it stale, and its fix must pass the tests again. (Say this only if R12 is merged; otherwise say "that is on our list".) | P2 |
| **How do you know the fix is right?** | Trusted tests we wrote, outside anything the agent can change. The runner copies the practice app to a temp folder, replaces one allowed file, runs the tests in a separate process with no secrets. If our infrastructure breaks the result is "inconclusive", never "pass". | P3 |
| **Is the incident real?** | No. Synthetic incidents on two small practice apps. The bug is real MongoDB E11000, the tests really run. The README says so. | P3 |
| **Is the login real?** | No. Four fake demo keys in `.env`. They show how identity flows, not real authentication. | P1 |
| **What did the placebo experiment show?** | Read the actual table. Do not round up. If a number is bad, say so. | P1 |
| **What would you do next?** | Revoke and sharing between teams, more bug families, a real login. | P2 |

---

## 5. Rehearsal checklist (14:15 checkpoint, then again before 17:15)

Time every step. Use a phone timer. Run it **twice**.

- [ ] Section 1 (reset, start, full screen, zoom 100%) done from a cold start in under 3 minutes.
- [ ] Section 1.1 (saved runs) done once; **C** shows two columns.
- [ ] Press **0** with Wi-Fi switched off: the replay still plays. Switch Wi-Fi back on.
- [ ] Full script run once with a timer. Over 3:00? Cut a beat, not words.
- [ ] Each fallback in the table tried once (voice off, **0**, bare keys, pill).
- [ ] Shift+2 at 0:00 gives a finished run inside 90 seconds on the venue Wi-Fi. Write the time down: ______ s.
- [ ] A **judge clicks Forget**: P2 told them exactly where the button is. Reason text typed and accepted.
- [ ] Headset mic tested in the actual room, with the room noise on.
- [ ] Slides open: title slide (name, tagline, team) and the results slide with real numbers.
- [ ] **Record backup video #1** of the whole run (screen at 1920x1080, mic on). Save as `backup-1415.mp4`. See `docs/VIDEO.md`.
- [ ] Everyone knows who answers which question (section 4).
- [ ] Phone hotspot ready as a Wi-Fi backup.

If anything fails twice, write it in team chat now and decide: fix, or drop that rung from the demo.

---

## 6. Honest limits (don't oversell)

- The incidents are synthetic, on two small practice apps. The bug is real, the tests really run.
- The four API keys are fake demo identities, not real authentication.
- Seeded distractors are labelled `seeded` in the UI and the README.
- Live runs need Atlas, Voyage, the LLM and (for voice) ElevenLabs over the network. Saved runs and the replay (key **0**) do not.
- The replay (**0**) is a recording and the page says **Replay**. Always say "recorded" out loud when you use it.
