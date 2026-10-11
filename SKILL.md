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
- **DESIGN IS DELEGATED TO NOTEBOOKLM (user decision, 2026-10-11 — supersedes the idiom/hex/`styles.py` approach).** NotebookLM's own slide design has improved a lot, so we no longer dictate palette, hex values, fonts, a named design idiom or a ground treatment. Instead the prompt carries a **COMPANY DESIGN BRIEF**: what the company actually does, its physical/operational world, its products and customers, and its brand personality. It then gives a **direct instruction for NotebookLM to create and project its own visual style and visual elements** (imagery, motifs, iconography, colour mood, chart choices) that resonate with that business. Example: a dredging company reads as maritime, a hospital chain as clinical, a wine maker as vineyard/terroir. `styles.py` and the `styles/` overrides are **retired**: §0 no longer applies them. Per-slide direction now specifies **content and which data the visual must show**, not how it is styled. Legibility still overrides everything.
- **Prior context MUST be in play (user requirement, 2026-10-11).** The notebook's older sources and prior-quarter Analyst Summary notes exist to be used. NotebookLM only generates from **selected** sources, and a Studio note that was never converted to a source is invisible to generation. §3.5 therefore converts any stray notes, selects ALL sources before generation, and verifies afterwards that the deck's "View prompt and N sources" count equals the notebook's total.
- **A per-run checklist gates `mark done` (new 2026-08-03).** Each step below writes a small flag via `python db.py checklist-set <TICKER> <field> <value>` as it actually completes. `db.py mark <TICKER> done` reads that checklist and REFUSES (nonzero exit, status left unchanged) unless `style_checked`, `framework_checked`, `deck_verified_complete` and `audio_verified_complete` are all set — this exists because a real run (DLF, 2026-08-03) was marked `done` on "Generating Slide Deck…" status text, i.e. confirmation that generation *started*, when the deck generation had actually *failed* a few minutes later; a `done` ticker is never retried, so that failure would have silently persisted forever. `python db.py checklist <TICKER>` shows current state. The best-effort steps (§5.5/§5.7/§5.8) are tracked too but deliberately do NOT gate — see those sections.

## Field-tested fixes (2026-05-24 — every one cost real time to learn; obey them)

