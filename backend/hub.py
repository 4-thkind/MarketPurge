"""Single in-memory state + pub/sub. Every feed writes here; every browser reads from here.
No polling on the client side: each update is pushed the moment it lands."""
import asyncio, json, time
from collections import deque


class Hub:
    def __init__(self):
        self.state = {"btc": None, "crypto_heat": {}, "nse_heat": {}, "news": deque(maxlen=60),
                      "forecast": None, "brief": None, "paper": None, "deriv": None, "nse_indices": {}}
        self.candles = deque(maxlen=1500)  # 1m BTC OHLCV, newest last
        self.clients: set[asyncio.Queue] = set()

    def subscribe(self) -> asyncio.Queue:
        q = asyncio.Queue(maxsize=500)
        self.clients.add(q)
        return q

    def unsubscribe(self, q):
        self.clients.discard(q)

    def publish(self, kind: str, data, src_ts_ms: int | None = None):
        """src_ts_ms = timestamp the *source* stamped on the event, so the UI can show true latency."""
        msg = json.dumps({"k": kind, "d": data, "src": src_ts_ms, "hub": int(time.time() * 1000)})
        for q in list(self.clients):
            if q.full():          # slow client: drop its oldest msg rather than stall everyone
                q.get_nowait()
            q.put_nowait(msg)

    def snapshot(self):
        s = dict(self.state)
        s["news"] = list(self.state["news"])
        s["candles"] = list(self.candles)[-200:]
        return s


hub = Hub()
