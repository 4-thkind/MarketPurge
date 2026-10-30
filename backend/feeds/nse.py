"""NSE heatmap, mirroring nseindia.com/market-data/live-market-indices/heatmap.

That page's 'Streaming' mode is not a WebSocket: it re-polls two JSON endpoints. We call the same two,
so our data is as fresh as NSE's own page:
  /api/heatmap-index?type=<category>                  -> index tiles (Broad / Sectoral / Thematic / Strategy)
  /api/heatmap-symbols?type=<category>&indices=<idx>  -> one tile per constituent stock

shortcut: unofficial endpoints behind Akamai bot protection (needs homepage cookies, can block servers),
and NSE's ToS restricts redistribution. OK for a prototype/investor demo. Before going public swap
`fetch_*` for a licensed broker feed (Kite Connect / Upstox / Angel SmartAPI); downstream is unchanged."""
import asyncio, os, time
from datetime import datetime, timedelta, timezone
import httpx
from ..hub import hub

CATEGORIES = ["Broad Market Indices", "Sectoral Indices", "Thematic Indices", "Strategy Indices"]
INDEX = os.getenv("NSE_INDEX", "NIFTY 50")
INDEX_CAT = os.getenv("NSE_INDEX_CATEGORY", "Broad Market Indices")
POLL_S = float(os.getenv("NSE_POLL_S", "5"))
IST = timezone(timedelta(hours=5, minutes=30))
BASE = "https://www.nseindia.com"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130 Safari/537.36",
           "Accept": "application/json", "Referer": f"{BASE}/market-data/live-market-indices/heatmap"}


def market_open(now=None):
    now = now or datetime.now(IST)
    return now.weekday() < 5 and (9, 15) <= (now.hour, now.minute) <= (15, 30)


def nse_ts(s: str) -> int:
    """'29-Oct-2026 12:10:50' (IST) -> epoch ms, so latency is measured from NSE's own update time."""
    return int(datetime.strptime(s, "%d-%b-%Y %H:%M:%S").replace(tzinfo=IST).timestamp() * 1000)


def parse_indices(rows):
    return [{"name": r["index"], "p": r["current"], "chg": r["pChange"], "ts": r["timeStamp"]} for r in rows]


def parse_symbols(rows):
    return {r["symbol"]: {"p": float(r["lastPrice"]), "chg": float(r["pChange"]), "vol": float(r["quantityTraded"]),
                          "vwap": float(r["VWAP"]), "ts": r["lastUpdatedTime"]} for r in rows}


async def run():
    async with httpx.AsyncClient(headers=HEADERS, timeout=8, follow_redirects=True) as c:
        primed = 0
        while True:
            try:
                if time.time() - primed > 300:  # Akamai cookies come from a normal page visit
                    await c.get(f"{BASE}/market-data/live-market-indices/heatmap")
                    primed = time.time()
                idx_res = await asyncio.gather(*[c.get(f"{BASE}/api/heatmap-index", params={"type": t}) for t in CATEGORIES])
                sym = await c.get(f"{BASE}/api/heatmap-symbols", params={"type": INDEX_CAT, "indices": INDEX})
                for r in (*idx_res, sym):
                    r.raise_for_status()

                indices = {t: parse_indices(r.json()) for t, r in zip(CATEGORIES, idx_res)}
                # NSE's CDN sometimes serves an older snapshot than the last poll; never step backwards
                old = hub.state["nse_indices"].get(CATEGORIES[0])
                if old and nse_ts(indices[CATEGORIES[0]][0]["ts"]) < nse_ts(old[0]["ts"]):
                    indices = hub.state["nse_indices"]
                if indices != hub.state["nse_indices"]:
                    hub.state["nse_indices"] = indices
                    hub.publish("nse_indices", indices, nse_ts(indices[CATEGORIES[0]][0]["ts"]))

                heat = parse_symbols(sym.json())
                me = next((i for i in indices[INDEX_CAT] if i["name"] == INDEX), None)
                if me:
                    heat["__index__"] = {"name": me["name"], "p": me["p"], "chg": me["chg"]}
                prev = hub.state["nse_heat"]
                changed = {k: v for k, v in heat.items() if prev.get(k) != v
                           and ("ts" not in v or k not in prev or nse_ts(v["ts"]) >= nse_ts(prev[k]["ts"]))}
                if changed:  # only push deltas
                    hub.state["nse_heat"].update(changed)
                    newest = max((v["ts"] for v in heat.values() if "ts" in v), key=nse_ts)
                    hub.publish("nse_heat", changed, nse_ts(newest))
            except Exception as e:
                print("[nse] fetch failed:", e)
                primed = 0
            await asyncio.sleep(POLL_S if market_open() else 60)  # prices are frozen after close
