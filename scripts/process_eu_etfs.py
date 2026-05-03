"""
process_eu_etfs.py
------------------
Reads CSV files from data/eu_etfs/ (one CSV per upload date), filters to a
curated list of ~42 thematic UCITS ETFs, computes performance ranks and a
composite score using the same formula as the US ETF view, then writes:

  - eu_etf_data.json     (latest snapshot for the EU ETF tab)
  - eu_history.json      (rolling history, one entry per CSV file date)

CSV files must be named like:  ETF_Euro_YYYY-MM-DD.csv
(or any name with YYYY-MM-DD in it — the date drives history ordering)

Schema produced (mirrors etf_data.json so frontend can re-use logic):

eu_etf_data.json = {
  "fetched_at": "...",
  "csv_date":   "2026-05-03",        # date of the source CSV
  "themes": { "<Theme>": { perfs:..., score:..., etfs_p1:[...] }, ... },
  "etfs":   { "<TICKER>": { name, theme, priority, perfs, score, ranks }, ... }
}

eu_history.json = [
  { "date": "2026-05-03",
    "scores": { "<TICKER>": { "c": <composite>, "t": <ticker> }, ... } },
  ...
]
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ─── Configuration ─────────────────────────────────────────────────────

WEIGHT_1M = 0.70
WEIGHT_1W = 0.20
WEIGHT_3M = 0.10

REPO_ROOT     = Path(__file__).resolve().parent.parent
CSV_DIR       = REPO_ROOT / "data" / "eu_etfs"
OUTPUT_FILE   = REPO_ROOT / "eu_etf_data.json"
HISTORY_FILE  = REPO_ROOT / "eu_history.json"
HISTORY_KEEP  = 200  # cap how many snapshots we keep

# CSV column names (TradingView export format)
COL_SYMBOL = "Symbol"
COL_PERFS  = {
    "1D":  "Price Change % 1 day",
    "1W":  "Performance % 1 week",
    "1M":  "Performance % 1 month",
    "3M":  "Performance % 3 months",
    "6M":  "Performance % 6 months",
    "1Y":  "Performance % 1 year",
}
TIMEFRAMES_OUT = ["1D", "1W", "1M", "3M", "1Y"]  # frontend will display these
RANK_TFS       = ["1W", "1M", "3M"]              # used for composite score

# ─── Curated EU ETF universe ───────────────────────────────────────────
# Mirrors the US theme structure where possible.
# Priority 1 = core thematic, 2 = strong proxy, 3 = adjacent

EU_UNIVERSE: List[dict] = [
    # AI & Tech
    {"ticker": "XAIX", "name": "Xtrackers AI & Big Data",                        "theme": "AI & Tech",      "priority": 1},
    {"ticker": "2B76", "name": "iShares Automation & Robotics",                  "theme": "AI & Tech",      "priority": 1},
    {"ticker": "XMLD", "name": "L&G Artificial Intelligence",                    "theme": "AI & Tech",      "priority": 1},
    {"ticker": "IROB", "name": "L&G ROBO Global Robotics & Automation",          "theme": "AI & Tech",      "priority": 1},
    {"ticker": "GOAI", "name": "Amundi MSCI Robotics & AI",                      "theme": "AI & Tech",      "priority": 1},
    {"ticker": "WTI2", "name": "WisdomTree Artificial Intelligence",             "theme": "AI & Tech",      "priority": 2},
    {"ticker": "AIFS", "name": "iShares AI Infrastructure",                      "theme": "AI & Tech",      "priority": 2},

    # Semiconductors
    {"ticker": "VVSM", "name": "VanEck Semiconductor",                           "theme": "Semiconductors", "priority": 1},
    {"ticker": "SEC0", "name": "iShares MSCI Global Semiconductors",             "theme": "Semiconductors", "priority": 1},
    {"ticker": "LSMC", "name": "Amundi MSCI Semiconductors",                     "theme": "Semiconductors", "priority": 1},

    # Cybersecurity
    {"ticker": "USPY", "name": "L&G Cyber Security",                             "theme": "Cybersecurity",  "priority": 1},
    {"ticker": "L0CK", "name": "iShares Digital Security",                       "theme": "Cybersecurity",  "priority": 1},
    {"ticker": "CBRS", "name": "First Trust Nasdaq Cyber Security",              "theme": "Cybersecurity",  "priority": 2},

    # Nuclear
    {"ticker": "NUKL", "name": "VanEck Uranium and Nuclear Technologies",        "theme": "Nuclear",        "priority": 1},
    {"ticker": "URNU", "name": "Global X Uranium",                               "theme": "Nuclear",        "priority": 1},

    # Clean Energy
    {"ticker": "IQQH", "name": "iShares Global Clean Energy Transition",         "theme": "Clean Energy",   "priority": 1},
    {"ticker": "RENW", "name": "L&G Clean Energy",                               "theme": "Clean Energy",   "priority": 2},

    # Infrastructure
    {"ticker": "IQQI", "name": "iShares Global Infrastructure",                  "theme": "Infrastructure", "priority": 1},
    {"ticker": "GRID", "name": "First Trust Nasdaq Clean Edge Smart Grid",       "theme": "Infrastructure", "priority": 1},
    {"ticker": "B41J", "name": "Global X European Infrastructure Development",   "theme": "Infrastructure", "priority": 2},

    # Defense
    {"ticker": "DFEN", "name": "VanEck Defense",                                 "theme": "Defense",        "priority": 1},
    {"ticker": "EUDF", "name": "WisdomTree Europe Defence",                      "theme": "Defense",        "priority": 1},
    {"ticker": "5J50", "name": "iShares Global Aerospace & Defence",             "theme": "Defense",        "priority": 1},
    {"ticker": "4MMR", "name": "Global X Defence Tech",                          "theme": "Defense",        "priority": 2},
    {"ticker": "ASWC", "name": "Future of Defence (HanETF)",                     "theme": "Defense",        "priority": 1},

    # Biotech
    {"ticker": "2B70", "name": "iShares NASDAQ US Biotechnology",                "theme": "Biotech",        "priority": 1},

    # EV & Mobility
    {"ticker": "BATE", "name": "L&G Battery Value-Chain",                        "theme": "EV & Mobility",  "priority": 1},

    # Materials
    {"ticker": "G2X",  "name": "VanEck Gold Miners",                             "theme": "Materials",      "priority": 1},
    {"ticker": "WMIN", "name": "VanEck S&P Global Mining",                       "theme": "Materials",      "priority": 1},
    {"ticker": "VVMX", "name": "VanEck Rare Earth and Strategic Metals",         "theme": "Materials",      "priority": 1},
    {"ticker": "SLVR", "name": "Global X Silver Miners",                         "theme": "Materials",      "priority": 1},
    {"ticker": "G2XJ", "name": "VanEck Junior Gold Miners",                      "theme": "Materials",      "priority": 2},
    {"ticker": "RARE", "name": "WisdomTree Strategic Metals",                    "theme": "Materials",      "priority": 1},
    {"ticker": "4COP", "name": "Global X Copper Miners",                         "theme": "Materials",      "priority": 1},
    {"ticker": "ETLX", "name": "L&G Gold Mining",                                "theme": "Materials",      "priority": 2},

    # Momentum
    {"ticker": "IS3R", "name": "iShares MSCI World Momentum Factor",             "theme": "Momentum",       "priority": 1},
    {"ticker": "CEMR", "name": "iShares MSCI Europe Momentum Factor",            "theme": "Momentum",       "priority": 1},

    # Crypto
    {"ticker": "BITC", "name": "CoinShares Bitcoin ETP",                         "theme": "Crypto",         "priority": 1},
    {"ticker": "WBIT", "name": "WisdomTree Physical Bitcoin",                    "theme": "Crypto",         "priority": 1},
    {"ticker": "IB1T", "name": "iShares Bitcoin ETP",                            "theme": "Crypto",         "priority": 1},
    {"ticker": "BTCE", "name": "Bitwise Physical Bitcoin",                       "theme": "Crypto",         "priority": 1},
    {"ticker": "DAVV", "name": "VanEck Crypto and Blockchain Innovators",        "theme": "Crypto",         "priority": 2},
]


# ─── CSV reading ───────────────────────────────────────────────────────

def parse_pct(s: str) -> Optional[float]:
    if s is None or s == "":
        return None
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def find_latest_csv() -> Optional[Tuple[Path, str]]:
    """Returns (path, iso_date) for the most recent CSV in CSV_DIR, or None."""
    if not CSV_DIR.exists():
        return None
    candidates: List[Tuple[Path, str]] = []
    date_re = re.compile(r"(\d{4}-\d{2}-\d{2})")
    for p in CSV_DIR.glob("*.csv"):
        m = date_re.search(p.stem)
        if not m:
            print(f"[skip] no date in filename: {p.name}", file=sys.stderr)
            continue
        candidates.append((p, m.group(1)))
    if not candidates:
        return None
    # Sort by date string (lexicographic == chronological for ISO dates)
    candidates.sort(key=lambda t: t[1])
    return candidates[-1]


def read_csv_for_tickers(csv_path: Path, wanted: set) -> Dict[str, Dict[str, Optional[float]]]:
    """
    Returns: { "<TICKER>": {"1D": ..., "1W": ..., "1M": ..., "3M": ..., "1Y": ...} }
    Only includes tickers in `wanted`.
    """
    out: Dict[str, Dict[str, Optional[float]]] = {}
    with csv_path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            sym = row.get(COL_SYMBOL, "").strip().upper()
            if sym not in wanted:
                continue
            perfs = {tf: parse_pct(row.get(col, "")) for tf, col in COL_PERFS.items()}
            # Frontend uses 1Y in place of YTD for EU; map it through unchanged
            out[sym] = perfs
    return out


# ─── Score / theme aggregation ─────────────────────────────────────────

def rank_lookup(values: List[Optional[float]]) -> List[Optional[int]]:
    """Returns rank (1 = highest) for each input value; None values get None rank."""
    indexed = [(i, v) for i, v in enumerate(values) if v is not None]
    indexed.sort(key=lambda x: -x[1])
    ranks: List[Optional[int]] = [None] * len(values)
    for rank, (i, _) in enumerate(indexed, start=1):
        ranks[i] = rank
    return ranks


def update_history(snapshot_date: str, etfs: Dict[str, dict]) -> List[dict]:
    """Appends today's snapshot to eu_history.json (replacing same date if present)."""
    history: List[dict] = []
    if HISTORY_FILE.exists():
        try:
            history = json.loads(HISTORY_FILE.read_text())
            if not isinstance(history, list):
                history = []
        except json.JSONDecodeError:
            history = []

    snapshot = {
        "date":   snapshot_date,
        "scores": {ticker: {"c": data["score"], "t": ticker} for ticker, data in etfs.items()},
    }
    history = [h for h in history if h.get("date") != snapshot_date]
    history.append(snapshot)
    history.sort(key=lambda h: h["date"])
    if len(history) > HISTORY_KEEP:
        history = history[-HISTORY_KEEP:]
    return history


