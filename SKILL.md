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
- **Carry-forward memory (new 2026-07).** After a run's deck + audio are confirmed, we also persist a compact **"Analyst Summary"** text source grounded in *this* quarter's primary sources (transcript + Deep Research report), so each quarter's analytical narrative — not just raw numbers — carries into future quarters as clean, auditable trend/correlation context. We deliberately do **NOT** recycle the generated deck/audio artifacts back as sources: that is lossy, compounds drift quarter-over-quarter, and worsens exactly the source contamination that fixes #11/#13 blame for bad decks. The summary is a short first-order text note instead. This step is **best-effort and NEVER blocks `done`** (deck + audio are the only gating deliverables). See §5.5.
- **Prompt generation stays dynamic.** The two Gems generate fresh, search-grounded prompts every run (do NOT replace with a static template). To keep Claude's context small, transfer each Gem response via **clipboard** (see Clipboard transfer). NOTE: `browser_evaluate`'s `filename` param saves the function's **return value**, NOT the page text — so it only archives the prompt body if you *return* the body (which leaks it into context). Don't use `filename` to archive prompts; the clipboard is the real transfer and the file fallback is not worth the context cost.
- **Framework floor on top of the dynamic prompt (new 2026-07-18).** The Gem owns the DYNAMIC layer (recent events, quarter catalysts, current street view); a static per-sector checklist in `framework.md` owns the ESSENTIALS floor (e.g. NIM/GNPA for lenders, realization/spreads for chemicals). Every Gem body is evaluated IN-PAGE against that checklist before the clipboard copy (§1.5), and missing essentials are injected as a compact addendum at the TOP of the body. The framework never rewrites or trims the Gem prompt — additive only, and never fatal.

## Field-tested fixes (2026-05-24 — every one cost real time to learn; obey them)

