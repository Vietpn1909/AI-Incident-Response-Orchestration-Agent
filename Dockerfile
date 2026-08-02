# ---- Stage 1: Build ----
FROM python:3.11-slim AS builder

# Cài vào virtualenv ở /opt/venv thay vì `pip install --user` (/root/.local).
# /root có quyền 700 nên user non-root ở stage 2 không đọc được, dẫn tới
# "exec: uvicorn: Permission denied" — container build xong nhưng exit 126.
RUN python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ---- Stage 2: Production ----
FROM python:3.11-slim

WORKDIR /app

# /opt/venv mặc định 755 nên appuser đọc và thực thi được.
COPY --from=builder /opt/venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH

# Security: run as non-root user
RUN useradd -m appuser

# Copy application code
COPY . .

# Create data directory with correct ownership
RUN mkdir -p /app/data && chown -R appuser:appuser /app

USER appuser

# Render (và phần lớn PaaS) truyền port qua biến $PORT thay vì cho chọn.
# Mặc định 8000 để chạy local và docker-compose không cần set gì.
ENV PORT=8000
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://localhost:' + os.environ.get('PORT', '8000') + '/health')" || exit 1

# Shell form (không phải JSON array) để $PORT được expand — dạng exec form sẽ
# truyền nguyên chuỗi "$PORT" cho uvicorn và container không bind được port,
# Render báo "no open ports detected" trong khi log app vẫn nói server đã chạy.
# `exec` để uvicorn thay thế shell, nhờ đó nhận được SIGTERM và shutdown gọn.
CMD exec uvicorn src.main:app --host 0.0.0.0 --port "$PORT"
