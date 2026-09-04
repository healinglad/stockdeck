#!/usr/bin/env python3
"""Local tracking DB for the stockdeck auto-routine.

Tracks, per fiscal quarter, which watchlist tickers have already had a
NotebookLM deck + Hindi audio generated, so the daily 9AM check never
re-runs the stockdeck flow for a company that's already covered.

Usage (run with the project's Python):
  python db.py init                  # create schema + seed watchlist + default quarter
  python db.py quarter               # print the current target quarter
  python db.py set-quarter "Q1 FY27" # change the target quarter
  python db.py pending               # tickers NOT yet done for current quarter (one per line)
  python db.py all                   # every watchlist ticker (one per line)
  python db.py slug <TICKER>         # print stored screener slug for a ticker
  python db.py set-slug <TICKER> <SLUG>
  python db.py get-notebook <TICKER> # print this ticker's NotebookLM notebook id ('' if none yet)
  python db.py set-notebook <TICKER> <NOTEBOOK_ID>  # store the per-ticker notebook id
  python db.py mark <TICKER> <status>      # status: done | failed | skipped
                                            # 'done' REFUSES unless the checklist's gating
                                            # fields are all set for this ticker+quarter (see below)
  python db.py seed-done <T1,T2,...>       # bulk-mark done for current quarter
  python db.py status                # summary counts for current quarter
  python db.py report                # full per-ticker status table for current quarter
  python db.py checklist-set <TICKER> <field> <value>  # record a per-run step outcome
  python db.py checklist <TICKER>    # show this ticker's checklist for the current quarter

Checklist fields (per ticker+quarter, written by SKILL.md as each step completes):
  GATING (all must be truthy before 'mark done' succeeds):
    style_checked, framework_checked, deck_verified_complete, audio_verified_complete
  NON-GATING (best-effort / informational; 'mark done' never checks these):
    style_idiom (text), sources_added (int), deck_generated, audio_generated,
    summary_saved, dataaudit_run, coverage_audit_run
  Boolean values accept 1/0, true/false, yes/no (case-insensitive).
"""
import sqlite3
import sys
import os
from datetime import datetime, timezone

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stockdeck.db")
DEFAULT_QUARTER = "Q1 FY27"

# Checklist fields written by SKILL.md as each step of a run completes.
# GATING fields are required (truthy) before `mark done` is allowed to succeed.
# NON-GATING fields are best-effort / informational only — never checked by `mark`.
CHECKLIST_BOOL_FIELDS = {
    "style_checked", "framework_checked", "deck_generated", "deck_verified_complete",
    "audio_generated", "audio_verified_complete", "summary_saved", "dataaudit_run",
    "coverage_audit_run",
}
CHECKLIST_INT_FIELDS = {"sources_added"}
CHECKLIST_TEXT_FIELDS = {"style_idiom"}
CHECKLIST_FIELDS = CHECKLIST_BOOL_FIELDS | CHECKLIST_INT_FIELDS | CHECKLIST_TEXT_FIELDS
CHECKLIST_GATING_FIELDS = [
    "style_checked", "framework_checked", "deck_verified_complete", "audio_verified_complete",
]

# Watchlist as provided by the user. Keys are the canonical ticker; the
# screener slug defaults to the ticker and can be overridden via set-slug.
# Two entries given as prose names are mapped to their NSE symbols.
WATCHLIST = [
    # Replace with your own NSE/BSE tickers. Sample shown:
    "RELIANCE", "TCS", "HCLTECH", "TATAELXSI", "BLUESTARCO",
    "CMSINFO", "TRENT", "MANKIND", "IEX", "NH",
]


def conn():
    c = sqlite3.connect(DB_PATH)
    c.execute("PRAGMA journal_mode=WAL")
    return c


def now():
    return datetime.now(timezone.utc).isoformat()


