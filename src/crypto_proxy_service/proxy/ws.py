from __future__ import annotations

import asyncio
import logging

import websockets
from fastapi import WebSocket

from crypto_proxy_service.config import Settings, build_upstream_ws_url

logger = logging.getLogger("crypto_proxy_service.proxy_ws")


async def _relay_ws(
    client_ws: WebSocket,
    upstream_ws: websockets.WebSocketClientProtocol,
) -> None:
    async def client_to_upstream() -> None:
        while True:
            message = await client_ws.receive()
            if message.get("type") == "websocket.disconnect":
                break
            if message.get("text") is not None:
                await upstream_ws.send(message["text"])
            elif message.get("bytes") is not None:
                await upstream_ws.send(message["bytes"])

    async def upstream_to_client() -> None:
        async for message in upstream_ws:
            if isinstance(message, bytes):
                await client_ws.send_bytes(message)
            else:
                await client_ws.send_text(message)

    await asyncio.gather(client_to_upstream(), upstream_to_client())


async def proxy_ws_request(
    client_ws: WebSocket,
    upstreams: list[str],
    path: str,
    query: str | None,
    settings: Settings,
) -> None:
    await client_ws.accept()

    if not upstreams:
        await client_ws.close(code=1011, reason="Internal Server Error")
        return

    for upstream_base in upstreams:
        ws_url = build_upstream_ws_url(upstream_base, path, query)
        try:
            async with websockets.connect(
                ws_url,
                open_timeout=settings.connect_timeout,
                close_timeout=settings.read_timeout,
            ) as upstream_ws:
                await _relay_ws(client_ws, upstream_ws)
                return
        except Exception:
            logger.exception("WS upstream connection failed: %s", ws_url)
            continue

    logger.error("All WS upstreams unavailable; closing client")
    await client_ws.close(code=1011, reason="Internal Server Error")
