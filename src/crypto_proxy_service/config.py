from __future__ import annotations

import os
import random
from dataclasses import dataclass
from itertools import cycle
from typing import Iterable

from dotenv import load_dotenv
from urllib.parse import SplitResult, urlsplit, urlunsplit


HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}


@dataclass(slots=True)
class Settings:
    http_upstreams: list[str]
    ws_upstreams: list[str]
    strategy: str
    connect_timeout: float
    read_timeout: float


def _parse_upstreams(value: str) -> list[str]:
    items = [item.strip().rstrip("/") for item in value.split(",")]
    return [item for item in items if item]


def load_settings() -> Settings:
    load_dotenv()
    http_upstreams_raw = os.getenv("UPSTREAMS", "")
    http_upstreams = _parse_upstreams(http_upstreams_raw)
    if not http_upstreams:
        http_upstreams = ["http://localhost:9000"]

    ws_upstreams_raw = os.getenv("WS_UPSTREAMS", "")
    ws_upstreams = _parse_upstreams(ws_upstreams_raw)

    strategy = os.getenv("UPSTREAM_STRATEGY", "random").lower()
    connect_timeout = float(os.getenv("CONNECT_TIMEOUT", "5"))
    read_timeout = float(os.getenv("READ_TIMEOUT", "30"))

    return Settings(
        http_upstreams=http_upstreams,
        ws_upstreams=ws_upstreams,
        strategy=strategy,
        connect_timeout=connect_timeout,
        read_timeout=read_timeout,
    )


class UpstreamPicker:
    def __init__(self, upstreams: Iterable[str], strategy: str) -> None:
        self._upstreams = list(upstreams)
        self._strategy = strategy
        self._cycle = cycle(self._upstreams)

    def pick(self) -> str:
        if not self._upstreams:
            raise RuntimeError("No upstreams configured")
        if self._strategy == "round_robin":
            return next(self._cycle)
        return random.choice(self._upstreams)


def build_upstream_url(upstream_base: str, path: str, query: str | None) -> str:
    base = urlsplit(upstream_base)
    base_path = base.path.rstrip("/")

    if path == "/":
        full_path = base_path or "/"
    else:
        if base_path:
            full_path = f"{base_path}{path}"
        else:
            full_path = path

    if query:
        if base.query:
            full_query = f"{base.query}&{query}"
        else:
            full_query = query
    else:
        full_query = base.query

    rebuilt = SplitResult(
        scheme=base.scheme,
        netloc=base.netloc,
        path=full_path,
        query=full_query,
        fragment="",
    )
    return urlunsplit(rebuilt)


def build_upstream_ws_url(upstream_base: str, path: str, query: str | None) -> str:
    base_url = build_upstream_url(upstream_base, path, query)
    if base_url.startswith("http://"):
        return base_url.replace("http://", "ws://", 1)
    if base_url.startswith("https://"):
        return base_url.replace("https://", "wss://", 1)
    return base_url
