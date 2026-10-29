# HANDOFF — MarketPulse (real-time market data product + AI model for investor demo)

Context transfer from a Claude.ai chat session (29 Oct 2026). Read this fully before touching code. The code in this folder is the current state; this file explains why it looks the way it does and what's next.

---

## 1. The assignment (in the owner's words, condensed)

Owner: **Utkarsh Singh** (B.Tech CSE-AI, MAIT). This is an **assigned task**, not a hackathon.

1. Pull market information from four reference websites (**TradingView BTCUSD page, TradingView News Flow, NSE India heatmap, Bloomberg Terminal**) into **our own API**, then show it on **our own website/product**.
2. Data must be **as new as it is on the source website** — no stale buffer. "Zero latency" was the ask; the honest target is *never older than the source site itself*.
3. Show **heatmaps** (stock-wise, like NSE / TradingView).
4. Have **our own AI model** that ingests this live info and does the job automatically. The model's purpose: **demo to investors** — "our model takes all this information and provides real-time intelligence." Paper trading models were the inspiration.
5. "The model should be ready now" — i.e. use a pretrained model, not a months-long training project.

### How the owner wants to work (follow these)
- Casual, efficient, no over-explanation. Crisp human prose, not AI-sounding.
- **Go through everything he attaches/names extensively by default.** He should never have to ask for thoroughness twice.
- Surgical edits over rebuilds.
- Mixes English/Hindi; reply in English.
- He was confused by being handed a zip without explanation — **always say what a deliverable contains and how to run it.**

---

## 2. What the reference sites actually do (researched live in a browser — don't redo this)

### TradingView BTCUSD (`tradingview.com/symbols/BTCUSD/`)
- Price source is **Bitstamp** (not Binance). Labelled "BTCUSD · Bitstamp". At research time BTC ≈ $80k.
- Page sections: price + change; performance (24h/1W/1M/3M/6M/YTD/1Y/5Y/10Y/All); **"Key facts today"** = AI-written bullets each with numbered source citations (options expiry, ETF flows, put/call ratio); **Key stats** = market cap, FDV, supply, **open interest, 24h liquidations, funding rate**; related coins list with % change; community posts; news list; ideas.
- Live data comes over TradingView's private socket (not usable/licensed). We replicate *the experience* from free primary sources.

