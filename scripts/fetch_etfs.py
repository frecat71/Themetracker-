"""
fetch_etfs.py — Finviz quote-page edition

For each ETF in our universe, fetches https://finviz.com/quote.ashx?t=<TICKER>
and parses the snapshot table for performance values.

Why per-ticker instead of screener:
  - Finviz screener's `t=` parameter doesn't accept ticker-list filters reliably
  - quote.ashx returns the same Performance Day/Week/Month/Quarter/YTD values
    we already use, with one consistent layout per ETF
  - Slower (one HTTP request per ticker) but deterministic and complete
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

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

FINVIZ_QUOTE = "https://finviz.com/quote.ashx?t={ticker}"

WEIGHT_1M = 0.70
WEIGHT_1W = 0.20
WEIGHT_3M = 0.10

REPO_ROOT = Path(__file__).resolve().parent.parent
ETF_FILE  = REPO_ROOT / "etf_data.json"

# ─── Curated ETF universe ──────────────────────────────────────────────
ETF_UNIVERSE: List[dict] = [
    # AI & Tech
    {"ticker": "BOTZ", "name": "Global X Robotics & AI ETF",                "theme": "AI & Tech", "priority": 1},
    {"ticker": "AIQ",  "name": "Global X Artificial Intelligence & Tech",   "theme": "AI & Tech", "priority": 1},
    {"ticker": "ROBO", "name": "ROBO Global Robotics & Automation",         "theme": "AI & Tech", "priority": 1},
    {"ticker": "IRBO", "name": "iShares Robotics & AI Multisector",         "theme": "AI & Tech", "priority": 2},
    {"ticker": "ARTY", "name": "iShares Future AI & Tech Active",           "theme": "AI & Tech", "priority": 1},
    {"ticker": "BAI",  "name": "iShares A.I. Innovation & Tech Active",     "theme": "AI & Tech", "priority": 1},
    {"ticker": "CHAT", "name": "Roundhill Generative AI & Tech",            "theme": "AI & Tech", "priority": 2},
    {"ticker": "HUMN", "name": "Tema Humanoid Robotics & AI",               "theme": "AI & Tech", "priority": 2},
    {"ticker": "THNQ", "name": "ROBO Global Artificial Intelligence",       "theme": "AI & Tech", "priority": 1},
    {"ticker": "AIVL", "name": "WisdomTree US AI Enhanced Value",           "theme": "AI & Tech", "priority": 3},

    # Semiconductors
    {"ticker": "SOXX", "name": "iShares Semiconductor",                     "theme": "Semiconductors", "priority": 1},
    {"ticker": "SMH",  "name": "VanEck Semiconductor",                      "theme": "Semiconductors", "priority": 1},
    {"ticker": "PSI",  "name": "Invesco Dynamic Semiconductors",            "theme": "Semiconductors", "priority": 1},
    {"ticker": "FTXL", "name": "First Trust Nasdaq Semiconductor",          "theme": "Semiconductors", "priority": 1},
    {"ticker": "SOXQ", "name": "Invesco PHLX Semiconductor",                "theme": "Semiconductors", "priority": 1},
    {"ticker": "XSD",  "name": "SPDR S&P Semiconductor",                    "theme": "Semiconductors", "priority": 2},

    # Cybersecurity
    {"ticker": "HACK", "name": "Amplify Cybersecurity",                     "theme": "Cybersecurity", "priority": 1},
    {"ticker": "CIBR", "name": "First Trust NASDAQ Cybersecurity",          "theme": "Cybersecurity", "priority": 1},
    {"ticker": "BUG",  "name": "Global X Cybersecurity",                    "theme": "Cybersecurity", "priority": 2},
    {"ticker": "WCBR", "name": "WisdomTree Cybersecurity",                  "theme": "Cybersecurity", "priority": 2},
    {"ticker": "IHAK", "name": "iShares Cybersecurity & Tech",              "theme": "Cybersecurity", "priority": 2},

    # Cloud & SaaS
    {"ticker": "WCLD", "name": "WisdomTree Cloud Computing",                "theme": "Cloud & SaaS",  "priority": 1},
    {"ticker": "SKYY", "name": "First Trust Cloud Computing",               "theme": "Cloud & SaaS",  "priority": 1},
    {"ticker": "CLOU", "name": "Global X Cloud Computing",                  "theme": "Cloud & SaaS",  "priority": 2},
    {"ticker": "IGV",  "name": "iShares Expanded Tech-Software",            "theme": "Cloud & SaaS",  "priority": 2},
    {"ticker": "PSJ",  "name": "Invesco Dynamic Software",                  "theme": "Cloud & SaaS",  "priority": 3},

    # Digital Infra
    {"ticker": "DTCR", "name": "Global X Data Center & Digital Infra",      "theme": "Digital Infra", "priority": 1},
    {"ticker": "VPN",  "name": "Global X Data Center REITs & Digital Infra","theme": "Digital Infra", "priority": 2},
    {"ticker": "SRVR", "name": "Pacer Benchmark Data & Infrastructure",     "theme": "Digital Infra", "priority": 2},

    # Nuclear / Uranium
    {"ticker": "URA",  "name": "Global X Uranium",                          "theme": "Nuclear", "priority": 1},
    {"ticker": "URNM", "name": "Sprott Uranium Miners",                     "theme": "Nuclear", "priority": 1},
    {"ticker": "NLR",  "name": "VanEck Uranium and Nuclear",                "theme": "Nuclear", "priority": 1},
    {"ticker": "URNJ", "name": "Sprott Junior Uranium Miners",              "theme": "Nuclear", "priority": 2},
    {"ticker": "NUKZ", "name": "Range Nuclear Renaissance",                 "theme": "Nuclear", "priority": 1},

    # Clean Energy
    {"ticker": "ICLN", "name": "iShares Global Clean Energy",               "theme": "Clean Energy", "priority": 1},
    {"ticker": "QCLN", "name": "First Trust Nasdaq Clean Edge Energy",      "theme": "Clean Energy", "priority": 1},
    {"ticker": "TAN",  "name": "Invesco Solar",                             "theme": "Clean Energy", "priority": 1},
    {"ticker": "FAN",  "name": "First Trust Global Wind Energy",            "theme": "Clean Energy", "priority": 2},
    {"ticker": "PBW",  "name": "Invesco WilderHill Clean Energy",           "theme": "Clean Energy", "priority": 2},
    {"ticker": "ACES", "name": "ALPS Clean Energy",                         "theme": "Clean Energy", "priority": 2},

    # Infrastructure
    {"ticker": "PAVE", "name": "Global X U.S. Infrastructure Development",  "theme": "Infrastructure", "priority": 1},
    {"ticker": "IFRA", "name": "iShares U.S. Infrastructure",               "theme": "Infrastructure", "priority": 1},
    {"ticker": "GRID", "name": "First Trust Nasdaq Clean Edge Smart Grid",  "theme": "Infrastructure", "priority": 1},
    {"ticker": "NFRA", "name": "FlexShares Global Infrastructure",          "theme": "Infrastructure", "priority": 2},

    # Defense & Aerospace
    {"ticker": "ITA",  "name": "iShares U.S. Aerospace & Defense",          "theme": "Defense", "priority": 1},
    {"ticker": "PPA",  "name": "Invesco Aerospace & Defense",               "theme": "Defense", "priority": 1},
    {"ticker": "XAR",  "name": "SPDR S&P Aerospace & Defense",              "theme": "Defense", "priority": 1},
    {"ticker": "SHLD", "name": "Global X Defense Tech",                     "theme": "Defense", "priority": 1},
    {"ticker": "ARKQ", "name": "ARK Autonomous Tech & Robotics",            "theme": "Defense", "priority": 3},

    # Biotech
    {"ticker": "XBI",  "name": "SPDR S&P Biotech",                          "theme": "Biotech", "priority": 1},
    {"ticker": "IBB",  "name": "iShares Biotechnology",                     "theme": "Biotech", "priority": 1},
    {"ticker": "ARKG", "name": "ARK Genomic Revolution",                    "theme": "Biotech", "priority": 2},
    {"ticker": "LABU", "name": "Direxion Daily S&P Biotech Bull 3X",        "theme": "Biotech", "priority": 3},
    {"ticker": "BBH",  "name": "VanEck Biotech",                            "theme": "Biotech", "priority": 2},

    # EV & Mobility
    {"ticker": "DRIV", "name": "Global X Autonomous & Electric Vehicles",   "theme": "EV & Mobility", "priority": 1},
    {"ticker": "LIT",  "name": "Global X Lithium & Battery Tech",           "theme": "EV & Mobility", "priority": 1},
    {"ticker": "IDRV", "name": "iShares Self-Driving EV and Tech",          "theme": "EV & Mobility", "priority": 2},
    {"ticker": "KARS", "name": "KraneShares Electric Vehicles",             "theme": "EV & Mobility", "priority": 2},
    {"ticker": "BATT", "name": "Amplify Lithium & Battery Technology",      "theme": "EV & Mobility", "priority": 2},

    # Fintech
    {"ticker": "FINX", "name": "Global X FinTech",                          "theme": "Fintech", "priority": 1},
    {"ticker": "ARKF", "name": "ARK Fintech Innovation",                    "theme": "Fintech", "priority": 1},
    {"ticker": "IPAY", "name": "Amplify CrowdBureau Online Payment Tech",   "theme": "Fintech", "priority": 2},

    # Materials
    {"ticker": "XME",  "name": "SPDR S&P Metals & Mining",                  "theme": "Materials", "priority": 1},
    {"ticker": "PICK", "name": "iShares MSCI Global Metals & Mining",       "theme": "Materials", "priority": 1},
    {"ticker": "REMX", "name": "VanEck Rare Earth/Strategic Metals",        "theme": "Materials", "priority": 1},
    {"ticker": "COPX", "name": "Global X Copper Miners",                    "theme": "Materials", "priority": 1},
    {"ticker": "GDX",  "name": "VanEck Gold Miners",                        "theme": "Materials", "priority": 1},
    {"ticker": "GDXJ", "name": "VanEck Junior Gold Miners",                 "theme": "Materials", "priority": 2},
    {"ticker": "SIL",  "name": "Global X Silver Miners",                    "theme": "Materials", "priority": 2},

    # Momentum
    {"ticker": "MTUM", "name": "iShares MSCI USA Momentum Factor",          "theme": "Momentum", "priority": 1},
    {"ticker": "PDP",  "name": "Invesco Dorsey Wright Momentum",            "theme": "Momentum", "priority": 2},
    {"ticker": "QMOM", "name": "Alpha Architect U.S. Quantitative Momentum","theme": "Momentum", "priority": 2},

    # Crypto / Blockchain
    {"ticker": "IBIT", "name": "iShares Bitcoin Trust",                     "theme": "Crypto", "priority": 1},
    {"ticker": "FBTC", "name": "Fidelity Wise Origin Bitcoin Fund",         "theme": "Crypto", "priority": 1},
    {"ticker": "GBTC", "name": "Grayscale Bitcoin Trust",                   "theme": "Crypto", "priority": 1},
    {"ticker": "ETHA", "name": "iShares Ethereum Trust",                    "theme": "Crypto", "priority": 2},
    {"ticker": "BKCH", "name": "Global X Blockchain",                       "theme": "Crypto", "priority": 2},
]


# ─── Finviz quote-page scraping ────────────────────────────────────────

def fetch_html(url: str, retries: int = 3, delay: float = 2.0) -> Optional[str]:
    headers = {
        "User-Agent":      USER_AGENT,
        "Accept":          "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
    }
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(url, headers=headers, timeout=20)
            r.raise_for_status()
            return r.text
        except Exception as e:
            print(f"[fetch] {url} attempt {attempt}: {e}", file=sys.stderr)
            if attempt < retries:
                time.sleep(delay * attempt)
    return None


def parse_pct(cell: str) -> Optional[float]:
    if not cell or cell.strip() in ("-", "", "—"):
        return None
    m = re.search(r"-?\d+\.?\d*", cell.replace(",", ""))
    if not m:
        return None
    try:
        return float(m.group(0))
    except ValueError:
        return None


def parse_quote_html(html: str) -> Dict[str, Optional[float]]:
    """
    Finviz quote page contains a snapshot table with key/value cells in pairs.
    Each <td class="snapshot-td2-cp"> holds a key, the next <td class="snapshot-td2"> the value.
    Performance keys we want: "Perf Day", "Perf Week", "Perf Month", "Perf Quarter", "Perf YTD".
    """
    soup = BeautifulSoup(html, "html.parser")

    keymap = {
        "Perf Day":     "1D",
        "Change":       "1D",   # fallback if Perf Day missing
        "Perf Week":    "1W",
        "Perf Month":   "1M",
        "Perf Quarter": "3M",
        "Perf Quart":   "3M",   # short form sometimes used
        "Perf YTD":     "YTD",
    }

    # The snapshot table cells are paired: every cell with the label class is followed
    # by a cell with the value class. We iterate over all <td> cells in document order.
    out: Dict[str, Optional[float]] = {tf: None for tf in ("1D", "1W", "1M", "3M", "YTD")}

    # Strategy 1: snapshot-td2-cp / snapshot-td2 pairs (legacy class names)
    cells = soup.find_all("td")
    for i, cell in enumerate(cells):
        text = cell.get_text(strip=True)
        if text in keymap and i + 1 < len(cells):
            tf = keymap[text]
            val = parse_pct(cells[i + 1].get_text(strip=True))
            if val is not None and out[tf] is None:
                out[tf] = val

    return out


def fetch_etf_perfs(ticker: str) -> Optional[Dict[str, Optional[float]]]:
    html = fetch_html(FINVIZ_QUOTE.format(ticker=ticker))
    if not html:
        return None
    perfs = parse_quote_html(html)
    # Require at least one of the medium-term timeframes to consider the fetch successful
    if perfs.get("1M") is None and perfs.get("1W") is None:
        return None
    return perfs


# ─── Score / theme aggregation ─────────────────────────────────────────

def rank_lookup(values: List[Optional[float]]) -> List[Optional[int]]:
    indexed = [(i, v) for i, v in enumerate(values) if v is not None]
    indexed.sort(key=lambda x: -x[1])
    ranks: List[Optional[int]] = [None] * len(values)
    for rank, (i, _) in enumerate(indexed, start=1):
        ranks[i] = rank
    return ranks


def main() -> None:
    rows: List[dict] = []
    total = len(ETF_UNIVERSE)
    for n, spec in enumerate(ETF_UNIVERSE, start=1):
        perfs = fetch_etf_perfs(spec["ticker"])
        time.sleep(0.6)  # polite delay between requests
        if not perfs:
            print(f"[etf] missing {spec['ticker']} ({n}/{total})", file=sys.stderr)
            continue
        rows.append({**spec, "perfs": perfs})
        if n % 10 == 0:
            print(f"[etf] progress {n}/{total}")

    print(f"[etf] fetched {len(rows)}/{total} ETFs")
    if not rows:
        raise RuntimeError("no ETF data parsed")

    for tf in ("1M", "1W", "3M"):
        vals = [r["perfs"].get(tf) for r in rows]
        ranks = rank_lookup(vals)
        for r, rk in zip(rows, ranks):
            r.setdefault("ranks", {})[tf] = rk if rk is not None else len(rows)

    for r in rows:
        rk = r["ranks"]
        r["score"] = WEIGHT_1M * rk["1M"] + WEIGHT_1W * rk["1W"] + WEIGHT_3M * rk["3M"]

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
        for tf in ("1D", "1W", "1M", "3M", "YTD"):
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
            "score":    r["score"],
        }

    payload = {
        "fetched_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "themes":     theme_out,
        "etfs":       etf_out,
    }
    ETF_FILE.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    print(f"[write] {ETF_FILE.relative_to(REPO_ROOT)}  ({len(etf_out)} ETFs / {len(theme_out)} themes)")


if __name__ == "__main__":
    main()