def init():
    c = conn()
    c.executescript(
        """
        CREATE TABLE IF NOT EXISTS config (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS watchlist (
            ticker TEXT PRIMARY KEY,
            screener_slug TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS done (
            ticker TEXT NOT NULL,
            quarter TEXT NOT NULL,
            status TEXT NOT NULL,          -- done | failed | skipped
            ts TEXT NOT NULL,
            PRIMARY KEY (ticker, quarter)
        );
        CREATE TABLE IF NOT EXISTS checklist (
            ticker TEXT NOT NULL,
            quarter TEXT NOT NULL,
            style_checked INTEGER NOT NULL DEFAULT 0,
            style_idiom TEXT NOT NULL DEFAULT '',
            framework_checked INTEGER NOT NULL DEFAULT 0,
            sources_added INTEGER NOT NULL DEFAULT 0,
            deck_generated INTEGER NOT NULL DEFAULT 0,
            deck_verified_complete INTEGER NOT NULL DEFAULT 0,
            audio_generated INTEGER NOT NULL DEFAULT 0,
            audio_verified_complete INTEGER NOT NULL DEFAULT 0,
            summary_saved INTEGER NOT NULL DEFAULT 0,
            dataaudit_run INTEGER NOT NULL DEFAULT 0,
            coverage_audit_run INTEGER NOT NULL DEFAULT 0,
            updated_ts TEXT,
            PRIMARY KEY (ticker, quarter)
        );
        """
    )
    # migration: per-ticker NotebookLM notebook id (one notebook per ticker)
    cols = [r[1] for r in c.execute("PRAGMA table_info(watchlist)").fetchall()]
    if "notebook_id" not in cols:
        c.execute("ALTER TABLE watchlist ADD COLUMN notebook_id TEXT")
    for t in WATCHLIST:
        c.execute(
            "INSERT OR IGNORE INTO watchlist(ticker, screener_slug) VALUES (?, ?)",
            (t, t),
        )
    c.execute(
        "INSERT OR IGNORE INTO config(key, value) VALUES ('quarter', ?)",
        (DEFAULT_QUARTER,),
    )
    c.commit()
    n = c.execute("SELECT COUNT(*) FROM watchlist").fetchone()[0]
    q = c.execute("SELECT value FROM config WHERE key='quarter'").fetchone()[0]
    c.close()
    print(f"initialized: {n} tickers in watchlist, current quarter = {q}")


def get_quarter(c):
    return c.execute("SELECT value FROM config WHERE key='quarter'").fetchone()[0]


def cmd_quarter():
    c = conn()
    print(get_quarter(c))
    c.close()


def set_quarter(q):
    c = conn()
    c.execute(
        "INSERT INTO config(key, value) VALUES ('quarter', ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (q,),
    )
    c.commit()
    c.close()
    print(f"quarter set to {q}")


def pending():
    c = conn()
    q = get_quarter(c)
    rows = c.execute(
        "SELECT w.ticker FROM watchlist w "
        "WHERE NOT EXISTS (SELECT 1 FROM done d WHERE d.ticker=w.ticker "
        "AND d.quarter=? AND d.status IN ('done','skipped')) "
        "ORDER BY w.ticker",
        (q,),
    ).fetchall()
    c.close()
    for (t,) in rows:
        print(t)


def all_tickers():
    c = conn()
    for (t,) in c.execute("SELECT ticker FROM watchlist ORDER BY ticker"):
        print(t)
    c.close()


def slug(ticker):
    c = conn()
    r = c.execute(
        "SELECT screener_slug FROM watchlist WHERE ticker=?", (ticker,)
    ).fetchone()
    c.close()
    print(r[0] if r else "")


def set_slug(ticker, s):
    c = conn()
    c.execute(
        "UPDATE watchlist SET screener_slug=? WHERE ticker=?", (s, ticker)
    )
    c.commit()
    c.close()
    print(f"{ticker} slug -> {s}")


def get_notebook(ticker):
    c = conn()
    r = c.execute(
        "SELECT notebook_id FROM watchlist WHERE ticker=?", (ticker,)
    ).fetchone()
    c.close()
    print(r[0] if r and r[0] else "")


def set_notebook(ticker, nb):
    c = conn()
    c.execute(
        "UPDATE watchlist SET notebook_id=? WHERE ticker=?", (nb, ticker)
    )
    c.commit()
    c.close()
    print(f"{ticker} notebook -> {nb}")


def _checklist_row(c, ticker, q):
    cols = [
        "style_checked", "style_idiom", "framework_checked", "sources_added",
        "deck_generated", "deck_verified_complete", "audio_generated",
        "audio_verified_complete", "summary_saved", "dataaudit_run",
        "coverage_audit_run", "updated_ts",
    ]
    row = c.execute(
        f"SELECT {', '.join(cols)} FROM checklist WHERE ticker=? AND quarter=?",
        (ticker, q),
    ).fetchone()
    return dict(zip(cols, row)) if row else None


def checklist_set(ticker, field, value):
    if field not in CHECKLIST_FIELDS:
        print(f"unknown checklist field: {field}")
        print(f"valid fields: {', '.join(sorted(CHECKLIST_FIELDS))}")
        sys.exit(1)
    if field in CHECKLIST_BOOL_FIELDS:
        v = value.strip().lower()
        if v in ("1", "true", "yes"):
            stored = 1
        elif v in ("0", "false", "no"):
            stored = 0
        else:
            print(f"bad boolean value for {field}: {value!r} (use 1/0/true/false/yes/no)")
            sys.exit(1)
    elif field in CHECKLIST_INT_FIELDS:
        try:
            stored = int(value)
        except ValueError:
            print(f"bad integer value for {field}: {value!r}")
            sys.exit(1)
    else:
        stored = value
    c = conn()
    q = get_quarter(c)
    c.execute(
        "INSERT INTO checklist(ticker, quarter) VALUES (?,?) "
        "ON CONFLICT(ticker, quarter) DO NOTHING",
        (ticker, q),
    )
    c.execute(
        f"UPDATE checklist SET {field}=?, updated_ts=? WHERE ticker=? AND quarter=?",
        (stored, now(), ticker, q),
    )
    c.commit()
    c.close()
    print(f"{ticker} [{q}] checklist.{field} -> {stored}")


