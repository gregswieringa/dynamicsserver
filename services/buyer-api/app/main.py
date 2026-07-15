from fastapi import FastAPI
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


@app.get("/health")
async def health() -> dict:
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    return {"status": "ok"}
