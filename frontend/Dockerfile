# ── Build stage ───────────────────────────────────────────────
FROM node:20-alpine AS build

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .
# Backend URL is baked in at build time. Defaults to .env.production (OGDCL);
# pass --build-arg API_BASE_URL=<url> to target a different backend (e.g. a
# per-company instance) — it overwrites .env.production for this build.
# NOTE: the ARG must NOT be named VITE_* — Docker ARGs become env vars during
# RUN steps, and Vite gives env vars priority over .env.production, so an
# empty VITE_API_BASE_URL would silently wipe the URL (localhost fallback).
ARG API_BASE_URL=""
RUN if [ -n "$API_BASE_URL" ]; then echo "VITE_API_BASE_URL=$API_BASE_URL" > .env.production; fi
RUN npm run build

# ── Serve stage ───────────────────────────────────────────────
FROM nginx:alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 8080
CMD ["nginx", "-g", "daemon off;"]
