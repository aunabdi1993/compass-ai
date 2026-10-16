# Builds the React app, then serves it and the API from one Python process.
FROM node:22-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY compass/ compass/
COPY --from=web /web/dist frontend/dist
ENV PYTHONUNBUFFERED=1
EXPOSE 8000
# Platforms like Render, Railway and Fly set $PORT; default to 8000 locally.
CMD ["sh", "-c", "uvicorn compass.server:app --host 0.0.0.0 --port ${PORT:-8000}"]
