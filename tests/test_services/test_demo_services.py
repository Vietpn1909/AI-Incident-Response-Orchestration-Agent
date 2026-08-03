"""Test contract cho phần demo do Trung sở hữu."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from demo.service_thanh_toan import main as payment_service


class _FakeConnection:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows
        self.calls: list[tuple[str, str, tuple[object, ...]]] = []

    async def execute(self, query: str, *args: object) -> str:
        self.calls.append(("execute", query, args))
        return "SELECT 1"

    async def fetchrow(self, query: str, *args: object) -> dict[str, object]:
        self.calls.append(("fetchrow", query, args))
        return {"id": "payment-1"}

    async def fetchval(self, query: str, *args: object) -> int:
        self.calls.append(("fetchval", query, args))
        return 1

    async def fetch(self, query: str, padding_bytes: int, limit: int) -> list[dict[str, object]]:
        assert "repeat('x', $1)" in query
        assert padding_bytes == payment_service.MEMORY_PADDING_BYTES
        assert limit == payment_service.MEMORY_LEAK_BATCH_ROWS
        return self._rows


class _AcquireContext:
    def __init__(self, connection: _FakeConnection) -> None:
        self._connection = connection

    async def __aenter__(self) -> _FakeConnection:
        return self._connection

    async def __aexit__(self, *args: object) -> None:
        return None


class _FakePool:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._connection = _FakeConnection(rows)

    @property
    def connection(self) -> _FakeConnection:
        return self._connection

    def acquire(self) -> _AcquireContext:
        return _AcquireContext(self._connection)

    def get_size(self) -> int:
        return 1

    def get_idle_size(self) -> int:
        return 1


@pytest_asyncio.fixture
async def payment_client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=payment_service.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture(autouse=True)
def reset_demo_state(monkeypatch: pytest.MonkeyPatch):
    payment_service.memory_leak_store.clear()
    monkeypatch.setattr(payment_service, "pool", None)
    yield
    payment_service.memory_leak_store.clear()


@pytest.mark.asyncio
async def test_login_sai_mat_khau_tra_401(payment_client: AsyncClient):
    response = await payment_client.post(
        "/login",
        json={"username": "demo", "password": "sai"},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Sai tài khoản hoặc mật khẩu"}


@pytest.mark.asyncio
async def test_login_dung_tra_token_gia(payment_client: AsyncClient):
    response = await payment_client.post(
        "/login",
        json={"username": "demo", "password": "demo"},
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "token": "fake-token"}


@pytest.mark.asyncio
async def test_pay_giu_connection_bang_truy_van_cham_truoc_khi_insert(
    payment_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    fake_pool = _FakePool([])
    monkeypatch.setattr(payment_service, "pool", fake_pool)

    response = await payment_client.post(
        "/pay",
        json={"order_id": "order-1", "amount": 100},
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "payment_id": "payment-1"}

    calls = fake_pool.connection.calls
    assert [method for method, _, _ in calls] == ["execute", "fetchrow", "fetchval"]
    assert "pg_sleep" in calls[0][1]
    assert calls[0][2] == (payment_service.PAYMENT_QUERY_DELAY_SECONDS,)
    assert "INSERT INTO payments" in calls[1][1]
    assert "count(*)" in calls[2][1]


@pytest.mark.asyncio
async def test_pay_batch_giu_du_lieu_qua_nhieu_request(
    payment_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    rows = [{"id": 1, "order_id": "order-1", "memory_padding": "x"}]
    monkeypatch.setattr(payment_service, "pool", _FakePool(rows))

    first = await payment_client.post("/pay/batch")
    second = await payment_client.post("/pay/batch")

    assert first.status_code == 200
    assert first.json()["retained_batches"] == 1
    assert second.json() == {"ok": True, "retained_batches": 2, "retained_rows": 2}
    assert len(payment_service.memory_leak_store) == 2
    assert payment_service.memory_leak_store[0] is not payment_service.memory_leak_store[1]


@pytest.mark.asyncio
async def test_pay_batch_nhac_chay_seed_khi_chua_co_du_lieu(
    payment_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(payment_service, "pool", _FakePool([]))

    response = await payment_client.post("/pay/batch")

    assert response.status_code == 409
    assert "seed.py" in response.json()["detail"]
