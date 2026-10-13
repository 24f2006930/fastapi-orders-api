# FastAPI Orders API

FastAPI service demonstrating idempotent order creation, cursor-based pagination, per-client rate limiting, and CORS support.

## Repository name

`fastapi-orders-api`

## Repository description

FastAPI orders API demonstrating idempotent POST requests, cursor-based pagination across 43 catalog orders, per-client rate limiting, and CORS.

## Live API

Base URL: https://fastapi-orders-api-ehd1.onrender.com

Interactive API documentation: https://fastapi-orders-api-ehd1.onrender.com/docs

## Features

- **Idempotent creation:** `POST /orders` requires `Idempotency-Key`. Repeating a key returns the same order ID and does not create another order.
- **Cursor pagination:** `GET /orders?limit=P&cursor=C` pages through catalog IDs 1–43 without gaps or duplicates.
- **Per-client rate limiting:** `X-Client-Id` clients receive up to 16 requests per 10-second window. Further requests receive HTTP 429 and `Retry-After`.
- **CORS:** Allows cross-origin browser requests and exposes the Retry-After response header.

## Endpoints

### Create an order

```bash
curl -i -X POST "https://YOUR-SERVICE.onrender.com/orders" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: example-key-001" \
  -d '{"item":"standard","quantity":1}'
```

The first request returns HTTP 201. Repeating the same idempotency key returns the same order ID.

### List catalog orders

```bash
curl "https://YOUR-SERVICE.onrender.com/orders?limit=10"
curl "https://YOUR-SERVICE.onrender.com/orders?limit=10&cursor=10"
```

Pass the returned `next_cursor` into the next request until it is `null`.

### Check rate limiting

```bash
curl -i "https://YOUR-SERVICE.onrender.com/orders?limit=1" -H "X-Client-Id: client-a"
```

The rate-limit bucket is isolated per client ID.

## Deployment

Deploy using Render Blueprint and the included `render.yaml`.

## Implementation note

The idempotency records and rate-limit buckets are held in process memory. This is suitable for a single-instance grading deployment, but a multi-instance production service should use a shared datastore and atomic operations.
