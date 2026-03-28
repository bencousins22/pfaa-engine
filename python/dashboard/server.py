"""
Aussie Agents Dashboard — FastAPI WebSocket server for memory + swarm visualization.
Serves a single-page HTML dashboard with real-time WebSocket updates.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
from typing import Any

# Add parent paths
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

logger = logging.getLogger("pfaa.dashboard")

HTML = """<!DOCTYPE html>
<html>
<head>
<title>Aussie Agents Dashboard</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { background: #1a1a2e; color: #e0e0e0; font-family: 'SF Mono', 'Fira Code', monospace; font-size: 14px; }
  .header { background: #6C3483; padding: 16px 24px; display: flex; align-items: center; gap: 16px; }
  .header h1 { color: white; font-size: 20px; font-weight: 700; }
  .header .badge { background: #1D8348; color: white; padding: 4px 12px; border-radius: 12px; font-size: 12px; }
  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; padding: 16px; }
  .card { background: #16213e; border-radius: 8px; padding: 16px; border: 1px solid #0f3460; }
  .card h2 { color: #85C1E9; font-size: 14px; margin-bottom: 12px; text-transform: uppercase; letter-spacing: 1px; }
  .stat { display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid #0f3460; }
  .stat-label { color: #6C3483; }
  .stat-value { color: #b3ffd9; font-weight: bold; }
  .bar { height: 8px; border-radius: 4px; margin-top: 4px; }
  .bar-fill { height: 100%; border-radius: 4px; transition: width 0.5s; }
  .bar-episode { background: #85C1E9; }
  .bar-concept { background: #6C3483; }
  .bar-principle { background: #FFA500; }
  .bar-skill { background: #1D8348; }
  .memory-item { padding: 8px; border-bottom: 1px solid #0f3460; }
  .memory-item .content { color: #b3ffd9; font-style: italic; }
  .memory-item .meta { color: #808080; font-size: 12px; margin-top: 4px; }
  .q-badge { display: inline-block; padding: 2px 6px; border-radius: 4px; font-size: 11px; font-weight: bold; }
  .q-high { background: #1D8348; color: white; }
  .q-mid { background: #FFA500; color: black; }
  .q-low { background: #e74c3c; color: white; }
  .log { background: #0d1117; border-radius: 4px; padding: 8px; max-height: 300px; overflow-y: auto; font-size: 12px; }
  .log-line { padding: 2px 0; }
  .log-line.tool { color: #85C1E9; }
  .log-line.agent { color: #b3ffd9; }
  .log-line.error { color: #e74c3c; }
  .log-line.status { color: #FFA500; }
  #status-dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
  .connected { background: #1D8348; }
  .disconnected { background: #e74c3c; }
  .full-width { grid-column: 1 / -1; }
</style>
</head>
<body>
<div class="header">
  <h1>Aussie Agents Dashboard</h1>
  <span class="badge">Platform for Autonomous Agents</span>
  <span id="status-dot" class="disconnected"></span>
  <span id="status-text" style="color:#808080;font-size:12px">connecting...</span>
</div>
<div class="grid">
  <div class="card">
    <h2>Memory Health</h2>
    <div id="memory-stats"></div>
  </div>
  <div class="card">
    <h2>Level Distribution</h2>
    <div id="level-bars"></div>
  </div>
  <div class="card">
    <h2>Recent Memories</h2>
    <div id="recent-memories" style="max-height:300px;overflow-y:auto"></div>
  </div>
  <div class="card">
    <h2>Q-Value Distribution</h2>
    <div id="q-dist"></div>
  </div>
  <div class="card full-width">
    <h2>Activity Log</h2>
    <div id="log" class="log"></div>
  </div>
</div>
<script>
let ws;
function connect() {
  ws = new WebSocket(`ws://${location.host}/ws`);
  ws.onopen = () => {
    document.getElementById('status-dot').className = 'connected';
    document.getElementById('status-text').textContent = 'connected';
    ws.send(JSON.stringify({type: 'status'}));
    ws.send(JSON.stringify({type: 'memories', limit: 20}));
  };
  ws.onclose = () => {
    document.getElementById('status-dot').className = 'disconnected';
    document.getElementById('status-text').textContent = 'disconnected';
    setTimeout(connect, 2000);
  };
  ws.onmessage = (e) => {
    const msg = JSON.parse(e.data);
    if (msg.type === 'status') renderStatus(msg.data);
    if (msg.type === 'memories') renderMemories(msg.data);
    if (msg.type === 'log') appendLog(msg.data);
  };
}

function renderStatus(s) {
  const el = document.getElementById('memory-stats');
  const m = s.memory || s;
  el.innerHTML = `
    <div class="stat"><span class="stat-label">Total</span><span class="stat-value">${m.total || 0}</span></div>
    <div class="stat"><span class="stat-label">Health</span><span class="stat-value">${m.health || '?'}</span></div>
    <div class="stat"><span class="stat-label">Maturity</span><span class="stat-value">${m.maturity || '?'}</span></div>
    <div class="stat"><span class="stat-label">Avg Q</span><span class="stat-value">${(m.avg_q_value || 0).toFixed(3)}</span></div>
    <div class="stat"><span class="stat-label">Links</span><span class="stat-value">${m.total_links || 0}</span></div>
  `;
  const bars = document.getElementById('level-bars');
  const levels = m.levels || {};
  const total = Object.values(levels).reduce((a, b) => a + b, 0) || 1;
  bars.innerHTML = Object.entries(levels).map(([lv, ct]) => `
    <div style="margin-bottom:8px">
      <div style="display:flex;justify-content:space-between"><span>${lv}</span><span>${ct}</span></div>
      <div class="bar"><div class="bar-fill bar-${lv}" style="width:${(ct/total*100).toFixed(0)}%"></div></div>
    </div>
  `).join('');
}

function renderMemories(mems) {
  const el = document.getElementById('recent-memories');
  el.innerHTML = mems.map(m => {
    const q = m.q_value || 0.5;
    const cls = q > 0.7 ? 'q-high' : q > 0.4 ? 'q-mid' : 'q-low';
    return `<div class="memory-item">
      <span class="q-badge ${cls}">Q=${q.toFixed(2)}</span>
      <span style="color:#6C3483;font-size:12px;margin-left:8px">[${m.level || 'episode'}]</span>
      <div class="content">${(m.content || '').substring(0, 120)}</div>
      <div class="meta">id=${(m.id || '').substring(0, 8)} · area=${m.area || '?'} · ret=${m.retrieval_count || 0}</div>
    </div>`;
  }).join('');
}

function appendLog(entry) {
  const el = document.getElementById('log');
  const cls = entry.type || 'status';
  const div = document.createElement('div');
  div.className = `log-line ${cls}`;
  div.textContent = `[${new Date().toLocaleTimeString()}] ${entry.message || JSON.stringify(entry)}`;
  el.appendChild(div);
  el.scrollTop = el.scrollHeight;
}

connect();
setInterval(() => { if (ws && ws.readyState === 1) ws.send(JSON.stringify({type:'status'})); }, 5000);
</script>
</body>
</html>"""


async def create_app():
    try:
        from fastapi import FastAPI, WebSocket, WebSocketDisconnect
        from fastapi.responses import HTMLResponse
    except ImportError:
        print("FastAPI not installed. Run: pip install fastapi uvicorn")
        return None

    app = FastAPI(title="Aussie Agents Dashboard")
    connections: list[WebSocket] = []

    @app.get("/")
    async def index():
        return HTMLResponse(HTML)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        await websocket.accept()
        connections.append(websocket)
        try:
            while True:
                raw = await websocket.receive_text()
                msg = json.loads(raw)

                if msg.get("type") == "status":
                    try:
                        from jmem.engine import JMemEngine
                        engine = JMemEngine.get()
                        async with engine:
                            ref = await engine.reflect()
                            status = await engine.status()
                        await websocket.send_json({"type": "status", "data": {**status, "memory": ref}})
                    except Exception as e:
                        await websocket.send_json({"type": "status", "data": {"error": str(e)}})

                elif msg.get("type") == "memories":
                    try:
                        from jmem.engine import JMemEngine
                        engine = JMemEngine.get()
                        async with engine:
                            all_docs = await engine.store.get_all()
                        mems = []
                        for doc in all_docs[-int(msg.get("limit", 20)):]:
                            m = doc["metadata"]
                            mems.append({
                                "id": doc["id"], "content": m.get("content", ""),
                                "level": m.get("level", "episode"), "q_value": float(m.get("q_value", 0.5)),
                                "area": m.get("area", "main"), "retrieval_count": int(m.get("retrieval_count", 0)),
                            })
                        await websocket.send_json({"type": "memories", "data": mems})
                    except Exception as e:
                        await websocket.send_json({"type": "memories", "data": []})

        except WebSocketDisconnect:
            connections.remove(websocket)

    return app


def main():
    import uvicorn
    logging.basicConfig(level=logging.INFO)
    app = asyncio.run(create_app())
    if app:
        uvicorn.run(app, host="0.0.0.0", port=8420, log_level="info")
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
