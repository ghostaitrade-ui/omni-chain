"""
Omni-Chain Web App
Flask server that serves the research engine via a web interface.
"""

import os
import json
import threading
from flask import Flask, render_template, request, jsonify, Response, stream_with_context
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)

# Cache recent reports in memory
report_cache = {}


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/research/<ticker>")
def research(ticker):
    ticker = ticker.upper().strip()
    if not ticker.isalpha() or len(ticker) > 5:
        return jsonify({"error": "Invalid ticker"}), 400

    def generate():
        yield f"data: {json.dumps({'status': 'running', 'message': f'Starting research on {ticker}...'})}\n\n"
        try:
            from research_engine import (
                get_price_data, get_options_data, get_news_sentiment,
                get_stocktwits_sentiment, get_insider_trades,
                get_polygon_details, get_google_trends,
                get_congressional_trades, get_backtesting_summary
            )
            import yfinance as yf
            from datetime import datetime

            company_name = yf.Ticker(ticker).info.get("longName", ticker)
            yield f"data: {json.dumps({'status': 'running', 'message': f'Fetching price data...'})}\n\n"
            price_data = get_price_data(ticker)

            yield f"data: {json.dumps({'status': 'running', 'message': 'Fetching options flow...'})}\n\n"
            options_data = get_options_data(ticker)

            yield f"data: {json.dumps({'status': 'running', 'message': 'Fetching news & sentiment...'})}\n\n"
            news_sentiment = get_news_sentiment(ticker)

            yield f"data: {json.dumps({'status': 'running', 'message': 'Fetching social sentiment...'})}\n\n"
            social_sentiment = get_stocktwits_sentiment(ticker)

            yield f"data: {json.dumps({'status': 'running', 'message': 'Fetching insider trades...'})}\n\n"
            insider_trades = get_insider_trades(ticker)

            yield f"data: {json.dumps({'status': 'running', 'message': 'Fetching company details...'})}\n\n"
            polygon_details = get_polygon_details(ticker)

            yield f"data: {json.dumps({'status': 'running', 'message': 'Fetching Google Trends...'})}\n\n"
            google_trends = get_google_trends(ticker, company_name)

            yield f"data: {json.dumps({'status': 'running', 'message': 'Checking congressional trades...'})}\n\n"
            congressional_trades = get_congressional_trades(ticker)

            yield f"data: {json.dumps({'status': 'running', 'message': 'Running backtest...'})}\n\n"
            backtest = get_backtesting_summary(ticker)

            report = {
                "ticker": ticker,
                "company": company_name,
                "generated": datetime.now().isoformat(),
                "price_data": price_data,
                "options_data": options_data,
                "news_sentiment": news_sentiment,
                "social_sentiment": social_sentiment,
                "insider_trades": insider_trades,
                "polygon_details": polygon_details,
                "google_trends": google_trends,
                "congressional_trades": congressional_trades,
                "backtest": backtest,
            }

            report_cache[ticker] = report
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
    from research_engine import (
        get_price_data, get_options_data, get_news_sentiment,
        get_stocktwits_sentiment, get_insider_trades, get_polygon_details,
        get_google_trends, get_congressional_trades, get_backtesting_summary
    )
    import yfinance as yf
    from datetime import datetime

    wl = WATCHLISTS.get(watchlist)
    if not wl:
        return jsonify({"error": f"Unknown watchlist: {watchlist}"}), 400

    results = []
    for ticker in wl["tickers"]:
        try:
            company_name = yf.Ticker(ticker).info.get("longName", ticker)
            report = {
                "ticker": ticker, "company": company_name,
                "generated": datetime.now().isoformat(),
                "price_data": get_price_data(ticker),
                "options_data": get_options_data(ticker),
                "news_sentiment": get_news_sentiment(ticker),
                "social_sentiment": get_stocktwits_sentiment(ticker),
                "insider_trades": get_insider_trades(ticker),
                "polygon_details": get_polygon_details(ticker),
                "google_trends": get_google_trends(ticker, company_name),
                "congressional_trades": get_congressional_trades(ticker),
                "backtest": get_backtesting_summary(ticker),
            }
            score, reasons = score_ticker(report)
            pd = report["price_data"]
            ns = report["news_sentiment"]
            bt = report["backtest"]
            od = report["options_data"]
            results.append({
                "ticker": ticker, "company": company_name,
                "score": score, "reasons": reasons,
                "note": wl["notes"].get(ticker, ""),
                "price": pd.get("current_price"),
                "change_1m": pd.get("change_1m_pct"),
                "change_1y": pd.get("change_1y_pct"),
                "sentiment": ns.get("sentiment_label"),
                "sentiment_score": ns.get("avg_sentiment_score"),
                "put_call": od.get("put_call_ratio"),
                "buy_hold_3y": bt.get("buy_hold_return_pct"),
                "max_drawdown": bt.get("max_drawdown_pct"),
                "volatility": bt.get("annualized_volatility_pct"),
                "short_float": pd.get("short_float"),
                "headlines": ns.get("headlines", [])[:3],
            })
        except Exception as e:
            results.append({"ticker": ticker, "error": str(e), "score": 0})

    results.sort(key=lambda x: x.get("score", 0), reverse=True)
    return jsonify({"watchlist": watchlist, "name": wl["name"], "results": results})


@app.route("/api/watchlists")
def watchlists():
    from sector_dashboard import WATCHLISTS
    return jsonify({k: v["name"] for k, v in WATCHLISTS.items()})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
