FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app \
    SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt \
    REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt

RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr tesseract-ocr-rus tesseract-ocr-eng libmagic1 curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml ./
RUN mkdir app && touch app/__init__.py \
    && pip install --upgrade pip \
    && pip install ".[dev]"
COPY app ./app
COPY tests ./tests
COPY docker-entrypoint.sh /usr/local/bin/bank-reporter-entrypoint
RUN chmod +x /usr/local/bin/bank-reporter-entrypoint

EXPOSE 8000
ENTRYPOINT ["/usr/local/bin/bank-reporter-entrypoint"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
