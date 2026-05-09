"""
Omni-Chain Research Engine
Aggregates news, sentiment, congressional trades, Google Trends,
SEC insider trades, StockTwits sentiment, and financial data.
"""

import os
import json
import time
import requests
import yfinance as yf
from datetime import datetime, timedelta
from dotenv import load_dotenv
from pytrends.request import TrendReq

load_dotenv()

# ── Shared session with browser-like headers to avoid Yahoo rate limits ──────
_session = requests.Session()
_session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
})

def _yf_ticker(ticker):
    """Return a yfinance Ticker using our shared session."""
    t = yf.Ticker(ticker)
    try:
        t.session = _session
    except Exception:
        pass
    return t

ALPHA_VANTAGE_KEY = os.getenv("ALPHA_VANTAGE_KEY")
FINNHUB_KEY       = os.getenv("FINNHUB_KEY", "")
NEWSAPI_KEY       = os.getenv("NEWSAPI_KEY", "")
POLYGON_KEY       = os.getenv("POLYGON_KEY", "")

# ─── DATA COLLECTORS ────────────────────────────────────────────────────────

def get_price_data(ticker):
    print(f"  [price] Fetching price data for {ticker}...")
    try:
        t = _yf_ticker(ticker)
        hist = t.history(period="1y")
        info = t.info
        price_now = hist["Close"].iloc[-1]
        price_1m  = hist["Close"].iloc[-22] if len(hist) > 22 else None
        price_3m  = hist["Close"].iloc[-66] if len(hist) > 66 else None
        price_1y  = hist["Close"].iloc[0]
        return {
            "current_price":   round(price_now, 2),
            "change_1m_pct":   round((price_now - price_1m) / price_1m * 100, 2) if price_1m else None,
            "change_3m_pct":   round((price_now - price_3m) / price_3m * 100, 2) if price_3m else None,
            "change_1y_pct":   round((price_now - price_1y) / price_1y * 100, 2),
            "52w_high":        round(hist["Close"].max(), 2),
            "52w_low":         round(hist["Close"].min(), 2),
            "avg_volume_30d":  int(hist["Volume"].tail(30).mean()),
            "market_cap":      info.get("marketCap"),
            "pe_ratio":        info.get("trailingPE"),
            "forward_pe":      info.get("forwardPE"),
            "dividend_yield":  info.get("dividendYield"),
            "beta":            info.get("beta"),
            "sector":          info.get("sector"),
            "industry":        info.get("industry"),
            "short_float":     info.get("shortPercentOfFloat"),
        }
    except Exception as e:
        return {"error": str(e)}


def get_options_data(ticker):
    print(f"  [options] Fetching options data for {ticker}...")
    try:
        t = _yf_ticker(ticker)
        expirations = t.options
        if not expirations:
            return {"error": "No options data available"}
        nearest = expirations[0]
        chain = t.option_chain(nearest)
        calls, puts = chain.calls, chain.puts
        total_call_oi = calls["openInterest"].sum()
        total_put_oi  = puts["openInterest"].sum()
        return {
            "nearest_expiry":    nearest,
            "put_call_ratio":    round(total_put_oi / total_call_oi, 2) if total_call_oi > 0 else None,
            "avg_call_iv_pct":   round(calls["impliedVolatility"].mean() * 100, 2),
            "avg_put_iv_pct":    round(puts["impliedVolatility"].mean() * 100, 2),
            "total_call_oi":     int(total_call_oi),
            "total_put_oi":      int(total_put_oi),
            "expirations_available": len(expirations),
        }
    except Exception as e:
        return {"error": str(e)}


