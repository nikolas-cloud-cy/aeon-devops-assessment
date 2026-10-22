# syntax=docker/dockerfile:1
# Pin by tag here for readability; in production pin the digest (python:3.12-slim@sha256:...)
# and let Renovate/Dependabot bump it.
FROM python:3.12-slim AS runtime

ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION} \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

# Non-root user with a fixed numeric UID so Kubernetes runAsNonRoot can verify it.
RUN groupadd --system --gid 10001 app \
 && useradd  --system --uid 10001 --gid app --no-create-home --shell /usr/sbin/nologin app

WORKDIR /srv
COPY --chown=10001:10001 app/main.py ./main.py

USER 10001:10001
EXPOSE 8080

# No HEALTHCHECK here: Kubernetes probes own health checking.
CMD ["python", "main.py"]
