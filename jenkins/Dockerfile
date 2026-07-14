# Jenkins as a container, driving the *host's* Docker daemon (not a nested
# one) via /var/run/docker.sock mounted in from the outside -- see
# docker-compose.jenkins.yml. That's what lets the Jenkinsfile's `docker
# build` / `docker compose` steps behave exactly like running them by hand
# on the VM.
FROM jenkins/jenkins:lts-jdk17

USER root

# docker CLI + compose plugin (for driving the host daemon), python3 (the
# buyer-api unit test stage builds its own venv per build), curl (health
# checks in scripts/deploy.sh / scripts/integration-test.sh), gcc + Postgres
# headers (requirements.txt's asyncpg pin predates this base image's python3,
# so pip has no pre-built wheel for it and must compile the C extension --
# hit this for real on the first build against a freshly provisioned VM).
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ca-certificates curl gnupg python3 python3-venv gcc libpq-dev python3-dev && \
    install -m 0755 -d /etc/apt/keyrings && \
    curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg && \
    chmod a+r /etc/apt/keyrings/docker.gpg && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
        > /etc/apt/sources.list.d/docker.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends docker-ce-cli docker-compose-plugin && \
    rm -rf /var/lib/apt/lists/*

# The bind-mounted docker.sock is owned by the host's docker group. The
# jenkins user needs to be in a group with that *same* GID inside the
# container to use it without running as root. Find the real value with
# `getent group docker` on the VM and pass it via docker-compose.jenkins.yml's
# DOCKER_GID build arg -- 999 below is a common default, not a universal one.
ARG DOCKER_GID=999
RUN if getent group docker >/dev/null; then \
        groupmod -g "${DOCKER_GID}" docker; \
    else \
        groupadd -g "${DOCKER_GID}" docker; \
    fi && \
    usermod -aG docker jenkins

USER jenkins
