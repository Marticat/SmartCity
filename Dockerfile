FROM node:22-bookworm-slim AS frontend
WORKDIR /build
ARG VITE_TILE_URL=https://tile.openstreetmap.org/{z}/{x}/{y}.png
ARG VITE_TILE_ATTRIBUTION
ENV VITE_TILE_URL=$VITE_TILE_URL VITE_TILE_ATTRIBUTION=$VITE_TILE_ATTRIBUTION
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DATA_DIR=/app/data
WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir torch==2.7.0 --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ /app/backend/
COPY scripts/ /app/scripts/
COPY data/ /app/data/
COPY --from=frontend /build/dist /app/frontend/dist
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)"
CMD ["python", "-m", "uvicorn", "backend.app.main:app", "--no-access-log", "--host", "0.0.0.0", "--port", "8000"]
