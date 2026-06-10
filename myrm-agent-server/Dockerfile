# syntax=docker/dockerfile:1.7
# MyrmAgent Server Docker Image (open-source distribution)
#
# BUILD CONTEXT (required): myrm-agent repository root (contains myrm-agent-server/ and shared/).
# Installs myrm-agent-harness[compiled-core] from PyPI via uv.lock.
#
#   docker build -f myrm-agent-server/Dockerfile -t myrm-server .
#
# For private CI that builds harness from source, use docker/Dockerfile.official

# ============================================================================
# Stage 1: Builder
# ============================================================================
FROM python:3.13-slim AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc libolm-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

COPY myrm-agent-server/pyproject.toml myrm-agent-server/uv.lock ./
COPY myrm-agent-server/app ./app
COPY myrm-agent-server/run.py ./run.py

ENV PATCHRIGHT_SKIP_BROWSER_DOWNLOAD=1 \
    PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1

RUN --mount=type=cache,target=/root/.cache/uv \
    uv venv \
    && uv sync --frozen --no-dev --all-extras --no-install-project

# ============================================================================
# Stage 2: Runtime
# ============================================================================
FROM python:3.13-slim AS runtime

LABEL maintainer="MyrmAgent"
LABEL description="MyrmAgent Server - AI Agent Backend"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEPLOY_MODE=local \
    PORT=25808 \
    HOST=0.0.0.0 \
    MPLBACKEND=Agg \
    MATPLOTLIBRC=/opt/mpl-config/matplotlibrc \
    MPLCONFIGDIR=/tmp/matplotlib

RUN groupadd -r myrm && useradd -r -g myrm -m -d /home/myrm myrm

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates xvfb x11vnc novnc websockify fluxbox \
    scrot xdotool at-spi2-core dbus-x11 \
    fontconfig fonts-noto-cjk fonts-noto-color-emoji fonts-liberation \
    && fc-cache -f \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /build/.venv /app/.venv
COPY --from=builder /build/app /app/app
COPY --from=builder /build/run.py /app/run.py
COPY myrm-agent-server/docker/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

COPY myrm-agent-server/docker/sandbox/matplotlibrc /opt/mpl-config/matplotlibrc
COPY shared /shared

RUN /app/.venv/bin/python -m myrm_agent_harness._verify_distribution --matplotlib-cjk \
    && rm -rf /tmp/_mpl_verify.png /tmp/matplotlib

WORKDIR /app
RUN mkdir -p /home/myrm/.myrm-agent && chown -R myrm:myrm /home/myrm /app

USER myrm

ENV PATH="/app/.venv/bin:$PATH" VIRTUAL_ENV="/app/.venv"

EXPOSE 25808 6080

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:25808/health || exit 1

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["python", "run.py", "--skip-port-check", "--host", "0.0.0.0", "--port", "25808"]
