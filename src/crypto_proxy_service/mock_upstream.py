from __future__ import annotations

import os
import time
from typing import Any

from fastapi import FastAPI, Request


app = FastAPI(title="Mock Upstream")

NAME = os.getenv("MOCK_NAME", "upstream")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "name": NAME}

def run() -> None:
    import uvicorn

    port = int(os.getenv("MOCK_PORT", "9000"))
    uvicorn.run("crypto_proxy_service.mock_upstream:app", host="0.0.0.0", port=port)


if __name__ == "__main__":
    run()
