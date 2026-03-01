from __future__ import annotations

import uvicorn
from fastapi import FastAPI, Request, WebSocket

from crypto_proxy_service.config import Settings, UpstreamPicker, load_settings
from crypto_proxy_service.proxy.http import proxy_http_request
from crypto_proxy_service.proxy.ws import proxy_ws_request


settings = load_settings()
http_picker = UpstreamPicker(settings.http_upstreams, settings.strategy)
ws_upstreams = settings.ws_upstreams or settings.http_upstreams
ws_picker = UpstreamPicker(ws_upstreams, settings.strategy)

app = FastAPI(title="Crypto Proxy Service")


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def http_proxy(path: str, request: Request):
    first = http_picker.pick()
    ordered = [first] + [u for u in settings.http_upstreams if u != first]
    return await proxy_http_request(request, ordered, settings)


@app.websocket("/ws/{path:path}")
async def ws_proxy(path: str, websocket: WebSocket):
    first = ws_picker.pick()
    ordered = [first] + [u for u in (settings.ws_upstreams or settings.http_upstreams) if u != first]
    full_path = f"/{path}"
    await proxy_ws_request(websocket, ordered, full_path, websocket.url.query or None, settings)


def run() -> None:
    uvicorn.run("crypto_proxy_service.main:app", host="0.0.0.0", port=8080, reload=True)


if __name__ == "__main__":
    run()
