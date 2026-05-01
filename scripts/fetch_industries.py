"""
fetch_industries.py
-------------------
Scrapes Finviz Group Screener (Industry / Performance view) and writes:
  - data.json     : current snapshot used by the heatmap / picks / top10 views
  - history.json  : appended daily snapshot used by the "Where is the puck going?" view

Schema produced (matches what static/app.js expects):

data.json = {
  "fetched_at": "2026-05-01T08:00:00Z",
  "industries": {
    "<Industry Name>": {
      "ticker":       "<finviz industry slug, used to build ind_xxx URL>",
      "perfs":  { "1D": 0.42, "1W": 1.2, "1M": 5.4, "3M": -1.2, "YTD": 8.0 },
      "ranks":  { "1D": 12,   "1W": 4,   "1M": 1,   "3M": 33,   "YTD": 8  },
      "composite": 5.4,                # weighted rank: 1M*0.7 + 1W*0.2 + 3M*0.1
      "acceleration": 29               # 3M-rank minus 1W-rank
    },
    ...
  }
}

history.json = [
  { "date": "2026-04-30", "scores": { "<Industry>": { "c": <composite>, "t": <ticker> }, ... } },
  ...
]
"""

from __future__ import annotations

import datetime as dt
import json
import re
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

FINVIZ_URL = "https://finviz.com/groups.ashx?g=industry&v=140"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# Finviz Performance view (v=140) column order. The first column is "No.",
# the second is "Name" (industry name), then performance columns:
PERF_COLS = ["1W", "1M", "3M", "6M", "1Y", "YTD", "1D"]
# We only keep the ones the frontend uses:
KEEP_TFS = ["1D", "1W", "1M", "3M", "YTD"]

# Score weights from app.js (line 263, infoScore tooltip)
WEIGHT_1M = 0.70
WEIGHT_1W = 0.20
WEIGHT_3M = 0.10

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_FILE = REPO_ROOT / "data.json"
HISTORY_FILE = REPO_ROOT / "history.json"
HISTORY_KEEP_DAYS = 120


# ---------------------------------------------------------------------------
# Scraping
# ---------------------------------------------------------------------------

def fetch_html(url: str, retries: int = 3, delay: float = 2.0) -> str:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
    }
    last_err: Optional[Exception] = None
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(url, headers=headers, timeout=30)
            r.raise_for_status()
            return r.text
        except Exception as e:
            last_err = e
            print(f"[fetch] attempt {attempt} failed: {e}", file=sys.stderr)
            if attempt < retries:
                time.sleep(delay * attempt)
    raise RuntimeError(f"failed to fetch {url}: {last_err}")


def slugify_industry(name: str) -> str:
    """
    Convert industry display name into the Finviz `ind_xxx` slug used in
    screener URLs. Finviz uses lowercase, no spaces, no punctuation.
    Example: 'Semiconductors' -> 'semiconductors'
             'Drug Manufacturers - General' -> 'drugmanufacturersgeneral'
    """
    s = name.lower()
    s = re.sub(r"[^a-z0-9]+", "", s)
    return s


def parse_pct(cell: str) -> Optional[float]:
    """Turn '+1.23%' / '-0.45%' / '-' into a float or None."""
    if not cell or cell.strip() in ("-", "", "—"):
        return None
    m = re.search(r"-?\d+\.?\d*", cell.replace(",", ""))
    if not m:
        return None
    try:
        return float(m.group(0))
    except ValueError:
        return None


