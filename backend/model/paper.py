"""Paper trader: acts on each forecast with fake money. Fees included so results aren't fantasy."""
from ..hub import hub

FEE = 0.001        # 0.1% per side, Binance spot taker
THRESH = 0.05      # % predicted move needed to go long; below that, sit flat


class Paper:
    def __init__(self, cash=100_000.0):
        self.cash, self.qty, self.start, self.trades = cash, 0.0, cash, []

    def equity(self, px):
        return self.cash + self.qty * px

    def on_forecast(self, f, px):
        if f["ret_pct"] > THRESH and self.qty == 0:
            self.qty = self.cash * (1 - FEE) / px
            self.cash = 0.0
            self.trades.append({"side": "BUY", "px": px, "t": f["from_t"]})
        elif f["ret_pct"] < -THRESH and self.qty > 0:
            self.cash = self.qty * px * (1 - FEE)
            self.qty = 0.0
            self.trades.append({"side": "SELL", "px": px, "t": f["from_t"]})
        s = {"equity": self.equity(px), "pnl_pct": (self.equity(px) / self.start - 1) * 100,
             "pos": "LONG" if self.qty else "FLAT", "trades": self.trades[-20:], "n": len(self.trades)}
        hub.state["paper"] = s
        hub.publish("paper", s)


paper = Paper()

if __name__ == "__main__":  # self-check
    p = Paper(1000)
    p.on_forecast({"ret_pct": 1, "from_t": 0}, 100)
    p.on_forecast({"ret_pct": -1, "from_t": 1}, 110)
    assert p.qty == 0 and abs(p.cash - 1000 * 0.999 / 100 * 110 * 0.999) < 1e-9, p.cash
    p.on_forecast({"ret_pct": 0.01, "from_t": 2}, 120)  # below threshold -> no trade
    assert len(p.trades) == 2
    print("paper ok")
