FROM node:20-alpine AS build

WORKDIR /app

COPY package.json ./
RUN npm install

COPY . .

ARG VITE_DOMAIN=localhost
ENV VITE_DOMAIN=${VITE_DOMAIN}
ARG VITE_APP_BASE=/
ENV VITE_APP_BASE=${VITE_APP_BASE}
ARG VITE_API_BASE_URL=
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
ARG VITE_WS_BASE_URL=
ENV VITE_WS_BASE_URL=${VITE_WS_BASE_URL}

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/nginx.conf

# Remove the auto-tuning script that overrides our worker settings
RUN rm -f /docker-entrypoint.d/30-tune-worker-processes.sh

# Remove default config if it exists
RUN rm -f /etc/nginx/conf.d/default.conf

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://127.0.0.1/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
