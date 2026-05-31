# stockdeck

Automated pipeline that turns an Indian-market quarterly result into a **NotebookLM slide deck + a Hindi audio overview**, driven end-to-end by browser automation.

Give it a ticker and a fiscal quarter (e.g. `RELIANCE Q4 FY26`) and it:

1. Asks two purpose-built **Gemini Gems** to write fresh, search-grounded NotebookLM prompts — one for a slide deck, one for a Hindi audio briefing.
2. Drives **NotebookLM** (via the Playwright MCP) using **one persistent notebook per ticker** — adding each quarter's sources via Deep Research (never deleting), so the notebook accumulates a multi-quarter history for YoY/QoQ correlation.
3. Generates both the **Slide Deck** and the **Hindi Audio Overview**, and verifies each actually started before recording success.

A companion daily routine checks screener.in for newly-released concall transcripts and runs the pipeline automatically for any watchlist ticker whose results are out.

## Architecture

```mermaid
flowchart TB
    U["Manual run<br/>/stockdeck TICKER Q4 FY26"]
    CRON["Daily 9 AM routine<br/>(stockdeck-auto-check)"]
    SCR["screener.in<br/>concall transcript check"]
    DB[("stockdeck.db<br/>SQLite tracker")]

    CRON -->|read pending tickers| DB
    CRON --> SCR
    U --> RUN
    SCR -->|transcript READY| RUN

    subgraph PIPE["stockdeck skill — driven via Playwright MCP"]
        RUN(["run pipeline"])
        PPTG["PPT Gem<br/>Gemini"]
        AUDG["Audio Gem<br/>Gemini"]
        DR["Deep Research<br/>Discover sources"]
        NB["NotebookLM<br/>one notebook per ticker"]
        RUN --> PPTG
        RUN --> AUDG
        RUN --> DR
        PPTG -->|deck prompt| NB
        AUDG -->|Hindi audio prompt| NB
        DR -->|transcripts, results,<br/>PPTs, broker notes| NB
    end

    NB --> DECK["Slide Deck"]
    NB --> AUDIO["Hindi Audio Overview"]
    RUN -->|mark done / failed| DB
```

- **Sources** come from NotebookLM **Deep Research** ("Discover"), which finds transcripts, results, investor presentations and broker notes for the quarter.
- **Grounding is strict** — both Gems instruct NotebookLM to ground every claim in the uploaded documents and to say "not disclosed" rather than estimate.
- **Prompts never enter the agent's context** — each Gem's output is moved Gemini → NotebookLM over the OS clipboard, so the multi-KB prompt body costs ~zero tokens.

## How it works

### Per-ticker run

```mermaid
sequenceDiagram
    participant A as Agent (skill)
    participant G as Gemini Gems
    participant N as NotebookLM
    participant D as db.py

    A->>D: get-notebook TICKER
    A->>G: prompt PPT Gem (ticker + quarter)
    G-->>A: STOCK_NAME + slide-deck prompt
    Note over A,G: prompt copied to OS clipboard (not into context)
    A->>N: open or create notebook
    A->>N: Deep Research "Discover"
    N-->>A: import sources (additive, never wiped)
    A->>N: Customize Slide Deck -> paste -> Generate
    A->>N: verify deck started (retry once)
    A->>G: prompt Audio Gem
    G-->>A: Hindi audio prompt
    A->>N: Customize Audio Overview (Hindi) -> paste -> Generate
    A->>N: verify audio started (retry once)
    A->>D: mark TICKER done (only if BOTH queued)
```

### Daily auto-check routine

```mermaid
flowchart TD
    START["Daily run"] --> Q{"pending empty<br/>for this quarter?"}
    Q -->|yes| HIB["Hibernate until<br/>the quarter rolls over"]
    Q -->|no| LOOP["Next pending ticker"]
    LOOP --> CHK{"transcript on screener.in<br/>dated in quarter window?"}
    CHK -->|no| LOOP
    CHK -->|yes| RUN["Run stockdeck skill"]
    RUN --> MARK["mark done / failed"]
    MARK --> CAP{"3 READY completed<br/>this run?"}
    CAP -->|yes| STOPN["Stop — rest stay pending<br/>for the next run"]
    CAP -->|no| LOOP
```

The quarter → reporting-window mapping (with a late-reporter tolerance month) is:

| Target quarter | Concall months accepted |
|----------------|-------------------------|
| Q1 FY*yy*      | Jul / Aug / Sep 20*(yy-1)* |
| Q2 FY*yy*      | Oct / Nov 20*(yy-1)* |
| Q3 FY*yy*      | Jan / Feb / Mar 20*yy* |
| Q4 FY*yy*      | Apr / May / Jun / Jul 20*yy* |

## Repo contents

| Path | What it is |
|------|------------|
| `SKILL.md` | The full automation skill — the step-by-step playbook the agent follows, including field-tested fixes for the NotebookLM / Gemini UIs. |
| `db.py` | Local SQLite tracker: per-quarter watchlist, per-ticker notebook IDs, and done/failed status so the routine never re-runs a covered ticker. |
| `gems/ppt_gem.md` | System instruction for the **PPT** Gemini Gem (the slide-deck prompt generator). |
| `gems/audio_gem.md` | System instruction for the **Audio** Gemini Gem (the Hindi briefing prompt generator). |

## Setup (bring your own accounts)

This is a personal automation; to run it you supply your own:

- A Google account signed into **Gemini** and **NotebookLM** (NotebookLM Pro recommended — 300 sources/notebook).
- Two **Gemini Gems** created from `gems/ppt_gem.md` and `gems/audio_gem.md`; put their Gem URLs into `SKILL.md`.
- The **Playwright MCP** (`@playwright/mcp`) pointed at a Chromium profile that's already signed into Google.
- Python 3 for `db.py`. Initialise with `python db.py init`, then edit the `WATCHLIST` to your own tickers.

### db.py quick reference

```
python db.py init                  # create schema + seed watchlist + default quarter
python db.py pending               # tickers not yet done for the current quarter
python db.py set-quarter "Q1 FY27" # roll over to a new quarter (resets pending)
python db.py get-notebook TICKER   # this ticker's NotebookLM notebook id
python db.py mark TICKER done       # record outcome (done | failed | skipped)
python db.py status                # summary counts for the current quarter
```

> The Gem prompt instructions in `gems/` are the interesting part — they're reusable on their own for anyone generating institutional-grade equity research prompts.

## Note

Built for personal use to track an Indian-equity watchlist. No warranty; not investment advice.
