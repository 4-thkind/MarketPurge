"""BTC/USD exactly like TradingView's BTCUSD page: same source (Bitstamp), tick-by-tick over WebSocket.
1m candles are built from those ticks. Binance public streams give the crypto heatmap and derivatives stats
(open interest, funding) that TradingView shows under 'Key stats'. No API keys anywhere."""
import asyncio, json, time
import httpx, websockets
from ..hub import hub

BITSTAMP_WS = "wss://ws.bitstamp.net"
BITSTAMP_OHLC = "https://www.bitstamp.net/api/v2/ohlc/btcusd/"
BINANCE_WS = "wss://data-stream.binance.vision/ws/!miniTicker@arr"
FAPI = "https://fapi.binance.com/fapi/v1"
HEAT_SYMBOLS = {"BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT", "DOGEUSDT", "AVAXUSDT",
                "DOTUSDT", "LINKUSDT", "TRXUSDT", "LTCUSDT", "XLMUSDT", "NEARUSDT", "BCHUSDT", "ATOMUSDT"}


async def seed_history():
    """Backfill 500 x 1m candles so the forecaster has context from second zero."""
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(BITSTAMP_OHLC, params={"step": 60, "limit": 500})
        r.raise_for_status()
    for k in r.json()["data"]["ohlc"]:
        hub.candles.append({"t": int(k["timestamp"]) * 1000, "o": float(k["open"]), "h": float(k["high"]),
                            "l": float(k["low"]), "c": float(k["close"]), "v": float(k["volume"]), "a": 0.0})


def on_trade(px: float, qty: float, ts_ms: int):
    """Fold one trade into the live 1m candle. Returns the candle."""
    t0 = ts_ms // 60_000 * 60_000
    c = hub.candles[-1] if hub.candles else None
    if c is None or c["t"] < t0:
        c = {"t": t0, "o": px, "h": px, "l": px, "c": px, "v": 0.0, "a": 0.0}
        hub.candles.append(c)
    elif c["t"] == t0:
        c.update(h=max(c["h"], px), l=min(c["l"], px), c=px)
    else:
        return c  # late trade for an already-closed minute: ignore
    c["v"] += qty
    c["a"] += px * qty
    return c


async def btc_stream():
    try:
        await seed_history()
    except Exception as e:
        print("[btc] history seed failed:", e)
    while True:
        try:
            async with websockets.connect(BITSTAMP_WS, ping_interval=20) as ws:
                await ws.send(json.dumps({"event": "bts:subscribe", "data": {"channel": "live_trades_btcusd"}}))
                print("[btc] connected to Bitstamp")
                async for raw in ws:
                    m = json.loads(raw)
                    if m.get("event") == "bts:request_reconnect":
                        break
                    if m.get("event") != "trade":
                        continue
                    d = m["data"]
                    ts = int(d["microtimestamp"]) // 1000
                    tick = {"p": float(d["price"]), "q": float(d["amount"]), "buy": d["type"] == 0, "T": ts}
                    hub.state["btc"] = tick
                    hub.publish("btc", tick, ts)
                    hub.publish("candle", on_trade(tick["p"], tick["q"], ts), ts)
        except Exception as e:
            print("[btc] dropped:", e, "- reconnecting")
            await asyncio.sleep(2)


async def heat_stream():
    while True:
        try:
            async with websockets.connect(BINANCE_WS, ping_interval=20, max_size=2**22) as ws:
                async for raw in ws:
                    d = json.loads(raw)
                    heat = {x["s"]: {"p": float(x["c"]), "chg": (float(x["c"]) / float(x["o"]) - 1) * 100,
                                     "vol": float(x["q"])} for x in d if x["s"] in HEAT_SYMBOLS}
                    if heat:
                        hub.state["crypto_heat"].update(heat)
                        hub.publish("crypto_heat", heat, d[0]["E"])
        except Exception as e:
            print("[heat] dropped:", e)
            await asyncio.sleep(2)


async def deriv_poll():
    """Open interest + funding rate, as on TradingView's 'Key stats'. Funding only changes every 8h; 15s is plenty."""
    async with httpx.AsyncClient(timeout=8) as c:
        while True:
            try:
                oi, pi = await asyncio.gather(c.get(f"{FAPI}/openInterest", params={"symbol": "BTCUSDT"}),
                                              c.get(f"{FAPI}/premiumIndex", params={"symbol": "BTCUSDT"}))
                s = {"oi_btc": float(oi.json()["openInterest"]), "funding_pct": float(pi.json()["lastFundingRate"]) * 100,
                     "mark": float(pi.json()["markPrice"])}
                s["oi_usd"] = s["oi_btc"] * s["mark"]
                hub.state["deriv"] = s
                hub.publish("deriv", s, int(time.time() * 1000))
            except Exception as e:
                print("[deriv]", e)
            await asyncio.sleep(15)


async def run():
    await asyncio.gather(btc_stream(), heat_stream(), deriv_poll())
