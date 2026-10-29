"""MarketPulse API.
  WS   /ws            live push stream (btc ticks, candles, heatmaps, news, forecast, brief, paper)
  GET  /api/snapshot  full current state (for first paint / other consumers)
  GET  /api/brief     regenerate the AI brief now
Run: uvicorn backend.main:app --port 8000   (MOCK=1 to run without internet)"""
import asyncio, os
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from .hub import hub
from .model import analyst, forecaster
from .model.paper import paper


@asynccontextmanager
async def lifespan(app):
    if os.getenv("MOCK"):
        from . import mock
        tasks = [mock.run()]
    else:
        from .feeds import crypto, news, nse
        tasks = [crypto.run(), nse.run(), news.run()]
    tasks += [forecaster.run(paper.on_forecast), analyst.run()]
    running = [asyncio.create_task(t) for t in tasks]
    yield
    for t in running:
        t.cancel()


app = FastAPI(title="MarketPulse", lifespan=lifespan)
UI = Path(__file__).resolve().parents[1] / "frontend" / "index.html"


@app.get("/")
def index():
    return FileResponse(UI)


@app.get("/api/snapshot")
def snapshot():
    return hub.snapshot()


@app.get("/api/brief")
async def brief():
    return await analyst.brief()


@app.websocket("/ws")
async def ws(sock: WebSocket):
    await sock.accept()
    q = hub.subscribe()
    try:
        await sock.send_json({"k": "snapshot", "d": hub.snapshot()})
        while True:
            await sock.send_text(await q.get())
    except WebSocketDisconnect:
        pass
    finally:
        hub.unsubscribe(q)
