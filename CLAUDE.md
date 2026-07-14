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

# integration tests (real Postgres + the real built buyer-api image; see below)
cd /path/to/dynamicsserver   # repo root
python3 -m venv .venv && source .venv/bin/activate
pip install -r tests/integration/requirements.txt
./scripts/integration-test.sh
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

### Integration tests use a real Postgres and the real built image

`tests/integration/` (top-level, since it exercises the whole running stack rather than importable code)
is a black-box suite: `scripts/integration-test.sh` brings up `docker-compose.test.yml` — a standalone
compose file (not a `docker-compose.yml` override, to sidestep Compose's list-merge rules for
`ports`/`volumes`) on ports 5433/8001 so it can run alongside a dev stack already on 5432/8000 — waits for
`/health`, runs pytest against the real HTTP service and, for a couple of DB-only checks, a direct
`psycopg` connection, then always tears the stack down (`trap ... down -v`), even on failure. Postgres's
data dir is `tmpfs`, so every run applies `db/init/*.sql` from scratch; there's no volume left behind to
clean up. This is what proves things the unit suite's `FakeSession` structurally cannot: that the real
asyncpg exception shape matches what `routers/users.py` unwraps, and — the most important one — that the
"clear the old default before setting a new one" logic in `routers/addresses.py` actually satisfies the
real `one_default_address_per_user` partial unique index rather than just the mock's dict.

An autouse fixture in `tests/integration/conftest.py` truncates `users`/`addresses`/`payment_methods`
before every test, so tests don't need to worry about state left by earlier tests in the same run.

`Jenkinsfile`'s "Integration tests" stage runs this same script in CI — see "CI/CD (Jenkins)" below.

### CI/CD (Jenkins)

Pulling phase 6 of the roadmap forward early, ahead of splitting into more services: a `Jenkinsfile`
(Multibranch Pipeline) runs on every branch/PR and additionally deploys on `main`. Jenkins itself runs as
a container (`jenkins/Dockerfile` + `docker-compose.jenkins.yml`) on the same Oracle Free Tier VM as
staging and production, so deploys are a direct `sh` step in the pipeline, not SSH to a separate host.

**Environments and ports** — one VM hosts staging and production as separate Compose projects
(`-p buyerapi-staging` / `-p buyerapi-prod`), isolated from each other via Compose's per-project
networks/volumes, same as `docker-compose.test.yml` already does for CI:

| environment | compose file                  | postgres port      | buyer-api port | builds or pulls?        |
|-------------|--------------------------------|--------------------|-----------------|--------------------------|
| dev         | `docker-compose.yml`           | 5432                | 8000            | builds from source, `--reload` |
| test (CI)   | `docker-compose.test.yml`      | 5433                | 8001            | builds from `db/` + `services/buyer-api`, tmpfs DB |
| staging     | `docker-compose.staging.yml`   | 5434 (loopback only)| 8081            | pulls `ghcr.io/gregswieringa/buyer-api(-postgres):<tag>` |
| production  | `docker-compose.prod.yml`      | 5435 (loopback only)| 8082            | pulls the same tag staging ran |

Postgres in staging/prod is bound to `127.0.0.1` only — buyer-api reaches it over the Compose network,
but it's never exposed on the VM's public IP.

**Schema is baked into an image, not bind-mounted** — `db/Dockerfile` (`FROM postgres:16`, `COPY init/
/docker-entrypoint-initdb.d/`) replaces the bind-mount of `./db/init` that dev still uses. This matters
because Jenkins runs `docker build`/`docker compose` from *inside* its own container by mounting the
host's `/var/run/docker.sock` (Docker-outside-of-Docker — no nested Docker daemon); the host daemon it's
driving would resolve a bind-mounted relative path against the *host's* filesystem, not Jenkins'
container filesystem, so `./db/init` would silently mount empty. Building it into the image sidesteps
that — `docker build` streams its context over the API, so it works regardless of which filesystem
namespace invoked it. Verified this directly: ran `docker compose -f docker-compose.test.yml up` from a
throwaway container with the repo copied into its own filesystem only (nothing bind-mounted, nothing at
that path on the real host) and confirmed the schema still loaded correctly.

**Build once, deploy the same artifacts everywhere** — the Jenkinsfile does *not* rebuild for
staging/prod. `scripts/integration-test.sh` already builds `buyerapi-it-buyer-api:latest` and
`buyerapi-it-postgres:latest` via `docker-compose.test.yml` and tests them against each other for real;
`docker compose down -v` removes containers/volumes/network but leaves both images in the Docker
daemon's cache, so the Push stage just `docker tag`s and pushes the exact images that passed integration
tests. Staging and (on approval) production both deploy that same tag — never a fresh build — via
`scripts/deploy.sh <staging|prod> <tag>`, which does `docker compose pull` + `up -d` + polls `/health`.

**Secrets** — `deploy/staging.env` and `deploy/prod.env` (gitignored, different Postgres passwords each)
must exist before `deploy.sh` will run; it refuses otherwise. `deploy/*.env.example` are the templates.
Since Jenkins re-clones its job workspace per build, these live outside it: `docker-compose.jenkins.yml`
mounts a separate persistent `deploy_env` volume at `/var/jenkins_home/deploy-env`, and the Jenkinsfile
points `DEPLOY_ENV_DIR` there. Populate that volume once, by hand (e.g. `docker compose cp` the real
files in, or exec into the Jenkins container and write them), after Jenkins is first stood up.

**One-time Jenkins/VM setup this assumes** (not yet done — this is the next step now that the Oracle VM
exists): install Docker on the VM; find its docker group GID (`getent group docker`) and build Jenkins
with `DOCKER_GID=<that value> docker compose -f docker-compose.jenkins.yml up -d --build`; populate the
`deploy_env` volume with real `staging.env`/`prod.env`; create the Jenkins `ghcr-credentials` credential
(a GitHub username + PAT with `write:packages`); create the Multibranch Pipeline job pointed at this
repo; add a GitHub webhook pointed at Jenkins; and add branch protection on `main` requiring the Jenkins
PR check to pass.

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
db/init/*.sql                  # schema source of truth, applied via postgres docker-entrypoint-initdb.d
db/Dockerfile                  # bakes db/init/*.sql into an image (used by test/staging/prod, not dev)
services/<name>-api/           # one FastAPI service per bounded context; buyer-api is the first
docker-compose.yml             # dev stack (builds from source, bind-mounted db/init, --reload)
docker-compose.test.yml        # CI/local integration-test stack (builds db/ + services/buyer-api, tmpfs DB)
docker-compose.staging.yml     # staging deploy target (pulls built images)
docker-compose.prod.yml        # production deploy target (pulls the same tags staging ran)
docker-compose.jenkins.yml     # Jenkins-as-a-container, driving the host's Docker daemon
jenkins/Dockerfile              # Jenkins image: docker CLI + compose plugin + python3
deploy/*.env.example           # templates for the real (gitignored) deploy/staging.env, deploy/prod.env
scripts/integration-test.sh    # builds + runs tests/integration/ against docker-compose.test.yml
scripts/deploy.sh              # deploys built tags to staging or prod
Jenkinsfile                    # Multibranch Pipeline: test on every branch, deploy on main
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
