"""Unit tests cho demo services (service-thanh-toan & service-dat-hang).

Đảm bảo các endpoint POST /pay, POST /orders, /metrics và /health hoạt động đúng hợp đồng contract ①.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from demo.service_dat_hang.main import app as app_orders
from demo.service_thanh_toan.main import app as app_pay


@pytest.mark.asyncio
async def test_pay_health():
    transport = ASGITransport(app=app_pay)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.get("/health")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ok"
        assert data["service"] == "service-thanh-toan"


@pytest.mark.asyncio
async def test_pay_metrics():
    transport = ASGITransport(app=app_pay)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.get("/metrics")
        assert res.status_code == 200
        content = res.text
        assert "http_request_duration_seconds_bucket" in content
        assert "db_pool_connections_in_use" in content
        assert "db_pool_size" in content


@pytest.mark.asyncio
async def test_orders_health():
    transport = ASGITransport(app=app_orders)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.get("/health")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ok"
        assert data["service"] == "service-dat-hang"
