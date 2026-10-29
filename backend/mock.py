"""Offline mode (MOCK=1): random-walk data in the same shapes the real feeds emit.
For demos without internet and for testing the UI/pipeline."""
import asyncio, random, time
from .hub import hub

NIFTY = ["RELIANCE", "HDFCBANK", "ICICIBANK", "INFY", "TCS", "BHARTIARTL", "ITC", "LT", "SBIN", "AXISBANK",
         "KOTAKBANK", "HINDUNILVR", "BAJFINANCE", "M&M", "MARUTI", "SUNPHARMA", "TITAN", "NTPC", "TATAMOTORS", "ULTRACEMCO"]
CRYPTO = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT", "AVAXUSDT"]


async def run():
    px, now = 68000.0, int(time.time() // 60 * 60_000)
    for i in range(500, 0, -1):  # history
        o = px; px *= 1 + random.gauss(0, 0.0008)
        hub.candles.append({"t": now - i * 60_000, "o": o, "h": max(o, px) * 1.0003, "l": min(o, px) * 0.9997,
                            "c": px, "v": random.uniform(5, 50), "a": 0})
    nse = {s: {"p": random.uniform(200, 4000), "chg": random.gauss(0, 1), "vol": random.uniform(1e8, 1e10)} for s in NIFTY}
    n = 0
    while True:
        await asyncio.sleep(0.2)
        n += 1
        px *= 1 + random.gauss(0, 0.0002)
        ts = int(time.time() * 1000)
        tick = {"p": px, "q": random.uniform(0.001, 0.5), "buy": random.random() > 0.5, "T": ts}
        hub.state["btc"] = tick
        hub.publish("btc", tick, ts)
        t0 = ts // 60_000 * 60_000
        c = hub.candles[-1]
        if c["t"] != t0:
            hub.candles.append({"t": t0, "o": px, "h": px, "l": px, "c": px, "v": 0, "a": 0})
        else:
            c.update(h=max(c["h"], px), l=min(c["l"], px), c=px, v=c["v"] + tick["q"])
        hub.publish("candle", hub.candles[-1], ts)
        if n % 5 == 0:
            for s in random.sample(NIFTY, 4):
                nse[s]["chg"] += random.gauss(0, 0.05)
            nse["__index__"] = {"name": "NIFTY 50 (mock)", "p": 24500, "chg": sum(v["chg"] for k, v in nse.items() if k != "__index__") / len(NIFTY)}
            hub.state["nse_heat"].update(nse)
            hub.publish("nse_heat", nse, ts)
            idx = {cat: [{"name": f"NIFTY {n}", "p": 10000, "chg": random.gauss(0, 1), "ts": ""} for n in names]
                   for cat, names in {"Broad Market Indices": ["50", "NEXT 50", "100", "500"],
                                      "Sectoral Indices": ["BANK", "IT", "AUTO", "PHARMA", "FMCG", "METAL"],
                                      "Thematic Indices": ["ENERGY", "INFRA"], "Strategy Indices": ["ALPHA 50"]}.items()}
            hub.state["nse_indices"] = idx
            hub.publish("nse_indices", idx, ts)
            d = {"oi_btc": 95000, "oi_usd": 95000 * px, "funding_pct": 0.0054, "mark": px}
            hub.state["deriv"] = d
            hub.publish("deriv", d, ts)
            heat = {s: {"p": 1, "chg": random.gauss(0, 2), "vol": random.uniform(1e6, 1e9)} for s in CRYPTO}
            hub.state["crypto_heat"].update(heat)
            hub.publish("crypto_heat", heat, ts)
        if n % 50 == 0:
            item = {"id": str(n), "src": "Mock Wire", "market": random.choice(["India", "Global", "Crypto"]), "title": f"Mock headline #{n // 50}", "url": "#", "ts": ts}
            hub.state["news"].appendleft(item)
            hub.publish("news", item, ts)
