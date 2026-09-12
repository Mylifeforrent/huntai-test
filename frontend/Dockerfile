# syntax=docker/dockerfile:1
#
# Frontend image (Stage 12). Multi-stage: Node only builds the static bundle;
# the runtime stage is nginx serving static assets. No Node runtime process
# ships to production (AGENTS.md §6).
#
# Build context is frontend/.

# ---- builder -----------------------------------------------------------------
FROM node:24-slim AS builder

WORKDIR /app

# npm ci honours .npmrc (legacy-peer-deps for the TS 7 / typescript-eslint peer
# range) and requires package-lock.json to be in lockstep.
COPY package.json package-lock.json .npmrc ./
RUN npm ci

# Set only for a cross-origin API; empty means same-origin /api/v1 (the default,
# because import.meta.env is replaced statically at build time).
ARG VITE_API_BASE_URL=
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL

COPY . .
RUN npm run build

# ---- runtime -----------------------------------------------------------------
FROM nginx:alpine AS runtime

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD wget -q --spider http://127.0.0.1/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
