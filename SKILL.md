---
name: stockdeck
description: Generate a NotebookLM slide deck AND a Hindi audio overview for Indian stock quarterly results. Triggers two Gemini Gems (PPT + Audio) to produce custom prompts, then drives NotebookLM (via Playwright MCP) using ONE PERSISTENT NOTEBOOK PER TICKER — adding the new quarter's sources (never deleting), then generating both a Slide Deck and a Hindi Audio Overview, verifying each actually started. Use when the user wants a stock results deck (e.g. "/stockdeck RELIANCE Q4 FY26", "make a deck for TCS Q4 FY26", or any request that combines a ticker with a fiscal quarter and asks for slides/presentation/deck/audio).
---

# stockdeck

Automated workflow for producing a NotebookLM **slide deck + Hindi audio overview** on Indian stock quarterly results. Driven entirely by the **Playwright MCP** (`mcp__mcp__browser_*` tools) — NOT the Claude in Chrome MCP, which has a server-side block on `notebooklm.google.com` that cannot be overridden.

## Architecture (read first — this changed in 2026-05)

- **ONE PERSISTENT NOTEBOOK PER TICKER.** Each ticker has its own NotebookLM notebook, stored in the local DB (`notebook_id` column). On the first run for a ticker we **create** the notebook; on every later run we **reuse** it. We **never delete sources** — each quarter's sources are **added**, so the notebook accumulates a multi-quarter history that NotebookLM can correlate (YoY / QoQ).
- **No source wipe.** The old single-shared-notebook + wipe-between-tickers flow is retired (it caused cross-contamination when a wipe partially failed). There is nothing to delete.
- **Quarter-scoping is mandatory.** Because the notebook holds several quarters of sources, every generation prompt MUST explicitly focus on the **target quarter** and use prior-quarter sources only for trend/correlation. (The Gem prompts already name the quarter; keep it.)
- **Verify generation actually started.** PPT/audio generation sometimes fails silently (quota, transient errors). After clicking Generate we VERIFY and RETRY ONCE before recording success. Only mark the ticker done in the DB after both deck and audio are confirmed queued.
- **Prompt generation stays dynamic.** The two Gems generate fresh, search-grounded prompts every run (do NOT replace with a static template). To keep Claude's context small, transfer each Gem response via **clipboard** (see Clipboard transfer). NOTE: `browser_evaluate`'s `filename` param saves the function's **return value**, NOT the page text — so it only archives the prompt body if you *return* the body (which leaks it into context). Don't use `filename` to archive prompts; the clipboard is the real transfer and the file fallback is not worth the context cost.

## Field-tested fixes (2026-05-24 — every one cost real time to learn; obey them)

