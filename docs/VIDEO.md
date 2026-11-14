# The 1-minute submission video

Owner: P3 (Sepehr). Cut between 15:45 and 16:05, upload by 16:20, submit by 16:30 (PLAN 10).
The video must show **code and functionality**, run **60 seconds or less**, and have working audio.

Source material: the backup recordings from the 14:15 checkpoint (backup #1) and 15:30 (backup #2, with the voice agent). Record fresh only if both are bad.

---

## 1. Shot list

Screen at 1920x1080, page full screen at 100% zoom. Times are in the final cut.

| Time | Shot | Keys (when recording) | What the viewer sees | Words (see section 2) |
| --- | --- | --- | --- | --- |
| **0:00-0:07** | Title card, then the idle page | none | Name, tagline "Memory with receipts", then the page with the 3:04 a.m. line | Story |
| **0:07-0:18** | **Earn** | **1** (an Earn run already recorded) | Steps run, "Tests pass", the receipt prints in, **Proven** stamp | Earn |
| **0:18-0:34** | **Reuse** | **Shift+2** | "Seen before", "Both conditions still true (2/2)", the patch with the **`mark_replayed` line highlighted "from memory"**, badge **Verified on attempt 1** | Reuse |
| **0:34-0:40** | **Refuse** | **Shift+3** | "Not applied: duplicate key is `customer_id`", **Not applied** stamp | Refuse |
| **0:40-0:47** | **Fence** | **Shift+4** | Pill flips to Platform engineer. "Nothing your team may see." | Fence |
| **0:47-0:55** | **Forget** | **5**, click Forget, then **C** | Grey **Void** card, then the compare overlay: with memory vs after Forget | Forget |
| **0:55-1:00** | Repo | none | The GitHub repo page (public), or the end card with the repo URL | Built today |

Cut hard on the action. Speed up waiting (a live Reuse run takes 30-90 seconds; the final cut shows about 16 seconds of it) with a 4x-8x speed-up and a small "4x" label in the corner. Never speed up the highlighted line moment: hold it for 3 seconds.

**Optional, if time allows and R9 is merged:** a 5-second shot of the voice panel with the spoken result, placed in the Reuse shot. Drop it before dropping anything else on the list.

**Also show code.** The rules ask for "code and functionality". Put 3 seconds of `trusted_tests/test_webhooks.py` (the `test_replay_recorded_for_reconciliation` function) over the Reuse shot, as a picture-in-picture, or one 3-second cut to it. If there is no room, show the repo page at the end with the file tree visible.

---

## 2. Narration script (126 words, plain English, about 50 seconds at a calm pace)

Read in a normal voice. One breath per paragraph. Don't rush: silence is fine.

> **Story.** Dana fixed this webhook bug in March, then left the company. At 3 a.m. the same alert pages Sam. This is Traceback: memory with receipts. *(25)*
>
> **Earn.** A memory is earned only when a fix passes our tests. The proof is stored in MongoDB Atlas. *(18)*
>
> **Reuse.** In a new session, the agent recalls it and checks two conditions in code. This highlighted line comes from memory: Payments' own rule for recording replays. All tests pass on the first attempt. *(33)*
>
> **Refuse.** A look-alike bug with a different duplicate key? Not applied. *(10)*
>
> **Fence.** Platform asks the same question and sees nothing. The team filter runs inside the database search. *(16)*
>
> **Forget.** An admin forgets the memory for good. Rerun it, and the line is gone. *(14)*
>
> **Built today.** Everything you just saw was built today, at this hackathon. *(10)*

Check the count before recording (run in a terminal, paste the script into a file `narration.txt` first): `wc -w narration.txt`. **It must be 140 words or fewer.** Cut a sentence rather than talk faster.

**Say only what the recording shows.** If the compare shot is missing or the without-memory run did not lose the line, delete the sentence "Rerun it, and the line is gone." If the Fence or Refuse shot failed, delete that paragraph. A shorter true video beats a longer one that claims more than it shows.

---

## 3. What to record

| Item | Setting |
| --- | --- |
| Screen | 1920x1080, browser full screen (F11), zoom 100% |
| Tool | Windows: **Win+G** (Game Bar) record, or **OBS Studio** (Display Capture, 30 fps, MP4) |
| Audio | Headset mic. Record the narration **separately** after the screen takes, so you can read it clean |
| Mouse | Hide it, or keep it still. Use the keys. No cursor wandering |
| Notifications | Focus assist on. Close everything else |
| Start state | Run `uv run python scripts/demo_reset.py`, then follow `docs/DEMO.md` section 1.1 so Compare has two runs |
| Takes | 3 takes of the whole flow. Keep the best one. Name them `take1.mp4`, `take2.mp4`, `take3.mp4` |

Recording order (screen only, no voice):
1. Idle page, 3 seconds.
2. **1** (Earn). Hold on the **Proven** stamp for 2 seconds.
3. **Shift+2** (Reuse). Let it run to the badge. Hold on the highlighted line for 3 seconds.
4. **Shift+3** (Refuse). Hold on the stamp for 2 seconds.
5. **Shift+4** (Fence). Hold for 2 seconds.
6. **5**, click Forget, type a reason. Then **C**. Hold on the overlay for 3 seconds. **Esc**.

If live runs are not available, record with key **0** (the replay) and put the word "recorded" in the narration. Never present a replay as a live run.

---

## 4. How to edit

Use any simple editor (Clipchamp is built into Windows 11; CapCut or DaVinci Resolve also work).

1. **Start from the backups.** Take the clips from `backup-1415.mp4` (14:15) and the 15:30 backup. Cut one clip per beat from the shot list. Prefer the 15:30 recording where it is clean.
2. Put the clips in the order of the shot list. Trim the waiting; add a "4x" label where you speed up.
3. Add the title card (0:00-0:03) and the repo end card (last 5 seconds): "Traceback · Memory with receipts · github.com/YaCnDehfuli/TraceBack".
4. Record the narration in one go, into the editor's voice-over track. Slide the clips (not the voice) until the words match the screen: the highlighted line must be on screen when you say "highlighted".
5. Add captions (auto-captions, then fix the words "Traceback", "Atlas", "Dana", "Sam", "MongoDB").
6. Check the final length: **60 seconds or less** (59 is safer). Cut from Refuse first, then the speed-up clips.
7. Export: **MP4, H.264, 1920x1080, 30 fps**, stereo AAC audio. File size under 100 MB.

---

## 5. Export checklist

Tick every box before uploading.

- [ ] Length is 1:00 or less. (File properties, or the editor's timeline.)
- [ ] **Audio check:** play it once with headphones and once through laptop speakers. Voice is clear and louder than any music (use no music). No clipping.
- [ ] The words "built today" are spoken **and** the date or the repo link is visible at the end.
- [ ] The highlighted `mark_replayed` line is readable at normal size (not blurry).
- [ ] No secrets on screen: no `.env`, no API keys, no connection strings, no Atlas password. (Pause the video at each shot and look.)
- [ ] No notifications or personal tabs visible.
- [ ] Nothing is presented as live that is a replay.
- [ ] Upload to the place the submission form asks for (YouTube is fine). Set it to **Unlisted**, never Private.
- [ ] Open the **unlisted link in a private (incognito) window**: it plays without logging in, with sound.
- [ ] **Play it on another laptop** (a teammate's) over the venue Wi-Fi: it plays, audio works, text is readable.
- [ ] Paste the link in team chat. P1 and P2 each open it.
- [ ] Put the link into the Cerebral Valley submission draft. Submit by **16:30**; 16:45 is the latest. The deadline is 17:00.
- [ ] Screenshot the submission confirmation into team chat.
- [ ] Keep the video file and the raw recordings on the laptop until 20:00.