def cmd_checklist(ticker):
    c = conn()
    q = get_quarter(c)
    row = _checklist_row(c, ticker, q)
    c.close()
    print(f"== {ticker} [{q}] checklist ==")
    if row is None:
        print("(no checklist row yet — nothing recorded for this ticker+quarter)")
        row = {f: (0 if f in CHECKLIST_BOOL_FIELDS else "") for f in CHECKLIST_FIELDS}
    else:
        for k, v in row.items():
            print(f"{k:24} {v}")
    missing = [g for g in CHECKLIST_GATING_FIELDS if not row.get(g)]
    if missing:
        print(f"-- NOT ready for `mark done`: missing {', '.join(missing)}")
    else:
        print("-- ready for `mark done`")


def mark(ticker, status):
    assert status in ("done", "failed", "skipped"), f"bad status {status}"
    c = conn()
    q = get_quarter(c)
    if status == "done":
        row = _checklist_row(c, ticker, q)
        missing = [g for g in CHECKLIST_GATING_FIELDS if not (row and row.get(g))]
        if missing:
            print(
                f"REFUSED: {ticker} [{q}] cannot be marked done — "
                f"checklist incomplete: {', '.join(missing)}"
            )
            print(
                f"Run `python db.py checklist {ticker}` to inspect, finish the "
                "missing step(s) in SKILL.md, then retry. Status left unchanged."
            )
            c.close()
            sys.exit(1)
    c.execute(
        "INSERT INTO done(ticker, quarter, status, ts) VALUES (?,?,?,?) "
        "ON CONFLICT(ticker, quarter) DO UPDATE SET status=excluded.status, ts=excluded.ts",
        (ticker, q, status, now()),
    )
    c.commit()
    c.close()
    print(f"{ticker} [{q}] -> {status}")


def seed_done(csv):
    c = conn()
    q = get_quarter(c)
    tickers = [t.strip() for t in csv.split(",") if t.strip()]
    for t in tickers:
        c.execute(
            "INSERT INTO done(ticker, quarter, status, ts) VALUES (?,?,?,?) "
            "ON CONFLICT(ticker, quarter) DO UPDATE SET status=excluded.status, ts=excluded.ts",
            (t, q, "done", now()),
        )
    c.commit()
    c.close()
    print(f"seeded {len(tickers)} tickers as done for {q}: {', '.join(tickers)}")


def status():
    c = conn()
    q = get_quarter(c)
    total = c.execute("SELECT COUNT(*) FROM watchlist").fetchone()[0]
    done_n = c.execute(
        "SELECT COUNT(*) FROM done WHERE quarter=? AND status='done'", (q,)
    ).fetchone()[0]
    failed_n = c.execute(
        "SELECT COUNT(*) FROM done WHERE quarter=? AND status='failed'", (q,)
    ).fetchone()[0]
    c.close()
    print(f"quarter={q}  total={total}  done={done_n}  failed={failed_n}  pending={total-done_n}")


def report():
    c = conn()
    q = get_quarter(c)
    rows = c.execute(
        "SELECT w.ticker, COALESCE(d.status,'pending'), COALESCE(d.ts,'') "
        "FROM watchlist w LEFT JOIN done d "
        "ON d.ticker=w.ticker AND d.quarter=? ORDER BY w.ticker",
        (q,),
    ).fetchall()
    c.close()
    print(f"== {q} ==")
    for t, st, ts in rows:
        print(f"{t:14} {st:8} {ts}")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    cmd = sys.argv[1]
    a = sys.argv[2:]
    if cmd == "init":
        init()
    elif cmd == "quarter":
        cmd_quarter()
    elif cmd == "set-quarter":
        set_quarter(a[0])
    elif cmd == "pending":
        pending()
    elif cmd == "all":
        all_tickers()
    elif cmd == "slug":
        slug(a[0])
    elif cmd == "set-slug":
        set_slug(a[0], a[1])
    elif cmd == "get-notebook":
        get_notebook(a[0])
    elif cmd == "set-notebook":
        set_notebook(a[0], a[1])
    elif cmd == "mark":
        mark(a[0], a[1])
    elif cmd == "checklist-set":
        checklist_set(a[0], a[1], a[2])
    elif cmd == "checklist":
        cmd_checklist(a[0])
    elif cmd == "seed-done":
        seed_done(a[0])
    elif cmd == "status":
        status()
    elif cmd == "report":
        report()
    else:
        print(f"unknown command: {cmd}")
        print(__doc__)


if __name__ == "__main__":
    main()
