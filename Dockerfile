# 階段一：編譯環境
FROM python:3.11-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# 移除 --user，讓套件直接裝在系統標準路徑下
RUN pip install --no-cache-dir -r requirements.txt

# 階段二：運行環境
FROM python:3.11-slim

WORKDIR /app

RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser

# 直接從 builder 複製完整的 python 環境套件（在 /usr/local 下）
COPY --from=builder /usr/local /usr/local

RUN mkdir -p /app/data /app/uploads && chown -R appuser:appuser /app

# 只複製程式碼，移除 .env 的 COPY
COPY --chown=appuser:appuser app /app/app

USER appuser

EXPOSE 8080

HEALTHCHECK --interval=30m --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/api/v1/health')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1", "--limit-concurrency", "64"]