def get_news_sentiment(ticker):
    """News from Finnhub + NewsAPI + Alpha Vantage sentiment scoring."""
    print(f"  [news] Fetching news for {ticker}...")
    headlines = []
    sentiment_scores = []

    # Finnhub — rich company news
    if FINNHUB_KEY:
        try:
            url = (f"https://finnhub.io/api/v1/company-news"
                   f"?symbol={ticker}"
                   f"&from={(datetime.now()-timedelta(days=7)).strftime('%Y-%m-%d')}"
                   f"&to={datetime.now().strftime('%Y-%m-%d')}"
                   f"&token={FINNHUB_KEY}")
            data = requests.get(url, timeout=10).json()
            if isinstance(data, list):
                for item in data[:15]:
                    headlines.append({
                        "headline": item.get("headline", ""),
                        "source":   item.get("source", ""),
                        "date":     datetime.fromtimestamp(item.get("datetime", 0)).strftime("%Y-%m-%d"),
                        "summary":  item.get("summary", "")[:200],
                        "url":      item.get("url", ""),
                    })
        except Exception:
            pass

    # NewsAPI — broad keyword search across 70k sources
    if NEWSAPI_KEY:
        try:
            t_info = _yf_ticker(ticker).info
            company = t_info.get("shortName", ticker)
            url = (f"https://newsapi.org/v2/everything"
                   f"?q={company}&language=en&sortBy=publishedAt"
                   f"&from={(datetime.now()-timedelta(days=7)).strftime('%Y-%m-%d')}"
                   f"&pageSize=10&apiKey={NEWSAPI_KEY}")
            data = requests.get(url, timeout=10).json()
            if data.get("status") == "ok":
                for item in data.get("articles", [])[:10]:
                    headlines.append({
                        "headline": item.get("title", ""),
                        "source":   item.get("source", {}).get("name", ""),
                        "date":     item.get("publishedAt", "")[:10],
                        "summary":  item.get("description", "")[:200],
                        "url":      item.get("url", ""),
                    })
        except Exception:
            pass

    # Alpha Vantage — sentiment scoring
    try:
        url = (f"https://www.alphavantage.co/query"
               f"?function=NEWS_SENTIMENT&tickers={ticker}"
               f"&limit=20&apikey={ALPHA_VANTAGE_KEY}")
        data = requests.get(url, timeout=10).json()
        if "feed" in data:
            for item in data["feed"]:
                for ts in item.get("ticker_sentiment", []):
                    if ts.get("ticker") == ticker:
                        sentiment_scores.append(float(ts.get("ticker_sentiment_score", 0)))
            if not headlines:
                for item in data["feed"][:10]:
                    headlines.append({
                        "headline": item.get("title", ""),
                        "source":   item.get("source", ""),
                        "date":     item.get("time_published", "")[:8],
                        "summary":  item.get("summary", "")[:200],
                        "url":      item.get("url", ""),
                    })
    except Exception:
        pass

    avg_sentiment = round(sum(sentiment_scores) / len(sentiment_scores), 3) if sentiment_scores else None
    label = "Bullish" if avg_sentiment and avg_sentiment > 0.1 else "Bearish" if avg_sentiment and avg_sentiment < -0.1 else "Neutral"

    return {
        "headlines":           headlines[:15],
        "headline_count":      len(headlines),
        "avg_sentiment_score": avg_sentiment,
        "sentiment_label":     label,
    }


def get_stocktwits_sentiment(ticker):
    """Social sentiment from StockTwits — no API key needed."""
    print(f"  [social] Fetching StockTwits sentiment for {ticker}...")
    try:
        url = f"https://api.stocktwits.com/api/2/streams/symbol/{ticker}.json"
        data = requests.get(url, timeout=10).json()
        messages = data.get("messages", [])
        bulls, bears = 0, 0
        recent_msgs = []
        for m in messages[:20]:
            sentiment = m.get("entities", {}).get("sentiment", {})
            if sentiment:
                if sentiment.get("basic") == "Bullish":
                    bulls += 1
                elif sentiment.get("basic") == "Bearish":
                    bears += 1
            recent_msgs.append({
                "text": m.get("body", "")[:140],
                "sentiment": sentiment.get("basic", "None") if sentiment else "None",
                "date": m.get("created_at", "")[:10],
            })
        total = bulls + bears
        bull_pct = round(bulls / total * 100, 1) if total > 0 else None
        return {
            "bull_pct":      bull_pct,
            "bear_pct":      round(bears / total * 100, 1) if total > 0 else None,
            "total_signals": total,
            "signal":        "Bullish" if bull_pct and bull_pct > 60 else "Bearish" if bull_pct and bull_pct < 40 else "Mixed",
            "recent_posts":  recent_msgs[:5],
        }
    except Exception as e:
        return {"error": str(e)}


