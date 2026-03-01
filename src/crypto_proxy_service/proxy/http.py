from __future__ import annotations

from typing import Iterable
from urllib.parse import urlsplit

import httpx
from fastapi import Request, Response
import logging

from crypto_proxy_service.config import (
    HOP_BY_HOP_HEADERS,
    Settings,
    build_upstream_url,
)

logger = logging.getLogger("crypto_proxy_service.proxy")


def _filter_headers(headers: Iterable[tuple[str, str]]) -> dict[str, str]:
    filtered: dict[str, str] = {}
    for key, value in headers:
        if key.lower() in HOP_BY_HOP_HEADERS:
            continue
        filtered[key] = value
    return filtered


async def proxy_http_request(
    request: Request,
    upstreams: list[str],
    settings: Settings,
) -> Response:
    if not upstreams:
        return Response(content="No upstreams configured", status_code=500)

    body = await request.body()
    headers = _filter_headers(request.headers.items())

    timeout = httpx.Timeout(settings.read_timeout, connect=settings.connect_timeout)
    last_response: httpx.Response | None = None
    async with httpx.AsyncClient(timeout=timeout) as client:
        for upstream_base in upstreams:
            url = build_upstream_url(
                upstream_base,
                request.url.path,
                request.url.query or None,
            )
            # Ensure upstream sees the correct Host header.
            headers["host"] = urlsplit(url).netloc
            try:
                upstream_response = await client.request(
                    request.method,
                    url,
                    content=body,
                    headers=headers,
                )
            except httpx.HTTPError:
                logger.exception("Upstream request failed: %s %s", request.method, url)
                continue

            last_response = upstream_response
            if upstream_response.status_code == 200:
                response_headers = _filter_headers(upstream_response.headers.items())
                return Response(
                    content=upstream_response.content,
                    status_code=upstream_response.status_code,
                    headers=response_headers,
                )
            try:
                error_body = upstream_response.text
            except Exception:
                error_body = "<unreadable>"
            if len(error_body) > 500:
                error_body = f"{error_body[:500]}...<truncated>"
            logger.warning(
                "Upstream returned non-200: %s %s -> %s, body=%s",
                request.method,
                url,
                upstream_response.status_code,
                error_body,
            )

    if last_response is None:
        return Response(content="Internal Server Error", status_code=500)

    return Response(content="Internal Server Error", status_code=500)
