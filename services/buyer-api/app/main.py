import socket

from fastapi import FastAPI, Request
from prometheus_fastapi_instrumentator import Instrumentator
from sqlalchemy import text

from app.db import engine
from app.routers import addresses, users

app = FastAPI(title="buyer-api")
app.include_router(users.router)
app.include_router(addresses.router)

# Exposes /metrics: http_requests_total{method,handler,status} and
# http_request_duration_seconds{method,handler} (a histogram -- Grafana
# queries it for per-operation latency percentiles). Scraped by Prometheus
# in docker-compose.observability.yml, not used in dev/test.
Instrumentator().instrument(app).expose(app)

# Docker sets a container's hostname to its own short container ID by
# default, so this is a distinct value per replica with no extra compose
# config -- lets you watch which of prod's 4 instances answered a given
# request straight from Postman/curl.
_INSTANCE_ID = socket.gethostname()


@app.middleware("http")
async def add_instance_id_header(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Instance-Id"] = _INSTANCE_ID
    return response


@app.get("/health")
async def health() -> dict:
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    return {"status": "ok"}
