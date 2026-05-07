"""
Omni-Chain Sector Dashboard
Runs the full research engine across a watchlist and produces
a scored comparison table — best setups ranked at the top.
"""

import os
import json
import sys
from datetime import datetime
from research_engine import generate_report

# ─── WATCHLISTS ──────────────────────────────────────────────────────────────

WATCHLISTS = {
    "peptide": {
        "name": "Peptide / GLP-1 Sector",
        "tickers": ["NVO", "LLY", "VKTX", "AMGN", "HIMS"],
        "notes": {
            "NVO":  "Ozempic/Wegovy maker — beaten down from highs",
            "LLY":  "Mounjaro/Zepbound — world's best-selling drug",
            "VKTX": "Pure-play GLP-1 pipeline — high short interest",
            "AMGN": "MariTide in trials — diversified biotech",
            "HIMS": "Compounding peptides — FDA risk, massive short float",
        }
    },
    "ai": {
        "name": "AI / Semiconductor Sector",
        "tickers": ["NVDA", "AMD", "INTC", "MSFT", "GOOGL"],
        "notes": {
            "NVDA":  "GPU dominance — 630% 3yr return",
            "AMD":   "NVDA challenger — data center growth",
            "INTC":  "Turnaround play — foundry strategy",
            "MSFT":  "Azure AI + OpenAI investment",
            "GOOGL": "Gemini AI + search dominance",
        }
    },
    "wheel": {
        "name": "Wheel Strategy Candidates",
        "tickers": ["AAPL", "MSFT", "JPM", "KO", "JNJ"],
        "notes": {
            "AAPL": "High liquidity, stable premium",
            "MSFT": "Low beta, consistent IV",
            "JPM":  "Financials — dividend + premium",
            "KO":   "Defensive, low volatility wheel",
            "JNJ":  "Healthcare defensive, stable",
        }
    },
}


# ─── SCORING ENGINE ──────────────────────────────────────────────────────────

def score_ticker(report):
    """
    Score a ticker 0-100 based on multiple signals.
    Higher = more favorable setup for research/trading attention.
    """
    score = 50  # baseline
    reasons = []

    pd = report.get("price_data", {})
    od = report.get("options_data", {})
    ns = report.get("news_sentiment", {})
    ss = report.get("social_sentiment", {})
    it = report.get("insider_trades", {})
    ct = report.get("congressional_trades", {})
    bt = report.get("backtest", {})
    gt = report.get("google_trends", {})

    # ── Momentum (price trend) ──
    change_1m = pd.get("change_1m_pct") or 0
    if change_1m > 10:
        score += 8; reasons.append(f"Strong 1M momentum +{change_1m}%")
    elif change_1m > 5:
        score += 4; reasons.append(f"Positive 1M momentum +{change_1m}%")
    elif change_1m < -10:
        score -= 6; reasons.append(f"Weak 1M momentum {change_1m}%")

    # ── News sentiment ──
    sentiment = ns.get("avg_sentiment_score") or 0
    if sentiment > 0.2:
        score += 8; reasons.append(f"Strong bullish news sentiment ({sentiment})")
    elif sentiment > 0.05:
        score += 4; reasons.append(f"Mild bullish news sentiment ({sentiment})")
    elif sentiment < -0.1:
        score -= 6; reasons.append(f"Bearish news sentiment ({sentiment})")

    # ── Social sentiment ──
    bull_pct = ss.get("bull_pct") or 0
    if bull_pct > 65:
        score += 6; reasons.append(f"Strong social bullishness ({bull_pct}%)")
    elif bull_pct > 50:
        score += 3; reasons.append(f"Mild social bullishness ({bull_pct}%)")
    elif bull_pct > 0 and bull_pct < 35:
        score -= 4; reasons.append(f"Social sentiment bearish ({bull_pct}%)")

    # ── Options flow (put/call ratio) ──
    pc = od.get("put_call_ratio") or 1
    if pc < 0.5:
        score += 7; reasons.append(f"Very bullish options flow (P/C {pc})")
    elif pc < 0.8:
        score += 4; reasons.append(f"Bullish options flow (P/C {pc})")
    elif pc > 1.5:
        score -= 5; reasons.append(f"Bearish options flow (P/C {pc})")

    # ── Congressional signal ──
    congress = ct.get("congressional_signal", "Neutral")
    if congress == "Bullish":
        score += 8; reasons.append("Congress buying")
    elif congress == "Bearish":
        score -= 6; reasons.append("Congress selling")

    # ── Insider signal ──
    insider = it.get("insider_signal", "Neutral")
    if insider == "Bullish":
        score += 6; reasons.append("Insiders buying")
    elif insider == "Bearish":
        score -= 4; reasons.append("Insiders selling")

    # ── Google Trends ──
    trend_dir = gt.get("trend_direction", "")
    vs_avg = gt.get("interest_vs_avg_pct") or 0
    if trend_dir == "Rising" and vs_avg > 20:
        score += 5; reasons.append(f"Google interest rising +{vs_avg}% vs avg")
    elif trend_dir == "Falling" and vs_avg < -30:
        score -= 3; reasons.append(f"Google interest falling {vs_avg}% vs avg")

    # ── Backtest quality ──
    win_rate = bt.get("daily_win_rate_pct") or 50
    if win_rate > 55:
        score += 4; reasons.append(f"Strong historical win rate {win_rate}%")
    max_dd = bt.get("max_drawdown_pct") or 0
    if max_dd < -40:
        score -= 3; reasons.append(f"High historical drawdown {max_dd}%")

    # ── Short interest (squeeze potential) ──
    short_float = pd.get("short_float") or 0
    if short_float > 0.2:
        score += 5; reasons.append(f"High short float {round(short_float*100,1)}% — squeeze potential")

    return max(0, min(100, round(score))), reasons