1. **Playwright MCP `--output-dir` must NOT be the drive root.** If it's `B:\`, every `browser_navigate` tries to write `B:\page-*.yml` and the sandbox denies it ("outside allowed roots"), blocking ALL navigation. Set `--output-dir` to a real subdir like `<project-root>` in `claude_desktop_config.json`, then restart the Claude app.
2. **Launching Deep Research: fill, then CLICK the Submit arrow — never press Enter.** Enter routes the text to the chat box (or is lost) and silently does nothing for source discovery. After selecting Deep Research and filling the research `<textarea>` via the native value-setter + `input` event, the research **Submit** button (`aria-label="Submit"`) enables after a short async tick. There are TWO `aria-label="Submit"` buttons: the **research** one sits near the box (top ≈236px), the **chat** one is lower (top ≈431px) and is disabled when chat is empty. Click the enabled Submit nearest the top. If none is enabled yet, re-check once (Angular lag) — do not click the disabled one.
3. **Detecting DR progress: NEVER match the bare word "research".** "Deep Research" lives permanently in the mode dropdown, so `/research/` is always true → false "still running" reads (cost a wasted 12-min wait). Real signals: a button with `aria-label="Stop"` = running; the stage label cycles **Planning… → Researching Websites… → Analyzing Results…**; **completion = Stop button gone AND an Import button present** (text `Import` / `add Import`). Click Import; source count jumps (~25–32). A quick `browser_take_screenshot` (an image, allowed — it's not `browser_snapshot`) is the fastest way to disambiguate a stuck vs advancing state.
4. **Deep Research takes ~24–32 min per ticker** (not "a few minutes"). Poll in ≤270s windows (240s is good — keeps the prompt cache warm). A daily run realistically finishes ~3 tickers; that's expected.
5. **Customize dialogs contain THREE textareas — target by placeholder, never `querySelector('textarea')`** (that grabs the off-screen research box). Slide Deck outline = placeholder matches `/outline/`; Audio = matches `/things to try|focus on/`.

   **THE 5000-CHAR "LIMIT" IS CLIENT-SIDE ONLY AND MUST BE BYPASSED — measured and proven 2026-07-26.** The outline textarea carries a plain HTML `maxlength="5000"` attribute. Per the HTML spec `maxlength` constrains **user edits only** (typing, `Control+V`) — it does **NOT** constrain programmatic assignment. Setting the value with the native setter writes the full string:
   ```js
   const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype,'value').set;
   setter.call(ta, body);                       // 12,000 chars verified held in DOM
   ta.dispatchEvent(new Event('input',{bubbles:true}));
   ```
   **End-to-end proof (TANLA notebook, 2026-07-26):** a 10,054-char prompt was set this way and generated. Opening the finished deck's **"View prompt and N sources"** panel showed the server had stored **all 10,054 chars** — all 55 interior directives plus the final instruction sitting at char 9,924, none truncated. The server does not reject or clip the payload (no 400/413; generation RPC returned 200).

   **Therefore: NEVER `Control+V` a prompt over 5000 chars** — the paste path *is* clipped by `maxlength` and silently loses the tail. Always use the native setter. Optionally also `ta.removeAttribute('maxlength')` first as belt-and-braces (not required — the setter alone is sufficient).

   **Consequence: the aggressive condense-to-fit is obsolete.** The 2026-07-23/24 fix (condense the Gem prompt to ≤3700 so a ≤5000 paste fits) was built on the false premise that 5000 was a hard server cap. It cost real design quality: the condense kept every mandatory slide *by name* but stripped the per-slide visual direction, leaving ~168 chars/slide of stub (measured on the archived TANLA prompt: 15 slides in 2,523 chars, with the grounding rule restated 6×). Pass the Gem's full, rich prompt instead — see §1.4.

   **Caveat — adherence is soft, and separate from transport.** In the same test, two literal "title this slide exactly X" markers were both ignored: the one at char ~100 *and* the one at char 9,924. NotebookLM treats the outline as **guidance**, not literal commands, and derives titles from content. So: full transport is proven; do **not** assume any single instruction is obeyed verbatim regardless of where it sits. Keep directives declarative ("include a waterfall bridging reported to adjusted PAT"), not imperative-literal ("title slide 7 exactly …"). Longer prompts also generate slower — the 10K test took ~14 min vs the usual 2–5.

   After setting the value, VERIFY `value.length` equals what you set, and keep the **content-survival check** (confirm the value still contains a transcript/Q&A token) as a last-line sanity check.
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
- `mark <TICKER> done|failed` → record outcome for the current quarter. **`done` fails closed** — see the checklist gate below and §6.
- `checklist-set <TICKER> <field> <value>` → record that a step of the current run actually happened (see per-step calls throughout §1–§5.8). Booleans accept 1/0/true/false/yes/no.
- `checklist <TICKER>` → print this ticker's current-quarter checklist and whether it's ready for `mark done`, for debugging a refused `mark done`.

(`styles.py` is RETIRED as of 2026-10-11 — design is delegated to NotebookLM via the company design brief; see §0. Do not run it.)

Captured Gem prompts are written to `<project-root>\stockwatch\prompts\<TICKER>_<Q>_ppt.txt` and `_audio.txt` (so a retry can skip the Gem step).

## Fixed resources

- **PPT Gem**: `https://gemini.google.com/gem/<YOUR_PPT_GEM_ID>` ("Meta-promptLM PPT")
- **Audio Gem**: `https://gemini.google.com/gem/<YOUR_AUDIO_GEM_ID>` ("Meta-promptLM - Audio")
- **Google account**: `<your-google-account>` (already signed into the Playwright Chromium profile at `<playwright-profile-dir>`)
- **Audio language**: always **हिन्दी (Hindi)** — non-negotiable. Verify the selection before Generate.
- **Gem mode**: keep the Gems on fast Google-Search grounding. If a **"Deep research"** chip is active on the composer, REMOVE it first (click its ✕) — Deep Research inserts a multi-minute "confirm plan" step that breaks polling.

## Fitting the full DYNAMIC prompt into 5000 — generate rich, then condense (2026-07-24, final approach)

**Design goal (from the user):** keep the visual/style theme **dynamic per sector and per stock** so decks don't all look identical and boring — the Gem's company-specific theming (e.g. Bandhan's "microfinance→universal bank" heritage-orange palette; a chemicals name's spread/realization-led chart choices) is a **feature to preserve**, not verbosity to strip. A single fixed house-style block was the wrong answer (it makes every deck look the same).

**Superseded 2026-07-26 — the two-pass condense was solving a problem that did not exist.** The old design here was: pass 1 generates a rich ~11–16K prompt, pass 2 compresses it to ≤3700 so the final paste fits "the 5000-char cap." That cap turned out to be a client-side `maxlength` attribute, bypassable with the native value setter, and a 10,054-char prompt was proven to transport and store intact end-to-end (fix #5). The compression was therefore pure self-inflicted loss — and it degraded design exactly where you'd predict: the condense obeyed "keep every mandatory slide **by name**" by keeping the *names* and discarding the per-slide visual direction, leaving ~168 chars/slide of stub while the grounding rule sat restated 6×.

**Current design — one pass, no ceiling:**
1. **The Gem generates the full, rich, dynamic prompt** with concrete per-slide visual direction (hero chart, encodings, annotations, KPI tiles). Target ~5–9K chars. Nothing compresses it.
2. **§1.5 prepends** the data-fidelity + units + framework-coverage addendum.
3. **§4/§5 write it in with the native value setter** (never `Control+V`, which *is* clipped at 5000).

**Removing the compression did not by itself fix the design (2026-07-26, second finding).** With the cap gone, prompts went 3.7–5.3K → 17–21K, yet decks still rendered white and generic. Three causes, none of them length: (1) **no canvas binding** — the prompts declared `Primary: #hex` and applied it only to charts; the word "background" appeared **zero** times in IEX's 21K prompt, so NotebookLM fell back to its white template; (2) **Tailwind collapse** — the Gem template's slot hints ("forest green family", "restrained red", "light grey") steered it to stock UI values, and FRACTAL/TANLA/IEX all emitted the identical triad `#10B981`/`#EF4444`/`#94A3B8` (emerald-500/red-500/slate-400), with FRACTAL's whole palette Tailwind; (3) **declare-once dilution** — DLF (May, characterful) referenced its hexes **35 times** across the prompt, re-applying the colour grammar per chart and per slide; the July prompts reference 7 hexes **once** in a header block. **The A/B on the hex-level fix DID NOT RUN — the Gem was degenerate (2026-07-26, third finding).** Canvas binding + a ban naming ten Tailwind hexes + per-slide restatement were put in the §1 pass-1 prompt and IEX Q1 FY27 was re-submitted four times. **Not one attempt produced a generation for IEX:**
- On **Flash**: two byte-identical 16,187-char replies — the Gem's own blank template, 9 unfilled `[Company Name]`/`[Ticker]`/`[#hex]` placeholders, zero hexes.
- On **3.1 Pro**: two byte-identical 17,106-char replies whose subject is **Kaynes Technology India Limited (KAYNES, Capital Goods / EMS)** — not IEX, not the requested company at all. The second of these was the reply to a *different* message, so the Gem was not reading the user turn.
- No reply in any attempt carried the `NOTEBOOKLM_PROMPT:` marker.

**Do not conclude from this that hex direction fails to transport — that test never happened.** An earlier version of this note claimed the A/B disproved hexes; it did not, because the response it measured was the KAYNES text rather than an IEX generation. The origin of the KAYNES echo is unresolved: `KAYNES` appears 0× in the local `gem_ppt_instructions.txt` snapshot, but per the sync task that snapshot is **not auto-refreshed from live Gemini** and may be stale relative to the live Gem's actual instructions.

**REPRODUCED 3/3 — the PPT Gem is currently returning KAYNES prompts for every ticker (2026-07-26 ~18:00).** Three different tickers, each in a **brand-new** Gem thread, on Gemini **Pro**:

| asked for | sector | reply length | names own company? | mentions KAYNES? |
|---|---|---|---|---|
| IEX | power exchange | 17,106 | no | yes |
| MEDANTA | hospitals | 12,768 | no | yes |
| SULA | wine / consumer | 15,205 | no | yes |

The three lengths differ, so the Gem **is** generating fresh text each time — it just substitutes Kaynes Technology India Limited (Capital Goods / EMS) as the subject. None carried the `NOTEBOOKLM_PROMPT:` marker, so the output-format contract is broken too. **Ruled out:** thread contamination (fresh threads), Flash (this was Pro), and the local instruction snapshot (`KAYNES` appears **0×** in `gem_ppt_instructions.txt`). **Most likely:** the live Gem's instructions have drifted from the local snapshot — the sync task explicitly notes the snapshot is *not* auto-refreshed from live Gemini — or Gemini cross-chat memory is anchoring on a past KAYNES run. Verify by opening the live Gem's own instructions; the Gems list menu (`/gems/view`) offered only "Make a copy" / "Delete", so the editor has to be reached another way.

**Blast radius: none so far.** An audit of all archived `*_ppt.txt` on 2026-07-26 found **16/16 real prompts naming their own ticker and 0 suspect** (the 25 sub-300-char files are the separate, already-known May/June capture failures). The Gem produced correct company-specific prompts at 10:36 / 10:52 / 11:08 (INDUSINDBK, FRACTAL, IEX) and was degenerate by ~13:30, so **the KAYNES fault began after 11:08 on 2026-07-26** and no shipped deck is affected. Re-run the audit before trusting any deck generated after that point.

**SUPERSEDED 2026-10-11 — design is now delegated to NotebookLM via a COMPANY DESIGN BRIEF (see Architecture).** The idiom notes below are kept only as history and as evidence that NotebookLM honours *semantic* design direction. Do NOT inject a named idiom, ground treatment or hex palette any more, and do not audit prompts for them.

**Former approach — DESIGN IDIOM, not hex values (2026-07-26, user's proposal).** Direction is given as one established design language chosen per company/sector (Swiss, Editorial, blueprint, Terminal, Industrial, Clinical, Isometric, Heritage), with colour expressed as ROLES and temperament rather than swatches. Rationale — argued on the merits, **not** on A/B evidence, which does not yet exist either way: an idiom is a *semantic* instruction, which is the only lever a generative slide tool plausibly exposes (NotebookLM takes no stylesheet); one idiom term carries more coherent design information than 3K chars of hand-specification, because the model has seen many internally-consistent examples of it; and it varies the deck's *structure* per sector rather than repainting one fixed 7-slot template — which is what "every deck looks the same" was really about, given DLF's 35 hex refs and IEX's 7 produced the same *kind* of deck. Isometric is constrained to structure/flow slides only (isometric financial charts are illegible), and legibility always overrides the idiom. **Audit a new prompt for a named idiom + a ground treatment, NOT for hex counts.**

**IDIOM APPROACH VALIDATED END-TO-END (2026-07-26).** Tested in the IEX notebook (`6cbd46ac`), which already held a same-day baseline deck ("IEX Q1 FY27 Performance Analysis") built from the old-style prompt — so sources, notebook and Format/Length defaults were held constant and the prompt was the only variable. The Gem was bypassed (it was returning KAYNES for every ticker), and a **2,594-char hand-authored idiom prompt** was written straight into the Customize textarea with the native value setter: *Terminal / data-dense dark*, ground stated, colour as roles, monospace numerals, small-multiples and bridge chart forms, per-slide restatement, legibility override.

Result deck: **"IEX Q1 FY27 Strategic Teardown"**. NotebookLM honoured the idiom **substantially**:
- **Ground: near-black graphite on ~5 of 6 slides observed** — cover, exec summary, guidance tracker, results-vs-street, key risks. The white default was broken.
- **Cover** rendered as a depth-of-market order-flow ladder with terminal chrome (`STATUS: LIVE`, `TICKER: NSE:IEX` in an amber-outlined box) — nothing like the old cover.
- **Colour roles held**: amber accent reserved for the focal number, phosphor green for positive deltas, red/amber for risk (`CERC COUPLING IMPACT: HIGH RISK`, `REGULATORY STATUS: PENDING`).
- **Typography**: monospace numerals and tabular blocks throughout, numerals dominant.
- **Chart forms followed direction**: RTM-vs-DAM step-area small-multiples rather than default vertical bars; a spread/divergence rail for Results vs Street.
- **Grounding rule respected**: labelled comparisons (`Q1 FY26: 32.4 BU` under `37.5 BU +15.9% YoY`).

**Known limitation — ground consistency is partial.** The *Sector KPI Deep-Dive* slide reverted to a light ground while its neighbours stayed dark. Most likely the model applying the prompt's own **"LEGIBILITY OVERRIDES STYLE"** clause to the densest chart slide — i.e. arguably correct behaviour, not a failure. If uniform darkness is wanted, narrow that clause to "raise contrast within the dark field; do not switch to a light ground" and lean harder on per-slide restatement.

**Conclusion: idiom-level direction transports; hex-level direction was never shown to.** Evidence images: `stockwatch/reports/IEX_deck_BEFORE.png`, `IEX_deck_AFTER*.png`.

**Also discovered: the Customize dialog has a native `Format` control** — "Detailed Deck" (comprehensive, full text) vs **"Presenter Slides" (clean, visual)** — plus a Length control (Short / Default). These were left at defaults for this A/B and are an **untested, possibly larger lever on the "text-heavy / ugly text" complaint than any prompt wording.** Test Presenter Slides next.

§1.4 survives only as a **de-duplication** step for prompts above ~9000 — it removes text stated twice, never the company design brief, a slide, a Q&A exchange or per-slide content direction. Length is not a target; instruction density is.

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
   **The echo guard MUST also catch square-bracket placeholders (2026-07-26).** The observed template echo does NOT contain `<the prompt to paste...>` — it comes back as the Gem's own design-system template carrying `[Company Name]`, `[Ticker]`, `[Sector / Sub-sector]`, `[#hex]`, `[1–2 line description...]`. Treat the response as a FAILED generation if **any** of these hold: (a) no `NOTEBOOKLM_PROMPT:` marker present; (b) `/\[(Company Name|Ticker|Sector|#hex)\]/` matches; (c) the count of `[...]`-style placeholders is `>= 3`. Two consecutive Flash replies passed the old guard on 2026-07-26 — byte-identical 16,187-char template echoes with 9 unfilled placeholders and zero hex values — which is exactly how a default-template deck gets produced from an apparently-successful run. **Also assert the PPT prompt carries the 2026-10-11 essentials before pasting:** (1) a company design brief (`/COMPANY DESIGN BRIEF|design brief/i`), (2) a full-Q&A instruction (`/every analyst|each analyst|all analyst/i`), and (3) a connect-the-dots instruction (`/connect(ing)? the dots|new disclosures|industry signals/i`). If any is missing, do NOT re-ask the Gem: the §1.5 fixed addendum carries all three anyway, so note `gem: missing-<n>` and continue. Do **not** assert on idiom names, ground treatment or hex counts any more. If the Gem still emits hex codes or a named idiom despite the override, that's tolerated, because the §1.5 DESIGN clause at position 0 tells NotebookLM to follow the brief rather than fixed styling.
   **WRONG-COMPANY GUARD (mandatory, 2026-07-26).** The Gem has been observed returning a fully-formed, rich, placeholder-free prompt **for an entirely different company** — a 17,106-char Kaynes Technology (EMS) prompt in reply to a request for IEX, twice, including as the reply to a message that never mentioned Kaynes. Nothing else in this pipeline would catch that: it has real content, real hexes, no placeholders, and would paste and generate cleanly — producing a KAYNES deck inside the IEX notebook. **Before pasting, assert the body mentions the expected company**: derive the expected name from `STOCK_NAME`, and require the ticker or a distinctive token of its company name to appear in the body. If a *different* known watchlist company appears instead, treat it as `failed`, start a FRESH thread, and do not paste. Run each ticker in its own fresh Gem thread rather than reusing one.

**Model matters: keep the PPT Gem off Flash.** The echo above happened on **Gemini Flash**. Switching the mode picker to **3.1 Pro** made the Gem generate real content on the next try. Check the picker (`aria-label="Open mode picker, currently …"`) at the start of a run and switch off Flash if needed.
2. `browser_press_key` **`Control+C`** (copies the selection via the real clipboard). **Confirm the copy** by reading `navigator.clipboard.readText().then(t => t.length)` (or re-select+re-copy if it reads empty) BEFORE removing the hidden textarea — a failed copy here is invisible until the paste comes up blank two steps later. Then remove the hidden textarea.
3. **In the NotebookLM tab**, open the Customize dialog, **wait for** its textarea to render, **click** it to focus, then `browser_press_key` **`Control+V`**. Verify `textarea.value.length` ≈ the copied length; if `< 50`, retry steps 1–3 once. **If still `< 50`, last-resort fallback: re-fetch the body from the archived `B:\...\prompts\` file and inject via chunked `execCommand('insertText')`.** Only if THAT also fails to populate the textarea do you abort and mark the ticker `failed`. Never click Generate on a short/blank textarea.
This uses the *entire* search-grounded Gem prompt (no condensing) and costs ~0 prompt tokens.

## Per-ticker procedure

Tickers run **sequentially**, but they no longer share state — each writes only to its own notebook.

### 0. Design approach — NotebookLM designs from a company brief (2026-10-11)

**No style override lookup any more.** `styles.py` / `styles/<TICKER>.md` are retired (the files stay on disk as history, but do not run `styles.py get` and do not inject their IDIOM blocks). The look of every deck is now created by NotebookLM itself from the COMPANY DESIGN BRIEF that the PPT Gem writes in §1. This lets NotebookLM's own, now much stronger, design engine pick styling and visual elements that resonate with what the company actually does.

`style_checked` is still a `mark done` gating field, so record that the design step was resolved:
```
python db.py checklist-set <TICKER> style_checked 1
python db.py checklist-set <TICKER> style_idiom "notebooklm-native (company design brief)"
```

### 1. Capture both Gem prompts (dynamic, search-grounded)

**Pass 1: generate the full, rich, DYNAMIC prompt.** There is **no length limit anywhere in this pipeline** — the 5000-char cap was disproven on 2026-07-26 (fix #5). The Gem must produce the COMPANY DESIGN BRIEF plus the complete content, with **per-slide content direction** (what the slide must prove, which data the visual must show), not just slide names. It must NOT prescribe styling. §1.4 runs only for genuine redundancy above ~9000.

**The live PPT Gem's own instructions still contain the old DESIGN IDIOM / colour-grammar / typography system, and a Q&A slide limited to "2–3 analyst questions".** The pass-1 message below explicitly overrides both. Keep the override paragraphs verbatim until the live Gem's instructions are updated (local snapshot: `stockwatch/gem_ppt_instructions.txt`).

Open the PPT Gem, remove any "Deep research" chip, submit:
```
Expand the Indian stock ticker <TICKER> to its full company name. Then generate a NotebookLM prompt that will produce a polished, visually rich PPT presentation summarising <QUARTER> <FY> results for that company.

OVERRIDE OF YOUR BUILT-IN DESIGN SYSTEM (mandatory): do NOT specify a design idiom, colour palette, hex values, colour roles, typefaces, page-ground treatment or a fixed layout grammar. Skip every such section of your template. NotebookLM's own slide designer now does this better than a hand specification, and fixed styling makes every deck look alike.

COMPANY DESIGN BRIEF (mandatory, put it near the top of the prompt under exactly this heading): in 4-6 lines, describe the company the way a designer needs to know it. Cover what it actually does and how it earns money, its physical and operational world (plants, ships, hospitals, vineyards, data centres, branches, trains...), its products and customers, and its brand personality and heritage. Then add this instruction to NotebookLM, verbatim: "Create your own visual style and visual elements for this deck: imagery, motifs, iconography, colour mood, textures and chart choices that clearly reflect this company's business and resonate with the work it does, so the deck could not be mistaken for any other company's. Apply it consistently across every slide. Do not fall back to a plain generic template. Legibility of numbers and charts always comes first."

PER-SLIDE DIRECTION: for EVERY slide, state what the slide must prove and exactly which data the visual must show (which metrics, which periods, what comparison, what to call out). Leave chart styling, colours and layout to NotebookLM. A slide reduced to a name is a failure.

The deck must focus strictly on <QUARTER> <FY>. Older material in the notebook (prior quarters' results, transcripts, Deep Research reports and Analyst Summary notes) is for trend, correlation and accountability, and the prompt must tell NotebookLM to USE it actively. Specifically: build the trend slides from the prior-quarter sources; score management's earlier promises against this quarter; and compare this quarter's commentary with what was said before.

GROUNDING RULE (state it in the prompt): every figure must be the ACTUAL reported figure for <QUARTER> <FY> from the uploaded sources; prior-period numbers only in explicitly labelled comparisons (e.g. "Q1 FY26: X vs Q1 FY27: Y"); write "not disclosed" if a figure is absent — never carry an older quarter's number as the current one.

UNITS RULE (state it in the prompt): all rupee amounts must be expressed in CRORES as "₹X cr" (Indian convention) — never millions or billions; convert if a source quotes mn/bn (₹1 cr = ₹10 mn). Percentages, margins and per-share figures stay as reported.

MANDATORY SLIDES (the prompt must name each, with the specific things it must contain): Cover; Executive Summary & variant perception; Quarter-over-Quarter & Year-over-Year trend (target quarter vs immediately-preceding quarter vs same quarter last year, each period labelled, plus a multi-quarter trend line from the older sources in the notebook); Management Guidance Tracker (prior-quarter promises from the older sources vs this quarter's actuals, DELIVERED/PARTIAL/MISSED); Sector/company KPI deep-dive — SPLIT ACROSS AS MANY CONSECUTIVE SLIDES AS THE KPI LIST REQUIRES, at most ~4 distinct KPIs per slide (a single slide asked to hold a ten-item pack silently drops most of it); Concall Q&A — COMPLETE (see below); New Disclosures & Industry Signals — Connecting the Dots (see below); Results vs Street (beat/miss vs consensus, rating/target changes); Key Risks (from MD&A/transcript); So-What summary.

CONCALL Q&A — NO COMPRESSION (overrides your template's "2-3 analyst questions"): the prompt must instruct NotebookLM to cover EVERY analyst question in the <QUARTER> <FY> concall transcript, not a selection. For each exchange show the analyst (name/firm if given), the question, the substance of management's answer with key figures, and the tone (direct / hedged / deflected), plus any hedge words or first-time disclosures. Do not merge, summarise away or drop exchanges; continue across as many "(cont.)" slides as needed. Link any hedged answer to a live commitment from the Guidance Tracker.

NEW DISCLOSURES & INDUSTRY SIGNALS — CONNECTING THE DOTS: the prompt must ask NotebookLM to pull out anything NEW in this quarter's concall and filings. That includes first-time metrics or disclosures, new targets, and any industry-specific guideline, regulation, policy, pricing or demand signal management cited (e.g. a regulator's new norm, a tariff or duty change, a sector capacity trend). For each item, connect it to what the notebook's older sources and prior Analyst Summaries said, and state whether it CONFIRMS, ACCELERATES, or REVERSES the multi-quarter trend, and what it implies for the next 2-4 quarters.

NO SLIDE LIMIT AND NO CONTENT TRIMMING (state this explicitly in the prompt): the headings above are a FLOOR, not a ceiling. There is no maximum slide count; the deck runs as long as the material requires. NEVER drop, merge, abbreviate or summarise away a required item, KPI, guidance line or Q&A exchange to fit a slide budget. If material does not fit, ADD ANOTHER SLIDE and continue on a "(cont.)" slide. Completeness outranks brevity and visual neatness in every case.

There is NO character limit on your output; do not self-censor for length. State each rule exactly ONCE.

Respond in exactly this format and nothing else: STOCK_NAME: <full company name> --- NOTEBOOKLM_PROMPT: <the full prompt to paste into NotebookLM Studio Customize Slide Deck>
```
Then the Audio Gem:
```
Expand the Indian stock ticker <TICKER> to its full company name. Then generate a NotebookLM Audio Overview prompt that will produce a polished Hindi audio briefing summarising <QUARTER> <FY> results for that company. Give it a delivery style suited to this company/sector.

Focus strictly on <QUARTER> <FY>. The notebook's older sources and prior-quarter Analyst Summary notes must be USED for trend, for tracking earlier promises against delivery, and for comparing commentary with what was said before.

GROUNDING RULE (state it in the prompt): every figure must be the ACTUAL reported <QUARTER> <FY> number from the sources; older-period figures only in explicitly labelled comparisons; never present a prior quarter's number as the current one.

UNITS RULE (state it in the prompt): all rupee amounts must be spoken in CRORES ("X करोड़ रुपये") — never millions or billions; convert if a source quotes mn/bn (₹1 cr = ₹10 mn). Percentages, margins and per-share figures stay as reported.

MUST COVER, by name: headline financials with QoQ & YoY deltas (each period labelled); management guidance/outlook and prior promises vs delivery; the concall Q&A IN FULL. Cover every analyst question with management's answer, tone and any soft guidance; do not pick a subset, and do not compress it to save time. Also cover new disclosures and industry-specific signals from the concall, connected to the multi-quarter trend: does each one confirm, accelerate or reverse it? End with the forward risks. No length cap: the briefing runs as long as the material needs.

Respond in exactly this format and nothing else: STOCK_NAME: <full company name> --- NOTEBOOKLM_AUDIO_PROMPT: <the full prompt to paste into NotebookLM Studio Customize Audio Overview>
```

**Submit the prompt** by filling the Quill composer (`.ql-editor.textarea`) via `focus()` + `execCommand('insertText', …)` (NOT the textarea setter — see Performance principles), then click the **Send** button (`aria-label*="Send"`).

**Completion check (robust):** poll until the Stop button is gone AND the response length is stable across two consecutive polls (a streaming reply transiently contains `---`). Gems can take 30–60s; poll patiently.

**Measure pass-1 length in-page** (return just the char count, never the body). If the full PPT prompt is ≤9000 chars — the usual case at ~5–8K — **skip §1.4 entirely and go straight to transfer.** There is no 5000-char ceiling to fit inside (fix #5): the native value setter writes the whole thing. Only run §1.4 when pass 1 exceeds ~9000.

### 1.4 De-duplication pass — ONLY when pass 1 is >9000 chars (in-page, same Gem thread)

**This is NOT a compress-to-fit step. Do not invoke it to hit a character budget.** Since 2026-07-26 we know the 5000 cap is client-side and bypassable, so the prompt is never trimmed to fit a limit. The only reason to shorten is that *genuinely redundant* text dilutes attention — the archived pre-fix prompts restated the grounding rule 6× while giving each slide ~168 chars. We cut the repetition, never the design.

The full pass-1 prompt already lives in the Gem thread's own context, so the Gem can rework it with nothing entering Claude's context. Send as a **second message** to the SAME Gem thread:
```
Rewrite the NOTEBOOKLM_PROMPT you just produced to remove redundancy ONLY. Do NOT compress to a character target and do NOT summarise. PRESERVE IN FULL, losing no detail: (1) the COMPANY DESIGN BRIEF and its instruction for NotebookLM to create its own company-resonant visual style; (2) EVERY slide with its full content direction (what it must prove, which data the visual shows); (3) the complete-Q&A instruction (every analyst question) and the New Disclosures & Industry Signals / connecting-the-dots slide; (4) the instruction to use prior-quarter sources and Analyst Summaries; (5) the no-slide-limit rule; (6) the data-grounding rule; (7) the units rule (all rupee amounts in crores, "₹X cr"). CUT ONLY: any instruction stated more than once (state it exactly once), "non-negotiable"/"mandatory" filler restatements, and any leftover palette/hex/typeface/idiom specification (styling is delegated to NotebookLM). Aim for maximum instruction density per character; length is otherwise unconstrained. Reply with ONLY this and nothing else: NOTEBOOKLM_PROMPT_DEDUPED: <the rewritten prompt>
```
Poll for completion (same robust check). Measure in-page. **A result in the 5–9K range is a good outcome — do not push it lower.** If it comes back under ~3500, the Gem over-compressed and gutted the design: send `That lost per-slide content direction. Restore every slide's full direction, every Q&A instruction and the company design brief, removing only literally repeated sentences. Length is not constrained.` Run the Audio Gem's dedupe identically (audio has no visual theme to protect; it is usually already short enough to skip).

**Slice the prompt into the hidden transfer textarea** (do NOT archive yet — §1.5 prepends the data-fidelity addendum first, and the archive must reflect the final text). In-page: slice after `NOTEBOOKLM_PROMPT:` (or `NOTEBOOKLM_PROMPT_DEDUPED:` if §1.4 ran), stop before "Gemini is AI", put it in a hidden `<textarea>` on `document.body`, and return only `STOCK_NAME` + the length. Same for audio. §1.5 then runs the framework check, prepends the addendum, and hands off to the paste.

**Clipboard is no longer the transfer mechanism for the paste.** `Control+V` is a user edit and *is* clipped at 5000 by `maxlength` (fix #5). Carry the body in the hidden textarea and write it into the NotebookLM field with the native value setter instead. The clipboard copy is now only useful for the local archive step.

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
   DESIGN (non-negotiable): Do not use a plain generic template. Read the COMPANY DESIGN BRIEF below and CREATE YOUR OWN visual style and visual elements (imagery, motifs, iconography, colour mood, textures, chart choices) that clearly reflect what this company does and resonate with its business. Apply it consistently on every slide. If anything below specifies fixed colours, hex values, fonts or a named design style, treat it only as a hint; the company brief governs. Legibility of numbers and charts always wins.
   COMPLETENESS (non-negotiable): There is NO slide limit; use as many slides as the material needs and continue on "(cont.)" slides rather than dropping anything. (a) Use ALL sources in this notebook: the older quarters' results, transcripts, Deep Research reports and Analyst Summary notes drive the multi-quarter trend, the promise-vs-delivery tracker, and the comparison of this quarter's commentary with earlier commentary. (b) Cover EVERY analyst question from the <QUARTER> <FY> concall Q&A (analyst, question, management's answer with figures, tone/hedging) with no merging or compression. (c) Include a "New Disclosures & Industry Signals — Connecting the Dots" section. List every new disclosure, new target, and industry-specific guideline, regulation, policy, pricing or demand signal raised in the concall, connect each to what earlier quarters' sources said, and state whether it confirms, accelerates or reverses the trend and what it implies for the next 2-4 quarters.
   ```
   (Omit the COVERAGE line entirely when no framework items are missing.) Replace `<QUARTER> <FY>` with the literal target quarter, e.g. `Q1 FY27`. The FIDELITY, UNITS, DESIGN and COMPLETENESS clauses are fixed text and are **never trimmed**. DESIGN and COMPLETENESS (2026-10-11, replacing the old idiom VISUAL clause) sit in the position-0 addendum deliberately. That guarantees the company-resonant design delegation, prior-source usage, full Q&A and connect-the-dots slide reach NotebookLM even if the Gem drops them. Position 0 is the highest-attention slot in the prompt. For the AUDIO body, inject FIDELITY, UNITS and only items (a)-(c) of COMPLETENESS, reworded as "cover" rather than "slides"; never inject DESIGN into audio. **The COVERAGE line is NEVER capped and NEVER trimmed** (changed 2026-07-30; the old ~350-char cap and its `overlay > concall-essentials > sector > universal` trim priority are both removed). It carries EVERY missing framework item in full, however long that runs. That cap only ever existed because the textarea was believed to truncate at 5000 chars — disproven by fix #5 — so trimming required coverage was pure self-inflicted loss. A trimmed coverage item is precisely an item the deck then silently omits, which is the failure mode §5.8 exists to catch.

   **Length check (informational only — there is NO 5000 ceiling; see fix #5):** compute `total = addendum.length + body.length` and note `budget: <total>`. Nothing is trimmed on the basis of this number. Flag only the two genuine outliers: **under ~2500** means the Gem or a dedupe pass gutted the design — go back to §1.4's "restore per-slide detail" retry; **over ~16000** is worth a single dedupe pass for attention-dilution reasons (and slower generation), not for any transport limit. Never blind code-trim the tail: that amputates whatever sits last, which was the original 2026-07-23 bug.
   After prepending, write the final text into the hidden textarea. Note `framework: +<key>+<key>` for the report.
5. **Never fatal:** if the framework file is unreadable or the evaluate errors, log `framework: skipped` and prepend ONLY the data-fidelity clause to the condensed body (skip just the coverage addendum — the fidelity clause is not framework-dependent). A missing framework check must never fail a ticker or block generation.
6. The archived `_ppt.txt`/`_audio.txt` should be written AFTER the prepend so the archive reflects exactly what was pasted (fidelity addendum + condensed dynamic prompt).
7. Record that this step ran: `python db.py checklist-set <TICKER> framework_checked 1`. Do this regardless of the outcome noted in the report (`framework: ok` / `+<keys>` / `skipped` / `unmapped-<TICKER>`) — the checklist flag means the check was *performed*, not that every item was found; a genuine `framework: skipped` (point 5) still counts as checked because the fallback (fidelity-clause-only) ran in its place.

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

Record the number of new sources added this run (post-import count minus pre-import count): `python db.py checklist-set <TICKER> sources_added <N>`. Informational only — never gates `mark done`.

### 3.5 Put ALL prior context in play — notes → sources, select every source (mandatory, 2026-10-11)

**Why (user requirement):** the per-ticker notebook holds earlier quarters' results, transcripts, Deep Research reports and Analyst Summary notes. These exist so the current deck can trend, track promises and connect dots. NotebookLM silently ignores two kinds of material: **sources whose checkbox is unticked**, and **Studio notes that were never converted to sources**. A deck can therefore look complete while having ignored every prior quarter.

1. **Notes → sources.** In Studio, list the saved notes (do not read their bodies into context). For each note that is a prior **Analyst Summary**, or any other analyst note the user saved, open its menu and click **Convert to source** (§5.5 step 3 explains the real click target). If the notes menu offers **Convert all notes to source**, use that once instead. Skip notes that are already sources. Never delete notes.
2. **Select every source.** In the Sources panel, make sure the **Select all sources** checkbox is ticked. Then verify in ONE `browser_evaluate`, returning only two numbers: `total` (source rows) and `checked` (rows whose checkbox is checked). If `checked < total`, tick Select all again (unticking then re-ticking if it was in a partial state) and re-verify.
3. **Prior-context sanity check.** Confirm at least one source from an EARLIER quarter is present. Match the source titles in-page against the previous quarter label and return only a boolean; also count `Deep Research Report` sources ≥ 2 once the notebook has history. On a first-ever run for a ticker, note `prior: none (new notebook)` — this is legitimate.
4. Note `context: <checked>/<total> selected, notes→sources +<n>, prior: yes|none` for the report. Not a gating field, but **never click Generate while `checked < total`** — retry once, and if it still won't select, note it in the report and proceed.

### 4. Slide Deck — generate AND verify

Open **Studio**, close any open artifact, click the **Slide Deck** row, then **Customize Slide Deck** (`aria-label === 'Customize Slide Deck'`).

**WAIT for the dialog's `<textarea>` to actually exist before writing.** After clicking Customize Slide Deck, `browser_wait_for` (or poll with `browser_evaluate` returning a bool) until the dialog `<textarea>` (placeholder matches `/outline/`) is present and visible — Angular renders it a tick late, and writing into a not-yet-rendered (or already-dismissed) dialog is the **`textarea_gone` failure** that silently produced default-template decks.

**Write with the native value setter — NOT `Control+V`** (fix #5: paste is a user edit and gets clipped at 5000 by `maxlength`, silently losing the tail of every rich prompt):
```js
const ta = [...document.querySelectorAll('textarea')].find(t=>/outline/i.test(t.placeholder||''));
const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype,'value').set;
setter.call(ta, body);                              // body from the hidden transfer textarea
ta.dispatchEvent(new Event('input',{bubbles:true})); // REQUIRED — Angular ignores the value without it
```
The `input` event is mandatory: without it Angular's model never sees the text and Generate submits an empty prompt.

**HARD-ABORT if the write did not land.** Re-read `textarea.value.length` and confirm it **equals the length you set** (not merely >0 — a 5000 exactly when you wrote more means something clipped it; investigate before generating). If it is `< 50`, **retry the full write once**. If it is **still `< 50` after the retry, DO NOT click Generate** — a blank/short prompt yields NotebookLM's generic default-quality deck (this is exactly what made the bad recent decks). Instead: close the dialog, record `failed` for this ticker, and continue. Never generate a deck whose prompt textarea didn't verify full. Save the verified length to `B:\...\prompts\<TICKER>_<Q>_ppt.txt` (a real char count like `len=4416`, never an error string like `textarea_gone` — if you're about to write an error string, that IS the abort signal).

**CONTENT-SURVIVAL CHECK (last-line sanity check).** Read the textarea value once and confirm it contains at least one content token — `/transcript|Q&A|Q & A|guidance tracker|risks/i`. This should always pass now, but if it fails, do NOT Generate: the Gem dropped substance or the write clipped. Re-write once and re-check. If it still fails, record `failed` and continue — a gutted deck is worse than none.

**POST-HOC PROOF OF WHAT THE SERVER STORED (optional, and the only way to audit this).** Once the deck is ready, open it and click **"View prompt and N sources"** — this panel renders the prompt NotebookLM actually kept. Verifying the tail of your prompt appears there is definitive proof nothing truncated end-to-end. Use it whenever you suspect clipping, or after any change to the write mechanism. (This is how the 2026-07-26 10,054-char test was proven.)

**Set Format and Length for maximum content BEFORE generating (2026-07-30).** The dialog exposes a
`Format` control — **"Detailed Deck"** (comprehensive, full text) vs "Presenter Slides" (clean, visual) —
and a `Length` control (Short / Default). Because content must never be trimmed, select **Detailed Deck**
and the **longest** Length offered (currently `Default`; if a longer option such as `Long` appears, take
it). Verify both read as intended before Generate — "Presenter Slides" and `Short` both actively
suppress content and must not be used for these decks.

Once the textarea verifies full AND passes the content-survival check, click **Generate**. Then **VERIFY START**: within ~20s a new Slide Deck artifact row should appear in the Studio list (or a "generating" state for it). If no new artifact appears and/or an error/quota toast shows → **retry once** (re-open Customize Slide Deck, re-wait, re-fill, Generate). If it still fails, record `failed` and continue to the next ticker — do NOT mark done.

**VERIFY COMPLETION — a started generation is NOT a finished one (2026-08-03 fix).** A real run (DLF, Q1 FY27, 2026-08-03) was marked `done` on the strength of "Generating Slide Deck…" status text — confirmation that generation had *started*, not that it *finished*. Checked a few minutes later, the deck had actually failed ("Slide Deck generation failed. Try a new one.") while the DB still said `done`; a `done` ticker is never retried, so this would have silently persisted forever. Do not repeat that: after the start-check above, **poll the Studio list in ≤270s windows for up to ~10 min total** until the artifact leaves its generating state — watch for EITHER a completed, openable artifact row (spinner/"Generating…" label gone) OR an explicit failure signal (a toast or row text such as "Slide Deck generation failed. Try a new one."). Do not stop after one status read; keep polling to a terminal state.
- **Finished successfully** → `python db.py checklist-set <TICKER> deck_generated 1` then `python db.py checklist-set <TICKER> deck_verified_complete 1`, and continue to §5.
- **SOURCE-USAGE PROOF (mandatory, 2026-10-11).** Open the finished deck and read the count `N` from its **"View prompt and N sources"** label. Return only the number. Compare it with §3.5's `total`. If `N < total`, the deck ignored part of the notebook, usually the prior quarters: note `sources-used: N/total`. Then fold a fix into the single §5.7/§5.8 regeneration (re-run §3.5 step 2 first, then regenerate). If `N == total`, note `sources-used: all`.
- **Finished with a failure signal** → retry once (re-open Customize Slide Deck, re-wait, re-fill, Generate, re-poll to a terminal state). If it fails again → record `failed` and continue to the next ticker. Do **not** set `deck_verified_complete`.
- **Still generating when the ~10 min budget is spent** → do not guess at success. Do not set `deck_verified_complete`; note the unresolved state in the report and either take one more poll window before moving on, or fall through to `failed` if the run must proceed. Only set `deck_verified_complete` on a terminal state you actually observed.

### 5. Audio Overview — Hindi, generate AND verify

Click **Customize Audio Overview**. In one evaluate: open the `mat-select`, pick the option containing `हिन्दी`, **then re-read the select's displayed value and confirm it shows हिन्दी** (if not, retry the selection). **WAIT for the dialog's `<textarea>` to exist** (same Angular-render race as §4), then write the audio prompt in with the **native value setter + `input` event** exactly as §4 — never `Control+V` (fix #5). **Verify `textarea.value.length` equals what you set; retry the write once if short, and if still short DO NOT click Generate** — record `failed` rather than queue a blank-prompt audio. **Also apply the same content-survival check as §4** (last-line sanity check): confirm the surviving value contains `/transcript|Q&A|Q & A|guidance|risks/i`; if not, re-run the §1.4 audio condense once before generating. Once verified full and content-survived, click **Generate**. **VERIFY START**: a new Audio Overview artifact appears; retry once on failure. Audio language MUST be Hindi — if it cannot be set, record `failed` rather than generating English.

**VERIFY COMPLETION — same "started ≠ finished" fix as §4 (2026-08-03).** Poll the Studio list in ≤270s windows for up to ~10 min total until the audio artifact reaches a terminal state (openable artifact with a Devanagari/Hindi title, OR an explicit failure signal). A "generating" status is not sufficient to proceed.
- **Finished successfully AND confirmed Hindi (Devanagari title, not English)** → `python db.py checklist-set <TICKER> audio_generated 1` then `python db.py checklist-set <TICKER> audio_verified_complete 1`.
- **Finished but in English, or a failure signal** → retry once (re-select हिन्दी, re-fill, Generate, re-poll to terminal). If it fails again → record `failed` and continue. Do **not** set `audio_verified_complete`.
- **Still generating past the ~10 min budget** → do not set `audio_verified_complete`; note it unresolved rather than assume success.

### 5.5 Persist a carry-forward "Analyst Summary" source (best-effort, non-blocking)

**Purpose.** Carry this quarter's *analytical narrative* into future quarters as a compact, auditable text source — grounded in **this** quarter's primary sources (transcript + Deep Research), NOT by recycling the generated deck/audio. Because the notebook is never wiped, the note persists and becomes trend/correlation context next quarter. (Every generation prompt is already quarter-scoped and treats older material as correlation-only, so a prior-quarter summary is context, never mistaken for the target quarter's data — see fix #11/#13 on why more sources ≠ better; this adds exactly ONE small text source per quarter.)

**This step runs AFTER deck and audio are confirmed queued and is BEST-EFFORT: it must NEVER downgrade a good run.** If any part fails, log `summary: skipped` and still proceed to `mark <TICKER> done`. Do NOT mark the ticker `failed` because the summary step failed.

**Idempotency (re-run guard).** The auto-generated source title does NOT reliably contain "Analyst Summary" (see step 3) — matching `/Analyst Summary/i` against `.source-title` elements is unreliable. Instead: open the most-recently-added note-derived source (its title is content-generated but still identifiable as the newest Studio note/source, "Xd ago"), and read its first line. If it already reads `<TICKER> <QUARTER> <FY> — Analyst Summary`, SKIP this whole step — never create a duplicate summary for the same quarter. A summary already existing for this quarter still counts as saved: `python db.py checklist-set <TICKER> summary_saved 1`.

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
4. **VERIFY.** Re-read the source count (`document.querySelectorAll('.source-title').length` before vs. after) — it should have risen by exactly 1. If it did → note `summary: saved` and `python db.py checklist-set <TICKER> summary_saved 1`. If not, retry steps 2-3 once; if still not, note `summary: skipped` and leave `summary_saved` at its default (do not set it) — continue regardless. **Either way, proceed to §6 and mark `done` if deck+audio succeeded.** `summary_saved` is informational only and is never part of the `mark done` gate.

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
6. Record `python db.py checklist-set <TICKER> dataaudit_run 1` for every outcome EXCEPT `dataaudit: skipped` (`ok`/`regenerated`/`no-baseline`/`pending` all mean the audit executed as designed). Leave it at its default on `skipped` — that is the honest signal that it didn't run. Informational only; never part of the `mark done` gate.

### 5.8 Coverage audit — did the deck actually carry everything? (best-effort, non-blocking)

**Why (2026-07-30, user requirement: content must NEVER be trimmed).** Instructions alone do not
guarantee coverage, because omission is **silent** — the deck looks complete and well-designed while
quietly missing KPIs. Measured on HCLTECH: a single KPI deep-dive slide was asked for 11 KPIs, rendered
4, and dropped 7 with no error, no warning and nothing any existing check would flag. §5.7 audits
whether the *numbers* are right; this audits whether the *required items are present at all*.

**When:** after the deck artifact has finished (reuse §5.7's completion poll — do not poll twice).
Best-effort: it never un-marks a `done` and never gates §6. Report as `coverage:`.

1. **Build the required-item list** — the same set §1.5 evaluated: universal essentials +
   concall essentials + the ticker's sector pack + its overlay row from `framework.md`. Use each item's
   regex, not its prose phrase. **Always add three 2026-10-11 items:**
   `qa_full` = `/Q&A|Q & A|analyst question|question.{0,20}answer/i` must match on **at least 2 slides** (one Q&A slide for a full concall means it was compressed; screenshot it to check before acting); `dots` = `/new disclosure|industry signal|connect(ing)? the dots|regulat|policy|guideline/i`; `trend_prior` = `/trend|QoQ|YoY|vs\.? Q[1-4]|over (the )?(last|past)/i`.
2. **Extract the deck text in ONE `browser_evaluate`** and test every regex against it in-page.
   Return ONLY the missing item keys — short strings, never the deck text.

   **HOW to extract (essential — slides are IMAGES, 2026-07-30).** Rendered slides are
   `lh3.googleusercontent.com` images, so there is no slide text in the DOM and canvas pixel
   sampling is blocked by CORS. The usable text layer is each slide image's **`alt` attribute**,
   which NotebookLM populates with a one-line description naming that slide's subject and metrics
   (e.g. *"Overview of cost of funds, net interest margin expansion, and liability management
   strategies for Q1 FY27."*). Collect them, de-duplicate (thumbnail and main view repeat the same
   image), and run the regexes over the concatenation:
   ```js
   () => Array.from(new Set(Array.from(document.querySelectorAll('img'))
           .map(i => i.alt || '').filter(a => a.length > 20))).join(' | ')
   ```
   This also yields a free slide-by-slide map and an accurate **slide count** for the report.

   **Treat it as a strong proxy, not proof — the false-negative rate is HIGH.** Alt text runs ~100
   chars per slide, so it summarises hard. A HIT is reliable (the item is definitely covered); a MISS
   is frequently WRONG.

   **Measured on HOMEFIRST 2026-07-30:** the audit reported 4 missing items. Opening the actual slide
   showed `cost of borrowings` (7.6%, in the spread chart) and `collection efficiency` (98.3%, its own
   panel) both plainly present, and `capital adequacy` sat on the next slide - so **3 of 4 "misses"
   were false negatives**, from a single alt line ("KPI deep-dive into spread dynamics, asset quality
   metrics, and credit cost trends") standing in for a slide carrying five distinct KPIs.

   Two consequences, both mandatory:
   - **ALWAYS screenshot the relevant slide before acting on a miss.** Never regenerate on alt text
     alone; you will usually be regenerating a deck that was already complete.
   - **Write the regexes to match PROSE, not just tickers-of-art.** `/GNPA|NNPA|stage.?3/` misses the
     phrase "asset quality metrics"; include the plain-English form (`/asset quality/`) for every item.
     Several apparent gaps in the first audit were purely this.
3. **Interpret:**
   - Nothing missing → `coverage: ok`.
   - 1+ items missing → **regenerate once**, re-writing the archived `_ppt.txt` prompt with a
     corrective line at position 0:
     `CRITICAL FIX: the previous deck omitted <keys>. Include EVERY one of these, ADDING SLIDES as
     needed — there is no slide limit. Do not drop or merge any other existing content to make room.`
     Note `coverage: regenerated (+<keys>)`. Do NOT delete the first deck; newest wins.
   - Deck unreadable or still generating past budget → `coverage: skipped` / `coverage: pending`.
4. **One corrective pass only** — never loop. If items are still missing after the regeneration, note
   `coverage: unresolved (<keys>)` in the report so a human sees exactly what the deck lacks. That is
   the honest outcome; silently accepting a thin deck is not.
5. This audit shares its regeneration budget with §5.7. If BOTH a fidelity fix and a coverage fix are
   needed, do **one** regeneration whose corrective line carries both instructions.
6. Record `python db.py checklist-set <TICKER> coverage_audit_run 1` for every outcome EXCEPT
   `coverage: skipped` (`ok`/`regenerated`/`unresolved`/`pending` all mean the audit executed). Leave it
   at its default on `skipped`. Informational only; never part of the `mark done` gate.

### 6. Record outcome

Only if BOTH deck and audio were confirmed queued **and their generation was verified complete, not merely started** (§4/§5's `deck_verified_complete`/`audio_verified_complete` checklist writes — the carry-forward summary in §5.5 and the §5.7/§5.8 audits are NOT gating conditions):
```
python db.py mark <TICKER> done
```
**`mark done` fails closed.** It reads this ticker+quarter's checklist and REFUSES — prints the missing fields, exits non-zero, leaves the ticker's status unchanged — unless `style_checked`, `framework_checked`, `deck_verified_complete` and `audio_verified_complete` are all set. `sources_added`, `summary_saved`, `dataaudit_run` and `coverage_audit_run` are never checked by the gate, matching the best-effort/non-blocking language in §5.5/§5.7/§5.8.

**If `mark done` refuses, that is a signal to go back and finish the missing step — never a reason to force it another way.** Do not hand-edit the DB, do not call `mark done` again hoping it passes, and do not paper over a refusal by calling `mark failed` as a substitute without actually knowing why the step is incomplete. Run `python db.py checklist <TICKER>` to see exactly what's missing, then either complete that step for real or record `failed` if the underlying step genuinely can't be completed this run.

Otherwise (deck or audio not verified complete) `python db.py mark <TICKER> failed` (it will auto-retry on the next routine run).

### 7. Report
One line per ticker:
```
✓ <TICKER> (<STOCK_NAME>) — notebook: <created|reused>, sources +<N>, condense: <full→condensed chars>, framework: ok|+<keys>|skipped, budget: ok(<total>), design: notebooklm-native, context: <checked>/<total> prior:yes|none, sources-used: all|<N>/<total>, slides: <N>, deck: queued✓+verified✓, audio (हिन्दी): queued✓+verified✓, summary: saved✓|skipped, dataaudit: ok|regenerated|pending|no-baseline|skipped, coverage: ok|regenerated(+<keys>)|unresolved(<keys>)|pending|skipped, checklist: ready|blocked(<missing>)
```
On failure, state which ticker, which step, and that it was marked `failed` for retry. (A `summary: skipped` is NOT a failure — deck+audio still make the run a `done`.)

## Things to be careful about

- **Use Playwright MCP, not Claude in Chrome** (server-side block on notebooklm.google.com).
- **NEVER `browser_snapshot`** on NotebookLM/Gemini.
- **Remove the "Deep research" chip** on the Gems before submitting.
- **No wipe, ever** — one notebook per ticker; sources are additive. Cross-contamination is now impossible.
- **Quarter-scope every prompt** — the notebook holds multiple quarters.
- **Verify both generations *complete*, not just start** (§4/§5, 2026-08-03) — "Generating…" status text is not proof of success; PPT generation has been observed to fail silently after appearing to start (DLF, Q1 FY27), so poll to a terminal state before setting `deck_verified_complete`/`audio_verified_complete`.
- **`mark done` fails closed on a per-run checklist (2026-08-03)** — it refuses unless `style_checked`, `framework_checked`, `deck_verified_complete` and `audio_verified_complete` are all recorded via `checklist-set` for this ticker+quarter. A refusal means go finish the missing step, not force the mark another way. `checklist <TICKER>` shows what's missing.
- **Design is NotebookLM-native (§0/§1, 2026-10-11).** Give NotebookLM a COMPANY DESIGN BRIEF plus an instruction to create its own company-resonant style; never dictate palette, hex, fonts or idiom. `styles.py` is retired.
- **Prior context must be selected and used (§3.5).** Convert notes to sources, tick every source, and prove it from the deck's "View prompt and N sources" count.
- **Concall Q&A is never compressed.** Every analyst question is covered, across as many "(cont.)" slides as needed; the live Gem's "2-3 questions" default is overridden in §1 and again in the §1.5 COMPLETENESS clause.
- **Connect the dots.** Each deck has a New Disclosures & Industry Signals slide tying new information and industry guidelines from the concall to the multi-quarter trend.
- **Carry-forward summary (§5.5) is best-effort** — never mark a ticker `failed` because it failed, and never let it delay/replace deck+audio. It is ONE small text source per quarter; do not recycle the generated deck/audio as sources (drift + contamination).
- **Hindi is mandatory** and must be confirmed set before Generate.
- **Pro source cap is 300/notebook** (~30 quarters). Prune only years out.
- **Auth / 2FA / quota** mid-run: stop and report, don't retry-loop or attempt to authenticate.
- **Pass the Gem's FULL rich prompt — there is no length limit (proven 2026-07-26).** The "5000-char cap" is a client-side `maxlength`; the native value setter bypasses it and a 10,054-char prompt was verified stored intact server-side via the deck's "View prompt" panel (fix #5). So: Gem writes a rich ~5–9K prompt with per-slide visual direction (§1), §1.5 prepends the fidelity+units addendum, §4/§5 write it in with the **native setter, never `Control+V`** (paste *is* clipped). §1.4 is now only a de-dup step above ~9000. Never blind-trim in code. The old condense-to-3700 is retired — it was the cause of the flat, stub-slide decks, not a fix for them.
- **CONTENT IS NEVER TRIMMED AND THERE IS NO SLIDE LIMIT (user requirement, 2026-07-30).** As many slides as the material requires — 20+ is fine and correct. Nothing in this pipeline may shorten *content* to fit anything: the COVERAGE line has no cap (§1.5, `framework.md`), the transport has no ceiling (fix #5, native setter), and the mandatory-slide list is a FLOOR that must be split across extra slides rather than compressed (§1 — a single slide given a ten-item sector pack drops most of it silently). The **only** permitted shortening anywhere is §1.4's redundancy removal, which may delete text stated twice and design *rationale* prose — it may **never** delete a slide, a KPI, a coverage item, or per-slide visual direction, and must never be run to hit a character target. Because omission is silent, §5.8 verifies coverage after the fact and regenerates once with the missing keys named; a `coverage: unresolved` line in the report is preferable to a tidy deck that quietly lacks half its KPIs.
- **Units: ALWAYS crores, never millions (user requirement, 2026-07-25).** Indian investors read ₹ cr; a deck quoting "₹4,200 mn" is harder to sanity-check against screener/broker notes. The UNITS clause is injected unconditionally in §1.5 alongside DATA FIDELITY, is also stated in both §1 Gem prompts, and is on the §1.4 condense PRESERVE list — three layers, because the condense pass is what historically dropped things. Lakh is acceptable ONLY where the company itself reports in lakh (e.g. capacity in lakh MTPA). Percentages, margins and per-share figures are untouched.
- **Data fidelity (§1.5 clause + §5.7 audit)** — figures in the deck must be the target quarter's ACTUAL reported numbers; prior-period figures only in explicitly labelled comparisons. The §5.7 audit is best-effort and never gates `done`, but a `dataaudit: regenerated|pending|skipped` should be visible in the report so a human can spot-check.
- **Framework check (§1.5) is additive-only and never fatal** — a `framework: skipped` run still generates; a framework gap must never mark a ticker `failed`. Keep `framework.md`'s ticker→sector map current when the watchlist changes.
