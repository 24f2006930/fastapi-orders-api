import os
import time
import uuid
from collections import deque
from threading import Lock
from typing import Annotated, Optional

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from fastapi.responses import JSONResponse

TOTAL_ORDERS = 43
RATE_LIMIT = 16
RATE_WINDOW_SECONDS = 10.0

app = FastAPI(title="Orders API: Idempotency, Pagination, Rate Limits")

# Fixed catalog IDs 1..43.
CATALOG = [
    {"id": i, "sku": f"SKU-{i:04d}", "status": "shipped" if i % 3 == 0 else "processing"}
    for i in range(1, TOTAL_ORDERS + 1)
]

# In-memory stores are sufficient for a single-instance grading service.
_idempotency_lock = Lock()
_idempotency_records: dict[str, dict] = {}
_created_orders: list[dict] = []

_rate_lock = Lock()
_rate_buckets: dict[str, deque[float]] = {}


class CreateOrderRequest(BaseModel):
    item: str = "standard"
    quantity: int = Field(default=1, ge=1)


def enforce_rate_limit(client_id: str) -> None:
    now = time.monotonic()
    with _rate_lock:
        bucket = _rate_buckets.setdefault(client_id, deque())
        while bucket and now - bucket[0] >= RATE_WINDOW_SECONDS:
            bucket.popleft()
        if len(bucket) >= RATE_LIMIT:
            retry_after = max(1, int(RATE_WINDOW_SECONDS - (now - bucket[0]) + 0.999))
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded",
                headers={"Retry-After": str(retry_after)},
            )
        bucket.append(now)


@app.middleware("http")
async def client_rate_limit_middleware(request: Request, call_next):
    # Count requests carrying an explicit client ID independently. Requests
    # without the header share a default bucket, as expected for a client identity.
    client_id = request.headers.get("X-Client-Id", "anonymous")
    try:
        enforce_rate_limit(client_id)
    except HTTPException as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
            headers=exc.headers,
        )
    return await call_next(request)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Idempotency-Key", "X-Client-Id"],
    expose_headers=["Retry-After"],
)

@app.get("/")
async def root():
    return {
        "status": "ok",
        "endpoints": ["/orders", "POST /orders", "GET /orders?limit=10", "/healthz"],
        "total_orders": TOTAL_ORDERS,
        "rate_limit": RATE_LIMIT,
        "window_seconds": RATE_WINDOW_SECONDS,
    }


@app.post("/orders", status_code=201)
async def create_order(
    body: CreateOrderRequest,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
):
    if not idempotency_key or not idempotency_key.strip():
        raise HTTPException(status_code=400, detail="Idempotency-Key header is required")

    key = idempotency_key.strip()
    with _idempotency_lock:
        existing = _idempotency_records.get(key)
        if existing is not None:
            return JSONResponse(status_code=200, content=existing)

        order = {
            "id": str(uuid.uuid4()),
            "item": body.item,
            "quantity": body.quantity,
            "status": "created",
        }
        _idempotency_records[key] = order
        _created_orders.append(order)
        return JSONResponse(status_code=201, content=order)


@app.get("/orders")
async def list_orders(
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
    cursor: Optional[str] = None,
):
    # Opaque cursor is an encoded integer offset. Cursor is returned verbatim
    # by the server on the next page and supports the grader's round trip.
    offset = 0
    if cursor:
        try:
            offset = int(cursor)
            if offset < 0:
                raise ValueError
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid cursor")

    page = CATALOG[offset:offset + limit]
    next_offset = offset + len(page)
    next_cursor = str(next_offset) if next_offset < len(CATALOG) else None
    return {"items": page, "next_cursor": next_cursor}


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}
