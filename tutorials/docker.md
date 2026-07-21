# Docker in This Project: A Tutorial

This document explains Docker from the ground up, then walks through **every Docker-related file
in this repository**, line by line where it matters, explaining not just what each line does but
*why* it's written that way. By the end, you should understand how Docker is used in local
development, in automated testing, in the CI/CD pipeline, and in the actual deployed system running
on a real server on the internet.

This is written for someone who has heard of Docker but hasn't necessarily used it much. If you
already know the basics (images vs. containers, what a Dockerfile is), skip ahead to whichever
section you need — the table of contents below links to everything.

## Table of contents

1. [What is Docker, really?](#1-what-is-docker-really)
2. [The building blocks you'll see everywhere in this repo](#2-the-building-blocks-youll-see-everywhere-in-this-repo)
3. [The Dockerfiles in this repo](#3-the-dockerfiles-in-this-repo)
4. [Docker Compose fundamentals](#4-docker-compose-fundamentals)
5. [Walking through every compose file](#5-walking-through-every-compose-file)
6. [Docker in CI/CD (Jenkins)](#6-docker-in-cicd-jenkins)
7. [Docker in testing](#7-docker-in-testing)
8. [Docker in the deployed cloud service](#8-docker-in-the-deployed-cloud-service)
9. [Hard-won lessons (the bugs we actually hit)](#9-hard-won-lessons-the-bugs-we-actually-hit)
10. [Quick-reference glossary](#10-quick-reference-glossary)
11. [Where to go next](#11-where-to-go-next)

---

## 1. What is Docker, really?

### The problem Docker solves

"It works on my machine" is the oldest joke in software. A program that runs fine on your laptop
can fail on a server because of differences in: the OS version, which libraries are installed,
which *versions* of those libraries, environment variables, file paths, and a hundred other small
things that are easy to overlook and hard to reproduce.

Docker's answer: package the application **together with everything it needs to run** — the exact
OS filesystem, the exact language runtime, the exact dependencies — into one self-contained unit.
That unit runs identically whether it's on your laptop, a teammate's laptop, a CI server, or a
production machine in a data center, because it's not relying on whatever happens to already be
installed on the host. It brought its own.

### Containers are not virtual machines

This is the single most important thing to understand early, because the words get used loosely.

A **virtual machine (VM)** emulates an entire computer — its own kernel, its own virtual hardware,
its own full OS boot process — running on top of your real machine via a hypervisor. VMs are heavy:
each one might take a full minute to boot and consume gigabytes of RAM before your application even
starts.

A **container** does not emulate a computer. It's a normal process running directly on your
machine's existing Linux kernel, but with the kernel providing that process an *isolated view* of
the system — its own filesystem, its own process list, its own network interfaces — using Linux
kernel features (namespaces and cgroups) that make the process *believe* it has a machine to itself,
while it's really just a fenced-off region of the one real machine. This is why containers start in
milliseconds, not minutes, and why running four containers costs a small fraction of what four VMs
would cost in memory and CPU. You'll see exactly this trade-off later in this document, when
`docker-compose.prod.yml` runs 4 instances of the same application as 4 lightweight containers, not
4 heavyweight VMs, on a single small cloud server with only 2GB of RAM.

### Images vs. containers

These two words are used precisely in Docker, and mixing them up is the #1 source of confusion for
newcomers:

- An **image** is a read-only template — a snapshot of a filesystem plus metadata about what command
  to run. It's the recipe. It doesn't do anything by itself; it just sits there (on your disk, or in
  a registry — more on that below).
- A **container** is a running (or stopped) *instance* created from an image. It's the meal you
  cooked from the recipe. You can create many containers from the same image, and each one gets its
  own isolated filesystem/process/network view, but they all started from the identical starting
  point defined by the image.

Analogy: a **class** in object-oriented programming is like an image; an **instance/object** created
from that class is like a container. You can create many objects from one class definition; you can
run many containers from one image.

A **Dockerfile** is the source code you use to *build* an image — a short script of instructions
("start from this base, copy these files in, run this install command, ..."). You'll read four of
them in [Section 3](#3-the-dockerfiles-in-this-repo).

### Where images live: registries

Once you've built an image, you often want to use it somewhere else — on a different machine
entirely. A **container registry** is a server that stores images so they can be pushed to it from
one machine and pulled from it on another. Docker Hub is the most famous public registry (that's
where official images like `postgres` and `python` come from in this project). This project also
pushes its *own* built images to **GHCR** (GitHub Container Registry, `ghcr.io`) — you'll see
`ghcr.io/gregswieringa/buyer-api` referenced throughout the deployment files. That's this project's
own application image, built once by CI and pulled from GHCR by every environment that needs it.

---

## 2. The building blocks you'll see everywhere in this repo

Before diving into real files, here's a glossary of the handful of concepts that show up
*constantly* below. Skim this once; you'll refer back to it.

- **`docker build`** — reads a Dockerfile and produces an image.
- **`docker run`** — creates and starts a container from an image.
- **Volume** — a persisted chunk of storage that lives *outside* a container's own filesystem, so
  data survives even if the container is deleted and recreated. Postgres's actual database files
  live in a volume in every compose file in this repo — if they didn't, deleting the container would
  delete the entire database.
- **Bind mount** — similar to a volume, but instead of Docker managing a hidden storage area, you
  point directly at a real folder on the host machine's own filesystem. Dev environments use these a
  lot (so you can edit code on your laptop and see the change immediately inside the running
  container). You'll see in [Section 9](#9-hard-won-lessons-the-bugs-we-actually-hit) that bind mounts
  have a serious gotcha in this project's CI setup.
- **Port publishing** — a container's network is isolated by default; nothing outside can reach it
  unless you explicitly *publish* a port, mapping "port X on the host machine" to "port Y inside the
  container." You'll see this written as `"8000:8000"` (host:container) throughout this repo.
- **Network** — containers can't see each other by default either. Docker Compose automatically
  creates a private network for each project and connects that project's containers to it, so they
  can reach each other by service name (e.g., the `buyer-api` container can reach Postgres just by
  connecting to the hostname `postgres` — Docker's internal DNS resolves that name to the right
  container's IP address on that shared network).
- **Environment variables** — how configuration (database passwords, feature flags, connection
  strings) gets passed into a container without baking secrets into the image itself.
- **Healthcheck** — a command Docker runs periodically *inside* a container to ask "are you actually
  working?" (not just "is the process still alive?"). A container can be running but still broken
  (e.g., Postgres process is up but not yet accepting connections) — healthchecks let other
  containers (and orchestration tools) wait for genuine readiness, not just process existence.
- **Docker Compose** — a tool for describing and running *multiple* containers together (with their
  networking, volumes, and startup order already wired up) from one YAML file, instead of typing a
  long `docker run` command by hand for each container. This project uses Compose for absolutely
  everything — there isn't a single place where a container is run by hand. [Section 4](#4-docker-compose-fundamentals)
  covers this properly.

---

## 3. The Dockerfiles in this repo

There are four Dockerfiles in this repository, each building an image for a different purpose.

### 3.1 `services/buyer-api/Dockerfile` — the real application image

```dockerfile
FROM python:3.12-slim

WORKDIR /srv

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

This is the image that actually runs the buyer-api FastAPI service in every real environment
(staging and production both run *this exact image*, just pulled from the registry rather than
built locally — more on that later). Line by line:

- **`FROM python:3.12-slim`** — every Dockerfile starts from a base image; you very rarely start
  completely from scratch. `python:3.12-slim` is an official image that already has Python 3.12
  installed on a minimal Debian Linux base ("slim" means stripped down — no compilers, no
  documentation, no extras — smaller image, faster to pull and start). This specific version pin
  matters a lot in this project; see the [gotchas section](#9-hard-won-lessons-the-bugs-we-actually-hit)
  for a real bug this exact version number caused (and fixed) down the line.
- **`WORKDIR /srv`** — sets the "current directory" for every instruction that follows, and for the
  container when it starts. `/srv` is just a folder name chosen inside the image; it doesn't need to
  exist beforehand, `WORKDIR` creates it.
- **`COPY requirements.txt .`** — copies one file from the *build context* (your project directory,
  on whichever machine is running `docker build`) into the image, at the current `WORKDIR` (`.`
  means "here"). Note this copies *only* `requirements.txt` at this point — not the whole `app`
  folder yet. That's deliberate.
- **`RUN pip install --no-cache-dir -r requirements.txt`** — installs every Python dependency listed
  in that file. `RUN` executes a shell command *at build time* — the result (all those installed
  packages) becomes a permanent part of the image.
- **`COPY app ./app`** — *now* copy the actual application source code in.

**Why copy `requirements.txt` before the app code, in two separate steps, instead of one
`COPY . .`?** This is a very common, deliberate Docker pattern, not an accident. Docker builds images
in layers, and caches each layer. If you change a line of Python code in `app/`, but your
dependencies haven't changed, Docker can reuse the cached layer from the `pip install` step (since
`requirements.txt` — the input to that step — didn't change) and only re-run the fast `COPY app`
step. If everything were one `COPY . .` followed by `pip install`, then *any* code change would
invalidate the cache and force a full dependency reinstall on every single build, which is much
slower. Ordering your Dockerfile from "changes rarely" to "changes often" is one of the most
important habits for fast builds.

- **`CMD [...]`** — the default command to run when a container starts from this image (unless
  overridden). Here it starts the actual web server, `uvicorn`, telling it to listen on all network
  interfaces (`0.0.0.0`, not just `localhost` — required for anything outside the container to reach
  it once the port is published) on port 8000.

Notice this Dockerfile has **no database connection details, no secrets, nothing environment
specific**. Those get supplied later, as environment variables, by whichever compose file starts a
container from this image. That's the whole point: this one image is generic enough to become
"the dev instance," "the staging instance," or "one of prod's four replicas," purely based on what
environment variables it's handed at `docker run` time.

### 3.2 `services/buyer-api/Dockerfile.test` — a second, test-only image

```dockerfile
FROM python:3.12-slim

WORKDIR /srv

COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt

COPY app ./app
COPY tests ./tests
COPY pytest.ini ./

CMD ["pytest", "-q"]
```

Nearly identical shape to the real Dockerfile, with three differences: it installs
`requirements-dev.txt` (extra packages needed only for testing, like `pytest`, that have no business
being in the actual production image), it also copies the `tests/` folder in, and instead of
starting a web server, its default command just *runs the test suite and exits*.

Why does this need to be a whole separate image, rather than just running `pytest` inside a
container built from the *real* Dockerfile with the tests bind-mounted in? Because of exactly how
this image gets used in CI — Jenkins itself runs as a container, and it turns out bind-mounting a
folder into a *sibling* container from inside another container doesn't work the way you'd expect.
This is one of the most important and non-obvious lessons in this whole project, fully explained in
[Section 9.1](#91-the-bind-mount-trap-docker-outside-of-docker).

### 3.3 `db/Dockerfile` — a custom Postgres image with the schema baked in

```dockerfile
FROM postgres:16

COPY init/ /docker-entrypoint-initdb.d/
```

Only two lines, but there's a real idea here. The official `postgres:16` image has a documented
convention: any `.sql` (or `.sh`) file placed in `/docker-entrypoint-initdb.d/` inside the container
gets automatically executed the *first time* that Postgres container starts with an empty data
directory. This project's schema — table definitions, indexes, an `ENUM` type or two — lives at
`db/init/001_buyer_schema.sql` in this repo, and rather than requiring every environment to somehow
have that file available on disk and bind-mount it in, this Dockerfile just **copies it directly
into the image**, so the schema travels with the image itself, wherever it's deployed.

Local development (`docker-compose.yml`) actually does *not* use this Dockerfile — it bind-mounts
`./db/init` from the host instead, for a good developer-experience reason explained in
[Section 5.1](#51-docker-composeyml--local-development). But every other environment (automated
tests, staging, production) uses this baked-in image instead, for a reason that isn't
developer-experience at all, but a genuine Docker networking gotcha — see
[Section 9.1](#91-the-bind-mount-trap-docker-outside-of-docker).

### 3.4 `jenkins/Dockerfile` — a customized CI server image

```dockerfile
FROM jenkins/jenkins:lts-jdk17

USER root

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ca-certificates curl gnupg python3 python3-venv && \
    install -m 0755 -d /etc/apt/keyrings && \
    curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg && \
    chmod a+r /etc/apt/keyrings/docker.gpg && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
        > /etc/apt/sources.list.d/docker.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends docker-ce-cli docker-compose-plugin && \
    rm -rf /var/lib/apt/lists/*

ARG DOCKER_GID=999
RUN if getent group docker >/dev/null; then \
        groupmod -g "${DOCKER_GID}" docker; \
    else \
        groupadd -g "${DOCKER_GID}" docker; \
    fi && \
    usermod -aG docker jenkins

USER jenkins
```

This one needs the most unpacking, because it's really about a specific pattern: **Docker running
Jenkins, and Jenkins itself needing to run Docker commands.**

- **`FROM jenkins/jenkins:lts-jdk17`** — starts from the official Jenkins image (LTS = long-term
  support release, `jdk17` = bundled with Java 17, which Jenkins needs to run).
- **`USER root`** — the base Jenkins image normally runs as an unprivileged `jenkins` user; this
  temporarily switches to `root` so the following `apt-get` commands (which install system packages)
  are allowed to run. Installing software system-wide requires root.
- The big `RUN apt-get ...` block installs: basic tools (`curl`, `gnupg`, certificate handling), a
  full Python 3 (needed for some of the CI pipeline's own scripts, explained in
  [Section 6](#6-docker-in-cicd-jenkins)), and — the important part — the **Docker CLI itself**
  (`docker-ce-cli`) plus the **Compose plugin**. Notice this does *not* install the actual Docker
  *engine/daemon* (the background service that does the real work of creating containers) — just the
  command-line client that talks to one. That's deliberate, and it's the crux of the whole pattern:
  this Jenkins container will be given access to the *host machine's own* Docker daemon (via a
  mechanism covered in [Section 5.5](#55-docker-composejenkinsyml--the-ci-server-itself)) rather than
  running a completely separate, nested Docker installation inside itself. This is called
  **Docker-outside-of-Docker (DooD)**, and it's the single most important idea to understand about how
  this project's CI works — see [Section 6](#6-docker-in-cicd-jenkins) for the full explanation.
- **`ARG DOCKER_GID=999`** and the `groupmod`/`usermod` block — a permissions detail. The mechanism
  that lets this Jenkins container talk to the host's Docker daemon is a shared file (a Unix socket)
  that gets mounted into the container. That file is owned, on the host, by a group called `docker`
  with some specific numeric group ID (GID). For the `jenkins` user *inside* this container to be
  allowed to use that file without running as root, the container needs a `docker` group with the
  *exact same numeric GID* as the host's — group names are just labels; what the Linux kernel actually
  checks is the number. `ARG DOCKER_GID` accepts that number as a build-time parameter (with `999` as
  a fallback guess), and the script creates or renumbers the group to match, then adds `jenkins` to it.
  You'll see the real value gets passed in when this image is actually built, in
  [Section 5.5](#55-docker-composejenkinsyml--the-ci-server-itself).
- **`USER jenkins`** — switches back to the unprivileged user for actually running Jenkins itself,
  once setup is done. Running services as non-root inside a container is good practice, same as it
  would be on a bare server.

---

## 4. Docker Compose fundamentals

Every environment in this project — dev, automated tests, staging, production, the CI server itself,
even the monitoring stack — is defined as a **Docker Compose file**: a YAML file listing one or more
`services` (each one becomes a running container) plus how they relate to each other.

Here's a minimal, annotated example (not from this repo, just for teaching) before you look at the
real ones:

```yaml
services:
  web:
    build: ./my-app          # build an image from a Dockerfile in this folder...
    # image: myregistry/my-app:v1   # ...or, alternatively, pull an already-built image
    ports:
      - "8080:80"             # host_port:container_port
    environment:
      DEBUG: "true"           # env vars available inside the container
    depends_on:
      db:
        condition: service_healthy   # wait for db's healthcheck to pass before starting
    restart: unless-stopped   # auto-restart if it crashes, but not if you deliberately stop it

  db:
    image: postgres:16
    volumes:
      - db_data:/var/lib/postgresql/data   # named volume, persists across restarts
    healthcheck:
      test: ["CMD-SHELL", "pg_isready"]
      interval: 5s

volumes:
  db_data:                    # declares the named volume used above
```

A few concepts worth calling out explicitly, since they appear in every real file below:

- **`build` vs. `image`** — a service either builds its own image from a local Dockerfile (`build:`)
  or pulls an already-built one from a registry (`image:`). You'll see this project deliberately
  split along exactly this line: dev and automated-test environments *build*; staging and production
  only ever *pull*. That distinction is the backbone of the whole CI/CD story — see
  [Section 6.2](#62-build-once-deploy-the-same-artifact-everywhere).
- **`depends_on` with `condition: service_healthy`** — plain `depends_on` (without a condition) only
  waits for a container to *start*, not for the application inside it to actually be ready. Adding
  `condition: service_healthy` makes Compose wait for that other service's `healthcheck` to report
  success first. Every compose file in this repo uses this for buyer-api waiting on Postgres —
  starting the API before the database can accept connections would just cause a crash loop.
- **Project names** — when you run `docker compose up`, Compose needs a "project name" to prefix all
  the resources it creates (containers, networks, volumes) so that multiple, unrelated compose
  projects on the same machine don't collide with each other. If you don't specify one, Compose
  guesses based on the current folder name — which turns out to matter a lot in this project (see
  [Section 9.4](#94-the-forgotten--p-flag)). This repo is careful to always pass an explicit project
  name with `-p` on the command line for exactly that reason.
- **Environment variable substitution** — you'll see things like `${IMAGE_TAG}` inside compose files.
  Compose substitutes these from your shell's environment or from a `--env-file` you pass on the
  command line, *before* interpreting the YAML. This is how the exact same `docker-compose.staging.yml`
  file can deploy different image tags on different days without ever being edited.

---

## 5. Walking through every compose file

There are six Compose files in this repo, one per distinct environment. They deliberately share as
much shape as possible (so learning one mostly teaches you the others), while differing in exactly
the ways that environment requires.

### 5.1 `docker-compose.yml` — local development

```yaml
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_USER: buyer
      POSTGRES_PASSWORD: buyer
      POSTGRES_DB: marketplace
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./db/init:/docker-entrypoint-initdb.d:ro
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U buyer -d marketplace"]
      interval: 5s
      timeout: 3s
      retries: 10

  buyer-api:
    build: ./services/buyer-api
    environment:
      DATABASE_URL: postgresql+asyncpg://buyer:buyer@postgres:5432/marketplace
    ports:
      - "8000:8000"
    volumes:
      - ./services/buyer-api/app:/srv/app
    command: ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
    depends_on:
      postgres:
        condition: service_healthy

volumes:
  pgdata:
```

This is what you run on your own laptop or Codespace while writing code (`docker compose up -d --build`,
per the README). Two services:

- **`postgres`** uses the plain, official `postgres:16` image directly (not the custom `db/Dockerfile`
  — see below for why), configured with a hardcoded dev username/password/database name (fine for
  local dev, never used anywhere real). `ports: "5432:5432"` publishes Postgres's standard port
  straight to your host machine, so you could connect a database GUI tool to `localhost:5432`
  directly if you wanted to.

  Two volumes are mounted:
  - `pgdata:/var/lib/postgresql/data` — a **named volume** holding the actual database files, so your
    data survives `docker compose down` and `up` again. (Wiping it requires the explicit
    `docker compose down -v`, mentioned in the README.)
  - `./db/init:/docker-entrypoint-initdb.d:ro` — a **bind mount** pointing straight at this repo's own
    `db/init/` folder on your host machine, read-only (`:ro`). This is *why* dev doesn't need the
    custom `db/Dockerfile` image: the schema file is picked up live from your working copy. Edit the
    schema, wipe the volume, restart, and the new schema applies immediately — no image rebuild
    required. This is a deliberate developer-experience trade-off that is *not* available to any other
    environment in this project — see [Section 9.1](#91-the-bind-mount-trap-docker-outside-of-docker)
    for why.

- **`buyer-api`** uses `build: ./services/buyer-api` (build from the Dockerfile you already read in
  [Section 3.1](#31-servicesbuyer-apidockerfile--the-real-application-image), rather than pulling a
  pre-built image — dev always builds fresh from whatever's on your disk). `DATABASE_URL` supplies the
  connection string as an environment variable, pointing at hostname `postgres` — that's not a real
  DNS name anywhere on the internet, it's Compose's own internal DNS resolving the *service name*
  `postgres` to that container's address on this project's private network. This is one of Compose's
  most useful features: containers refer to each other by their service name, and it just works.

  The bind mount `./services/buyer-api/app:/srv/app` overlays your live source code *on top of* what
  got baked into the image at build time, and the `command:` override adds `--reload` to uvicorn's
  startup flags — together, these mean editing a Python file on your laptop makes the running server
  reload it immediately, without rebuilding the image or restarting the container. This combination
  (bind-mounted source + `--reload`) is an extremely common local-dev pattern, and one more reason dev
  looks meaningfully different from every other compose file in this repo: **none of the deployed
  environments do this** — they run whatever was actually baked into the image, full stop, which is
  the entire point of a reliable deployment (see [Section 6.2](#62-build-once-deploy-the-same-artifact-everywhere)).

### 5.2 `docker-compose.test.yml` — automated testing

```yaml
services:
  postgres:
    build: ./db
    environment:
      POSTGRES_USER: buyer
      POSTGRES_PASSWORD: buyer
      POSTGRES_DB: marketplace
    ports:
      - "5433:5432"
    tmpfs:
      - /var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U buyer -d marketplace"]
      interval: 2s
      timeout: 3s
      retries: 20

  buyer-api:
    build: ./services/buyer-api
    environment:
      DATABASE_URL: postgresql+asyncpg://buyer:buyer@postgres:5432/marketplace
    ports:
      - "8001:8000"
    depends_on:
      postgres:
        condition: service_healthy
```

This is what `scripts/integration-test.sh` spins up (full explanation of that script in
[Section 7.2](#72-integration-tests-a-real-full-stack-in-a-box)). Compared to dev, three
differences worth understanding:

1. **`postgres: build: ./db`** — this is the custom Dockerfile from
   [Section 3.3](#33-dbdockerfile--a-custom-postgres-image-with-the-schema-baked-in), built fresh
   every time, instead of the plain `postgres:16` image plus a bind mount that dev uses. This is the
   first place you'll see the "bake the schema in, don't bind-mount it" pattern actually matter — this
   suite runs from inside Jenkins, and a bind mount would silently break there (full story in
   [Section 9.1](#91-the-bind-mount-trap-docker-outside-of-docker)).
2. **`tmpfs: - /var/lib/postgresql/data`** — instead of a persistent named volume, Postgres's data
   directory here lives in `tmpfs`, meaning **RAM, not disk**, and it vanishes the instant the
   container stops. That's exactly what you want for a test database: every test run starts from a
   truly empty, freshly-initialized schema (so `db/init/*.sql` reliably runs every single time),
   there's zero leftover state to accidentally pollute the next run, and it's faster than real disk
   I/O to boot.
3. **Different host ports** (5433/8001 instead of 5432/8000) — so this test stack can run *at the
   same time* as a dev stack already up on the default ports, without a port collision. This is a
   small detail, but it's what lets you run the test suite without first tearing down whatever you
   were doing in dev.

Both services still `build:` rather than `image:` here — this environment is about testing whatever
is currently on disk (the code someone just wrote), the same as dev, just with a stricter, disposable
database underneath it and no live-reload conveniences (nothing here is meant to be edited
interactively; it's meant to run once, get tested, and disappear).

### 5.3 `docker-compose.staging.yml` — staging deployment

```yaml
services:
  postgres:
    image: ghcr.io/gregswieringa/buyer-api-postgres:${IMAGE_TAG}
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB}
    ports:
      - "127.0.0.1:${POSTGRES_PORT}:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}"]
      interval: 5s
      timeout: 3s
      retries: 10
    restart: unless-stopped
    logging:
      driver: loki
      options:
        loki-url: "http://127.0.0.1:3100/loki/api/v1/push"
        loki-retries: "3"
        loki-batch-size: "400"

  buyer-api:
    image: ghcr.io/gregswieringa/buyer-api:${IMAGE_TAG}
    environment:
      DATABASE_URL: postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}
    ports:
      - "${BUYER_API_PORT}:8000"
    depends_on:
      postgres:
        condition: service_healthy
    restart: unless-stopped
    logging:
      driver: loki
      options:
        loki-url: "http://127.0.0.1:3100/loki/api/v1/push"
        loki-retries: "3"
        loki-batch-size: "400"

volumes:
  pgdata:
```

This is the first file that runs on the *real deployment server* (an always-on cloud VM, not a
laptop), and it looks different in a few important ways.

- **Every `image:` line pulls from `ghcr.io`, and there is no `build:` anywhere.** This is the single
  biggest conceptual shift in this whole document: dev and test *build* images from source; staging
  (and production, next) only ever *pull an already-built image*. The image was built exactly once,
  by CI, tested there, and pushed to the registry — staging's job is only to run that exact, already-
  proven artifact. See [Section 6.2](#62-build-once-deploy-the-same-artifact-everywhere) for why this
  matters so much.
- **`${IMAGE_TAG}`, `${POSTGRES_USER}`, `${POSTGRES_PASSWORD}`, etc. are all variables**, substituted
  from an environment file (`deploy/staging.env`, populated from `deploy/staging.env.example` with
  real values that are *never committed to git*) at deploy time. The same compose file deploys a
  different image tag every time CI builds a new one, without ever being edited.
- **`ports: "127.0.0.1:${POSTGRES_PORT}:5432"`** — notice the extra `127.0.0.1:` prefix that wasn't
  in the dev version. This binds the published port *only to the server's own loopback interface*,
  meaning nothing outside the server itself can reach Postgres directly over the network, even though
  the port is technically "published." This is a deliberate security decision: a database should
  never be reachable from the open internet. (`buyer-api`'s port has no such prefix — it's *meant* to
  be reachable from outside, that's the whole point of a public API.)
- **`restart: unless-stopped`** — dev and test never set a restart policy (if they crash, you're
  sitting right there to notice and restart them by hand). A real deployed server needs to recover on
  its own — if the container crashes, or the whole VM reboots, Docker will bring it back up
  automatically, without a human needing to notice and intervene.
- **`logging: driver: loki`** — instead of Docker's default logging behavior (writing logs to a local
  file on the server, which you'd have to SSH in and read one container at a time), every log line
  from these containers is shipped to a centralized log database (Loki) that a web dashboard (Grafana)
  can search across every container at once. Full explanation of this whole stack in
  [Section 5.6](#56-docker-composeobservabilityyml--the-monitoring-stack).

Notice also there's no bind mount and no `--reload` command override anywhere — this environment
runs the image exactly as it was built, with zero live-editing conveniences, because there's no
"live editing" happening on a deployment target. That absence is a feature, not an oversight.

### 5.4 `docker-compose.prod.yml` — production (the most complex file)

Production started out nearly identical to staging, then grew a genuinely new capability: instead of
one instance of `buyer-api`, it runs **four**, behind a **load balancer**, modeling how a real
production API tier would sit behind a single entry point serving multiple backend instances (the way
a real "backend-for-frontend" would route to many instances of an account API, rather than one).

```yaml
services:
  postgres:
    image: ghcr.io/gregswieringa/buyer-api-postgres:${IMAGE_TAG}
    # ... identical in shape to staging's postgres service ...
```

The `postgres` service here is unchanged from staging — same loopback-only binding, same logging, same
health check. Only `buyer-api` and a brand-new `traefik` service are different:

```yaml
  buyer-api:
    image: ghcr.io/gregswieringa/buyer-api:${IMAGE_TAG}
    environment:
      DATABASE_URL: postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}
    deploy:
      replicas: 4
    healthcheck:
      test: ["CMD", "python3", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=2)"]
      interval: 10s
      timeout: 3s
      retries: 5
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.buyer-api.rule=PathPrefix(`/`)"
      - "traefik.http.services.buyer-api.loadbalancer.server.port=8000"
      - "traefik.http.services.buyer-api.loadbalancer.healthcheck.path=/health"
      - "traefik.http.services.buyer-api.loadbalancer.healthcheck.interval=10s"
    depends_on:
      postgres:
        condition: service_healthy
    restart: unless-stopped
    logging: { ... same as staging ... }
```

Line by line, what's new:

- **No `ports:` at all.** In staging, `buyer-api` published its own port directly. Here, it doesn't
  publish anything — because it *can't*: with 4 replicas of the same service, all 4 containers would
  need to bind the identical host port simultaneously, which is impossible (only one process can own
  a given port on a given network interface at a time). Instead, `traefik` (below) is the *only*
  service in this whole file with a published port, and it's the one deciding which of the 4
  containers actually handles each incoming request.
- **`deploy: replicas: 4`** — tells Compose to run four separate containers from this one service
  definition, each identical (same image, same environment variables, same everything), each with an
  automatically generated distinguishing name (`buyerapi-prod-buyer-api-1` through `-4`). This is
  Docker Compose's built-in horizontal-scaling feature — note this works with plain
  `docker compose up`, no separate orchestration system (like Docker Swarm or Kubernetes) required,
  though this project's own roadmap does plan to eventually move to Kubernetes for exactly this kind
  of scaling need at a larger scale.
- **`healthcheck:`** — buyer-api didn't have one at all until production needed it. It uses Python's
  built-in `urllib` module rather than `curl` or `wget`, because the base image
  (`python:3.12-slim`, [Section 3.1](#31-servicesbuyer-apidockerfile--the-real-application-image))
  doesn't include either of those tools, but it does, obviously, include Python.
- **`labels:`** — these five lines are how **Traefik** (the load balancer, described next) is
  configured, *without a separate Traefik config file*. Traefik watches the Docker API for containers
  carrying labels starting with `traefik.`, and builds its routing configuration from them
  automatically, live, as containers come and go. Breaking down each label:
  - `traefik.enable=true` — "please route traffic to me" (opt-in, not automatic — explained below).
  - `traefik.http.routers.buyer-api.rule=PathPrefix(\`/\`)` — the rule deciding which incoming
    requests get sent here: anything starting with `/` — i.e., everything. (An alternative, common
    rule type matches by domain name instead, but this server is reached by raw IP address for
    testing, not a domain name, so a domain-based rule would never match anything.)
  - `traefik.http.services.buyer-api.loadbalancer.server.port=8000` — which port *inside* the
    container Traefik should actually connect to (buyer-api listens on 8000 internally, same as
    every other environment in this project).
  - `.loadbalancer.healthcheck.path=/health` and `.interval=10s` — Traefik does its *own*, separate
    active health checking of each of the 4 backend containers (hitting `/health` every 10 seconds),
    independent of Docker's own `healthcheck:` above. This is what actually keeps Traefik from
    routing real user traffic to one of the 4 containers if it's just been restarted and isn't ready
    yet.

```yaml
  traefik:
    image: traefik:v3.6
    command:
      - "--providers.docker=true"
      - "--providers.docker.exposedByDefault=false"
      - "--entrypoints.web.address=:80"
      - "--accesslog=true"
    ports:
      - "${BUYER_API_PORT}:80"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
    restart: unless-stopped
```

- **`command:`** passes Traefik its *static* configuration (settings that can't change at runtime,
  unlike the *dynamic* per-container routing rules that came from labels above):
  - `--providers.docker=true` — "watch the Docker API for containers" (as opposed to, say, watching a
    Kubernetes API, which Traefik also supports but isn't used here).
  - `--providers.docker.exposedByDefault=false` — **important**: without this, Traefik would try to
    build a route for *every single container on the entire host* — Jenkins, Grafana, staging's
    buyer-api, everything — since by default it assumes every container wants to be routed to unless
    told otherwise. Setting this to `false` flips that default, so *only* containers explicitly
    carrying `traefik.enable=true` (just `buyer-api`, above) get a route. This matters because
    Traefik isn't scoped to "this compose project" in any way — it can see (and, without this flag,
    would try to route to) literally every container the host's Docker daemon is running, across
    every unrelated project.
  - `--entrypoints.web.address=:80` — defines a named "entrypoint" called `web` listening on port 80
    *inside the Traefik container* (this is the port the `ports:` mapping below connects to the
    outside world; it's separate from and has nothing to do with buyer-api's own port 8000).
  - `--accesslog=true` — makes Traefik log every request it proxies (which backend it went to, status
    code, timing) — useful for exactly the kind of "is load actually spreading across all 4?" question
    this setup was built to answer.
- **`ports: "${BUYER_API_PORT}:80"`** — this is now the *only* public port for the entire production
  API. Requests hit Traefik on this port; Traefik decides which of the 4 buyer-api containers actually
  handles it.
- **`volumes: - /var/run/docker.sock:/var/run/docker.sock:ro`** — this is the exact same "give a
  container access to the host's Docker daemon" pattern used for Jenkins
  ([Section 3.4](#34-jenkinsdockerfile--a-customized-ci-server-image)), and it's what lets Traefik
  discover containers/labels live at all. The `:ro` (read-only) suffix restricts *writing to the
  socket file itself*, but — worth being precise about this, because it's easy to assume more safety
  than actually exists — it does **not** meaningfully restrict what Traefik can *do* through the
  Docker API once it can talk to it at all; reading container metadata this way is a real, accepted
  privilege, not a sandboxed one. This project accepts that trade-off deliberately for this VM (the
  same trade-off already made for Jenkins and, in the next compose file, Prometheus), rather than
  pretending `:ro` makes it safe.

**Why Traefik, and not something like nginx?** Traditional reverse proxies like nginx need a static
list of backend servers written into a config file, which you'd have to regenerate and reload every
time a container was added, removed, or replaced. Traefik was built specifically for container
environments — it watches the Docker API live and updates its routing automatically the instant
containers change, with no config file and no reload step. Given this project runs 4 identical,
frequently-replaced containers behind one entry point, that's exactly the problem Traefik exists to
solve.

### 5.5 `docker-compose.jenkins.yml` — the CI server itself

```yaml
services:
  jenkins:
    build:
      context: ./jenkins
      args:
        DOCKER_GID: ${DOCKER_GID:-999}
    network_mode: host
    volumes:
      - jenkins_home:/var/jenkins_home
      - deploy_env:/var/jenkins_home/deploy-env
      - /var/run/docker.sock:/var/run/docker.sock
    restart: unless-stopped
    logging: { ... }

volumes:
  jenkins_home:
  deploy_env:
```

- **`build: context: ./jenkins, args: DOCKER_GID: ...`** — builds the custom image from
  [Section 3.4](#34-jenkinsdockerfile--a-customized-ci-server-image), and this is where that
  Dockerfile's `ARG DOCKER_GID` actually gets a real value: `${DOCKER_GID:-999}` reads it from the
  shell environment when you run `docker compose up` (this project's docs tell you to find the real
  number with `getent group docker` on the server first, then export it, so the Jenkins user inside
  the container ends up in a group that really can use the mounted socket).
- **`network_mode: host`** — this is different from every other service in this document, and it's
  there to fix a genuinely confusing bug: normally, every container gets its own private network
  namespace, meaning `localhost` *inside* a container refers to that container itself, not the
  machine it's running on. Jenkins' pipeline needs to run commands like `curl localhost:8081/health`
  to check whether other containers (started by the *host's* Docker daemon) are healthy — but without
  `network_mode: host`, "localhost" from inside the default-networked Jenkins container is a
  completely different, private "localhost" that doesn't see those ports at all, even though they're
  genuinely open and working on the real machine. `network_mode: host` makes Jenkins skip having its
  own network namespace entirely and directly share the real host's, so its "localhost" really is the
  host's localhost, and any `curl localhost:<port>` behaves exactly the way it would if you typed it
  yourself while SSH'd into the machine. This is explained in much more depth, including how it was
  actually discovered, in [Section 9.2](#92-jenkins-needed-network_mode-host).
- **Two named volumes with different jobs**: `jenkins_home` holds Jenkins' entire own state — every
  job configuration, every plugin, every credential — so none of that is lost if the container is ever
  recreated (e.g., to pick up a new image after editing the Dockerfile). `deploy_env` is a *separate*
  volume holding the real secret files (`staging.env`, `prod.env` with actual database passwords) —
  kept deliberately outside `jenkins_home` and outside any Git checkout, because Jenkins re-clones its
  job workspace from scratch on every single build; anything only living inside that per-build
  workspace would be gone by the next run. This volume survives independently of that churn.
- **`/var/run/docker.sock:/var/run/docker.sock`** (note: no `:ro` here, unlike Traefik's) — Jenkins
  needs full read-write access to the Docker socket, because its whole job is *building new images*
  and *starting/stopping containers* (deploying), not just passively reading container metadata the
  way Traefik does.

### 5.6 `docker-compose.observability.yml` — the monitoring stack

```yaml
services:
  loki:
    image: grafana/loki:2.9.6
    command: -config.file=/etc/loki/loki-config.yaml
    volumes:
      - ./observability/loki-config.yaml:/etc/loki/loki-config.yaml:ro
      - loki_data:/loki
    ports:
      - "127.0.0.1:3100:3100"
    restart: unless-stopped

  prometheus:
    image: prom/prometheus:v2.55.1
    volumes:
      - ./observability/prometheus.yml:/etc/prometheus/prometheus.yml:ro
      - prometheus_data:/prometheus
    ports:
      - "127.0.0.1:9090:9090"
    networks:
      - default
      - buyerapi-staging
      - buyerapi-prod
    restart: unless-stopped

  grafana:
    image: grafana/grafana:11.1.0
    environment:
      GF_SECURITY_ADMIN_PASSWORD: ${GRAFANA_ADMIN_PASSWORD}
    volumes:
      - ./observability/grafana-datasources.yaml:/etc/grafana/provisioning/datasources/loki.yaml:ro
      - ./observability/grafana-datasources-prometheus.yaml:/etc/grafana/provisioning/datasources/prometheus.yaml:ro
      - ./observability/grafana-dashboards.yaml:/etc/grafana/provisioning/dashboards/dashboards.yaml:ro
      - ./observability/dashboards:/var/lib/grafana/dashboards:ro
      - grafana_data:/var/lib/grafana
    ports:
      - "8083:3000"
    depends_on:
      - loki
      - prometheus
    restart: unless-stopped

networks:
  buyerapi-staging:
    external: true
    name: buyerapi-staging_default
  buyerapi-prod:
    external: true
    name: buyerapi-prod_default

volumes:
  loki_data:
  grafana_data:
  prometheus_data:
```

Three services working together as a monitoring stack, deployed as their own separate compose
project (deliberately not bundled into staging or prod's own files, since it needs to observe *both*
of them at once).

- **`loki`** collects and stores **logs** (plain text lines every container prints). It's bound to
  `127.0.0.1` only — nothing outside the server itself ever needs to talk to Loki directly; only
  Grafana (below) and the containers shipping logs to it need to reach it, and both of those things
  happen on the server itself.
- **`prometheus`** collects and stores **metrics** (numeric measurements over time — request counts,
  latencies). Unlike everything else in this document, notice the `networks:` list: Prometheus joins
  *three* networks — its own project's `default` network, plus two **external** networks it doesn't
  own (`buyerapi-staging_default` and `buyerapi-prod_default`, the private networks Compose
  automatically created for the staging and production projects). This is how Prometheus is able to
  directly reach `buyer-api`'s `/metrics` endpoint inside those other, completely separate compose
  projects — it genuinely joins their networks as a normal participant, rather than needing any of
  the special workarounds Jenkins or Traefik needed. This is deliberately the *simplest* of the three
  approaches used in this project for "one container reaching into another project's network," and
  [Section 9.3](#93-three-different-fixes-for-one-underlying-problem) compares all three side by
  side.
- **`grafana`** is the actual web dashboard a human looks at, querying both Loki and Prometheus (both
  are pre-configured automatically via the mounted YAML files under `volumes:` — "provisioning" files
  that tell Grafana where its data sources and dashboards live, so nobody has to click through a setup
  wizard by hand). Notice it's published on host port **8083**, not Grafana's actual default port
  3000 — a real bug is the reason for that specific number, explained in
  [Section 9.5](#95-grafana-moved-off-port-3000).
- **The `networks:` block at the bottom** declares those two external networks by their real,
  Compose-generated names (`<project-name>_default`) so this file can reference networks it doesn't
  itself create.

---

## 6. Docker in CI/CD (Jenkins)

This project's whole CI/CD pipeline (defined in the `Jenkinsfile`, at the repository root) is built
entirely around Docker, in two different ways that are worth clearly separating:

1. Jenkins itself *is* Docker (a container, per [Section 5.5](#55-docker-composejenkinsyml--the-ci-server-itself)).
2. Every single stage of the pipeline *uses* Docker as its actual tool for testing, building, and
   deploying.

### 6.1 Docker-outside-of-Docker (DooD)

Jenkins runs as a container, but its job is to *build images* and *start/stop other containers* — and
those are things a container can't normally do to itself or its neighbors, because containers are
isolated from each other and from the host by design. The trick this project uses is called
**Docker-outside-of-Docker**: rather than installing a whole separate, nested Docker installation
inside the Jenkins container (which is possible, but heavyweight and has its own well-known problems),
Jenkins is given the Docker *client* tools plus a mounted door straight to the *host's own* Docker
daemon (`/var/run/docker.sock`, from [Section 5.5](#55-docker-composejenkinsyml--the-ci-server-itself)).
Every `docker build` or `docker compose up` that Jenkins runs is really telling the *host's* Docker
daemon to do the work — Jenkins is just the one issuing the command. The containers that get created
this way are genuinely **siblings** of the Jenkins container, not children nested inside it.

This explains why the Jenkinsfile's stages look, syntactically, exactly like commands you could type
yourself over SSH on the server — because that's effectively what's happening.

### 6.2 Build once, deploy the same artifact everywhere

Look at the `Jenkinsfile`'s stages in order:

```groovy
stage('Unit tests') { ... }
stage('Integration tests') { ... }
stage('Push images') { when { branch 'main' } ... }
stage('Deploy to staging') { when { branch 'main' } ... }
stage('Promote to production') { when { branch 'main' } ... }
```

Every branch (including pull requests) runs the first two stages. Only `main` continues past that.
Here's the key idea, expressed entirely through Docker images:

1. **Unit tests** build a throwaway test image (`Dockerfile.test`,
   [Section 3.2](#32-servicesbuyer-apidockerfiletest--a-second-test-only-image)) and run it once,
   just to execute the test suite and exit.
2. **Integration tests** build the *real* application image and the *real* custom Postgres image
   (via `docker-compose.test.yml`, [Section 5.2](#52-docker-composetestyml--automated-testing)) and
   run the black-box test suite against them for real, over the network, exactly as an outside client
   would use the API.
3. **Push images** — and here's the important part — does **not build anything new**. It takes the
   *exact images that just passed the integration tests* (still sitting in the Jenkins host's local
   Docker image cache, because `docker compose down -v` removes containers/volumes/networks but never
   deletes the underlying images), tags them with the Git commit hash, and pushes those *same bytes*
   to GHCR.
4. **Deploy to staging** and **Promote to production** never build anything either — they run
   `scripts/deploy.sh`, which does `docker compose pull` (fetch that exact tagged image from GHCR)
   and `docker compose up -d` (start containers from it), using `docker-compose.staging.yml` /
   `docker-compose.prod.yml` from [Sections 5.3](#53-docker-composestagingyml--staging-deployment)
   and [5.4](#54-docker-composeprodyml--production-the-most-complex-file).

The whole point: the image that gets deployed to production is provably, byte-for-byte, the same
image that was tested minutes earlier — not a fresh rebuild that merely *should* be identical.
Rebuilding separately for each environment always carries a small risk that something about the build
environment differs subtly between "when tests ran" and "when production got built" (a dependency
version resolved differently, a base image got updated in between, ...). Building exactly once and
promoting that same artifact through every stage eliminates that risk entirely.

### 6.3 `scripts/deploy.sh`, read as a Docker script

```bash
COMPOSE=(docker compose -p "buyerapi-${ENVIRONMENT}" -f "docker-compose.${ENVIRONMENT}.yml" --env-file "$ENV_FILE")
IMAGE_TAG="$IMAGE_TAG" "${COMPOSE[@]}" pull
IMAGE_TAG="$IMAGE_TAG" "${COMPOSE[@]}" up -d
```

This script is what actually performs a deploy, whether Jenkins calls it or a human runs it directly
over SSH. `-p "buyerapi-${ENVIRONMENT}"` sets the Compose *project name* explicitly (rather than
letting Compose guess one from the current folder — the exact thing [Section 9.4](#94-the-forgotten--p-flag)
explains going wrong once). `-f "docker-compose.${ENVIRONMENT}.yml"` picks the right compose file for
"staging" or "prod". `--env-file "$ENV_FILE"` supplies all those `${IMAGE_TAG}`, `${POSTGRES_PASSWORD}`,
etc. variables from the real secrets file. `pull` fetches the exact tagged image from GHCR; `up -d`
starts (or replaces) containers from it, in the background (`-d` = detached).

---

## 7. Docker in testing

There are two entirely separate test suites in this project, and they use Docker in two
fundamentally different ways — worth understanding as two different testing *philosophies*, not just
two different scripts.

### 7.1 Unit tests: no real Docker containers, but still a Docker *image*

The unit test suite (`services/buyer-api/tests/`) doesn't actually talk to a real Postgres database
at all — it fakes the database layer entirely in Python (a `FakeSession` object standing in for a
real database connection), so it can run in milliseconds without needing any container running.
Locally, a developer just runs `pytest` directly in a virtual environment — no Docker involved at
all.

In CI, though, this suite runs *inside* a Docker container built from `Dockerfile.test`
([Section 3.2](#32-servicesbuyer-apidockerfiletest--a-second-test-only-image)) rather than directly
on the Jenkins machine. That's not about needing isolation from a real database (there isn't one) —
it's about needing the *exact right Python version*. Jenkins' own Python (whatever version happens to
come with its base OS image) turned out to be incompatible with one of this project's pinned
dependencies; building and running inside a container pinned to `python:3.12-slim` — the same version
the real production image uses — sidesteps that entirely. The full story of *why* is in
[Section 9.6](#96-the-python-version-that-wouldnt-compile).

### 7.2 Integration tests: a real, full stack in a box

The integration suite (top-level `tests/integration/`) is the opposite philosophy: no faking anything.
`scripts/integration-test.sh` brings up the *actual* `docker-compose.test.yml` stack — a real
Postgres container, running the real schema, talking to a real running instance of the real
application image — and then runs tests as an outside HTTP client, exactly as a real user's request
would arrive. This is what proves things the unit suite's fake database *structurally cannot*: that a
real Postgres constraint violation actually produces the exact error shape the application code
expects to unwrap, or that a database-level uniqueness rule (like "only one default address per
user") really holds up against genuine concurrent writes, not just against a mock's in-memory
dictionary.

The whole stack — Postgres and buyer-api both — is torn down completely at the end
(`trap cleanup EXIT` in the script, running `docker compose down -v` no matter whether the tests
passed or failed), so every run starts completely fresh, and nothing is left behind on disk
afterward.

---

## 8. Docker in the deployed cloud service

Zooming out from individual files: the actual production system is **one small cloud VM** (a Hetzner
server, 2 vCPU / ~2GB RAM) running every single thing described in this document, all at once, all as
Docker containers, managed as five separate Compose *projects* that don't know about each other
except where they're deliberately connected:

| Compose project | What it runs | Purpose |
|---|---|---|
| `buyerapi-staging` | 1× buyer-api + Postgres | Developer verification environment |
| `buyerapi-prod` | 4× buyer-api + Postgres + Traefik | The real, public-facing production system |
| `dynamicsserver` (Jenkins) | Jenkins | Builds, tests, and deploys everything else |
| `observability` | Loki, Prometheus, Grafana | Centralized logs and metrics for both environments |

Each project gets its own private Docker network by default, which is exactly why Prometheus needed
to explicitly join two *other* projects' networks to reach them
([Section 5.6](#56-docker-composeobservabilityyml--the-monitoring-stack)), and why Jenkins needed
`network_mode: host` to see ports on the shared machine at all
([Section 5.5](#55-docker-composejenkinsyml--the-ci-server-itself)). Nothing about this is automatic
or accidental — every cross-project connection in this system was a deliberate decision, made because
that specific container genuinely needed to reach something outside its own project.

### Security decisions worth noticing

A few patterns repeat throughout this document, and they're all part of the same underlying
philosophy — expose only what genuinely needs to be reachable from the internet, and be honest about
what's *not* actually protected just because it looks locked down:

- **Postgres is never reachable from the internet**, in staging or production — only from
  `127.0.0.1` (the loopback interface), which only processes running on the server itself can use.
- **Loki and Prometheus are loopback-only too** — only Grafana and the containers shipping data into
  them need to reach them, and that all happens on the same machine.
- **Grafana, Jenkins, and the production API itself are the only things genuinely exposed to the
  public internet**, each behind its own login (or, for the API, simply being the public product).
- **Every container that's handed access to the Docker socket** (Jenkins, Traefik, and — indirectly,
  by joining other projects' networks rather than the socket itself — Prometheus) **is trusted with a
  real, unrestricted amount of power** over the whole host, `:ro` mount flags notwithstanding. This is
  accepted, not hidden, throughout this project's own documentation (`CLAUDE.md`) — a real production
  system with actual users would very likely want a narrower-scoped alternative (like a
  socket-proxy that only allows *reading* specific, safe API endpoints) rather than raw socket access
  for anything internet-facing, but for a personal learning lab, the simpler approach was a
  deliberate, informed trade-off.

---

## 9. Hard-won lessons (the bugs we actually hit)

Everything above describes the system as it exists *now*. It didn't start out this way — several of
the design decisions above exist specifically *because* of a real bug that got debugged, root-caused,
and fixed. Reading about them is one of the best ways to actually understand Docker's sharper edges,
since these are exactly the kind of mistakes a junior developer is likely to make once, too.

### 9.1 The bind-mount trap (Docker-outside-of-Docker)

**The setup:** `docker-compose.yml` (dev) bind-mounts `./db/init` from the host straight into
Postgres. It's simple and it works — while you're running Compose directly on your own machine.

**The bug:** the very first version of `docker-compose.test.yml` did the exact same thing. It worked
perfectly when run by hand. It silently *broke* when Jenkins ran it — Postgres would start up with a
completely empty schema, no tables at all, as if `db/init/*.sql` had never existed.

**Why:** this is the Docker-outside-of-Docker pattern from [Section 6.1](#61-docker-outside-of-docker-dood)
biting back. When Jenkins (itself a container) tells the *host's* Docker daemon "bind-mount
`./db/init` into this new container," the host daemon resolves that relative path **against its own
filesystem** — not against the filesystem *inside the Jenkins container* where that folder actually
exists. The path genuinely doesn't exist from the host daemon's point of view, so Docker just quietly
mounts nothing there instead of raising an error.

**The fix:** `db/Dockerfile` ([Section 3.3](#33-dbdockerfile--a-custom-postgres-image-with-the-schema-baked-in))
copies the SQL files *into the image itself* at build time, instead of bind-mounting them in at run
time. `docker build` streams its build context (the files it needs) over the Docker API connection
itself, so it works correctly regardless of which container or machine initiated the build — there's
no host-filesystem-path ambiguity to get wrong, because nothing is resolved as a path on the host at
all. This is why dev alone gets to use the convenient bind-mount version, and every other environment
in this project uses the baked-in image instead — dev is the only place actually running Compose
directly against its own filesystem, with no DooD indirection in the way.

### 9.2 Jenkins needed `network_mode: host`

**The bug:** the very first working version of the Jenkinsfile would deploy staging successfully
(the containers really did start and become healthy — confirmed by SSHing in and checking directly),
but the deploy script's own health check would then report failure and abort the pipeline.

**Why:** `scripts/deploy.sh` (running inside Jenkins) does `curl http://localhost:${PORT}/health` to
confirm the deploy actually worked. Since Jenkins is a container with its own private network
namespace by default, "localhost" from its point of view is Jenkins' *own* loopback interface — not
the real server's. The staging container really was healthy and really was listening on that port —
just on the *host's* localhost, which is a completely different, private network as far as the
default-networked Jenkins container is concerned. The curl call wasn't failing because anything was
broken; it was asking the wrong "localhost" entirely.

**The fix:** `network_mode: host` on the Jenkins service
([Section 5.5](#55-docker-composejenkinsyml--the-ci-server-itself)) — this makes Jenkins skip having
its own network namespace and share the real host's directly, so "localhost" inside Jenkins really is
the host's localhost, same as if you'd SSH'd in and typed the command yourself.

### 9.3 Three different fixes for one underlying problem

Sections 9.1 and 9.2 are really the same root problem wearing two different disguises: **a container
resolving something (a file path, a hostname) against the wrong frame of reference**, because DooD
means the container issuing a Docker command and the container that command actually affects don't
share a filesystem or a network namespace by default. This project ended up with three genuinely
different fixes for essentially the same category of problem, worth comparing directly since each one
teaches something different:

1. **Bake it into the image** (`db/Dockerfile`, `Dockerfile.test`) — used when the thing that needs to
   travel with the container is *files*. Solves it by removing the need to resolve a path at all.
2. **Share the host's network entirely** (`network_mode: host` for Jenkins) — used when the container
   needs to behave, network-wise, exactly as if it weren't containerized at all. The blunt, all-or-
   nothing option — Jenkins gets *complete* access to the host's network, not just the one port it
   actually needed.
3. **Explicitly join another project's specific network** (Prometheus joining `buyerapi-staging_default`
   and `buyerapi-prod_default`) — the most surgical of the three: Prometheus gets access to exactly
   the two networks it needs, and nothing else, rather than either baking anything in or getting
   blanket host-level access.

If you're ever solving this class of problem yourself, option 3 is generally the most precise tool
when it's available (you're reaching into a network, not needing raw files or the whole host); option
1 is right when the real issue is file paths, not networking at all; option 2 is a broader hammer,
appropriate when a component genuinely needs to behave as if un-containerized.

### 9.4 The forgotten `-p` flag

**The bug:** the very first time the observability stack (Loki/Prometheus/Grafana) was started, it
was brought up with a plain `docker compose -f docker-compose.observability.yml up -d`, with no
explicit project name. Compose silently defaulted to naming the project after the current folder —
which happened to be the exact same name Jenkins' own compose project had *already* been using. Both
ended up sharing one project namespace, and Docker printed a confusing "orphan containers" warning
about Jenkins not belonging to the file just run.

**Why this matters, not just as a cosmetic annoyance:** Compose project names determine the names of
the volumes it creates. If a *second* attempt had used a genuinely different, unrelated project name
by mistake, Compose would have looked for volumes matching *that* name, found none, and happily
created brand new, empty ones — silently starting Jenkins over from a completely blank slate (no
saved jobs, no credentials, nothing), rather than reusing its real, already-populated data.

**The fix:** always pass an explicit `-p <project-name>` on every `docker compose` command in this
project — you'll notice `scripts/deploy.sh` and `scripts/integration-test.sh` both do this
deliberately, never relying on Compose's folder-name guess.

### 9.5 Grafana moved off port 3000

Not a Docker bug at all, but worth knowing since it explains a specific, otherwise-mysterious number
in the compose file: Grafana's own default port is 3000. This project originally published it there.
A user then found their home network's router silently blocked *outbound* connections to port 3000
specifically (apparently a common practice for networks that want to block casual access to
locally-run dev servers), while the exact same request worked fine over cellular data, and other
ports on the same server (8080, 8081, 8082) worked fine over the same blocked home network. The fix
was simply to move Grafana to port 8083 instead — nothing about Docker or Grafana was actually broken;
this is purely a lesson that **the port number you choose to publish something on can matter for
reasons entirely outside your own system's control.**

### 9.6 The Python version that wouldn't compile

**The bug:** the very first version of the Jenkinsfile's unit test stage ran `pytest` directly on the
Jenkins container's own Python installation (rather than inside a dedicated Docker image at all). It
failed, with a C compiler error deep inside installing one of the project's dependencies (`asyncpg`,
which talks to Postgres and includes a compiled C extension for speed).

**Why:** the Jenkins container's Debian base OS happened to default to a newer version of Python than
the one this project's dependencies were tested and pinned against. That newer Python changed
low-level internals that the pinned version of `asyncpg`'s C code depended on — not just "no
pre-built wheel available" (which pip can usually work around by compiling from source), but a
genuine, real incompatibility that couldn't be compiled around at all, on *any* newer Python version,
without upgrading the dependency itself.

**The fix:** `Dockerfile.test` ([Section 3.2](#32-servicesbuyer-apidockerfiletest--a-second-test-only-image))
pins the *exact same* Python version (`python:3.12-slim`) that the real production Dockerfile uses,
and unit tests run *inside a container built from it*, rather than directly on whatever Python
happens to be lying around on the CI machine. This is a nice, concrete example of exactly the
motivating idea from [Section 1](#1-what-is-docker-really): the application's *real* runtime
environment is fully specified by Docker, so testing inside that same specified environment (instead
of "whatever's on this particular machine") is what actually catches this kind of bug, rather than
hiding it until it surfaces somewhere unlucky.

---

## 10. Quick-reference glossary

| Term | Meaning |
|---|---|
| **Image** | A read-only template for a container — a filesystem snapshot plus metadata. Built from a Dockerfile. |
| **Container** | A running (or stopped) instance created from an image. |
| **Dockerfile** | A script of instructions for building an image. |
| **Registry** | A server that stores images so they can be pushed/pulled between machines (e.g., Docker Hub, GHCR). |
| **Docker Compose** | A tool + YAML file format for defining and running multiple related containers together. |
| **Compose project** | A named group of containers/networks/volumes created from one compose file + project name. |
| **Volume** | Docker-managed persistent storage, surviving container deletion. |
| **Bind mount** | A mount pointing directly at a real folder on the host's own filesystem. |
| **`tmpfs` mount** | A mount backed by RAM, not disk — gone the instant the container stops. |
| **Port publishing** | Mapping a container's internal port to a port on the host machine, so the outside world can reach it. |
| **Network** | An isolated virtual network Docker creates so containers in the same project can reach each other by name. |
| **Healthcheck** | A command Docker runs periodically inside a container to verify it's genuinely ready, not just running. |
| **DooD (Docker-outside-of-Docker)** | Giving a container access to the *host's* Docker daemon (via a mounted socket) instead of running a nested Docker installation inside it. |
| **`network_mode: host`** | Making a container share the host's real network stack directly, instead of getting its own isolated one. |
| **Reverse proxy / load balancer** | A single entry point that receives traffic and forwards it to one of several backend instances (Traefik, in this project). |
| **`deploy: replicas: N`** | Docker Compose's built-in feature for running N identical copies of one service. |
| **Build once, deploy everywhere** | The practice of building an image exactly once, testing it, then promoting that *exact same* artifact through every environment, rather than rebuilding per environment. |

---

## 11. Where to go next

- Try it yourself: `docker compose up -d --build` at the repo root brings up the dev stack described
  in [Section 5.1](#51-docker-composeyml--local-development). Then `docker compose ps` to see the
  running containers, and `docker compose logs buyer-api --tail 60` to watch its logs.
- Run `docker ps` on your own machine at any point to see every container currently running, or
  `docker images` to see every image you've built or pulled.
- Read `CLAUDE.md` at the repo root — it documents the *current* state of this whole system (ports,
  what's deployed where, one-time setup steps) at a level of detail this tutorial deliberately doesn't
  repeat, since CLAUDE.md is kept up to date as the project keeps changing and this tutorial is meant
  to teach the durable ideas underneath it.
- The official [Docker documentation](https://docs.docker.com/) and
  [Docker Compose documentation](https://docs.docker.com/compose/) are both genuinely well-written and
  worth reading directly once the concepts above feel familiar — this tutorial covers *this project's*
  usage of Docker, not the entirety of what Docker can do.
