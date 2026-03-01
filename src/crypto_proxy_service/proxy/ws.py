from __future__ import annotations

import asyncio

import websockets
from fastapi import WebSocket

from crypto_proxy_service.config import Settings, build_upstream_ws_url


async def _relay_ws(client_ws: WebSocket, upstream_ws: websockets.WebSocketClientProtocol) -> None:
    async def client_to_upstream() -> None:
        try:
            while True:
                message = await client_ws.receive()
                if message.get("type") == "websocket.disconnect":
                    break
                if message.get("text") is not None:
                    await upstream_ws.send(message["text"])
                elif message.get("bytes") is not None:
                    await upstream_ws.send(message["bytes"])
        except Exception:
            pass

    async def upstream_to_client() -> None:
        try:
            async for message in upstream_ws:
                if isinstance(message, bytes):
                    await client_ws.send_bytes(message)
                else:
                    await client_ws.send_text(message)
        except Exception:
            pass

    await asyncio.gather(client_to_upstream(), upstream_to_client())


async def proxy_ws_request(
    client_ws: WebSocket,
    upstream_base: str,
    path: str,
    query: str | None,
    settings: Settings,
) -> None:
    await client_ws.accept()

    ws_url = build_upstream_ws_url(upstream_base, path, query)
    async with websockets.connect(
        ws_url,
        open_timeout=settings.connect_timeout,
        close_timeout=settings.read_timeout,
    ) as upstream_ws:
        await _relay_ws(client_ws, upstream_ws)
