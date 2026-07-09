# syntax=docker/dockerfile:1
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md LICENSE ./
COPY stt_bench ./stt_bench
COPY config ./config
COPY data ./data

RUN pip install --no-cache-dir .

ENV STT_BENCH_HOST=0.0.0.0
ENV STT_BENCH_PORT=8766
ENV STT_BENCH_DB_PATH=/data/results.db
ENV STT_BENCH_CACHE_DIR=/data/cache
ENV STT_BENCH_DATA_DIR=/app/data
ENV STT_BENCH_CONFIG_DIR=/app/config

EXPOSE 8766
VOLUME ["/data"]

CMD ["stt-bench", "serve", "--host", "0.0.0.0", "--port", "8766"]
