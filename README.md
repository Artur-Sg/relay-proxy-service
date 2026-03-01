# crypto-proxy-service

Skeleton Python service that accepts HTTP and WebSocket requests and proxies them to one of the upstreams from environment configuration.

## Requirements
- Python 3.11+

## Setup
1. Create `.env` from `.env.example` and adjust `UPSTREAMS` (and `WS_UPSTREAMS` if needed).
2. Install dependencies.

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

## Run
```bash
source .venv/bin/activate
uvicorn crypto_proxy_service.main:app --host 0.0.0.0 --port 8080 --reload
```

## Routes
- HTTP: `/{path}` (all methods)
- WebSocket: `/ws/{path}`

## Notes
- Hop-by-hop headers are filtered.
- WebSocket proxying is basic; add auth, timeouts, and better error handling as needed.

## Local mock upstreams
Run two mock upstreams with different ports/names:

```bash
source .venv/bin/activate
MOCK_NAME=upstream-1 uvicorn crypto_proxy_service.mock_upstream:app --host 0.0.0.0 --port 9000 --reload
```

```bash
source .venv/bin/activate
MOCK_NAME=upstream-2 uvicorn crypto_proxy_service.mock_upstream:app --host 0.0.0.0 --port 9001 --reload
```

Then set `.env`:
```
UPSTREAMS=http://localhost:9000,http://localhost:9001
UPSTREAM_STRATEGY=round_robin
```

Example requests:
```bash
curl -i http://localhost:8080/health
```

```bash
curl -i 'http://localhost:8080/prices?symbol=ETHUSDT&limit=3'
```

```bash
curl -i -X POST http://localhost:8080/orders \
  -H 'Content-Type: application/json' \
  -d '{"symbol":"BTCUSDT","side":"buy","qty":0.1,"price":68000}'
```

## Real upstream example (Polygon Amoy)
Configure `.env` to use real upstreams:
```
UPSTREAMS=https://polygon-amoy.api.onfinality.io/rpc?apikey=YOUR_API_KEY,https://polygon-amoy.drpc.org
WS_UPSTREAMS=
UPSTREAM_STRATEGY=random
```

If an upstream includes a path (like `/rpc`), call the proxy root `/` so it maps to that base path.

Example request through the proxy:
```bash
curl --request POST \
  --url http://localhost:8080/ \
  --header 'content-type: application/json' \
  --data '{
  "jsonrpc": "2.0",
  "method": "eth_blockNumber",
  "params": [],
  "id": 1
}'
```
