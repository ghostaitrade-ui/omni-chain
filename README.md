# Omni-Chain Research Engine

A multi-source financial research tool that aggregates news sentiment, social sentiment, congressional trades, Google Trends, insider activity, options flow, and backtesting into a single ranked report for any stock ticker.

## What It Does

- Pulls live data from 8+ sources simultaneously
- Scores and ranks tickers within a sector
- Saves all reports to a local knowledge base
- Runs sector-wide dashboards with one command

## Data Sources

| Source | Data |
|---|---|
| yfinance | Price, options chain, fundamentals |
| Finnhub | News, insider trades |
| NewsAPI | Broad news from 70,000+ sources |
| Alpha Vantage | News sentiment scoring |
| StockTwits | Social sentiment |
| Polygon.io | Company details |
| Google Trends | Consumer interest |
| QuiverQuant | Congressional trades |
| FRED | Macro/economic data |
| Alpaca | Paper trading execution |

## Setup

1. Clone the repo
2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Copy `.env.example` to `.env` and fill in your API keys
4. Run a single ticker report:
   ```
   python research_engine.py AAPL
   ```
5. Run a sector dashboard:
   ```
   python sector_dashboard.py peptide
   python sector_dashboard.py ai
   python sector_dashboard.py wheel
   ```

## Available Watchlists

- `peptide` — GLP-1/peptide sector (NVO, LLY, VKTX, AMGN, HIMS)
- `ai` — AI/semiconductor sector (NVDA, AMD, INTC, MSFT, GOOGL)
- `wheel` — Wheel strategy candidates (AAPL, MSFT, JPM, KO, JNJ)

## API Keys Required

All free tiers available — see `.env.example` for the full list.

## Project Structure

```
omni-chain/
├── research_engine.py    # Core data collection + reporting
├── sector_dashboard.py   # Multi-ticker ranked comparison
├── .env.example          # API key template
├── CLAUDE.md             # Claude Code instructions
├── knowledge/            # Saved reports (gitignored)
└── logs/                 # Run logs (gitignored)
```
