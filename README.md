# dynamicsserver

Nonce change.

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
- `POST /users/{id}/addresses`, `GET /users/{id}/addresses`, `PATCH /users/{id}/addresses/{address_id}`, `POST /users/{id}/addresses/{address_id}/set-default`

`payment_methods` exists in the schema but has no API yet — next up once checkout enters the picture.

## Tests

### Unit tests (mocked DB, no Postgres needed)

```bash
cd services/buyer-api
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest -q
```

### Integration tests (real Postgres + the real built image)

```bash
python3 -m venv .venv && source .venv/bin/activate   # from the repo root
pip install -r tests/integration/requirements.txt
./scripts/integration-test.sh
```

Spins up an isolated Postgres + buyer-api via `docker-compose.test.yml` (ports 5433/8001, so it won't
clash with a dev stack on 5432/8000), runs the suite, and tears everything down afterward — pass or fail.
