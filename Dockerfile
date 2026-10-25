# syntax=docker/dockerfile:1.7
FROM python:3.12-slim-bookworm AS builder
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1
RUN python -m venv /opt/venv
COPY requirements.lock /tmp/requirements.lock
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then export PIP_CERT=/run/secrets/proxy_ca; fi; \
    /opt/venv/bin/pip install --require-hashes -r /tmp/requirements.lock
COPY scripts/download_officecli.py /tmp/download_officecli.py
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then export SSL_CERT_FILE=/run/secrets/proxy_ca; fi; \
    python /tmp/download_officecli.py /usr/local/bin/officecli

FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PATH="/opt/venv/bin:${PATH}" \
    PYTHONPATH=/app/src OFFICECLI_SKIP_UPDATE=1 OFFICECLI_NO_AUTO_RESIDENT=1 \
    OFFICECLI_MCP_DATA_DIR=/data OFFICECLI_MCP_HOST=0.0.0.0 OFFICECLI_MCP_PORT=8080
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then \
      printf 'Acquire::https::CaInfo "/run/secrets/proxy_ca";\n' > /etc/apt/apt.conf.d/99-build-ca; \
    fi; \
    apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates libicu72 libssl3 zlib1g libgcc-s1 libstdc++6 \
    && rm -rf /var/lib/apt/lists/* /etc/apt/apt.conf.d/99-build-ca \
    && groupadd --gid 10001 app && useradd --uid 10001 --gid app --create-home app \
    && mkdir -p /data && chown app:app /data
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /usr/local/bin/officecli /usr/local/bin/officecli
WORKDIR /app
COPY src ./src
COPY LICENSE NOTICE ./
COPY vendor/officecli/LICENSE vendor/officecli/NOTICE vendor/officecli/THIRD-PARTY-NOTICES.txt /usr/share/licenses/officecli/
RUN chmod -R a+rX /app /usr/share/licenses/officecli
USER app
RUN officecli --version
VOLUME ["/data"]
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.getenv('OFFICECLI_MCP_PORT','8080')+'/health',timeout=3)" || exit 1
ENTRYPOINT ["python", "-m", "officecli_mcp.server"]
