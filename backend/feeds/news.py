"""News flow: polls market RSS feeds with conditional GET (ETag/Last-Modified), so an
unchanged feed costs ~nothing and we can poll every few seconds. New headlines are pushed instantly."""
import asyncio, hashlib, os, time
from email.utils import parsedate_to_datetime
import feedparser, httpx
from ..hub import hub

# (url, market) - market drives the filter chips, like TradingView News Flow's "Market" filter.
# TradingView's own feed is licensed (Reuters, Dow Jones...) and can't be redistributed; these are public RSS.
FEEDS = {
    "ET Markets": ("https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms", "India"),
    "Moneycontrol": ("https://www.moneycontrol.com/rss/marketreports.xml", "India"),
    "Livemint": ("https://www.livemint.com/rss/markets", "India"),
    "Business Standard": ("https://www.business-standard.com/rss/markets-106.rss", "India"),
    "CNBC": ("https://www.cnbc.com/id/100003114/device/rss/rss.html", "Global"),
    "Yahoo Finance": ("https://finance.yahoo.com/news/rssindex", "Global"),
    "CoinDesk": ("https://www.coindesk.com/arc/outboundfeeds/rss/", "Crypto"),
    "Cointelegraph": ("https://cointelegraph.com/rss", "Crypto"),
}
POLL_S = float(os.getenv("NEWS_POLL_S", "10"))
seen: set[str] = set()


def _ts(e):
    for f in ("published", "updated"):
        try:
            return int(parsedate_to_datetime(e[f]).timestamp() * 1000)
        except Exception:
            pass
    return int(time.time() * 1000)


async def _poll(c, name, url, market, cache):
    h = {}
    if cache.get("etag"): h["If-None-Match"] = cache["etag"]
    if cache.get("mod"): h["If-Modified-Since"] = cache["mod"]
    r = await c.get(url, headers=h)
    if r.status_code == 304:
        return []
    r.raise_for_status()
    cache["etag"], cache["mod"] = r.headers.get("etag"), r.headers.get("last-modified")
    fresh = []
    for e in feedparser.parse(r.content).entries[:20]:
        key = hashlib.sha1((e.get("link") or e.get("title", "")).encode()).hexdigest()
        if key in seen:
            continue
        seen.add(key)
        fresh.append({"id": key, "src": name, "market": market, "title": e.get("title", "").strip(), "url": e.get("link"), "ts": _ts(e)})
    return fresh


async def run():
    caches = {n: {} for n in FEEDS}
    first = True
    async with httpx.AsyncClient(timeout=8, follow_redirects=True, headers={"User-Agent": "MarketPulse/0.1"}) as c:
        while True:
            res = await asyncio.gather(*[_poll(c, n, u, m, caches[n]) for n, (u, m) in FEEDS.items()], return_exceptions=True)
            items = sorted([i for r in res if isinstance(r, list) for i in r], key=lambda x: x["ts"])
            for i in items:
                hub.state["news"].appendleft(i)
                if not first:  # don't spam the stream with the initial backlog
                    hub.publish("news", i, i["ts"])
            if first and items:
                hub.publish("news_reset", list(hub.state["news"]))
            first = False
            await asyncio.sleep(POLL_S)