def get_insider_trades(ticker):
    """SEC insider trading filings via Finnhub."""
    print(f"  [insider] Fetching insider trades for {ticker}...")
    try:
        if not FINNHUB_KEY:
            return {"error": "Finnhub key required"}
        url = f"https://finnhub.io/api/v1/stock/insider-transactions?symbol={ticker}&token={FINNHUB_KEY}"
        data = requests.get(url, timeout=10).json()
        txns = data.get("data", [])[:20]
        buys  = [t for t in txns if t.get("transactionType") in ["P-Purchase", "Buy"]]
        sells = [t for t in txns if t.get("transactionType") in ["S-Sale", "Sell"]]
        recent = [{
            "name":   t.get("name", ""),
            "type":   t.get("transactionType", ""),
            "shares": t.get("share", 0),
            "value":  t.get("value", 0),
            "date":   t.get("transactionDate", ""),
        } for t in txns[:5]]
        return {
            "recent_transactions": recent,
            "insider_buys":        len(buys),
            "insider_sells":       len(sells),
            "insider_signal":      "Bullish" if len(buys) > len(sells) else "Bearish" if len(sells) > len(buys) else "Neutral",
        }
    except Exception as e:
        return {"error": str(e)}


def get_polygon_details(ticker):
    """Polygon.io — ticker details, financials snapshot."""
    print(f"  [polygon] Fetching Polygon data for {ticker}...")
    try:
        if not POLYGON_KEY:
            return {"error": "Polygon key required"}
        url = f"https://api.polygon.io/v3/reference/tickers/{ticker}?apiKey={POLYGON_KEY}"
        data = requests.get(url, timeout=10).json().get("results", {})
        return {
            "description":    data.get("description", "")[:300],
            "employees":      data.get("total_employees"),
            "list_date":      data.get("list_date"),
            "homepage":       data.get("homepage_url"),
            "sic_description": data.get("sic_description"),
            "share_class_shares_outstanding": data.get("share_class_shares_outstanding"),
            "weighted_shares_outstanding":    data.get("weighted_shares_outstanding"),
        }
    except Exception as e:
        return {"error": str(e)}


def get_google_trends(ticker, company_name=None):
    print(f"  [trends] Fetching Google Trends for {ticker}...")
    try:
        pytrends = TrendReq(hl="en-US", tz=360)
        kw = company_name if company_name else ticker
        pytrends.build_payload([kw], timeframe="today 12-m")
        data = pytrends.interest_over_time()
        if data.empty:
            return {"error": "No trends data"}
        recent = int(data[kw].iloc[-1])
        avg    = int(data[kw].mean())
        return {
            "current_interest":    recent,
            "avg_12m_interest":    avg,
            "peak_12m_interest":   int(data[kw].max()),
            "trend_direction":     "Rising" if recent > avg else "Falling",
            "interest_vs_avg_pct": round((recent - avg) / avg * 100, 1) if avg > 0 else 0,
        }
    except Exception as e:
        return {"error": str(e)}