def scrape_finviz() -> Dict[str, dict]:
    """
    Returns: { "<Industry Name>": {"ticker": "...", "perfs": {tf: pct}}, ... }
    """
    html = fetch_html(FINVIZ_URL)
    soup = BeautifulSoup(html, "html.parser")

    # Finviz wraps the data table in a `table.styled-table-new` element,
    # but historically the structure has shifted. Find the table that
    # contains "Name" and "Perf Week" in its header.
    target_table = None
    for tbl in soup.find_all("table"):
        header_text = tbl.get_text(" ", strip=True)[:200].lower()
        if "name" in header_text and ("perf week" in header_text or "perf month" in header_text):
            target_table = tbl
            break

    if target_table is None:
        raise RuntimeError("could not locate Finviz industry table")

    rows = target_table.find_all("tr")
    if len(rows) < 2:
        raise RuntimeError("industry table has no data rows")

    # Identify column positions from the header row
    header_cells = [c.get_text(strip=True) for c in rows[0].find_all(["th", "td"])]

    def col_index(*candidates: str) -> Optional[int]:
        for i, h in enumerate(header_cells):
            for c in candidates:
                if c.lower() in h.lower():
                    return i
        return None

    idx = {
        "name": col_index("Name"),
        "1D":   col_index("Perf Day", "Change"),
        "1W":   col_index("Perf Week"),
        "1M":   col_index("Perf Month"),
        "3M":   col_index("Perf Quart"),
        "YTD":  col_index("Perf YTD"),
    }
    if idx["name"] is None:
        raise RuntimeError(f"could not find Name column in headers: {header_cells}")

    industries: Dict[str, dict] = {}
    for tr in rows[1:]:
        cells = [c.get_text(strip=True) for c in tr.find_all(["td", "th"])]
        if not cells or idx["name"] >= len(cells):
            continue
        name = cells[idx["name"]]
        if not name:
            continue

        perfs: Dict[str, Optional[float]] = {}
        for tf in KEEP_TFS:
            ci = idx.get(tf)
            perfs[tf] = parse_pct(cells[ci]) if (ci is not None and ci < len(cells)) else None

        industries[name] = {
            "ticker": slugify_industry(name),
            "perfs":  perfs,
        }

    if not industries:
        raise RuntimeError("parsed zero industries")

    return industries


# ---------------------------------------------------------------------------
# Ranking + score
# ---------------------------------------------------------------------------

def compute_ranks_and_scores(industries: Dict[str, dict]) -> None:
    """Mutates `industries` in place, adding ranks / composite / acceleration."""
    n = len(industries)

    # rank within each timeframe (1 = highest perf)
    for tf in KEEP_TFS:
        ordered = sorted(
            industries.items(),
            key=lambda kv: (kv[1]["perfs"].get(tf) is None, -(kv[1]["perfs"].get(tf) or 0)),
        )
        for rank, (name, _) in enumerate(ordered, start=1):
            industries[name].setdefault("ranks", {})[tf] = rank

    # composite score and acceleration
    for name, row in industries.items():
        r = row["ranks"]
        row["composite"]    = WEIGHT_1M * r["1M"] + WEIGHT_1W * r["1W"] + WEIGHT_3M * r["3M"]
        row["acceleration"] = r["3M"] - r["1W"]


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------

def update_history(industries: Dict[str, dict], today_iso: str) -> List[dict]:
    history: List[dict] = []
    if HISTORY_FILE.exists():
        try:
            history = json.loads(HISTORY_FILE.read_text())
            if not isinstance(history, list):
                history = []
        except json.JSONDecodeError:
            history = []

    # Build today's snapshot — only what computeMovers() needs (composite + ticker)
    snapshot = {
        "date": today_iso,
        "scores": {
            name: {"c": row["composite"], "t": row["ticker"]}
            for name, row in industries.items()
        },
    }

    # Replace today's entry if it already exists (re-run on same day)
    history = [h for h in history if h.get("date") != today_iso]
    history.append(snapshot)
    history.sort(key=lambda h: h["date"])

    # Trim to last N days
    if len(history) > HISTORY_KEEP_DAYS:
        history = history[-HISTORY_KEEP_DAYS:]

    return history


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print(f"[scrape] fetching {FINVIZ_URL}")
    industries = scrape_finviz()
    print(f"[scrape] got {len(industries)} industries")

    compute_ranks_and_scores(industries)

    now_utc = dt.datetime.now(dt.timezone.utc)
    today_iso = now_utc.date().isoformat()

    payload = {
        "fetched_at": now_utc.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "industries": industries,
    }
    DATA_FILE.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    print(f"[write] {DATA_FILE.relative_to(REPO_ROOT)}")

    history = update_history(industries, today_iso)
    HISTORY_FILE.write_text(json.dumps(history, indent=2, ensure_ascii=False))
    print(f"[write] {HISTORY_FILE.relative_to(REPO_ROOT)} ({len(history)} snapshots)")


if __name__ == "__main__":
    main()
