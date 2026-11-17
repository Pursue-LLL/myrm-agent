# MyrmAgent Frontend Docker Image
#
# Multi-stage build: deps → builder → runner
# Uses Next.js standalone output for minimal image size.
#
# Build context must be the project root directory.
# Usage via docker-compose:
#   docker compose --profile app up -d
#
# Manual build:
#   docker build -f myrm-agent-frontend/Dockerfile \
#     --build-arg API_HOST=backend --build-arg API_PORT=25808 -t myrm-frontend .

# ============================================================================
# Stage 1: Dependencies
# ============================================================================
FROM oven/bun:1-alpine AS deps

RUN apk add --no-cache libc6-compat

WORKDIR /app
COPY myrm-agent-frontend/package.json myrm-agent-frontend/bun.lock ./
RUN bun install --frozen-lockfile

# ============================================================================
# Stage 2: Builder (Node.js runs next build, bun runs the build script)
# ============================================================================
FROM node:22-alpine AS builder

# The build script is a bun script. bun comes from the deps stage, so the version that installed the dependencies is
# the one that builds with them.
COPY --from=deps /usr/local/bin/bun /usr/local/bin/bun

WORKDIR /app

# Dockerfile.dockerignore, next to this file, keeps the host's dependencies, build output and env files out of the
# copies below.
COPY --from=deps /app/node_modules ./frontend/node_modules
COPY myrm-agent-frontend/ ./frontend
COPY shared ./shared

WORKDIR /app/frontend

# Configurable API backend address (baked into build at rewrites compilation)
ARG API_HOST=localhost
ARG API_PORT=25808
ENV API_HOST=$API_HOST \
    API_PORT=$API_PORT \
    NEXT_TELEMETRY_DISABLED=1

RUN bun run build

# ============================================================================
# Stage 3: Runner
# ============================================================================
FROM node:22-alpine AS runner

WORKDIR /app

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

RUN addgroup --system --gid 1001 nodejs \
    && adduser --system --uid 1001 nextjs

# next.config.ts sets outputFileTracingRoot to the parent of the frontend directory, so the standalone output nests the
# server under frontend/. server.js changes to its own directory at start, and that is where it looks for public/ and
# .next/static.
COPY --from=builder /app/frontend/public ./frontend/public
COPY --from=builder --chown=nextjs:nodejs /app/frontend/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/frontend/.next/static ./frontend/.next/static

USER nextjs

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost:3000/ || exit 1

CMD ["node", "frontend/server.js"]
