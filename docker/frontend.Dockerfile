# syntax=docker/dockerfile:1

FROM node:22-alpine AS frontend-build

WORKDIR /app/pwa

COPY pwa/package.json pwa/package-lock.json ./
RUN npm ci

COPY pwa/index.html pwa/tsconfig.json pwa/vite.config.ts ./
COPY pwa/src ./src

ARG VITE_API_BASE_URL=
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}

RUN npm run build

FROM nginx:1.27-alpine AS runtime

COPY docker/nginx/frontend.conf /etc/nginx/conf.d/default.conf
COPY --from=frontend-build /app/pwa/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD wget -qO- http://127.0.0.1/ >/dev/null 2>&1 || exit 1
