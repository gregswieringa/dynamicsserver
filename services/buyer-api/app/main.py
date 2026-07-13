from fastapi import FastAPI
from sqlalchemy import text

from app.db import engine
from app.routers import addresses, users

app = FastAPI(title="buyer-api")
app.include_router(users.router)
app.include_router(addresses.router)


@app.get("/health")
async def health() -> dict:
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    return {"status": "ok"}