# ─── DASHBOARD RUNNER ────────────────────────────────────────────────────────

def run_dashboard(watchlist_key="peptide"):
    wl = WATCHLISTS.get(watchlist_key)
    if not wl:
        print(f"Unknown watchlist: {watchlist_key}")
        print(f"Available: {', '.join(WATCHLISTS.keys())}")
        return

    print(f"\n{'='*65}")
    print(f"  OMNI-CHAIN SECTOR DASHBOARD")
    print(f"  {wl['name']}")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*65}")
    print(f"  Analyzing {len(wl['tickers'])} tickers — this takes ~60 seconds...\n")

    results = []
    for ticker in wl["tickers"]:
        try:
            report = generate_report(ticker)
            score, reasons = score_ticker(report)
            results.append({
                "ticker":  ticker,
                "score":   score,
                "reasons": reasons,
                "report":  report,
                "note":    wl["notes"].get(ticker, ""),
            })
        except Exception as e:
            print(f"  ERROR on {ticker}: {e}")

    # Sort by score descending
    results.sort(key=lambda x: x["score"], reverse=True)

    # ── Ranked Summary Table ──
    sep = "=" * 65
    print(f"\n{sep}")
    print(f"  RANKED RESULTS — {wl['name']}")
    print(f"{sep}")
    print(f"  {'Rank':<5} {'Ticker':<7} {'Score':<7} {'Price':<10} {'1M%':<8} {'News':<10} {'Note'}")
    print(f"  {'-'*60}")

    for i, r in enumerate(results, 1):
        pd_  = r["report"].get("price_data", {})
        ns_  = r["report"].get("news_sentiment", {})
        rank_icon = "*" if i == 1 else ">"
        price   = str(pd_.get('current_price', '?'))
        change  = str(pd_.get('change_1m_pct', '?')) + '%'
        signal  = str(ns_.get('sentiment_label', '?'))
        note    = r['note'][:35]
        print(f"  {rank_icon} {i:<4} {r['ticker']:<7} {r['score']:<7} ${price:<9} {change:<8} {signal:<10} {note}")

    # ── Detailed Breakdown ──
    print(f"\n{sep}")
    print(f"  SCORING BREAKDOWN")
    print(f"{sep}")
    for r in results:
        print(f"\n  {r['ticker']} — Score: {r['score']}/100")
        for reason in r["reasons"]:
            print(f"    + {reason}")

    # ── Top Pick Call-Out ──
    top = results[0]
    print(f"\n{sep}")
    print(f"  TOP PICK: {top['ticker']} (Score: {top['score']}/100)")
    print(f"  {top['note']}")
    bt_ = top["report"].get("backtest", {})
    od_ = top["report"].get("options_data", {})
    print(f"  3Y Return: {bt_.get('buy_hold_return_pct','?')}%  |  "
          f"Max DD: {bt_.get('max_drawdown_pct','?')}%  |  "
          f"P/C Ratio: {od_.get('put_call_ratio','?')}")
    print(f"{sep}\n")

    # Save dashboard report
    os.makedirs("knowledge", exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"knowledge/dashboard_{watchlist_key}_{timestamp}.json"
    save_data = [{
        "ticker": r["ticker"],
        "score":  r["score"],
        "reasons": r["reasons"],
        "note":   r["note"],
        "price":  r["report"].get("price_data", {}).get("current_price"),
        "sentiment": r["report"].get("news_sentiment", {}).get("sentiment_label"),
    } for r in results]
    with open(filename, "w") as f:
        json.dump({"watchlist": watchlist_key, "generated": timestamp, "results": save_data}, f, indent=2)
    print(f"  Dashboard saved: {filename}")
    return results


# ─── ENTRY POINT ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    watchlist = sys.argv[1] if len(sys.argv) > 1 else "peptide"
    run_dashboard(watchlist)
