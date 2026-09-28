# Single-container deploy: FastAPI serves the API *and* the built React app.
# The database is built at first start from the committed public-data snapshot + demo scenario.

FROM node:20-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PORT=8000
WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install -r requirements.txt
COPY backend/ ./
COPY --from=web /web/dist /app/frontend/dist
EXPOSE 8000
CMD ["sh", "-c", "[ -f data/sitescout.db ] || python -m scripts.bootstrap; exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
