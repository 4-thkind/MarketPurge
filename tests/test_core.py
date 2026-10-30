from datetime import datetime
from backend.feeds.nse import parse_indices, parse_symbols, market_open, nse_ts, IST
from backend.feeds.crypto import on_trade
from backend.hub import hub


def test_nse_parse_real_shapes():  # payloads captured from nseindia.com's heatmap page, 29-Oct-2026
    idx = parse_indices([{"close": 22698.85, "current": 22866.45, "index": "NIFTY 50", "pChange": 0.74,
                          "timeStamp": "29-Oct-2026 12:10:43"}])
    assert idx[0] == {"name": "NIFTY 50", "p": 22866.45, "chg": 0.74, "ts": "29-Oct-2026 12:10:43"}
    sym = parse_symbols([{"VWAP": "1818.09", "lastPrice": "1856.6", "pChange": "5.41", "quantityTraded": "8160706045.35",
                          "symbol": "ADANIPORTS", "lastUpdatedTime": "29-Oct-2026 12:10:50"}])
    assert sym["ADANIPORTS"]["chg"] == 5.41 and sym["ADANIPORTS"]["p"] == 1856.6


def test_nse_ts_is_ist():
    from datetime import timezone
    assert nse_ts("29-Oct-2026 12:10:50") == int(datetime(2026, 10, 29, 6, 40, 50, tzinfo=timezone.utc).timestamp() * 1000)


def test_market_hours():
    assert market_open(datetime(2026, 10, 29, 10, 0, tzinfo=IST))
    assert not market_open(datetime(2026, 10, 29, 16, 0, tzinfo=IST))
    assert not market_open(datetime(2026, 11, 1, 10, 0, tzinfo=IST))  # Sunday


def test_candles_from_trades():
    hub.candles.clear()
    on_trade(100, 1, 60_000)
    on_trade(105, 2, 90_000)
    on_trade(99, 1, 119_999)
    c = on_trade(101, 1, 120_000)          # new minute
    assert len(hub.candles) == 2 and c["o"] == 101
    first = hub.candles[0]
    assert (first["o"], first["h"], first["l"], first["c"], first["v"]) == (100, 105, 99, 99, 4)
    on_trade(500, 1, 70_000)               # late trade for closed minute is ignored
    assert hub.candles[0]["h"] == 105


def test_forecast_baseline(monkeypatch):
    from backend.model import forecaster
    from backend.model.forecaster import forecast, PRED_LEN
    monkeypatch.setattr(forecaster, "_pred", None)  # pin the EMA path even when Kronos is installed
    c = [{"t": i * 60000, "o": 100 + i, "h": 101 + i, "l": 99 + i, "c": 100 + i, "v": 1, "a": 1} for i in range(200)]
    p = forecast(c)
    assert len(p) == PRED_LEN and p[-1] > c[-1]["c"]
    assert all(type(v) is float for v in p)  # numpy floats leak np.bool_/int64 into hub state and break json
