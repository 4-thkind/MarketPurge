# MarketPulse

Live market data → our own API → our own model → one dashboard.

```
Binance WS (BTC ticks, 1m candles, crypto heatmap) ─┐
NSE NIFTY 50 (heatmap, ~3s)                         ├─► Hub (in-memory, push) ─► /ws + /api/snapshot ─► dashboard
RSS news (ET, Moneycontrol, Mint, CoinDesk…, ~10s)  ┘          │
                                                               ├─► Forecaster (Kronos) ─► Paper trader
                                                               └─► AI Analyst (Claude) ─► investor brief
```

## Run
```bash
./setup.sh                                # deps + Kronos model (skip Kronos → EMA baseline)
uvicorn backend.main:app --port 8000      # open http://localhost:8000
MOCK=1 uvicorn backend.main:app           # offline demo, fake data
export ANTHROPIC_API_KEY=...              # enables the AI analyst panel
```

## Latency, honestly
- **BTC**: push WebSocket from the exchange. Every tick carries the exchange timestamp; the header shows real exchange→browser latency (typically 100–300 ms from India).
- **NSE**: the free/unofficial endpoint updates every few seconds. True tick-level NSE data needs a broker feed (Kite Connect, Upstox, Angel SmartAPI). Swap `feeds/nse.py:fetch` for the broker's tick handler; nothing downstream changes.
- **News**: RSS with conditional GET; a headline appears within ~10 s of the publisher pushing it.

## Model
`model/forecaster.py` runs Kronos (open-source foundation model for OHLCV candles) on live 1m BTC candles every minute, predicts the next 15 min, and **scores itself live** (direction hit-rate on the dashboard). The paper trader acts on each forecast with fees. Showing a live, self-scored hit-rate is what makes the investor demo credible.

## Add a source
Write `feeds/<name>.py` with an async `run()` that calls `hub.publish(kind, data, source_ts_ms)`, add it in `main.py`, add a handler in `frontend/index.html`.
