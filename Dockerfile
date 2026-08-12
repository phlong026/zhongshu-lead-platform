FROM python:3.12-slim-bookworm@sha256:2c68a80a104412b1795c87e3a8d7ece2632362987e5cad94b01d0654f4afb2a2

ARG APP_VERSION=1.2.0
ARG APP_BUILD_SHA=unknown
LABEL org.opencontainers.image.title="zhongshu-lead-platform" \
      org.opencontainers.image.version="${APP_VERSION}" \
      org.opencontainers.image.revision="${APP_BUILD_SHA}"
ENV APP_VERSION=${APP_VERSION} \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && addgroup --system app \
    && adduser --system --ingroup app app
COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN printf '%s\n' "${APP_BUILD_SHA}" > /app/.build-sha \
    && chown app:app /app/.build-sha
RUN chmod +x /app/docker/entrypoint.sh /app/docker/scheduler-entrypoint.sh \
    && mkdir -p /app/storage /app/backups /tmp/zhongshu-scheduler \
    && chown -R app:app /app /tmp/zhongshu-scheduler
USER app
EXPOSE 8000
CMD ["/app/docker/entrypoint.sh"]
