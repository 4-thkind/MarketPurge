"""BTC forecaster on live 1m candles.

Uses Kronos (open-source foundation model for OHLCV candles, AAAI 2026, MIT) when it's installed
via setup.sh; otherwise falls back to an EMA-drift baseline so the app still runs.
Every minute: forecast next PRED_LEN candles -> publish -> paper trader acts on it -> later we score it."""
import asyncio, os, sys, time
from pathlib import Path
import pandas as pd
from ..hub import hub

PRED_LEN = int(os.getenv("PRED_LEN", "15"))
LOOKBACK = 400
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "vendor" / "Kronos"))

try:
    from model import Kronos, KronosTokenizer, KronosPredictor  # Kronos repo layout
    _tok = KronosTokenizer.from_pretrained("NeoQuasar/Kronos-Tokenizer-base")
    _mdl = Kronos.from_pretrained(os.getenv("KRONOS_MODEL", "NeoQuasar/Kronos-small"))
    _pred = KronosPredictor(_mdl, _tok, device=os.getenv("DEVICE", "cpu"), max_context=512)
    ENGINE = "kronos"
except Exception as e:
    print("[forecaster] Kronos unavailable, using EMA baseline:", e)
    _pred, ENGINE = None, "ema-baseline"


def forecast(candles: list[dict]) -> list[float]:
    """Return predicted closes for the next PRED_LEN minutes."""
    df = pd.DataFrame(candles[-LOOKBACK:])
    if _pred:
        ts = pd.to_datetime(df["t"], unit="ms")
        x = df.rename(columns={"o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"})
        y_ts = pd.Series(pd.date_range(ts.iloc[-1] + pd.Timedelta(minutes=1), periods=PRED_LEN, freq="1min"))
        # no "amount": seeded history has a=0 but live candles don't; Kronos derives it from volume * price instead
        out = _pred.predict(df=x[["open", "high", "low", "close", "volume"]], x_timestamp=ts,
                            y_timestamp=y_ts, pred_len=PRED_LEN, T=1.0, top_p=0.9, sample_count=3, verbose=False)
        return [float(v) for v in out["close"]]
    fast, slow = df["c"].ewm(span=8).mean().iloc[-1], df["c"].ewm(span=34).mean().iloc[-1]
    drift = (fast - slow) / slow / 10  # per-minute drift, damped
    last = df["c"].iloc[-1]
    return [float(last * (1 + drift) ** (i + 1)) for i in range(PRED_LEN)]  # plain floats: numpy types break json


async def run(on_forecast):
    scored = []  # (target_minute_ts, predicted_close) for live accuracy
    while True:
        await asyncio.sleep(60 - time.time() % 60 + 1)  # just after each minute closes
        # not candles[:-1]: BTC trades are sparse, so the newest candle may itself be the minute that just closed
        now_min = int(time.time()) // 60 * 60_000
        closed = [c for c in hub.candles if c["t"] < now_min]
        if len(closed) < 60 or closed[-1]["t"] == (hub.state["forecast"] or {}).get("from_t"):
            continue  # nothing new closed since the last forecast; don't forecast (and score) it twice
        # score forecasts whose target minute has now closed: did we call the direction right?
        # A minute with no trades has no candle, so use the last close at or before the target.
        px_at = lambda t: next(c["c"] for c in reversed(closed) if c["t"] <= t)
        due = [s for s in scored if s[0] <= closed[-1]["t"]]
        hits = [(p > base) == (px_at(t) > base) for t, p, base in due]

        try:
            preds = await asyncio.to_thread(forecast, closed)
        except Exception as e:  # one bad minute must not kill the forecaster task
            print("[forecaster]", e)
            continue
        scored = [s for s in scored if s[0] > closed[-1]["t"]]
        last = closed[-1]
        scored.append((last["t"] + 60_000 * PRED_LEN, preds[-1], last["c"]))
        prev = hub.state["forecast"] or {}
        acc = prev.get("acc", {"hits": 0, "n": 0})
        acc = {"hits": acc["hits"] + sum(hits), "n": acc["n"] + len(hits)}
        f = {"engine": ENGINE, "from_t": last["t"], "base": last["c"], "path": preds,
             "ret_pct": (preds[-1] / last["c"] - 1) * 100, "horizon_min": PRED_LEN, "acc": acc}
        hub.state["forecast"] = f
        hub.publish("forecast", f)
        on_forecast(f, last["c"])
