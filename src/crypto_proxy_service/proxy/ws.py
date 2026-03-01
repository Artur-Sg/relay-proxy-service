from __future__ import annotations

import asyncio
import logging
from collections import deque

import websockets
from fastapi import WebSocket

from crypto_proxy_service.config import Settings, build_upstream_ws_url

logger = logging.getLogger("crypto_proxy_service.proxy_ws")

_MAX_BUFFERED_MESSAGES = 100


async def _relay_ws(
    client_ws: WebSocket,
    upstream_ws: websockets.WebSocketClientProtocol,
    outgoing: asyncio.Queue[bytes | str],
    stop_event: asyncio.Event,
) -> None:
    async def client_to_buffer() -> None:
        try:
            while not stop_event.is_set():
                message = await client_ws.receive()
                if message.get("type") == "websocket.disconnect":
                    stop_event.set()
                    break
                if message.get("text") is not None:
                    payload: bytes | str = message["text"]
                elif message.get("bytes") is not None:
                    payload = message["bytes"]
                else:
                    continue

                if outgoing.full():
                    logger.warning("WS outgoing buffer full; closing client")
                    stop_event.set()
                    await client_ws.close(code=1011, reason="Internal Server Error")
                    break
                await outgoing.put(payload)
        except Exception:
            stop_event.set()

    async def buffer_to_upstream() -> None:
        try:
            while not stop_event.is_set():
                payload = await outgoing.get()
                await upstream_ws.send(payload)
        except Exception:
            stop_event.set()

    async def upstream_to_client() -> None:
        try:
            async for message in upstream_ws:
                if isinstance(message, bytes):
                    await client_ws.send_bytes(message)
                else:
                    await client_ws.send_text(message)
        except Exception:
            stop_event.set()

    await asyncio.gather(client_to_buffer(), buffer_to_upstream(), upstream_to_client())


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

    outgoing: asyncio.Queue[bytes | str] = asyncio.Queue(maxsize=_MAX_BUFFERED_MESSAGES)
    stop_event = asyncio.Event()

    order = deque(upstreams)
    while not stop_event.is_set():
        attempts = 0
        while attempts < len(upstreams) and not stop_event.is_set():
            upstream_base = order[0]
            order.rotate(-1)
            ws_url = build_upstream_ws_url(upstream_base, path, query)
            attempts += 1
            try:
                async with websockets.connect(
                    ws_url,
                    open_timeout=settings.connect_timeout,
                    close_timeout=settings.read_timeout,
                ) as upstream_ws:
                    await _relay_ws(client_ws, upstream_ws, outgoing, stop_event)
                    if stop_event.is_set():
                        return
            except Exception:
                logger.exception("WS upstream connection failed: %s", ws_url)
                continue

        if not stop_event.is_set():
            logger.error("All WS upstreams unavailable; closing client")
            await client_ws.close(code=1011, reason="Internal Server Error")
            return
