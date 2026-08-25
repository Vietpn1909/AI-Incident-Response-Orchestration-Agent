# Dockerfile dùng chung cho cả 2 service demo.
# docker-compose.demo.yml quyết định chạy service nào qua `command`.

FROM python:3.11-slim

RUN python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

# Port thật do compose truyền vào (8001 hoặc 8002).
ENV PORT=8001
EXPOSE 8001 8002 8003 8004

CMD exec uvicorn service_thanh_toan.main:app --host 0.0.0.0 --port "$PORT"
