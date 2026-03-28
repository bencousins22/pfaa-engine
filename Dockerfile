# PFAA Engine — Multi-stage build
FROM node:22-slim AS node-build
WORKDIR /app
COPY package.json tsconfig.json ./
RUN npm install
COPY src/ ./src/
COPY bin/ ./bin/
RUN npx tsc

FROM python:3.12-slim AS final
WORKDIR /app

# Install Node.js
RUN apt-get update && apt-get install -y curl && \
    curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && \
    apt-get install -y nodejs && \
    rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements.txt pyproject.toml setup.py ./
RUN pip install --no-cache-dir -r requirements.txt 2>/dev/null || true

# Node deps
COPY package.json tsconfig.json ./
RUN npm install --production

# Copy built TS
COPY --from=node-build /app/dist ./dist/
COPY --from=node-build /app/node_modules ./node_modules/

# Copy Python source
COPY agent_setup_cli/ ./agent_setup_cli/
COPY python/ ./python/
COPY agents/ ./agents/
COPY bin/ ./bin/
COPY pfaa.config.json .env.example ./

# Expose ports
EXPOSE 8420

ENV PYTHONPATH=/app/python:/app
ENV PYTHON_GIL=0
ENV NODE_ENV=production

# Default: run the Agent Zero-style CLI
CMD ["node", "bin/pfaa-cli.js"]
