"""
Omni-Chain Web App — sequential, no threads, minimal memory footprint.
"""

import os
import json
import time
from flask import Flask, render_template, jsonify, Response, stream_with_context
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)

# ── Report cache: {ticker: {"ts": epoch, "report": {...}}} ───────────────────
_cache = {}
CACHE_TTL = 1800  # 30 min

def _cached(ticker):
    e = _cache.get(ticker)
    return e["report"] if e and (time.time() - e["ts"]) < CACHE_TTL else None

def _cache_set(ticker, report):
    _cache[ticker] = {"ts": time.time(), "report": report}


def _build_report(ticker, company_name, status_cb=None):
    """Sequential fetch — one API call at a time, minimal memory."""
    from research_engine import (
        get_price_data, get_options_data, get_news_sentiment,
        get_stocktwits_sentiment, get_insider_trades,
        get_polygon_details, get_google_trends,
        get_congressional_trades, get_backtesting_summary,
        get_price_forecast, get_analyst_targets,
    )
    from datetime import datetime

    def step(name, fn):
        if status_cb:
            status_cb(name)
        try:
            return fn()
        except Exception as e:
            return {"error": str(e)}

    # Polygon call count per ticker: 1 (bars, shared by price+backtest+forecast)
    # Finnhub calls: 4 (news, sentiment score, analyst target, analyst rec, insider)
    # Other: 2 (StockTwits, QuiverQuant) — all fast, no rate limits
    # Total: ~7 calls, ~15-20s per ticker
    report = {
        "ticker":              ticker,
        "company":             company_name,
        "generated":           datetime.now().isoformat(),
        "price_data":          step("Fetching price data...",        lambda: get_price_data(ticker)),
        "backtest":            step("Running backtest...",           lambda: get_backtesting_summary(ticker)),
        "forecast":            step("Building price forecast...",    lambda: get_price_forecast(ticker)),
        "analyst":             step("Fetching analyst targets...",   lambda: get_analyst_targets(ticker)),
        "news_sentiment":      step("Fetching news & sentiment...",  lambda: get_news_sentiment(ticker)),
        "social_sentiment":    step("Fetching social sentiment...",  lambda: get_stocktwits_sentiment(ticker)),
        "insider_trades":      step("Fetching insider trades...",    lambda: get_insider_trades(ticker)),
        "congressional_trades":step("Checking congress trades...",   lambda: get_congressional_trades(ticker)),
        # polygon_details and google_trends skipped on free tier (extra Polygon call + pytrends OOM)
        "polygon_details":     {"note": "Available on paid tier"},
        "options_data":        {"note": "Available on paid tier"},
        "google_trends":       {"note": "Available on paid tier"},
    }
    _cache_set(ticker, report)
    return report


def _scored_row(ticker, report, notes):
    from sector_dashboard import score_ticker
    score, reasons = score_ticker(report)
    pd = report.get("price_data", {})
    ns = report.get("news_sentiment", {})
    bt = report.get("backtest", {})
    od = report.get("options_data", {})
    fc = report.get("forecast", {})
    an = report.get("analyst", {})
    return {
        "ticker":          ticker,
        "company":         report.get("company", ticker),
        "score":           score,
        "reasons":         reasons,
        "note":            notes.get(ticker, ""),
        "price":           pd.get("current_price"),
        "change_1m":       pd.get("change_1m_pct"),
        "change_1y":       pd.get("change_1y_pct"),
        "sentiment":       ns.get("sentiment_label"),
        "put_call":        od.get("put_call_ratio"),
        "buy_hold_3y":     bt.get("buy_hold_return_pct"),
        "max_drawdown":    bt.get("max_drawdown_pct"),
        "volatility":      bt.get("annualized_volatility_pct"),
        "short_float":     pd.get("short_float"),
        "headlines":       ns.get("headlines", [])[:5],
        "forecast":        fc,
        "analyst":         an,
        "insider_signal":  report.get("insider_trades", {}).get("insider_signal"),
        "congress_signal": report.get("congressional_trades", {}).get("congressional_signal"),
        "social_signal":   report.get("social_sentiment", {}).get("signal"),
        "gt_direction":    report.get("google_trends", {}).get("trend_direction"),
    }


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/research/<ticker>")
def research(ticker):
    ticker = ticker.upper().strip()
    if not ticker.isalpha() or len(ticker) > 5:
        return jsonify({"error": "Invalid ticker"}), 400

    def generate():
        cached = _cached(ticker)
        if cached:
            yield f"data: {json.dumps({'status':'running','message':'Loading from cache...'})}\n\n"
            yield f"data: {json.dumps({'status':'complete','report':cached})}\n\n"
            return

        yield f"data: {json.dumps({'status':'running','message':f'Starting research on {ticker}...'})}\n\n"
        try:
            from research_engine import _polygon_get
            try:
                ref = _polygon_get(f"/v3/reference/tickers/{ticker}")
                company_name = ref.get("results", {}).get("name", ticker)
            except Exception:
                company_name = ticker

            messages = []

            def cb(msg):
                messages.append(msg)

            # Can't yield inside callback, so we yield a single progress message then build
            yield f"data: {json.dumps({'status':'running','message':f'Fetching all data for {ticker}...'})}\n\n"
            report = _build_report(ticker, company_name)

            os.makedirs("knowledge", exist_ok=True)
            from datetime import datetime
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            with open(f"knowledge/{ticker}_{ts}.json", "w") as f:
                json.dump(report, f, indent=2, default=str)

            yield f"data: {json.dumps({'status':'complete','report':report})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'status':'error','message':str(e)})}\n\n"

    return Response(stream_with_context(generate()), mimetype="text/event-stream")


@app.route("/api/dashboard/<watchlist>")
def dashboard(watchlist):
    from sector_dashboard import WATCHLISTS

    wl = WATCHLISTS.get(watchlist)
    if not wl:
        return jsonify({"error": f"Unknown watchlist: {watchlist}"}), 400

    def generate():
        tickers = wl["tickers"]
        yield f"data: {json.dumps({'status':'start','name':wl['name'],'total':len(tickers)})}\n\n"

        collected = []
        for i, ticker in enumerate(tickers):
            try:
                cached = _cached(ticker)
                if cached:
                    report = cached
                else:
                    from research_engine import _polygon_get
                    try:
                        ref = _polygon_get(f"/v3/reference/tickers/{ticker}")
                        company_name = ref.get("results", {}).get("name", ticker)
                    except Exception:
                        company_name = ticker
                    yield f"data: {json.dumps({'status':'ticker_loading','ticker':ticker,'done':i,'total':len(tickers)})}\n\n"
                    report = _build_report(ticker, company_name)

                row = _scored_row(ticker, report, wl["notes"])
            except Exception as e:
                row = {"ticker": ticker, "error": str(e), "score": 0}

            collected.append(row)
            yield f"data: {json.dumps({'status':'ticker','result':row,'done':i+1,'total':len(tickers)})}\n\n"

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
