# dynamicsserver

A distributed marketplace, built as a systems-design learning lab — Etsy-shaped (accounts, stores, catalog, cart, checkout, inventory), backend-first, no real users.

## Phase 0: buyer-api

The first service: buyer/user profiles backed by Postgres.

```
db/init/001_buyer_schema.sql   # schema source of truth (users, addresses, payment_methods)
services/buyer-api/            # FastAPI service
```

Run it:

```
docker compose up -d --build
curl localhost:8000/health
```

API docs (Swagger UI) at `localhost:8000/docs` once running.

Endpoints:
- `POST /users`, `GET /users`, `GET /users/{id}`, `PATCH /users/{id}`
- `POST /users/{id}/addresses`, `GET /users/{id}/addresses`, `POST /users/{id}/addresses/{address_id}/set-default`

`payment_methods` exists in the schema but has no API yet — next up once checkout enters the picture.