1. **Playwright MCP `--output-dir` must NOT be the drive root.** If it's `B:\`, every `browser_navigate` tries to write `B:\page-*.yml` and the sandbox denies it ("outside allowed roots"), blocking ALL navigation. Set `--output-dir` to a real subdir like `<project-root>` in `claude_desktop_config.json`, then restart the Claude app.
2. **Launching Deep Research: fill, then CLICK the Submit arrow — never press Enter.** Enter routes the text to the chat box (or is lost) and silently does nothing for source discovery. After selecting Deep Research and filling the research `<textarea>` via the native value-setter + `input` event, the research **Submit** button (`aria-label="Submit"`) enables after a short async tick. There are TWO `aria-label="Submit"` buttons: the **research** one sits near the box (top ≈236px), the **chat** one is lower (top ≈431px) and is disabled when chat is empty. Click the enabled Submit nearest the top. If none is enabled yet, re-check once (Angular lag) — do not click the disabled one.
3. **Detecting DR progress: NEVER match the bare word "research".** "Deep Research" lives permanently in the mode dropdown, so `/research/` is always true → false "still running" reads (cost a wasted 12-min wait). Real signals: a button with `aria-label="Stop"` = running; the stage label cycles **Planning… → Researching Websites… → Analyzing Results…**; **completion = Stop button gone AND an Import button present** (text `Import` / `add Import`). Click Import; source count jumps (~25–32). A quick `browser_take_screenshot` (an image, allowed — it's not `browser_snapshot`) is the fastest way to disambiguate a stuck vs advancing state.
4. **Deep Research takes ~24–32 min per ticker** (not "a few minutes"). Poll in ≤270s windows (240s is good — keeps the prompt cache warm). A daily run realistically finishes ~3 tickers; that's expected.
5. **Customize dialogs contain THREE textareas — target by placeholder, never `querySelector('textarea')`** (that grabs the off-screen research box). Slide Deck outline = placeholder matches `/outline/`; Audio = matches `/things to try|focus on/`. Click+focus that specific textarea, `Control+V`, then VERIFY `value.length>0`. These fields **HARD-TRUNCATE at 5000 chars** — this is NOT harmless (corrected 2026-07-23). A prompt longer than 5000 chars loses everything past char 5000, and the Gems were emitting 11–16K-char prompts with the **slide list at the tail**, so the Q&A/transcript-forensics, guidance-tracker, grounding, and risks slides were silently amputated on ~every deck — the true cause of "no Q&A coverage" and stale-number decks. **Corrected again 2026-07-24 (final): generate rich, then condense — keeping the DYNAMIC per-stock visual theme.** The Gem generates its full, characterful, sector/stock-tailored prompt with NO length pressure (§1 pass 1); a second in-page condense pass in the same Gem thread compresses it to ≤3700 chars, explicitly preserving the visual theme + every named slide + grounding, cutting only repetition/filler (§1.4); then §1.5 prepends the ~950-char data-fidelity + units addendum (plus up to ~350 chars of coverage), landing the paste under 5000. This keeps visuals dynamic (not a boring fixed block) AND fits the cap — the old 11–16K prompts' actual information compresses to ~3700 losing only repeated prose. If the condense overruns, re-condense in the Gem (never blind code-trim). The §4/§5 paste-verify additionally does a **content-survival check** (confirm the pasted value still contains a transcript/Q&A token) as a last-line sanity check.
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

## Fitting the full DYNAMIC prompt into 5000 — generate rich, then condense (2026-07-24, final approach)

**Design goal (from the user):** keep the visual/style theme **dynamic per sector and per stock** so decks don't all look identical and boring — the Gem's company-specific theming (e.g. Bandhan's "microfinance→universal bank" heritage-orange palette; a chemicals name's spread/realization-led chart choices) is a **feature to preserve**, not verbosity to strip. A single fixed house-style block was the wrong answer (it makes every deck look the same). The right answer is **two passes**:

1. **Pass 1 — the Gem generates the FULL, rich, dynamic prompt** (its custom per-stock visual theme + all content slides), under NO length pressure. Let it be as rich as it wants (the ~11–16K chars it naturally produces). Asking one pass to be *both* creatively rich *and* under a hard char count is the exact tension that fails — so pass 1 has only one job: be complete and characterful.
2. **Pass 2 — an in-page condense step compresses that full prompt to ≤3700 chars**, explicitly preserving (a) the company-specific visual theme & palette, (b) every mandatory content slide (Q&A forensics, guidance tracker, KPI deep-dive, results-vs-street, risks…), and (c) the data-grounding rule — while cutting ONLY repetition, restated "non-negotiable" mandates, and filler prose. Compression is a task LLMs do reliably when given one clear job ("shorten this, keep X/Y/Z, cut repeats"), unlike the failed "be short while also covering 8 things." **This runs in the Gemini tab (same thread, which already holds the full prompt in its own context), so nothing enters Claude's context** — the clipboard transfer then carries the condensed version. Target ≤3700 leaves ~700 chars for the §1.5 data-fidelity + framework prepend, keeping the final paste under the 5000 cap.

This keeps visuals **dynamic and stock-specific** AND fits the limit. If the condensed output is still >5000 after the prepend, re-issue the condense once with a tighter target; only as an absolute last resort accept a >5000 paste (NotebookLM will truncate the tail) and flag it — but a focused condense reliably lands under 3700 (the old 11K Bandhan prompt's actual information content compresses to ~3700 losing nothing but repetition).

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
To move a Gem prompt from the Gemini tab to NotebookLM without context bloat. Use **trusted key events** (`browser_press_key`) for copy/paste — `document.execCommand('copy')` often returns false in automation because it needs a user gesture; a real `Control+C` keystroke does not.

**Orientation for the current two-pass flow (2026-07-24):** the body you ultimately transfer is the **CONDENSED** prompt from §1.4 (slice after `NOTEBOOKLM_PROMPT_CONDENSED:` / `NOTEBOOKLM_AUDIO_PROMPT_CONDENSED:`, not the pass-1 markers), and the **`Control+C` + archive happen in §1.5**, AFTER the data-fidelity addendum is prepended — so the clipboard and the `_ppt.txt`/`_audio.txt` archive reflect the final pasted text (addendum + condensed dynamic prompt). The generic steps below are the underlying mechanics; §1.4/§1.5 own the ordering.
1. **In the Gemini tab**, after the response is complete, run one `browser_evaluate` that: locates the response text, slices out the prompt body (after `NOTEBOOKLM_PROMPT:` / `NOTEBOOKLM_AUDIO_PROMPT:`, stopping before "Gemini is AI"), creates a hidden `<textarea>` with that body appended to `document.body`, and calls `ta.focus(); ta.select();`. Return only `STOCK_NAME` + the body length — never the body. **ALWAYS pass `filename` to archive the full body to `B:\...\prompts\<TICKER>_<Q>_ppt.txt` (resp. `_audio.txt`) — this is mandatory, not optional.** The archive is the fallback the §4/§5 paste depends on, and its presence (with a real char count) is how a later audit confirms the PPT prompt was actually captured. A run where the PPT file is **missing** means this step silently failed and the deck got NotebookLM's default template — the exact cause of the bad recent decks.
   **Guard the slice:** if the body length is `< 200` or the body still contains the literal `<the prompt to paste...>` placeholder (i.e. the Gem echoed the template instead of generating), the Gem did not produce a real prompt — **re-submit the Gem once**; if it fails again, record `failed` and skip this ticker rather than pasting garbage.
2. `browser_press_key` **`Control+C`** (copies the selection via the real clipboard). **Confirm the copy** by reading `navigator.clipboard.readText().then(t => t.length)` (or re-select+re-copy if it reads empty) BEFORE removing the hidden textarea — a failed copy here is invisible until the paste comes up blank two steps later. Then remove the hidden textarea.
3. **In the NotebookLM tab**, open the Customize dialog, **wait for** its textarea to render, **click** it to focus, then `browser_press_key` **`Control+V`**. Verify `textarea.value.length` ≈ the copied length; if `< 50`, retry steps 1–3 once. **If still `< 50`, last-resort fallback: re-fetch the body from the archived `B:\...\prompts\` file and inject via chunked `execCommand('insertText')`.** Only if THAT also fails to populate the textarea do you abort and mark the ticker `failed`. Never click Generate on a short/blank textarea.
This uses the *entire* search-grounded Gem prompt (no condensing) and costs ~0 prompt tokens.

## Per-ticker procedure

Tickers run **sequentially**, but they no longer share state — each writes only to its own notebook.

### 1. Capture both Gem prompts (dynamic, search-grounded)

**Pass 1: generate the full, rich, DYNAMIC prompt (no length limit here — condensing happens in §1.4).** The Gem must produce its characterful per-stock/per-sector visual theme AND the complete content. The only additions to the old instruction are the explicit MANDATORY-SLIDE naming (so completeness is guaranteed before condensing) and the grounding rule — the visual theming stays fully the Gem's own dynamic creation.

Open the PPT Gem, remove any "Deep research" chip, submit:
```
Expand the Indian stock ticker <TICKER> to its full company name. Then generate a NotebookLM prompt that will produce a polished, visually rich PPT presentation summarising <QUARTER> <FY> results for that company.

Make the deck's VISUAL THEME distinctive and tailored to THIS company and sector — a custom colour palette with a one-line rationale tied to the company's story, sector-appropriate chart choices, and a consistent slide grammar. (Do not reuse a generic template; the visual character should feel specific to this stock.)

The deck must focus strictly on <QUARTER> <FY>; older-quarter material is for trend/correlation only.

GROUNDING RULE (state it in the prompt): every figure must be the ACTUAL reported figure for <QUARTER> <FY> from the uploaded sources; prior-period numbers only in explicitly labelled comparisons (e.g. "Q1 FY26: X vs Q1 FY27: Y"); write "not disclosed" if a figure is absent — never carry an older quarter's number as the current one.

UNITS RULE (state it in the prompt): all rupee amounts must be expressed in CRORES as "₹X cr" (Indian convention) — never millions or billions; convert if a source quotes mn/bn (₹1 cr = ₹10 mn). Percentages, margins and per-share figures stay as reported.

MANDATORY SLIDES (the prompt must name each, with the specific things it must contain): Cover; Executive Summary & variant perception; Quarter-over-Quarter & Year-over-Year trend (target quarter vs immediately-preceding quarter vs same quarter last year, each period labelled); Management Guidance Tracker (prior-quarter promises vs this quarter's actuals, DELIVERED/PARTIAL/MISSED); Sector/company KPI deep-dive (the specific KPIs this company's analysts track); Concall Transcript Q&A Forensics (the specific analyst questions and how management answered — tone, hedge-words, any first-time or soft-guidance disclosures); Results vs Street (beat/miss vs consensus, rating/target changes); Key Risks (from MD&A/transcript); So-What summary.

Respond in exactly this format and nothing else: STOCK_NAME: <full company name> --- NOTEBOOKLM_PROMPT: <the full prompt to paste into NotebookLM Studio Customize Slide Deck>
```
Then the Audio Gem:
```
Expand the Indian stock ticker <TICKER> to its full company name. Then generate a NotebookLM Audio Overview prompt that will produce a polished Hindi audio briefing summarising <QUARTER> <FY> results for that company. Give it a delivery style suited to this company/sector.

Focus strictly on <QUARTER> <FY>; older-quarter material for trend/correlation only.

GROUNDING RULE (state it in the prompt): every figure must be the ACTUAL reported <QUARTER> <FY> number from the sources; older-period figures only in explicitly labelled comparisons; never present a prior quarter's number as the current one.

UNITS RULE (state it in the prompt): all rupee amounts must be spoken in CRORES ("X करोड़ रुपये") — never millions or billions; convert if a source quotes mn/bn (₹1 cr = ₹10 mn). Percentages, margins and per-share figures stay as reported.

MUST COVER, by name: headline financials with QoQ & YoY deltas (each period labelled); management guidance/outlook; the key concall Q&A exchanges (what analysts pressed on and how management responded, including tone and any soft guidance); 2-3 forward risks.

Respond in exactly this format and nothing else: STOCK_NAME: <full company name> --- NOTEBOOKLM_AUDIO_PROMPT: <the full prompt to paste into NotebookLM Studio Customize Audio Overview>
```

**Submit the prompt** by filling the Quill composer (`.ql-editor.textarea`) via `focus()` + `execCommand('insertText', …)` (NOT the textarea setter — see Performance principles), then click the **Send** button (`aria-label*="Send"`).

**Completion check (robust):** poll until the Stop button is gone AND the response length is stable across two consecutive polls (a streaming reply transiently contains `---`). Gems can take 30–60s; poll patiently.

**Measure pass-1 length in-page** (return just the char count, never the body). If the full PPT prompt is already ≤3700 chars, skip the condense pass — go straight to transfer. If it's longer (the usual case, ~11–16K), run §1.4.

### 1.4 Condense pass (in-page, same Gem thread — zero Claude context cost)

The full pass-1 prompt already lives in the Gem thread's own context, so the Gem can compress it without anything entering Claude's context. Send this as a **second message** to the SAME PPT Gem thread (fill the Quill composer + click Send, exactly as pass 1):
```
Condense the NOTEBOOKLM_PROMPT you just produced to at most 3700 characters. PRESERVE, losing nothing: (1) the company-specific visual theme — its custom palette + rationale, chart-type choices, and slide grammar; (2) EVERY mandatory slide by name, including the Concall Transcript Q&A Forensics, Management Guidance Tracker, KPI deep-dive, Results vs Street, and Key Risks slides; (3) the data-grounding rule; (4) the units rule (all rupee amounts in crores, "₹X cr"). CUT ONLY: repeated phrases, any instruction stated more than once, "non-negotiable"/"mandatory" filler restatements, and long prose that can be a terse directive. Keep it dense and directive, not verbose. Reply with ONLY this and nothing else: NOTEBOOKLM_PROMPT_CONDENSED: <the condensed prompt>
```
Poll for completion (same robust check). **Measure the condensed length in-page.** If still >3700, send one more message: `Still too long at <N> chars — compress further to under 3700, cutting only repetition and filler, keeping all named slides + the visual theme + grounding + the crores units rule.` Do this at most twice. Run the Audio Gem's condense identically (same PRESERVE list including the units rule; target ≤2000 for audio, which leaves ample room). If after two tries it will not get under ~4700 (leaving minimal room for the fidelity prepend), proceed anyway and let the §1.5 code check + §4 content-survival check catch it — a mostly-condensed prompt that slightly overruns is far better than the old 11K amputation.

**Slice the CONDENSED prompt into the hidden transfer textarea** (do NOT copy-to-clipboard or archive yet — §1.5 prepends the data-fidelity addendum first, and the clipboard copy + archive must reflect that final text). In-page: slice the body after `NOTEBOOKLM_PROMPT_CONDENSED:` (stop before "Gemini is AI"), put it in the hidden `<textarea>` appended to `document.body`, and return only `STOCK_NAME` + the condensed length. Do the audio Gem the same way (slicing after `NOTEBOOKLM_AUDIO_PROMPT_CONDENSED:`). §1.5 then runs the framework check, prepends the addendum, and does the `Control+C` + archive + paste.

Read only the `STOCK_NAME` line into context (identical from both Gems).

### 1.5 Evaluate the Gem body against the coverage framework (in-page, before the copy)

**Why:** the dynamic Gem prompt sometimes emphasises this quarter's story and drops a structural essential (a lender prompt with no GNPA line, a chemicals prompt with no realization/spread coverage). This step guarantees the floor without touching the dynamic layer.

**When:** for BOTH the PPT and audio condensed bodies, in the same browser context that holds the hidden transfer textarea — AFTER §1.4 has sliced the condensed body into the textarea, BEFORE `Control+C`. (This step runs on the condensed body and owns the final `Control+C` + archive + paste.)

1. **Once per run** (not per ticker), read `framework.md` (this skill's directory). It defines: the ticker→sector map (keyword fallback if unmapped), the universal checklist, the sector packs, AND a **company-overlay table** (structural specifics like IEX market coupling, HBL Kavach, TMPV's JLR) — each item as `key | case-insensitive regex | addendum phrase`.
2. In one `browser_evaluate`, run every applicable regex (universal + the ticker's sector pack + the ticker's overlay row if present) against the textarea's value. **Return ONLY the missing item keys** (short strings) — never the body. If the ticker is unmapped, use the keyword fallback and flag `framework: unmapped-<TICKER>` in the report so the map gets extended.
3. **The DATA FIDELITY clause below is ALWAYS injected — unconditionally, on every run, for both PPT and audio bodies — even when the framework check finds nothing missing.** (Field-tested need, 2026-07-23: generated decks have been observed presenting prior-quarter figures as the current quarter's, and slide numbers not matching the reported results. The notebook holds multiple quarters of sources, so without this clause NotebookLM sometimes grabs the wrong period's numbers.) If no framework items are missing, the addendum consists of the fidelity clause alone; note `framework: ok`.
4. **Prepend the DATA FIDELITY + coverage addendum to the CONDENSED body from §1.4.** The condensed prompt already carries the dynamic visual theme AND all content slides — this step only guarantees the fidelity floor and re-inserts any framework essential the condense may have dropped. Order: addendum at position 0, then the condensed body beneath it.
   ```
   DATA FIDELITY (non-negotiable): Every headline financial figure (revenue, EBITDA, margins, PAT, EPS, segment numbers) MUST be the ACTUAL REPORTED figure for <QUARTER> <FY>, taken from this quarter's results/transcript sources. NEVER present a prior quarter's or prior year's figure as the current quarter's. Prior-period figures may appear ONLY in explicitly labelled comparisons (e.g. "Q1 FY26: X vs Q1 FY27: Y") with their period named on the same line. If a current-quarter figure is not found in the sources, write "not disclosed" — do not substitute an older number.
   UNITS (non-negotiable): Express ALL rupee amounts in CRORES as "₹X cr" (Indian convention) — never millions or billions. If a source quotes mn/bn, CONVERT (₹1 cr = ₹10 mn = ₹0.01 bn; $1 mn ≈ ₹8.3 cr at ~83/USD — use the source's own rate if given). Use lakh only where the company itself reports in lakh (e.g. capacity in lakh MTPA). Percentages, margins, per-share and per-unit figures stay as reported.
   COVERAGE ADDENDUM (mandatory — in addition to everything below, the output MUST cover): <phrase1>; <phrase2>; ...
   ```
   (Omit the COVERAGE line entirely when no framework items are missing.) Replace `<QUARTER> <FY>` with the literal target quarter, e.g. `Q1 FY27`. The FIDELITY and UNITS clauses are fixed text (~950 chars combined) and are **never trimmed**. Cap the COVERAGE line at ~350 chars; if over, trim in priority order **overlay > concall-essentials > sector > universal** (overlay = company-specific structural factors; concall-essentials = Q&A mining, tone/soft-guidance signals, guidance deltas, one-offs, first-time disclosures).

   **Deterministic length check (in the same `browser_evaluate` that prepends, BEFORE writing the hidden textarea):** compute `total = fidelityAddendum.length + condensedBody.length`. Since §1.4 targets the condensed body ≤3700 and the addendum (fidelity + units + coverage) is ≤1300, `total` is normally **≤5000** → note `budget: ok(<total>)` and proceed. **If `total > 5000`, the condense didn't go far enough** — go back to §1.4 and send ONE more condense message in the Gem thread targeting a tighter size, then re-transfer and re-measure. Do NOT trim the visual theme or content yourself in code — re-condensing IN THE GEM preserves the dynamic theme intelligently, whereas a blind code-side tail-trim would amputate whatever's last (exactly the original bug). Only if re-condense still overruns after one retry, accept the slight overrun (NotebookLM truncates the tail) and flag `budget: OVERRUN(<total>)` for investigation. In practice a focused condense lands well under 3700.
   Re-select the textarea (`ta.focus(); ta.select();`) after prepending, then proceed to `Control+C`. Note `framework: +<key>+<key>` for the report.
5. **Never fatal:** if the framework file is unreadable or the evaluate errors, log `framework: skipped` and prepend ONLY the data-fidelity clause to the condensed body (skip just the coverage addendum — the fidelity clause is not framework-dependent). A missing framework check must never fail a ticker or block generation.
6. The archived `_ppt.txt`/`_audio.txt` should be written AFTER the prepend so the archive reflects exactly what was pasted (fidelity addendum + condensed dynamic prompt).

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

**CONTENT-SURVIVAL CHECK (last-line sanity check, not the primary defense — that's the §1.4 condense + §1.5 length check).** Read the textarea value once and confirm it contains at least one content token — `/transcript|Q&A|Q & A|guidance tracker|risks/i`. This should always pass now (the condensed body preserves all named slides and the fidelity addendum is prepended), but if it somehow fails, do NOT Generate: the condense dropped substance or the paste truncated. Re-run the §1.4 condense once (asking it to preserve the Q&A/guidance/risks slides), re-paste, and re-check. If it still fails, record `failed` and continue — a gutted deck is worse than none.

Once the textarea verifies full AND passes the content-survival check, click **Generate**. Then **VERIFY**: within ~20s a new Slide Deck artifact row should appear in the Studio list (or a "generating" state for it). If no new artifact appears and/or an error/quota toast shows → **retry once** (re-open Customize Slide Deck, re-wait, re-fill, Generate). If it still fails, record `failed` and continue to the next ticker — do NOT mark done.

### 5. Audio Overview — Hindi, generate AND verify

Click **Customize Audio Overview**. In one evaluate: open the `mat-select`, pick the option containing `हिन्दी`, **then re-read the select's displayed value and confirm it shows हिन्दी** (if not, retry the selection). **WAIT for the dialog's `<textarea>` to exist** (same Angular-render race as §4), then with the audio prompt on the clipboard, **click the textarea to focus it** and `browser_press_key` **`Control+V`**. **Verify `textarea.value.length >= 50`; retry the paste once if short, and if still short DO NOT click Generate** — record `failed` rather than queue a blank-prompt audio. **Also apply the same content-survival check as §4** (last-line sanity check — §1.4 condense + §1.5 length check are the real defense): confirm the surviving value contains `/transcript|Q&A|Q & A|guidance|risks/i`; if not, re-run the §1.4 audio condense once before generating. Once verified full and content-survived, click **Generate**. **VERIFY** a new Audio Overview artifact appears; retry once on failure. Audio language MUST be Hindi — if it cannot be set, record `failed` rather than generating English.

### 5.5 Persist a carry-forward "Analyst Summary" source (best-effort, non-blocking)

**Purpose.** Carry this quarter's *analytical narrative* into future quarters as a compact, auditable text source — grounded in **this** quarter's primary sources (transcript + Deep Research), NOT by recycling the generated deck/audio. Because the notebook is never wiped, the note persists and becomes trend/correlation context next quarter. (Every generation prompt is already quarter-scoped and treats older material as correlation-only, so a prior-quarter summary is context, never mistaken for the target quarter's data — see fix #11/#13 on why more sources ≠ better; this adds exactly ONE small text source per quarter.)

**This step runs AFTER deck and audio are confirmed queued and is BEST-EFFORT: it must NEVER downgrade a good run.** If any part fails, log `summary: skipped` and still proceed to `mark <TICKER> done`. Do NOT mark the ticker `failed` because the summary step failed.

**Idempotency (re-run guard).** The auto-generated source title does NOT reliably contain "Analyst Summary" (see step 3) — matching `/Analyst Summary/i` against `.source-title` elements is unreliable. Instead: open the most-recently-added note-derived source (its title is content-generated but still identifiable as the newest Studio note/source, "Xd ago"), and read its first line. If it already reads `<TICKER> <QUARTER> <FY> — Analyst Summary`, SKIP this whole step — never create a duplicate summary for the same quarter.

Steps:
1. **Generate the summary inside NotebookLM** (grounded on its own sources — zero Claude context cost; do NOT read the body). In the chat box, fill and send exactly:
   ```
   Begin your reply with exactly this line and nothing before it:
   <TICKER> <QUARTER> <FY> — Analyst Summary
   Then, using ONLY this notebook's sources for <QUARTER> <FY>, write a plain-text analyst summary in under 350 words covering: revenue, EBITDA/margin and PAT with QoQ and YoY deltas; management guidance/outlook; key segment or geography highlights; and 2-3 forward risks or watch-items. No markdown headers, no preamble after the first line.
   ```
   Poll until the chat response is complete (Stop button gone AND response length stable across two consecutive polls — same completion pattern as the Gem check in §1). You only act on buttons; never pull the body into context.
2. **Save the response as a note.** On the completed chat message, click its save-to-note control (`button[aria-label*="Save message to a note" i]`, take the LAST match — never enumerate all buttons).
3. **Convert the note to a source.** In Studio, NotebookLM auto-titles the note from its own content summary, NOT your literal first line (e.g. you'll see something like "HCLTech Q1 FY27 Performance Analysis and AI Growth Strategy" instead of "HCLTECH Q1 FY27 — Analyst Summary") — **this is expected, don't fight it.** To open the note: a plain `.click()` on the title `<span>` does nothing (Angular's real click target is a sibling `button.artifact-stretched-button` that overlays the row) — either `browser_click` with a `text=` selector (Playwright resolves the real button even when the synthetic `.click()` no-ops) or `document.querySelector('button[aria-labelledby="..."]')` using the id from the title span's `aria-describedby`/tooltip pairing. Once open, click **Convert to source**. **Do not chase renaming the resulting source to match the literal `Analyst Summary` string** — the Rename dialog's Save button silently no-ops on the native-setter+dispatchEvent('input') pattern that works everywhere else in this skill (untriaged; low priority since it's cosmetic). What actually matters for §5.5 step 4's idempotency check and for NotebookLM's own retrieval is the **note body**, which does correctly start with `<TICKER> <QUARTER> <FY> — Analyst Summary` — verify by opening the note and reading its first line, not by grepping source titles.
4. **VERIFY.** Re-read the source count (`document.querySelectorAll('.source-title').length` before vs. after) — it should have risen by exactly 1. If it did → note `summary: saved`. If not, retry steps 2-3 once; if still not, note `summary: skipped` and continue. **Either way, proceed to §6 and mark `done` if deck+audio succeeded.**

### 5.7 Data-fidelity audit of the generated deck (best-effort, non-blocking)

**Why (2026-07-23):** even with quarter-scoped prompts, generated decks have shown (a) figures that don't match the reported results and (b) prior-quarter numbers presented as the current quarter's. This step catches both cheaply, grounded in the notebook's own sources — no external data needed.

**When:** after deck + audio are confirmed queued (and §5.5 done). **Best-effort: never un-marks a `done`, never blocks §6.** Report its outcome in the `dataaudit:` field.

1. **Get the ground truth (one short line into context — this is allowed, it's ~30 tokens).** In the notebook chat, fill and send:
   ```
   Using ONLY the <QUARTER> <FY> results/transcript sources in this notebook, reply in EXACTLY one line, no preamble: REV=<value+unit> EBITDA_OR_NII=<value+unit> PAT=<value+unit> for <QUARTER> <FY> (consolidated if available). Write NA for any figure not in the sources.
   ```
   Poll for completion (Stop gone + stable length), then read ONLY that one line into context.
2. **Wait for the deck artifact to finish** — poll the Studio list in ≤270s windows for up to ~10 min total. Deck generation usually completes within this. If still generating when the budget is spent → note `dataaudit: pending` and move on (do not hold the run hostage).
3. **Check the deck in-page.** Open the completed Slide Deck artifact, and in ONE `browser_evaluate` (passing the ground-truth numbers in as literals): extract the deck's full text in-page, normalize numbers (strip commas/₹/spaces), and return ONLY booleans/short strings: `{revFound, patFound, ebitdaFound, priorQuarterAsHeadline}` — where `priorQuarterAsHeadline` is true if a headline/title slide names a different quarter (e.g. "Q4 FY26 Results") than the target. Never return the deck text itself.
4. **Interpret:**
   - All key figures found + headline quarter correct → `dataaudit: ok`.
   - `REV`/`PAT` from ground truth NOT found in the deck, or headline quarter wrong → the deck likely used stale or wrong-period figures. **Regenerate once:** re-open Customize Slide Deck, re-paste the archived `_ppt.txt` prompt, and prepend one corrective line: `CRITICAL FIX: the headline financials MUST be <QUARTER> <FY> actuals — REV=<X>, PAT=<Y> as reported. Do not use any other period's figures as current.` Then Generate and note `dataaudit: regenerated`. (Do NOT delete the first deck artifact — leave both; newest wins.)
   - Ground truth came back all-NA (sources genuinely lack the numbers — e.g. transcript-only notebook) → `dataaudit: no-baseline` (nothing to check against; not a failure).
   - Any step errors or the artifact can't be read → `dataaudit: skipped`.
5. A `regenerated` deck is NOT re-audited (one corrective pass only — avoid loops). A ticker is never marked `failed` by this section; the audit's job is to catch and correct, not to gate.

### 6. Record outcome

Only if BOTH deck and audio were confirmed queued (the carry-forward summary in §5.5 is NOT a gating condition):
```
python db.py mark <TICKER> done
```
Otherwise `python db.py mark <TICKER> failed` (it will auto-retry on the next routine run).

### 7. Report
One line per ticker:
```
✓ <TICKER> (<STOCK_NAME>) — notebook: <created|reused>, sources +<N>, condense: <full→condensed chars>, framework: ok|+<keys>|skipped, budget: ok(<total>)|OVERRUN(<total>), deck: queued✓, audio (हिन्दी): queued✓, summary: saved✓|skipped, dataaudit: ok|regenerated|pending|no-baseline|skipped
```
On failure, state which ticker, which step, and that it was marked `failed` for retry. (A `summary: skipped` is NOT a failure — deck+audio still make the run a `done`.)

## Things to be careful about

- **Use Playwright MCP, not Claude in Chrome** (server-side block on notebooklm.google.com).
- **NEVER `browser_snapshot`** on NotebookLM/Gemini.
- **Remove the "Deep research" chip** on the Gems before submitting.
- **No wipe, ever** — one notebook per ticker; sources are additive. Cross-contamination is now impossible.
- **Quarter-scope every prompt** — the notebook holds multiple quarters.
- **Verify both generations** before marking done; PPT generation has been observed to fail silently.
- **Carry-forward summary (§5.5) is best-effort** — never mark a ticker `failed` because it failed, and never let it delay/replace deck+audio. It is ONE small text source per quarter; do not recycle the generated deck/audio as sources (drift + contamination).
- **Hindi is mandatory** and must be confirmed set before Generate.
- **Pro source cap is 300/notebook** (~30 quarters). Prune only years out.
- **Auth / 2FA / quota** mid-run: stop and report, don't retry-loop or attempt to authenticate.
- **Generate rich, then condense — the visual theme is DYNAMIC per stock/sector (2026-07-24).** The Gem writes its full, characterful, company-tailored prompt with no length pressure (§1 pass 1); an in-page condense pass in the same Gem thread compresses it to ≤3700 preserving the visual theme + every named slide + grounding (§1.4); §1.5 prepends the fidelity addendum. The final paste is `[DATA FIDELITY + coverage addendum] + [condensed dynamic prompt]`, under 5000. Never blind-trim in code — if the condense overruns, re-condense IN THE GEM (it preserves the theme intelligently; a code tail-trim would amputate whatever's last, the original bug). This keeps each deck visually distinct AND reliably delivers Q&A/guidance/risks to NotebookLM.
- **Units: ALWAYS crores, never millions (user requirement, 2026-07-25).** Indian investors read ₹ cr; a deck quoting "₹4,200 mn" is harder to sanity-check against screener/broker notes. The UNITS clause is injected unconditionally in §1.5 alongside DATA FIDELITY, is also stated in both §1 Gem prompts, and is on the §1.4 condense PRESERVE list — three layers, because the condense pass is what historically dropped things. Lakh is acceptable ONLY where the company itself reports in lakh (e.g. capacity in lakh MTPA). Percentages, margins and per-share figures are untouched.
- **Data fidelity (§1.5 clause + §5.7 audit)** — figures in the deck must be the target quarter's ACTUAL reported numbers; prior-period figures only in explicitly labelled comparisons. The §5.7 audit is best-effort and never gates `done`, but a `dataaudit: regenerated|pending|skipped` should be visible in the report so a human can spot-check.
- **Framework check (§1.5) is additive-only and never fatal** — a `framework: skipped` run still generates; a framework gap must never mark a ticker `failed`. Keep `framework.md`'s ticker→sector map current when the watchlist changes.