def get_congressional_trades(ticker):
    print(f"  [congress] Fetching congressional trades for {ticker}...")
    try:
        url = f"https://api.quiverquant.com/beta/historical/congresstrading/{ticker}"
        headers = {"Accept": "application/json", "User-Agent": "omni-chain-research/1.0"}
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            trades = r.json()
            recent = trades[:10] if trades else []
            buys  = [t for t in recent if "Purchase" in str(t.get("Transaction", ""))]
            sells = [t for t in recent if "Sale" in str(t.get("Transaction", ""))]
            return {
                "recent_trades":        recent[:5],
                "buy_count_recent":     len(buys),
                "sell_count_recent":    len(sells),
                "congressional_signal": "Bullish" if len(buys) > len(sells) else "Bearish" if len(sells) > len(buys) else "Neutral",
                "total_trades_found":   len(trades),
            }
        return {"error": f"Status {r.status_code}", "recent_trades": []}
    except Exception as e:
        return {"error": str(e), "recent_trades": []}


def get_backtesting_summary(ticker):
    print(f"  [backtest] Running backtest for {ticker}...")
    try:
        hist = _yf_ticker(ticker).history(period="3y")
        if hist.empty or len(hist) < 252:
            return {"error": "Insufficient history"}
        closes = hist["Close"]
        bh_return = round((closes.iloc[-1] - closes.iloc[0]) / closes.iloc[0] * 100, 2)
        ma50, ma200   = closes.rolling(50).mean(), closes.rolling(200).mean()
        signals       = (ma50 > ma200).astype(int)
        daily_returns = closes.pct_change()
        strat_returns = (signals.shift(1) * daily_returns).dropna()
        strat_total   = round((1 + strat_returns).prod() * 100 - 100, 2)
        drawdown      = (closes - closes.cummax()) / closes.cummax()
        return {
            "period":                  "3 years",
            "buy_hold_return_pct":     bh_return,
            "ma_crossover_return_pct": strat_total,
            "max_drawdown_pct":        round(drawdown.min() * 100, 2),
            "annualized_volatility_pct": round(daily_returns.std() * (252 ** 0.5) * 100, 2),
            "daily_win_rate_pct":      round((daily_returns > 0).sum() / len(daily_returns) * 100, 1),
            "data_points":             len(hist),
        }
    except Exception as e:
        return {"error": str(e)}


# ─── REPORT GENERATOR ───────────────────────────────────────────────────────

