# Bakes db/init/*.sql into the image instead of relying on a bind-mount at
# runtime. Needed once Jenkins runs docker compose from inside its own
# container (Docker-outside-of-Docker, driving the host daemon via a
# mounted socket): a bind-mounted host path like ./db/init resolves against
# the *host's* filesystem, not the caller container's, so it silently fails
# to find anything there. Building it into the image sidesteps that
# entirely (docker build streams its context over the API, so it works
# regardless of which filesystem namespace invoked it), and matches the
# "deploy a pre-built artifact" principle already used for buyer-api.
FROM postgres:16

COPY init/ /docker-entrypoint-initdb.d/