### TradingView News Flow (`tradingview.com/news-flow/`)
- Full feed list, newest first. Each row: provider icon, "x minutes ago", provider name, headline.
- Filters: **Watchlist, Instrument, Market, Corporate activity, Crypto topics, Country, Provider** (multi-select).
- New items appear without refresh and **flash twice**. Clicking opens a **split-screen reader** on the right; full keyboard nav (arrows, PgUp/PgDn, Enter opens, Esc closes, Tab switches focus).
- Content is **licensed** (Reuters, Dow Jones, dpa-AFX, Quartr, Moody's…), paywalled → **cannot be scraped/redistributed**. We use public RSS instead with the same UX.

### NSE India heatmap (`nseindia.com/market-data/live-market-indices/heatmap`)
- 4 category tabs: **Broad Market Indices (21), Sectoral, Thematic, Strategy**. Colour legend +5/+3/+1/0/−1/−3/−5 %. "As on <timestamp> IST" + refresh. Clicking an index shows its constituent stocks heatmap.
- **"Streaming On" is NOT a WebSocket** — verified by hooking `WebSocket`/`EventSource` (none opened). It re-polls JSON endpoints (~every 15s observed):
  - `GET /api/heatmap-index-catergory-list` → `["Broad Market Indices","Sectoral Indices","Thematic Indices","Strategy Indices"]` (typo "catergory" is NSE's)
  - `GET /api/heatmap-index?type=Broad%20Market%20Indices` → `[{index, indexLongName, current, close, open, high, low, pChange, timeStamp:"29-Oct-2026 12:10:43", yrHigh, yrLow}, …]`
  - `GET /api/heatmap-symbols?type=Broad%20Market%20Indices&indices=NIFTY%2050` → 50 rows: `{symbol, lastPrice, change, pChange, VWAP, high, low, quantityTraded, totalTradedVolume, series, marketType, lastUpdatedTime}` — **all numbers are strings**.
  - `GET /api/marketStatus` → `marketState[]` with Capital Market open/closed, NIFTY last.
- Protected by **Akamai bot detection** (POSTs to an obfuscated `/WTauFd3c/...` sensor path). Server-side requests need cookies from a normal page visit and may still get blocked. NSE ToS restricts redistribution.
- Conclusion: calling the same endpoints at the same cadence = **exactly as fresh as NSE's own page**. True tick-level NSE requires a licensed broker feed.

### Bloomberg Terminal
- Paid product (~$30k/yr), no data obtainable. Borrow **design ideas only**: Launchpad = customizable multi-panel workspace with security monitors, alerts, charting, market-moving news; "most-read news" analytics; dense dark terminal aesthetic. The dashboard already follows the multi-panel idea.

---

## 3. Data source decisions (and why)

| Need | Source | Mechanism | Freshness |
|---|---|---|---|
| BTC/USD price + 1m candles | **Bitstamp** `wss://ws.bitstamp.net`, channel `live_trades_btcusd`; history `GET https://www.bitstamp.net/api/v2/ohlc/btcusd/?step=60&limit=500` | WebSocket push, candles built from trades | ~100–300 ms from India, matches TradingView |
| Crypto heatmap | Binance `wss://data-stream.binance.vision/ws/!miniTicker@arr` | WS push, 1s | 24h % change |
| BTC derivatives (OI, funding) | Binance futures `fapi.binance.com/fapi/v1/openInterest`, `/premiumIndex` (BTCUSDT) | poll 15s | funding changes every 8h |
| NSE indices + stock heatmap | NSE endpoints above | poll 5s in market hours (09:15–15:30 IST Mon–Fri), 60s otherwise | same as nseindia.com |
| News | RSS: ET Markets, Moneycontrol, Livemint, Business Standard (India); CNBC, Yahoo Finance (Global); CoinDesk, Cointelegraph (Crypto) | poll 10s with ETag/If-Modified-Since, dedupe by SHA1(link) | ~10s after publisher |
| Production NSE (later) | Zerodha **Kite Connect** (₹2,000/mo + data add-on, 3,000 instruments WS), **Upstox v2**, **Angel One SmartAPI** (free, 1,000 instruments, 100–400 ms) | broker WS | tick-level, licensed |

---

## 4. The model (investor-demo story)

- **Kronos** — open-source foundation model for financial candlesticks (OHLCV "K-lines"), trained on 45+ global exchanges, **AAAI 2026**, MIT license, repo `github.com/shiyu-coder/Kronos`. Already pretrained → "ready now".
  - HF weights: `NeoQuasar/Kronos-mini` (4.1M, ctx 2048, CPU-friendly), `NeoQuasar/Kronos-small` (24.7M, ctx 512, **default**), `NeoQuasar/Kronos-base` (102.3M, ctx 512). Tokenizer `NeoQuasar/Kronos-Tokenizer-base` (mini uses `Kronos-Tokenizer-2k`). Large (499M) not public.
  - Not on pip — `setup.sh` clones the repo into `vendor/Kronos` and the code imports `from model import Kronos, KronosTokenizer, KronosPredictor`.
  - API: `KronosPredictor(model, tokenizer, device, max_context=512).predict(df=[open,high,low,close,volume,amount], x_timestamp, y_timestamp, pred_len, T=1.0, top_p=0.9, sample_count=N)` → DataFrame with `close` column.
- **Fallback**: if Kronos import fails, an EMA(8/34) drift baseline runs so the app never breaks. Dashboard shows which engine is live.
- **Self-scoring (the key pitch)**: every minute it forecasts the next 15 min, and when the target minute closes it scores **direction hit-rate live** on the dashboard. "Watch its track record in real time" is credible to investors; "it predicts the market" is not. Never claim profitability.
- **Paper trader**: $100k fake capital, goes long if predicted 15-min move > +0.05%, exits if < −0.05%, **0.1% fee per side** so results aren't fantasy.
- **AI Analyst**: Claude (`claude-sonnet-5-5`, env `ANALYST_MODEL`) writes "Key facts right now" — 3–5 bullets each ending with a bracketed source ([Bitstamp], [NSE], [Moneycontrol], [Model]), mirroring TradingView's Key facts. Every 5 min + on demand. Needs `ANTHROPIC_API_KEY`.

---

## 5. Architecture & files

```
marketpulse/
├─ backend/
│  ├─ hub.py            single in-memory state + pub/sub fan-out. publish(kind, data, src_ts_ms)
│  ├─ main.py           FastAPI: GET / (dashboard), GET /api/snapshot, GET /api/brief, WS /ws
│  ├─ mock.py           MOCK=1 offline random-walk data in the exact real shapes
│  ├─ feeds/
│  │  ├─ crypto.py      Bitstamp BTC trades→candles (on_trade), Binance heatmap, Binance OI/funding
│  │  ├─ nse.py         NSE heatmap endpoints, parse_indices/parse_symbols, nse_ts (IST→epoch ms), market_open
│  │  └─ news.py        RSS conditional-GET poller, FEEDS = {name: (url, market)}
│  └─ model/
│     ├─ forecaster.py  Kronos/EMA forecast every minute + live hit-rate scoring
│     ├─ paper.py       paper trader (has __main__ self-check)
│     └─ analyst.py     Claude brief from hub state
├─ frontend/index.html  single page, vanilla JS, TradingView lightweight-charts@4.2.0 from unpkg
├─ tests/test_core.py   5 tests (NSE parsing on real captured payloads, IST timestamps, market hours, candle builder, forecast)
├─ setup.sh             pip install + clone Kronos + its requirements
├─ requirements.txt     fastapi, uvicorn[standard], websockets, httpx, feedparser, pandas, anthropic
└─ README.md
```

### Data flow
feeds → `hub.state` + `hub.publish()` → every connected browser gets the message instantly over `/ws`. On connect the client first receives `{"k":"snapshot","d":{...}}`. Slow clients drop their oldest message instead of blocking others (queue max 500).

### WebSocket message contract `{"k": kind, "d": data, "src": source_ts_ms, "hub": hub_ts_ms}`
| kind | data |
|---|---|
| `btc` | `{p, q, buy, T}` single trade |
| `candle` | `{t, o, h, l, c, v, a}` current 1m candle (t = minute start, ms) |
| `crypto_heat` | `{SYMBOL: {p, chg, vol}}` deltas |
| `deriv` | `{oi_btc, oi_usd, funding_pct, mark}` |
| `nse_indices` | `{category: [{name, p, chg, ts}]}` |
| `nse_heat` | `{SYMBOL: {p, chg, vol, vwap, ts}, "__index__": {name, p, chg}}` deltas only |
| `news` / `news_reset` | `{id, src, market, title, url, ts}` / list |
| `forecast` | `{engine, from_t, base, path[15], ret_pct, horizon_min, acc:{hits, n}}` |
| `paper` | `{equity, pnl_pct, pos, trades[], n}` |
| `brief` | `{text, model}` |

`src` = timestamp the **source** stamped (Bitstamp microtimestamp, NSE lastUpdatedTime) → header shows true source→browser latency.

### Env vars
`MOCK=1`, `ANTHROPIC_API_KEY`, `ANALYST_MODEL`, `BRIEF_EVERY_S` (300), `KRONOS_MODEL` (NeoQuasar/Kronos-small), `DEVICE` (cpu/cuda:0), `PRED_LEN` (15), `NSE_INDEX` (NIFTY 50), `NSE_INDEX_CATEGORY`, `NSE_POLL_S` (5), `NEWS_POLL_S` (10).

### Run
```bash
./setup.sh                               # deps + Kronos (~100MB weights on first run)
uvicorn backend.main:app --port 8000     # http://localhost:8000
MOCK=1 uvicorn backend.main:app          # offline demo
python -m pytest -q tests
```

---

## 6. Verification status — be honest about this

**Verified (in a sandbox with no internet):** 5/5 tests pass; mock mode end-to-end over the WebSocket (all message kinds flowing); dashboard JS parses; paper-trader self-check; NSE parsers tested against **real payloads captured from nseindia.com**.

**NOT verified yet — do these first:**
1. Real run against Bitstamp WS + OHLC REST, Binance WS + futures REST (`fapi.binance.com` may be geo-blocked in some regions).
2. NSE from a server (Akamai may block; it worked from a real browser). Test **during market hours**.
3. Every RSS URL — some may have moved/403; drop or replace dead ones.
4. Kronos actually loading and predicting (`predict()` signature from README; check `out["close"]` shape and CPU latency with sample_count=3 — must finish well under 60s; drop to Kronos-mini or sample_count=1 if slow).
5. Dashboard visually in a real browser (never rendered — chart lib is CDN-loaded).

---

## 7. Known risks / shortcuts (marked `shortcut:` in code)
- NSE endpoints are unofficial + ToS-restricted → demo only. Swap `nse.py`'s fetching for a broker feed before going public; downstream unchanged.
- TradingView/Bloomberg data itself is not usable — we mirror UX, not data.
- In-memory state: restart = lose news/paper history. Fine for demo.
- Analyst model string `claude-sonnet-5-5` — confirm it's valid on the account.
- Client latency number assumes the viewer's clock is synced.

---

## 8. Next steps (priority order)
1. **Do section 6 checks**, fix whatever breaks.
2. **News Flow parity**: split-screen reader panel (click headline → right pane), keyboard nav, Provider/Country filters, and tag headlines to instruments (BTC, NIFTY stocks) so clicking a heatmap tile filters news to that symbol.
3. **NSE parity**: click an index tile → load that index's constituents (`heatmap-symbols?type=<cat>&indices=<name>`; needs a client→server request or a small `GET /api/nse/symbols` endpoint), show "As on <ts> IST", `marketStatus` badge.
4. **BTCUSD parity**: performance row (24h/1W/1M/YTD/1Y from Bitstamp daily OHLC), 24h liquidations (Binance `!forceOrder@arr` WS), related coins list.
5. **Investor-demo polish**: a "Model track record" panel (hit-rate over time chart, paper equity curve), persisted to SQLite so it survives restarts and accumulates history before the pitch. Run it for days before the demo.
6. Optionally fine-tune Kronos on BTC 1m data (repo has finetune scripts) and report baseline-vs-Kronos-vs-finetuned hit rates — strong investor slide.
7. Deploy (single small VM; uvicorn behind nginx with WS upgrade). Production NSE via Angel SmartAPI (free) or Kite Connect.

Keep it lean: no new frameworks unless needed; vanilla JS frontend is intentional.
