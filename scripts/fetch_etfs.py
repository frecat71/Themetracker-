"""
fetch_etfs.py — Finviz screener edition
Fetches all ETFs in one batch via the Finviz screener (Performance view),
parses the table, computes scores, and writes etf_data.json.
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

# Finviz screener — Performance view (v=141), filter by ticker list (t=)
FINVIZ_SCREENER = "https://finviz.com/screener.ashx?v=141&t={tickers}"

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


# ─── Finviz scraping ───────────────────────────────────────────────────

def fetch_html(url: str, retries: int = 3, delay: float = 2.0) -> str:
    headers = {
        "User-Agent":      USER_AGENT,
        "Accept":          "text/html,application/xhtml+xml",
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


def parse_screener_html(html: str) -> Dict[str, Dict[str, Optional[float]]]:
    soup = BeautifulSoup(html, "html.parser")
    target_table = None
    for tbl in soup.find_all("table"):
        head_text = tbl.get_text(" ", strip=True)[:300].lower()
        if "ticker" in head_text and ("perf week" in head_text or "perf month" in head_text):
            target_table = tbl
            break

    if target_table is None:
        raise RuntimeError("could not locate Finviz screener table")

    rows = target_table.find_all("tr")
    if len(rows) < 2:
        raise RuntimeError("screener table has no data rows")

    header_cells = [c.get_text(strip=True) for c in rows[0].find_all(["th", "td"])]

    def col_index(*candidates: str) -> Optional[int]:
        for i, h in enumerate(header_cells):
            for c in candidates:
                if c.lower() in h.lower():
                    return i
        return None

    idx = {
        "ticker": col_index("Ticker"),
        "1D":     col_index("Perf Day", "Change"),
        "1W":     col_index("Perf Week"),
        "1M":     col_index("Perf Month"),
        "3M":     col_index("Perf Quart"),
        "YTD":    col_index("Perf YTD"),
    }
    if idx["ticker"] is None:
        raise RuntimeError(f"could not find Ticker column in headers: {header_cells}")

    out: Dict[str, Dict[str, Optional[float]]] = {}
    for tr in rows[1:]:
        cells = [c.get_text(strip=True) for c in tr.find_all(["td", "th"])]
        if not cells or idx["ticker"] >= len(cells):
            continue
        ticker = cells[idx["ticker"]].upper()
        if not ticker or not re.match(r"^[A-Z][A-Z0-9.\-]*$", ticker):
            continue

        perfs: Dict[str, Optional[float]] = {}
        for tf in ("1D", "1W", "1M", "3M", "YTD"):
            ci = idx.get(tf)
            perfs[tf] = parse_pct(cells[ci]) if (ci is not None and ci < len(cells)) else None
        out[ticker] = perfs

    return out


def scrape_finviz_etfs(tickers: List[str]) -> Dict[str, Dict[str, Optional[float]]]:
    if not tickers:
        return {}

    BATCH_SIZE = 100
    out: Dict[str, Dict[str, Optional[float]]] = {}
    for i in range(0, len(tickers), BATCH_SIZE):
        batch = tickers[i : i + BATCH_SIZE]
        url = FINVIZ_SCREENER.format(tickers=",".join(batch))
        html = fetch_html(url)
        out.update(parse_screener_html(html))
        if i + BATCH_SIZE < len(tickers):
            time.sleep(1.0)
    return out


def rank_lookup(values: List[Optional[float]]) -> List[Optional[int]]:
    indexed = [(i, v) for i, v in enumerate(values) if v is not None]
    indexed.sort(key=lambda x: -x[1])
    ranks: List[Optional[int]] = [None] * len(values)
    for rank, (i, _) in enumerate(indexed, start=1):
        ranks[i] = rank
    return ranks


def main() -> None:
    tickers = [spec["ticker"] for spec in ETF_UNIVERSE]
    print(f"[scrape] fetching {len(tickers)} ETFs from Finviz")
    perfs_by_ticker = scrape_finviz_etfs(tickers)
    print(f"[scrape] got data for {len(perfs_by_ticker)}/{len(tickers)} tickers")

    rows: List[dict] = []
    for spec in ETF_UNIVERSE:
        perfs = perfs_by_ticker.get(spec["ticker"].upper())
        if not perfs:
            print(f"[etf] missing {spec['ticker']}", file=sys.stderr)
            continue
        rows.append({**spec, "perfs": perfs})

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
