"""AI analyst: turns the live state (price, forecast, heatmaps, headlines) into a short investor brief.
Optional - needs ANTHROPIC_API_KEY. Runs every BRIEF_EVERY_S and on demand via /api/brief."""
import asyncio, json, os
from ..hub import hub

MODEL = os.getenv("ANALYST_MODEL", "claude-sonnet-5-5")
EVERY = int(os.getenv("BRIEF_EVERY_S", "300"))
PROMPT = """You are a markets desk analyst. Using ONLY the live data below, write "Key facts right now":
3-5 one-line bullets covering BTC (price, derivatives positioning, what the forecast model says and its live
hit rate), NIFTY (breadth, biggest movers, strongest/weakest sector index), and the headlines that matter.
End each bullet with its source in brackets, e.g. [Bitstamp], [NSE], [ET Markets], [Model].
Max 120 words. No advice, no hype. Skip anything the data doesn't support.

DATA:
{data}"""


def _context():
    s = hub.state
    movers = sorted(((k, v["chg"]) for k, v in s["nse_heat"].items() if k != "__index__"), key=lambda x: x[1])
    return json.dumps({
        "btc_last": s["btc"] and s["btc"]["p"],
        "forecast": s["forecast"] and {k: s["forecast"][k] for k in ("engine", "ret_pct", "horizon_min", "acc")},
        "nifty": s["nse_heat"].get("__index__"),
        "btc_derivatives": s["deriv"],
        "sector_indices": sorted(((i["name"], i["chg"]) for i in s["nse_indices"].get("Sectoral Indices", [])), key=lambda x: x[1]),
        "nifty_breadth": {"up": sum(c > 0 for _, c in movers), "down": sum(c < 0 for _, c in movers)},
        "nifty_losers": movers[:3], "nifty_gainers": movers[-3:],
        "crypto": {k: round(v["chg"], 2) for k, v in s["crypto_heat"].items()},
        "headlines": [f'{n["src"]}: {n["title"]}' for n in list(s["news"])[:15]],
    }, default=str)


async def brief():
    if not os.getenv("ANTHROPIC_API_KEY"):
        b = {"text": "Set ANTHROPIC_API_KEY to enable the AI analyst.", "model": None}
    else:
        from anthropic import AsyncAnthropic
        r = await AsyncAnthropic().messages.create(model=MODEL, max_tokens=400,
                                                   messages=[{"role": "user", "content": PROMPT.format(data=_context())}])
        b = {"text": r.content[0].text, "model": MODEL}
    hub.state["brief"] = b
    hub.publish("brief", b)
    return b


async def run():
    await asyncio.sleep(30)  # let feeds warm up
    while True:
        try:
            await brief()
        except Exception as e:
            print("[analyst]", e)
        await asyncio.sleep(EVERY)
