# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A distributed marketplace (Etsy/Amazon/Grubhub-shaped: accounts, stores, catalog, cart, checkout, inventory)
built as a personal systems-design learning lab — backend-first, no real users, built incrementally
across many sessions. Optimize for teaching real distributed-systems behavior (multi-region consistency,
observability, chaos testing) over product completeness.

Budget ceiling: $50/month hosting. Planned compute mix (later phases): Oracle Cloud Always Free tier +
cheap Hetzner VMs in different real locations, used to simulate genuine multi-region latency/outages
rather than same-host containers pretending to be "regions."

### Roadmap (phased, each phase assumes the ones before it)

0. One service, one datastore — **current phase, in progress**
1. Split marketplace core into services (users, catalog, cart, orders, inventory) behind a gateway
2. Introduce messaging (Redpanda/Kafka) for order/inventory events
3. Move to local k8s (kind/k3d), Helm charts, HPA
4. Real multi-node cluster spanning Oracle free tier + Hetzner VMs
5. Observability: Prometheus + Grafana + Loki
6. CI/CD: Jenkins pipelines, post-deploy smoke tests
7. Load testing: k6 simulating thousands of virtual shoppers
8. Chaos engineering: Pumba/Chaos Mesh/Toxiproxy — kill pods, kill a region, corrupt DNS
9. Capstone: multi-region inventory consistency (naive counters → event-sourced ledger → CRDTs → sagas)

## Commands

```bash
# start everything (Postgres + buyer-api)
docker compose up -d --build

# rebuild after model/schema changes
docker compose down -v          # -v wipes the pg volume — db/init/*.sql only runs on a fresh volume
docker compose up -d --build

# logs
docker compose logs buyer-api --tail 60
docker compose logs postgres --tail 60      # constraint-violation DETAIL lines show up here, not in the app log

# health check
curl localhost:8000/health

# Swagger UI
# localhost:8000/docs

# unit tests for a service (buyer-api shown; no DB needed, see below)
cd services/buyer-api
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest -q
```

No linter is set up yet.

### Unit tests mock the database — no Postgres required

`services/<name>-api/tests/` drives the routers through `fastapi.testclient.TestClient`, overriding the
`get_db` dependency with `tests/fake_db.py::FakeSession` — a dict-backed double that implements just enough
of `AsyncSession` (`add`/`get`/`flush`/`commit`/`refresh`/`execute` for `select`/`update`) to run the actual
router code with zero DB connection. It reproduces the ORM's behavior of applying Python-side column
defaults (`default=uuid.uuid4`, `default=_utcnow`, etc.) at flush time by reading them off the SQLAlchemy
mapper, so it doesn't need updating when `models.py` changes.

`FakeSession` only understands the query shapes the routers currently issue (`select`/`update` over
`User`/`Address` with equality/`is_`/`order_by`/`limit`/`offset`); anything else raises `NotImplementedError`
on purpose. If a new router introduces a new query shape, extend `_matches`/`_execute_*` in `fake_db.py`
rather than adding a one-off mock inside a test file.

To simulate a DB-level failure (e.g. the constraint-violation branch in `create_user`), set
`fake_session.raise_on_commit` to an exception from `make_integrity_error(constraint_name, message)`, which
reconstructs the same `exc.orig.__cause__`-with-`.constraint_name` chain asyncpg produces (see
"Integrity-error handling pattern" below) — this is what regression-tests the duplicate-email-vs-other-
constraint mislabeling bug.

### Exposing a service to external tools (Postman, etc.) from this Codespace

Ports default to `private` (requires a browser-authenticated GitHub session, which tools like Postman can't
do). To let an external tool hit a service directly:

```bash
gh codespace ports visibility 8000:public -c "$CODESPACE_NAME"
# ... use https://$CODESPACE_NAME-8000.$GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN ...
gh codespace ports visibility 8000:private -c "$CODESPACE_NAME"   # revert when done
```

## Architecture

### Layout

```
db/init/*.sql              # schema source of truth, applied via postgres docker-entrypoint-initdb.d
services/<name>-api/       # one FastAPI service per bounded context; buyer-api is the first
docker-compose.yml         # wires postgres + all services together
```

Each future service gets its own directory under `services/`, its own Dockerfile, and joins the
same `docker-compose.yml`. Expect a `catalog-api`, `cart-api`, `orders-api`, `inventory-api`, etc. to
follow the same shape as `buyer-api`.

### Schema-first, not migration-first

`db/init/001_buyer_schema.sql` is the authoritative schema definition — it runs once, automatically,
when the `postgres` container's volume is first created. SQLAlchemy models under `services/*/app/models.py`
are a query-layer mirror of that DDL; they never call `create_all()`. Postgres `ENUM` types (`account_status`,
`user_role`, `address_kind`) are declared with `create_type=False` on the SQLAlchemy side for this reason.
When the schema changes, edit the `.sql` file and `docker compose down -v` to force a fresh apply — there is
no Alembic/migration tooling yet.

### SQLAlchemy default gotchas (already hit these once — don't reintroduce them)

Postgres has server-side defaults (`gen_random_uuid()`, `now()`) for `id`/`created_at`/`updated_at`, but
`Mapped[T]` columns without an explicit default still send a literal `NULL` on insert rather than omitting
the column — Postgres then rejects it as a NOT NULL violation. Every such column needs a matching
Python-side default (`default=uuid.uuid4`, `default=_utcnow`) in the model. Relatedly, `Mapped[datetime]`
infers a timezone-*naive* column type unless the column is declared with `mapped_column(DateTime(timezone=True), ...)`
— needed here since every timestamp column in the DDL is `timestamptz`.

### Integrity-error handling pattern

`exc.orig` on a caught `sqlalchemy.exc.IntegrityError` (asyncpg dialect) is a wrapper that only carries
`pgcode`/`sqlstate` — the real driver exception, with `.constraint_name` and `.message`, is chained as
`exc.orig.__cause__`. Inspect that, not `exc.orig` directly, when branching on which constraint failed
(see `routers/users.py`). A bare `except IntegrityError` that assumes a single cause (e.g. "must be the
unique email") will silently mislabel unrelated failures — this happened once with the `phone_e164` CHECK
constraint reporting as a duplicate-email error.

### Validation duplicated by design

Phone numbers are validated in two places on purpose: `schemas.py` (Pydantic, regex-matches E.164) for a
fast, clear 422 at the API boundary, and the `phone_e164` CHECK constraint in the DDL as a DB-level backstop.
Keep both in sync if the format rule ever changes.

### Default-address/payment-method invariant

`addresses` and `payment_methods` each have a partial unique index (`WHERE is_default`) enforcing at most
one default per user at the DB level. Application code that sets `is_default = true` must first clear any
existing default in the same transaction (see `create_address` / `set_default_address` in
`routers/addresses.py`) or the insert/update will violate that index.