1. **Playwright MCP `--output-dir` must NOT be the drive root.** If it's `B:\`, every `browser_navigate` tries to write `B:\page-*.yml` and the sandbox denies it ("outside allowed roots"), blocking ALL navigation. Set `--output-dir` to a real subdir like `<project-root>` in `claude_desktop_config.json`, then restart the Claude app.
2. **Launching Deep Research: fill, then CLICK the Submit arrow — never press Enter.** Enter routes the text to the chat box (or is lost) and silently does nothing for source discovery. After selecting Deep Research and filling the research `<textarea>` via the native value-setter + `input` event, the research **Submit** button (`aria-label="Submit"`) enables after a short async tick. There are TWO `aria-label="Submit"` buttons: the **research** one sits near the box (top ≈236px), the **chat** one is lower (top ≈431px) and is disabled when chat is empty. Click the enabled Submit nearest the top. If none is enabled yet, re-check once (Angular lag) — do not click the disabled one.
3. **Detecting DR progress: NEVER match the bare word "research".** "Deep Research" lives permanently in the mode dropdown, so `/research/` is always true → false "still running" reads (cost a wasted 12-min wait). Real signals: a button with `aria-label="Stop"` = running; the stage label cycles **Planning… → Researching Websites… → Analyzing Results…**; **completion = Stop button gone AND an Import button present** (text `Import` / `add Import`). Click Import; source count jumps (~25–32). A quick `browser_take_screenshot` (an image, allowed — it's not `browser_snapshot`) is the fastest way to disambiguate a stuck vs advancing state.
4. **Deep Research takes ~24–32 min per ticker** (not "a few minutes"). Poll in ≤270s windows (240s is good — keeps the prompt cache warm). A daily run realistically finishes ~3 tickers; that's expected.
5. **Customize dialogs contain THREE textareas — target by placeholder, never `querySelector('textarea')`** (that grabs the off-screen research box). Slide Deck outline = placeholder matches `/outline/`; Audio = matches `/things to try|focus on/`. Click+focus that specific textarea, `Control+V`, then VERIFY `value.length>0`. These fields **cap at 5000 chars** (a longer pasted prompt truncates to 5000 — acceptable; put the quarter-scope instruction early in the Gem prompt).
6. **Gem fill and send must be SEPARATE `browser_evaluate` calls.** Doing `insertText` then `Send.click()` in one evaluate races — an empty message sends and the Gem replies "you haven't specified a company". Fill in one call, Send in the next. Adding the full name in the prompt (e.g. `BLUESTARCO (Blue Star Limited)`) further hardens it.
7. **The OS clipboard persists across `browser_navigate` and 30+ min waits.** Copy the PPT body, run the whole Deep-Research + deck flow, and it's still there to paste. Same for the audio body. One ticker = copy PPT → (notebook/DR/deck) → copy audio → audio. No need to re-copy unless a paste verifies empty.
8. **New-notebook auto-naming is fine — skip the rename.** NotebookLM auto-titles the notebook from the Deep Research report (e.g. "Blue Star Limited FY26 … Report"); that's descriptive enough. Renaming needs Angular-aware events and isn't worth the tokens. The `notebook_id` saved to the DB is what matters for reuse.
9. **Auto-check re-runs: skip the screener detection sweep if a READY list already exists this session.** 42 WebFetches (whole pages → prose) is the biggest token sink and is pure waste when the ready tickers are already known. If you must detect, ask WebFetch for a one-word `READY`/`none`, not a prose row dump.
10. **The `textarea_gone` paste failure (2026-06-06).** When the Customize Slide Deck `<textarea>` is queried before Angular renders it (or after it dismisses), the verify read returns the string `"textarea_gone"`, which got written to the `_ppt.txt` archive AND the flow continued to Generate on an empty prompt → NotebookLM's generic default deck, still marked `done`. **Confirmed bad by this:** THOMASCOOK (its newest artifacts are generic-market decks "Market Outlook / Macro Volatility / Strategic Market Intelligence", 54 contaminated sources, and English off-topic audios "Semaglutide Patent Cliffs"). Guarded now in §1/§4: a deck whose textarea did not verify `>= 50` chars MUST be marked `failed`, never `done`.
11. **Do NOT use `_ppt.txt` archive presence as a deck-quality signal (2026-06-07 — corrected; the earlier note over-flagged).** Archiving the PPT body to file was *optional* until 2026-06-07, so a **missing `*_ppt.txt` is NOT evidence of a bad deck** — most runs without an archive produced perfectly good decks. A full audit of the 16 "no-archive" notebooks found only THOMASCOOK genuinely bad; 9 tickers wrongly re-flagged on the missing-archive theory (TRENT, BBOX, HBLENGINE, MOSCHIP, ORIENTPPR, POLYPLEX, SAFARI, TMCV, UJJIVANSFB) all had correct company-specific decks + Hindi audio and were restored to `done`. **The ONLY authoritative quality signal is the notebook's own Studio artifacts**, readable in one `browser_evaluate` (no viewer needed): enumerate saved artifacts (they carry `more_vert`; generator rows carry `chevron_forward`). **GOOD** = a Slide Deck titled company+quarter-specifically (the institutional prompt yields words like *Forensic / Teardown / X-Ray / Diagnostic / Strategic Review*) AND a Hindi Deep-Dive audio (Devanagari title, tag `Deep Dive`), with ~10–35 sources. **BAD** = generic-market deck titles + **English** audio (tag `waving_hand`, e.g. about oil/pharma) + 50+ sources (Deep Research pulled in generic "HSIE Results Daily" market newsletters). Source contamination (50+) is the real root cause of bad decks, not the paste.
12. **Hindi audio silently coming out in English (2026-06-07).** Separate, lower-severity failure seen on later runs (TATACOMM, TIPSMUSIC, TITAGARH): the deck is fine but the Audio Overview generated in **English** (tag `waving_hand`, English title) — the हिन्दी `mat-select` choice didn't stick before Generate. §5 already says to re-read the select and confirm हिन्दी; treat a non-Devanagari audio title as a failed language selection and regenerate the audio.
13. **Deep Research silently falling back to Fast Research → only 10 sources (2026-06-07 — the real "shallow deck" cause; likely what makes some decks feel thinner than EIDPARRY).** On a cluster of Jun-1 and Jun-5 runs the Discover dropdown switch to "Deep Research" did not take, so NotebookLM ran **Fast Research**, which caps at **exactly 10 web links and creates NO `Deep Research Report` source**. The decks still come out company-specific and pass every artifact check — they're just built on ~10 articles instead of Deep Research's 25–50, so they're **correct but shallow**. 13 notebooks were affected (TRENT, HBLENGINE, MOSCHIP, ORIENTPPR, POLYPLEX, SAFARI, TMCV, UJJIVANSFB, METROBRAND, NH, POLYMED, REDTAPE, ROSSARI); EIDPARRY/APTUS/etc. used real Deep Research (25–56 sources + the report artifact). **Tell:** source count is a flat **10** and `Deep Research Report` is absent. **Now guarded in §3** — verify the dropdown reads "Deep Research" before searching, and after Import assert sources ≥20 AND a `Deep Research Report` source exists; a flat-10 result means re-run in Deep Research mode. Audit lesson: when judging deck quality, also check **source count** — a company-specific deck on only 10 sources is a shallow (Fast Research) deck, not a full one.

## Inputs

Parse the invocation as: `TICKER[,TICKER...] Q<n> FY<yy>`. Also accept shorthand `Q<n>Y<yy>` (e.g. `KSB Q4Y26` → Q4 FY26). If ambiguous, ask once.

## Local state (DB helper)

Run with the project Python:
`python "<project-root>\stockwatch\db.py" <cmd>`
- `get-notebook <TICKER>` → prints the ticker's notebook id (empty if none yet).
- `set-notebook <TICKER> <ID>` → store the notebook id after creating one.
- `mark <TICKER> done|failed` → record outcome for the current quarter.
Captured Gem prompts are written to `<project-root>\stockwatch\prompts\<TICKER>_<Q>_ppt.txt` and `_audio.txt` (so a retry can skip the Gem step).

## Fixed resources

- **PPT Gem**: `https://gemini.google.com/gem/<YOUR_PPT_GEM_ID>` ("Meta-promptLM PPT")
- **Audio Gem**: `https://gemini.google.com/gem/<YOUR_AUDIO_GEM_ID>` ("Meta-promptLM - Audio")
- **Google account**: `<your-google-account>` (already signed into the Playwright Chromium profile at `<playwright-profile-dir>`)
- **Audio language**: always **हिन्दी (Hindi)** — non-negotiable. Verify the selection before Generate.
- **Gem mode**: keep the Gems on fast Google-Search grounding. If a **"Deep research"** chip is active on the composer, REMOVE it first (click its ✕) — Deep Research inserts a multi-minute "confirm plan" step that breaks polling.

## Performance principles (every rule is load-bearing)

- **NEVER call `browser_snapshot`** on NotebookLM or Gemini — the DOM is huge. Use `browser_evaluate` for every query.
- **NEVER enumerate all buttons.** Filter immediately by **exact** `aria-label`. (Substring matching on "add" once matched the **"Create notebook"** button and created a stray empty notebook — match `aria-label === 'Add source'`, not `includes('add')`.)
- **Two different editors — do NOT confuse them:**
  - **Gemini Gem composer = a Quill `.ql-editor` contenteditable `<div>`.** The `HTMLTextAreaElement` value-setter throws *"Illegal invocation"* and `innerHTML` is blocked by TrustedHTML. Fill it with `el.focus(); document.execCommand('selectAll'); document.execCommand('insertText', false, text)`.
  - **NotebookLM Customize dialog = a real `<textarea>`.** The native value-setter works there — but prefer the **clipboard paste** path below so the prompt never enters Claude's context.
- **NEVER pull the Gem prompt body into Claude's context.** A Gem response is 20–30 KB; reading it (×2 per ticker) is the single biggest token leak. Keep it in the browser: extract it in-page, copy to clipboard, paste into NotebookLM. Only ever read the one-line `STOCK_NAME`.
- **Return minimal data from `browser_evaluate`** — counts/booleans/short strings, not page `innerText` dumps. (The tool echoes your function source back too, so keep functions short.)
- **Save big Gem outputs to a file** via the `filename` param. The Playwright MCP now runs with `--output-dir B:\`, so absolute `B:\...` filenames are allowed (after the app restart that applied this). Pass an absolute B: path; do not echo the text.
- **Poll, don't sleep blindly.** And require generation to be *confirmed*, not assumed.

### Clipboard transfer (full prompt, zero context cost)
To move a full Gem prompt from the Gemini tab to NotebookLM without context bloat. Use **trusted key events** (`browser_press_key`) for copy/paste — `document.execCommand('copy')` often returns false in automation because it needs a user gesture; a real `Control+C` keystroke does not.
1. **In the Gemini tab**, after the response is complete, run one `browser_evaluate` that: locates the response text, slices out the prompt body (after `NOTEBOOKLM_PROMPT:` / `NOTEBOOKLM_AUDIO_PROMPT:`, stopping before "Gemini is AI"), creates a hidden `<textarea>` with that body appended to `document.body`, and calls `ta.focus(); ta.select();`. Return only `STOCK_NAME` + the body length — never the body. **ALWAYS pass `filename` to archive the full body to `B:\...\prompts\<TICKER>_<Q>_ppt.txt` (resp. `_audio.txt`) — this is mandatory, not optional.** The archive is the fallback the §4/§5 paste depends on, and its presence (with a real char count) is how a later audit confirms the PPT prompt was actually captured. A run where the PPT file is **missing** means this step silently failed and the deck got NotebookLM's default template — the exact cause of the bad recent decks.
   **Guard the slice:** if the body length is `< 200` or the body still contains the literal `<the prompt to paste...>` placeholder (i.e. the Gem echoed the template instead of generating), the Gem did not produce a real prompt — **re-submit the Gem once**; if it fails again, record `failed` and skip this ticker rather than pasting garbage.
2. `browser_press_key` **`Control+C`** (copies the selection via the real clipboard). **Confirm the copy** by reading `navigator.clipboard.readText().then(t => t.length)` (or re-select+re-copy if it reads empty) BEFORE removing the hidden textarea — a failed copy here is invisible until the paste comes up blank two steps later. Then remove the hidden textarea.
3. **In the NotebookLM tab**, open the Customize dialog, **wait for** its textarea to render, **click** it to focus, then `browser_press_key` **`Control+V`**. Verify `textarea.value.length` ≈ the copied length; if `< 50`, retry steps 1–3 once. **If still `< 50`, last-resort fallback: re-fetch the body from the archived `B:\...\prompts\` file and inject via chunked `execCommand('insertText')`.** Only if THAT also fails to populate the textarea do you abort and mark the ticker `failed`. Never click Generate on a short/blank textarea.
This uses the *entire* search-grounded Gem prompt (no condensing) and costs ~0 prompt tokens.

## Per-ticker procedure

Tickers run **sequentially**, but they no longer share state — each writes only to its own notebook.

### 1. Capture both Gem prompts (dynamic, search-grounded)

Open the PPT Gem, remove any "Deep research" chip, submit:
```
Expand the Indian stock ticker <TICKER> to its full company name. Then generate a NotebookLM prompt that will produce a polished PPT presentation summarising <QUARTER> <FY> results for that company. The deck must focus strictly on <QUARTER> <FY>; if older-quarter material is present, use it only for trend/correlation. Respond in exactly this format and nothing else: STOCK_NAME: <full company name> --- NOTEBOOKLM_PROMPT: <the prompt to paste into NotebookLM Studio Customize Slide Deck>
```
Then the Audio Gem:
```
Expand the Indian stock ticker <TICKER> to its full company name. Then generate a NotebookLM Audio Overview prompt that will produce a polished Hindi audio briefing summarising <QUARTER> <FY> results for that company. Focus strictly on <QUARTER> <FY>; use older-quarter material only for trend/correlation. Respond in exactly this format and nothing else: STOCK_NAME: <full company name> --- NOTEBOOKLM_AUDIO_PROMPT: <the prompt to paste into NotebookLM Studio Customize Audio Overview>
```

**Submit the prompt** by filling the Quill composer (`.ql-editor.textarea`) via `focus()` + `execCommand('insertText', …)` (NOT the textarea setter — see Performance principles), then click the **Send** button (`aria-label*="Send"`).

**Completion check (robust):** poll until the Stop button is gone AND the response length is stable across two consecutive polls (a streaming reply transiently contains `---`). Gems can take 30–60s; poll patiently.

**Transfer the prompt via clipboard, not via context** (see Clipboard transfer above): in-page, slice the body after `NOTEBOOKLM_PROMPT:` (stop before "Gemini is AI"), copy it to the clipboard, and optionally archive it to `B:\...\prompts\<TICKER>_<Q>_ppt.txt` with the `filename` param. Return only `STOCK_NAME` and the body length. Do the audio Gem the same way (`_audio.txt`), then paste each into its NotebookLM dialog with `Control+V`.

Read only the `STOCK_NAME` line into context (identical from both Gems).

### 2. Find or create THIS ticker's notebook

```
nb = python db.py get-notebook <TICKER>
```
- If `nb` non-empty → `browser_navigate` to `https://notebooklm.google.com/notebook/<nb>`. (Has historical sources — good.)
- If empty → go to `https://notebooklm.google.com/`, click **Create new notebook**, read the id from the resulting URL (`/notebook/<ID>`), and **immediately** `python db.py set-notebook <TICKER> <ID>` (so a mid-run crash never loses it). The new notebook opens with `?addSource=true` (Add-source dialog already open). **Rename it** from its auto-generated title (it may inherit a junk name like a source's title) to `<STOCK_NAME> — <TICKER>` via the title `<input>`.

There is **NO wipe step**. Do not delete any sources — **except** obvious junk auto-added by a failed import (e.g. a BSE "Access Denied" page): open the source's `⋮` → **Remove source** → confirm **Delete** in the dialog (deletion needs that 2nd confirm click).

### 3. Add this quarter's sources (additive, deterministic-first)

**Note (confirmed 2026-05-23):** BSE India PDF URLs (`bseindia.com/xml-data/corpfiling/...`) are blocked by NotebookLM's servers — they return an access-denied HTML page instead of the PDF content. Do NOT attempt to add BSE transcript/PPT URLs as website sources; skip directly to Discover. Screener.in and other non-BSE URLs may work but are lower priority than Discover.

1. Run **Discover** for breadth. Open the Add-source dialog; it has a research-mode dropdown showing **"Fast Research"**. **Switch it to "Deep Research"** first: click the `search_spark Fast Research` trigger, then click the `travel_explore Deep Research — In-depth report and results` option.
   **VERIFY the switch stuck before searching (load-bearing — see fix #13).** Re-read the dropdown trigger's text and confirm it now reads **"Deep Research"**, not "Fast Research". If it still says Fast Research, re-open and re-select — do NOT proceed on Fast Research. Fast Research silently caps Discover at **~10 web links and produces NO Deep Research report**, yielding correct-but-shallow decks; Deep Research returns a curated **25–50** sources plus a `Deep Research Report` source artifact. Then type the query into `textarea[placeholder="Search the web for new sources"]` (submit:true):
   ```
   "<STOCK_NAME>" (Transcript OR "Financial Results" OR "Brokerage Reports" OR "Market expert comments") "<QUARTER> <FY>"
   ```
   **Poll patiently** — Deep Research can take several minutes and may show a "researching"/"confirm plan" interim step (confirm it if shown). Wait for the completion state (e.g. "Research completed" / the Import button appearing), then click **Import** (button text is `add\nImport`). Because this runs long, do detection for the *next* ticker only after Import, and never sleep-block; poll in ≤270s windows.
2. **Dedup:** before importing, skip any discovered source whose title already exists in the notebook (avoid re-adding evergreen pages each quarter).

**Confirm Deep Research actually engaged (not just that sources increased).** After Import, assert BOTH: (a) total source count rose to **≥20** (a flat **exactly 10** added means it silently fell back to Fast Research — re-run Discover in Deep Research mode), AND (b) a source titled `Deep Research Report: …` now exists in the notebook (`/Deep Research Report/i` against the source list). If either check fails, the run is shallow — redo the Deep Research discovery before generating, or the deck will be thin. Source count check: `document.querySelectorAll('button[id^="source-item-more-button-"]').length`.

### 4. Slide Deck — generate AND verify

Open **Studio**, close any open artifact, click the **Slide Deck** row, then **Customize Slide Deck** (`aria-label === 'Customize Slide Deck'`).

**WAIT for the dialog's `<textarea>` to actually exist before pasting.** After clicking Customize Slide Deck, `browser_wait_for` (or poll with `browser_evaluate` returning a bool) until the dialog `<textarea>` is present and visible — Angular renders it a tick late, and pasting into a not-yet-rendered (or already-dismissed) dialog is the **`textarea_gone` failure** that silently produced default-template decks. Only once the textarea exists: **click it to focus**, then `browser_press_key` **`Control+V`**.

**HARD-ABORT if the paste did not land.** Re-read `textarea.value.length`. If it is `< 50`, **retry the full paste once** (re-focus, re-copy PPT body from §1 if needed, `Control+V`). If it is **still `< 50` after the retry, DO NOT click Generate** — a blank/short prompt yields NotebookLM's generic default-quality deck (this is exactly what made the bad recent decks). Instead: close the dialog, record `failed` for this ticker, and continue. Never generate a deck whose prompt textarea didn't verify full. Save the verified length to `B:\...\prompts\<TICKER>_<Q>_ppt.txt` (a real char count like `len=4416`, never an error string like `textarea_gone` — if you're about to write an error string, that IS the abort signal).

Once the textarea verifies full (length ≈ the copied body), click **Generate**. Then **VERIFY**: within ~20s a new Slide Deck artifact row should appear in the Studio list (or a "generating" state for it). If no new artifact appears and/or an error/quota toast shows → **retry once** (re-open Customize Slide Deck, re-wait, re-fill, Generate). If it still fails, record `failed` and continue to the next ticker — do NOT mark done.

### 5. Audio Overview — Hindi, generate AND verify

Click **Customize Audio Overview**. In one evaluate: open the `mat-select`, pick the option containing `हिन्दी`, **then re-read the select's displayed value and confirm it shows हिन्दी** (if not, retry the selection). **WAIT for the dialog's `<textarea>` to exist** (same Angular-render race as §4), then with the audio prompt on the clipboard, **click the textarea to focus it** and `browser_press_key` **`Control+V`**. **Verify `textarea.value.length >= 50`; retry the paste once if short, and if still short DO NOT click Generate** — record `failed` rather than queue a blank-prompt audio. Once verified full, click **Generate**. **VERIFY** a new Audio Overview artifact appears; retry once on failure. Audio language MUST be Hindi — if it cannot be set, record `failed` rather than generating English.

### 6. Record outcome

Only if BOTH deck and audio were confirmed queued:
```
python db.py mark <TICKER> done
```
Otherwise `python db.py mark <TICKER> failed` (it will auto-retry on the next routine run).

### 7. Report
One line per ticker:
```
✓ <TICKER> (<STOCK_NAME>) — notebook: <created|reused>, sources +<N>, deck: queued✓, audio (हिन्दी): queued✓
```
On failure, state which ticker, which step, and that it was marked `failed` for retry.

## Things to be careful about

- **Use Playwright MCP, not Claude in Chrome** (server-side block on notebooklm.google.com).
- **NEVER `browser_snapshot`** on NotebookLM/Gemini.
- **Remove the "Deep research" chip** on the Gems before submitting.
- **No wipe, ever** — one notebook per ticker; sources are additive. Cross-contamination is now impossible.
- **Quarter-scope every prompt** — the notebook holds multiple quarters.
- **Verify both generations** before marking done; PPT generation has been observed to fail silently.
- **Hindi is mandatory** and must be confirmed set before Generate.
- **Pro source cap is 300/notebook** (~30 quarters). Prune only years out.
- **Auth / 2FA / quota** mid-run: stop and report, don't retry-loop or attempt to authenticate.
- **Trust Gem prompts verbatim**; paste as-is (they're search-grounded each run).
