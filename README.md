# Theme Tracker (v2)

Finviz industry / thematic ETF momentum dashboard. Static site on GitHub Pages, daily data refresh via GitHub Actions.

## What's new in v2
- **English only** — German strings removed, no language toggle
- **Expanded ETF universe** — ~70 ETFs across 14 themes (was ~40 across 14)
- **Visual polish** — proper sparkline cells, refined INST/HOT/ACCEL/FRESH badges, cleaner pick cards, improved table contrast and hover states
- **Same scoring logic** — composite, acceleration, INST badge, First Flag filter unchanged

## Files

```
themetracker/
├── index.html               static page
├── static/app.js            rendering + interaction
├── static/style.css         theme
├── data.json                daily Finviz industry snapshot
├── history.json             rolling history for puck view
├── etf_data.json            daily ETF snapshot
├── scripts/
│   ├── fetch_industries.py  Finviz scraper
│   ├── fetch_etfs.py        Yahoo Finance ETF scraper
│   └── requirements.txt
└── .github/workflows/daily.yml   cron, commits JSON daily
```

## Scoring (unchanged)
```
composite     = rank_1M × 0.70 + rank_1W × 0.20 + rank_3M × 0.10
acceleration  = rank_3M − rank_1W
INST          = ranks["1M"] ≤ 40 AND ranks["3M"] ≤ 40
```

## Updating an existing deploy
Drop the v2 files in your existing `themetracker` repo, overwriting `index.html`, `static/`, and `scripts/`. Keep your existing `data.json` / `history.json` / `etf_data.json` so puck history isn't reset. Commit, push, GitHub Pages rebuilds automatically.

The next scheduled (or manually triggered) workflow run will populate the expanded ETF universe.
