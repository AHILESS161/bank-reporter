FROM node:24-bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates chromium fonts-liberation fonts-noto-core fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY package.json ./
RUN npm install --omit=dev --ignore-scripts
COPY server.mjs action-policy.json ./

ENV AGENT_BROWSER_EXECUTABLE_PATH=/usr/bin/chromium \
    AGENT_BROWSER_CONTENT_BOUNDARIES=1 \
    AGENT_BROWSER_MAX_OUTPUT=100000 \
    AGENT_BROWSER_NO_WEBMCP=1

EXPOSE 8787
CMD ["node", "server.mjs"]
