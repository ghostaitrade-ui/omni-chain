"""
Omni-Chain Web App
Flask server that serves the research engine via a web interface.
"""

import os
import json
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import Flask, render_template, request, jsonify, Response, stream_with_context
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)

# ── In-memory cache: {ticker: {"ts": timestamp, "report": {...}}} ─────────────
report_cache = {}
CACHE_TTL = 1800  # 30 minutes

def _cached(ticker):
    """Return cached report if fresh, else None."""
    entry = report_cache.get(ticker)
    if entry and (time.time() - entry["ts"]) < CACHE_TTL:
        return entry["report"]
    return None

def _cache_set(ticker, report):
    report_cache[ticker] = {"ts": time.time(), "report": report}

def _build_report(ticker, company_name):
    """Fetch all data sources in parallel and return assembled report."""
    from research_engine import (
        get_price_data, get_options_data, get_news_sentiment,
        get_stocktwits_sentiment, get_insider_trades,
        get_polygon_details, get_google_trends,
        get_congressional_trades, get_backtesting_summary,
        get_price_forecast, get_analyst_targets,
    )
    from datetime import datetime

    tasks = {
        "price_data":          lambda: get_price_data(ticker),
        "options_data":        lambda: get_options_data(ticker),
        "news_sentiment":      lambda: get_news_sentiment(ticker),
        "social_sentiment":    lambda: get_stocktwits_sentiment(ticker),
        "insider_trades":      lambda: get_insider_trades(ticker),
        "polygon_details":     lambda: get_polygon_details(ticker),
        "google_trends":       lambda: get_google_trends(ticker, company_name),
        "congressional_trades":lambda: get_congressional_trades(ticker),
        "backtest":            lambda: get_backtesting_summary(ticker),
        "forecast":            lambda: get_price_forecast(ticker),
        "analyst":             lambda: get_analyst_targets(ticker),
    }

    results = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(fn): key for key, fn in tasks.items()}
        for future in as_completed(futures):
            key = futures[future]
            try:
                results[key] = future.result()
            except Exception as e:
                results[key] = {"error": str(e)}

    report = {
        "ticker":    ticker,
        "company":   company_name,
        "generated": datetime.now().isoformat(),
        **results,
    }
    _cache_set(ticker, report)
    return report


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/research/<ticker>")
def research(ticker):
    ticker = ticker.upper().strip()
    if not ticker.isalpha() or len(ticker) > 5:
        return jsonify({"error": "Invalid ticker"}), 400

    def generate():
        # Serve from cache instantly if available
        cached = _cached(ticker)
        if cached:
            yield f"data: {json.dumps({'status': 'running', 'message': 'Loading from cache...'})}\n\n"
            yield f"data: {json.dumps({'status': 'complete', 'report': cached})}\n\n"
            return

        yield f"data: {json.dumps({'status': 'running', 'message': f'Starting research on {ticker}... (fetching all sources in parallel)'})}\n\n"
        try:
            from research_engine import _polygon_get

            try:
                ref = _polygon_get(f"/v3/reference/tickers/{ticker}")
                company_name = ref.get("results", {}).get("name", ticker)
            except Exception:
                company_name = ticker

            yield f"data: {json.dumps({'status': 'running', 'message': f'Pulling data from 9 sources simultaneously...'})}\n\n"

            report = _build_report(ticker, company_name)

            os.makedirs("knowledge", exist_ok=True)
            from datetime import datetime
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            with open(f"knowledge/{ticker}_{ts}.json", "w") as f:
                json.dump(report, f, indent=2, default=str)

            yield f"data: {json.dumps({'status': 'complete', 'report': report})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'status': 'error', 'message': str(e)})}\n\n"

    return Response(stream_with_context(generate()), mimetype="text/event-stream")


@app.route("/api/dashboard/<watchlist>")
def dashboard(watchlist):
    from sector_dashboard import WATCHLISTS, score_ticker
    from research_engine import _polygon_get

    wl = WATCHLISTS.get(watchlist)
    if not wl:
        return jsonify({"error": f"Unknown watchlist: {watchlist}"}), 400

    def _scored_row(ticker, report):
        score, reasons = score_ticker(report)
        pd_data = report.get("price_data", {})
        ns      = report.get("news_sentiment", {})
        bt      = report.get("backtest", {})
        od      = report.get("options_data", {})
        fc      = report.get("forecast", {})
        an      = report.get("analyst", {})
        return {
            "ticker": ticker, "company": report.get("company", ticker),
            "score": score, "reasons": reasons,
            "note": wl["notes"].get(ticker, ""),
            "price":        pd_data.get("current_price"),
            "change_1m":    pd_data.get("change_1m_pct"),
            "change_1y":    pd_data.get("change_1y_pct"),
            "sentiment":    ns.get("sentiment_label"),
            "put_call":     od.get("put_call_ratio"),
            "buy_hold_3y":  bt.get("buy_hold_return_pct"),
            "max_drawdown": bt.get("max_drawdown_pct"),
            "volatility":   bt.get("annualized_volatility_pct"),
            "short_float":  pd_data.get("short_float"),
            "headlines":    ns.get("headlines", [])[:5],
            "forecast":     fc,
            "analyst":      an,
            "insider_signal":  report.get("insider_trades", {}).get("insider_signal"),
            "congress_signal": report.get("congressional_trades", {}).get("congressional_signal"),
            "social_signal":   report.get("social_sentiment", {}).get("signal"),
            "gt_direction":    report.get("google_trends", {}).get("trend_direction"),
        }

    def generate():
        yield f"data: {json.dumps({'status':'start','name':wl['name'],'total':len(wl['tickers'])})}\n\n"

        collected = []

        def fetch_one(ticker):
            try:
                cached = _cached(ticker)
                if cached:
                    return _scored_row(ticker, cached)
                try:
                    ref = _polygon_get(f"/v3/reference/tickers/{ticker}")
                    company_name = ref.get("results", {}).get("name", ticker)
                except Exception:
                    company_name = ticker
                report = _build_report(ticker, company_name)
                return _scored_row(ticker, report)
            except Exception as e:
                return {"ticker": ticker, "error": str(e), "score": 0}

        # Sequential — one ticker at a time to stay within 512MB free tier RAM
        for ticker in wl["tickers"]:
            row = fetch_one(ticker)
            collected.append(row)
            yield f"data: {json.dumps({'status':'ticker','result':row,'done':len(collected),'total':len(wl['tickers'])})}\n\n"

        collected.sort(key=lambda x: x.get("score", 0), reverse=True)
        for i, r in enumerate(collected):
            r["rank"] = i + 1
        yield f"data: {json.dumps({'status':'complete','results':collected})}\n\n"

    return Response(stream_with_context(generate()), mimetype="text/event-stream")


@app.route("/api/watchlists")
def watchlists():
    from sector_dashboard import WATCHLISTS
    return jsonify({k: v["name"] for k, v in WATCHLISTS.items()})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
