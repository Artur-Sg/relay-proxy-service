from __future__ import annotations

import uvicorn
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from http import HTTPStatus
import logging

from crypto_proxy_service.config import Settings, UpstreamPicker, load_settings
from crypto_proxy_service.metrics import HTTP_ERRORS_TOTAL, HTTP_RESPONSE_TIME_SECONDS
from crypto_proxy_service.proxy.http import ProxyResult, proxy_http_request
from crypto_proxy_service.proxy.ws import proxy_ws_request


settings = load_settings()
http_picker = UpstreamPicker(settings.http_upstreams, settings.strategy)
ws_upstreams = settings.ws_upstreams or settings.http_upstreams
ws_picker = UpstreamPicker(ws_upstreams, settings.strategy)


@asynccontextmanager
async def lifespan(app: FastAPI):
    timeout = httpx.Timeout(settings.read_timeout, connect=settings.connect_timeout)
    async with httpx.AsyncClient(timeout=timeout) as client:
        app.state.http_client = client
        yield

app = FastAPI(title="Crypto Proxy Service", lifespan=lifespan)
access_logger = logging.getLogger("uvicorn.error")


@app.middleware("http")
async def timing_middleware(request: Request, call_next):
    import time

    request.state.start_time = time.perf_counter()
    return await call_next(request)


@app.get("/metrics")
async def metrics() -> PlainTextResponse:
    data = generate_latest()
    return PlainTextResponse(content=data, media_type=CONTENT_TYPE_LATEST)


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def http_proxy(path: str, request: Request):
    first = http_picker.pick()
    ordered = [first] + [u for u in settings.http_upstreams if u != first]
    start = request.state.start_time if hasattr(request.state, "start_time") else None
    if start is None:
        import time

        start = time.perf_counter()

    result: ProxyResult = await proxy_http_request(
        request, ordered, request.app.state.http_client, settings
    )
    duration = None
    try:
        import time

        duration = time.perf_counter() - start
    except Exception:
        duration = None

    labels = {
        "method": request.method,
        "path": request.url.path,
        "status": str(result.response.status_code),
        "result": result.result,
        "upstream_status": str(result.upstream_status or ""),
    }
    if duration is not None:
        HTTP_RESPONSE_TIME_SECONDS.labels(**labels).observe(duration)
    if result.response.status_code >= 400:
        HTTP_ERRORS_TOTAL.labels(**labels).inc()

    try:
        client = request.client
        host = client.host if client else "-"
        port = client.port if client else "-"
        http_version = request.scope.get("http_version", "1.1")
        try:
            phrase = HTTPStatus(result.response.status_code).phrase
        except ValueError:
            phrase = ""
        upstream_used = result.upstream or (ordered[0] if ordered else "-")
        access_logger.info(
            '%s:%s - "%s %s HTTP/%s" %s %s upstream=%s',
            host,
            port,
            request.method,
            request.url.path,
            http_version,
            result.response.status_code,
            phrase,
            upstream_used,
        )
    except Exception:
        access_logger.exception("Failed to write access log")

    return result.response


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