def generate_report(ticker):
    ticker = ticker.upper()
    print(f"\n{'='*60}")
    print(f"  OMNI-CHAIN RESEARCH ENGINE")
    print(f"  Ticker: {ticker}  |  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*60}\n")

    company_name = _yf_ticker(ticker).info.get("longName", ticker)

    report = {
        "ticker":              ticker,
        "company":             company_name,
        "generated":           datetime.now().isoformat(),
        "price_data":          get_price_data(ticker),
        "options_data":        get_options_data(ticker),
        "news_sentiment":      get_news_sentiment(ticker),
        "social_sentiment":    get_stocktwits_sentiment(ticker),
        "insider_trades":      get_insider_trades(ticker),
        "polygon_details":     get_polygon_details(ticker),
        "google_trends":       get_google_trends(ticker, company_name),
        "congressional_trades": get_congressional_trades(ticker),
        "backtest":            get_backtesting_summary(ticker),
    }

    pd = report["price_data"]
    od = report["options_data"]
    ns = report["news_sentiment"]
    ss = report["social_sentiment"]
    it = report["insider_trades"]
    gt = report["google_trends"]
    ct = report["congressional_trades"]
    bt = report["backtest"]

    sep = "=" * 60
    summary_lines = [
        f"\n{sep}",
        f"  RESEARCH SUMMARY: {ticker} — {company_name}",
        f"{sep}",
        f"\nPRICE & FUNDAMENTALS",
        f"  Current Price    : ${pd.get('current_price', 'N/A')}",
        f"  1-Month Change   : {pd.get('change_1m_pct', 'N/A')}%",
        f"  3-Month Change   : {pd.get('change_3m_pct', 'N/A')}%",
        f"  1-Year Change    : {pd.get('change_1y_pct', 'N/A')}%",
        f"  52-Week Range    : ${pd.get('52w_low')} - ${pd.get('52w_high')}",
        f"  P/E Ratio        : {pd.get('pe_ratio', 'N/A')}",
        f"  Beta             : {pd.get('beta', 'N/A')}",
        f"  Short Float      : {pd.get('short_float', 'N/A')}",
        f"  Sector           : {pd.get('sector', 'N/A')}",
        f"\nOPTIONS FLOW",
        f"  Put/Call Ratio   : {od.get('put_call_ratio', 'N/A')} ({'Bearish lean' if od.get('put_call_ratio') and od.get('put_call_ratio') > 1 else 'Bullish lean'})",
        f"  Avg Call IV      : {od.get('avg_call_iv_pct', 'N/A')}%",
        f"  Avg Put IV       : {od.get('avg_put_iv_pct', 'N/A')}%",
        f"  Nearest Expiry   : {od.get('nearest_expiry', 'N/A')}",
        f"\nNEWS SENTIMENT",
        f"  Signal           : {ns.get('sentiment_label', 'N/A')}",
        f"  Score            : {ns.get('avg_sentiment_score', 'N/A')}",
        f"  Headlines Found  : {ns.get('headline_count', 0)}",
    ]

    if ns.get("headlines"):
        summary_lines.append(f"\n  Recent Headlines:")
        for h in ns["headlines"][:5]:
            summary_lines.append(f"    • [{h.get('date','')}] {h.get('headline','')[:75]}")

    summary_lines += [
        f"\nSOCIAL SENTIMENT (StockTwits)",
        f"  Signal           : {ss.get('signal', 'N/A')}",
        f"  Bullish          : {ss.get('bull_pct', 'N/A')}%",
        f"  Bearish          : {ss.get('bear_pct', 'N/A')}%",
        f"  Signals Analyzed : {ss.get('total_signals', 0)}",
        f"\nINSIDER TRADES (SEC)",
        f"  Signal           : {it.get('insider_signal', 'N/A')}",
        f"  Recent Buys      : {it.get('insider_buys', 'N/A')}",
        f"  Recent Sells     : {it.get('insider_sells', 'N/A')}",
        f"\nGOOGLE TRENDS (Consumer Interest)",
        f"  Current          : {gt.get('current_interest', 'N/A')}/100",
        f"  12-Month Avg     : {gt.get('avg_12m_interest', 'N/A')}/100",
        f"  Direction        : {gt.get('trend_direction', 'N/A')}",
        f"  vs. Average      : {gt.get('interest_vs_avg_pct', 'N/A')}%",
        f"\nCONGRESSIONAL TRADES",
        f"  Signal           : {ct.get('congressional_signal', 'N/A')}",
        f"  Recent Buys      : {ct.get('buy_count_recent', 'N/A')}",
        f"  Recent Sells     : {ct.get('sell_count_recent', 'N/A')}",
        f"  Total on Record  : {ct.get('total_trades_found', 'N/A')}",
        f"\nBACKTEST (3 Years)",
        f"  Buy & Hold       : {bt.get('buy_hold_return_pct', 'N/A')}%",
        f"  MA Strategy      : {bt.get('ma_crossover_return_pct', 'N/A')}%",
        f"  Max Drawdown     : {bt.get('max_drawdown_pct', 'N/A')}%",
        f"  Annualized Vol   : {bt.get('annualized_volatility_pct', 'N/A')}%",
        f"  Daily Win Rate   : {bt.get('daily_win_rate_pct', 'N/A')}%",
        f"\n{sep}",
    ]

    summary = "\n".join(summary_lines)
    report["summary"] = summary
    print(summary)

    os.makedirs("knowledge", exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"knowledge/{ticker}_{timestamp}.json"
    with open(filename, "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\n  Report saved: {filename}")
    return report


# ─── ENTRY POINT ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    ticker = sys.argv[1].upper() if len(sys.argv) > 1 else "AAPL"
    generate_report(ticker)
