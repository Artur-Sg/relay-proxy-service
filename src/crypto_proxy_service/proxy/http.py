from __future__ import annotations

from typing import Iterable
from urllib.parse import urlsplit

import httpx
from dataclasses import dataclass

from fastapi import Request, Response
import logging

from crypto_proxy_service.config import (
    HOP_BY_HOP_HEADERS,
    Settings,
    build_upstream_url,
)

logger = logging.getLogger("crypto_proxy_service.proxy")


@dataclass(slots=True)
class ProxyResult:
    response: Response
    result: str
    upstream_status: int | None
    upstream: str | None


def _filter_headers(headers: Iterable[tuple[str, str]]) -> dict[str, str]:
    filtered: dict[str, str] = {}
    for key, value in headers:
        if key.lower() in HOP_BY_HOP_HEADERS:
            continue
        filtered[key] = value
    return filtered


def _filter_response_headers(headers: Iterable[tuple[str, str]]) -> dict[str, str]:
    filtered = _filter_headers(headers)
    return {key: value for key, value in filtered.items() if key.lower() != "content-length"}


async def proxy_http_request(
    request: Request,
    upstreams: list[str],
    client: httpx.AsyncClient,
    settings: Settings,
) -> ProxyResult:
    if not upstreams:
        return ProxyResult(
            response=Response(content="Internal Server Error", status_code=500),
            result="no_upstreams",
            upstream_status=None,
            upstream=None,
        )

    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            if int(content_length) > settings.max_body_bytes:
                return ProxyResult(
                    response=Response(content="Payload Too Large", status_code=413),
                    result="payload_too_large",
                    upstream_status=None,
                )
        except ValueError:
            pass

    body = await request.body()
    if len(body) > settings.max_body_bytes:
        return ProxyResult(
            response=Response(content="Payload Too Large", status_code=413),
            result="payload_too_large",
            upstream_status=None,
        )
    headers = _filter_headers(request.headers.items())

    last_response: httpx.Response | None = None
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
            logger.exception(
                "Upstream request failed: method=%s upstream=%s url=%s",
                request.method,
                upstream_base,
                url,
            )
            continue

        last_response = upstream_response
        if upstream_response.status_code == 200:
            response_headers = _filter_response_headers(upstream_response.headers.items())
            return ProxyResult(
                response=Response(
                    content=upstream_response.content,
                    status_code=upstream_response.status_code,
                    headers=response_headers,
                ),
                result="ok",
                upstream_status=upstream_response.status_code,
                upstream=upstream_base,
            )
        try:
            error_body = upstream_response.text
        except Exception:
            error_body = "<unreadable>"
        if len(error_body) > 500:
            error_body = f"{error_body[:500]}...<truncated>"
        logger.warning(
            "Upstream returned non-200: method=%s upstream=%s url=%s status=%s body=%s",
            request.method,
            upstream_base,
            url,
            upstream_response.status_code,
            error_body,
        )
        if upstream_response.status_code < 500 and upstream_response.status_code not in (401, 403):
            return ProxyResult(
                response=Response(content="Internal Server Error", status_code=500),
                result="upstream_non_200",
                upstream_status=upstream_response.status_code,
                upstream=upstream_base,
            )

    if last_response is None:
        return ProxyResult(
            response=Response(content="Internal Server Error", status_code=500),
            result="upstream_unavailable",
            upstream_status=None,
            upstream=None,
        )

    return ProxyResult(
        response=Response(content="Internal Server Error", status_code=500),
        result="upstream_5xx",
        upstream_status=last_response.status_code,
        upstream=None,
    )
