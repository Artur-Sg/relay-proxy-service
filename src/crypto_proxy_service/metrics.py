from __future__ import annotations

from prometheus_client import Counter, Histogram

HTTP_RESPONSE_TIME_SECONDS = Histogram(
    "proxy_http_response_time_seconds",
    "HTTP response time from proxy",
    labelnames=["method", "path", "status", "result", "upstream_status"],
)

HTTP_ERRORS_TOTAL = Counter(
    "proxy_http_errors_total",
    "HTTP errors observed by proxy",
    labelnames=["method", "path", "status", "result", "upstream_status"],
)
