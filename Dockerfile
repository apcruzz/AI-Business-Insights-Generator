# Build static frontend assets separately so the running Python image does not need Node or npm.
FROM node:22-bookworm-slim AS frontend
WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci
COPY index.html vite.config.js ./
COPY src/ ./src/
COPY data/sample_catalog.json ./data/sample_catalog.json
RUN npm run build

FROM python:3.12-slim-bookworm AS runtime
# Keep native math libraries from starting competing thread pools on the small hosted instance.
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 APP_ENV=production \
    OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
    SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && test -s "$SSL_CERT_FILE" \
    && useradd --create-home --uid 10001 dashboard
COPY backend/ ./backend/
COPY gunicorn.conf.py ./
# Include only fictional generated examples, never local uploads or the original Cafe.csv.
COPY data/samples/*_Demo.csv ./data/samples/
COPY --from=frontend /build/dist/ ./dist/
# Run requests without root privileges; Gunicorn reads Render's PORT in gunicorn.conf.py.
USER dashboard
EXPOSE 10000
CMD ["gunicorn", "--config", "gunicorn.conf.py", "backend.production:create_app()"]