# ─── Main ──────────────────────────────────────────────────────────────

def main() -> None:
    pick = find_latest_csv()
    if pick is None:
        raise RuntimeError(f"no dated CSV files found in {CSV_DIR.relative_to(REPO_ROOT)}")
    csv_path, csv_date = pick
    print(f"[csv] using {csv_path.relative_to(REPO_ROOT)}  (date: {csv_date})")

    wanted = {spec["ticker"].upper() for spec in EU_UNIVERSE}
    perfs_by_ticker = read_csv_for_tickers(csv_path, wanted)
    print(f"[csv] matched {len(perfs_by_ticker)}/{len(wanted)} curated tickers")

    rows: List[dict] = []
    for spec in EU_UNIVERSE:
        perfs = perfs_by_ticker.get(spec["ticker"].upper())
        if not perfs:
            print(f"[etf] missing {spec['ticker']}", file=sys.stderr)
            continue
        rows.append({**spec, "perfs": perfs})

    if not rows:
        raise RuntimeError("no curated EU ETFs found in CSV — check tickers")

    # Compute per-timeframe ranks
    for tf in RANK_TFS:
        vals = [r["perfs"].get(tf) for r in rows]
        ranks = rank_lookup(vals)
        for r, rk in zip(rows, ranks):
            r.setdefault("ranks", {})[tf] = rk if rk is not None else len(rows)

    # Composite score
    for r in rows:
        rk = r["ranks"]
        r["score"] = WEIGHT_1M * rk["1M"] + WEIGHT_1W * rk["1W"] + WEIGHT_3M * rk["3M"]

    # Build themes
    themes: Dict[str, dict] = {}
    for r in rows:
        themes.setdefault(r["theme"], {"members": [], "p1": []})
        themes[r["theme"]]["members"].append(r)
        if r["priority"] == 1:
            themes[r["theme"]]["p1"].append(r)

    theme_out: Dict[str, dict] = {}
    for theme, info in themes.items():
        pool = info["p1"] if info["p1"] else info["members"]
        avg_perfs = {}
        for tf in TIMEFRAMES_OUT:
            xs = [m["perfs"].get(tf) for m in pool if m["perfs"].get(tf) is not None]
            avg_perfs[tf] = (sum(xs) / len(xs)) if xs else None
        avg_score = sum(m["score"] for m in pool) / len(pool)
        theme_out[theme] = {
            "perfs":   avg_perfs,
            "score":   avg_score,
            "etfs_p1": [m["ticker"] for m in info["p1"]],
        }

    etf_out: Dict[str, dict] = {}
    for r in rows:
        etf_out[r["ticker"]] = {
            "name":     r["name"],
            "theme":    r["theme"],
            "priority": r["priority"],
            "perfs":    r["perfs"],
            "ranks":    r["ranks"],
            "score":    r["score"],
        }

    payload = {
        "fetched_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "csv_date":   csv_date,
        "themes":     theme_out,
        "etfs":       etf_out,
    }
    OUTPUT_FILE.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    print(f"[write] {OUTPUT_FILE.relative_to(REPO_ROOT)}  ({len(etf_out)} ETFs / {len(theme_out)} themes)")

    history = update_history(csv_date, etf_out)
    HISTORY_FILE.write_text(json.dumps(history, indent=2, ensure_ascii=False))
    print(f"[write] {HISTORY_FILE.relative_to(REPO_ROOT)}  ({len(history)} snapshots)")


if __name__ == "__main__":
    main()
