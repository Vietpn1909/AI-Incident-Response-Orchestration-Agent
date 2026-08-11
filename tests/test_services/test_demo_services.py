"""Test contract cho phần demo do Trung sở hữu."""

from __future__ import annotations

from collections.abc import AsyncIterator
import logging
import os

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from demo import attack
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
    payment_service.auth_failure_events.clear()
    monkeypatch.setattr(payment_service, "pool", None)
    yield
    payment_service.memory_leak_store.clear()
    payment_service.auth_failure_events.clear()


@pytest.mark.asyncio
async def test_login_sai_mat_khau_tra_401(payment_client: AsyncClient):
    response = await payment_client.post(
        "/login",
        json={"username": "demo", "password": "sai"},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Sai tài khoản hoặc mật khẩu"}


@pytest.mark.asyncio
async def test_login_thong_ke_mot_ip_thu_nhieu_tai_khoan(payment_client: AsyncClient):
    for username in ("account-a", "account-b", "account-a"):
        response = await payment_client.post(
            "/login",
            json={"username": username, "password": "sai"},
        )
        assert response.status_code == 401

    unique_sources, unique_accounts, top_source_ratio = payment_service._auth_failure_snapshot()
    assert unique_sources == 1
    assert unique_accounts == 2
    assert top_source_ratio == 1.0


@pytest.mark.asyncio
async def test_metrics_cong_bo_ba_so_lieu_uc3(payment_client: AsyncClient):
    await payment_client.post(
        "/login",
        json={"username": "account-a", "password": "sai"},
    )

    response = await payment_client.get("/metrics")

    assert response.status_code == 200
    assert "auth_failure_unique_source_ips_1m 1.0" in response.text
    assert "auth_failure_unique_accounts_1m 1.0" in response.text
    assert "auth_failure_top_source_ratio_1m 1.0" in response.text


def test_attack_rai_request_len_dung_so_account():
    accounts = {attack._account_for_request(index, 100) for index in range(12_000)}
    assert len(accounts) == 100


def test_thong_ke_dang_nhap_chi_giu_cua_so_mot_phut():
    payment_service.auth_failure_events.extend(
        [
            (10.0, "10.0.0.1", "account-a"),
            (20.0, "10.0.0.1", "account-b"),
        ]
    )

    assert payment_service._auth_failure_snapshot(now=70.0) == (1, 2, 1.0)
    assert payment_service._auth_failure_snapshot(now=81.0) == (0, 0, 0.0)


@pytest.mark.asyncio
async def test_login_dung_tra_token_gia(payment_client: AsyncClient):
    response = await payment_client.post(
        "/login",
        json={"username": "demo", "password": "demo"},
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "token": "fake-token"}
    assert payment_service._auth_failure_snapshot() == (0, 0, 0.0)


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


@pytest.mark.asyncio
async def test_debug_rce_sim_disables_logging(
    payment_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    # Mock os.dup2 to not actually redirect test runner output
    monkeypatch.setattr(os, "dup2", lambda fd1, fd2: None)
    
    response = await payment_client.post("/debug/rce-sim")
    assert response.status_code == 200
    assert response.json()["logging_disabled"] is True
    
    root_logger = logging.getLogger()
    assert len(root_logger.handlers) == 1
    assert isinstance(root_logger.handlers[0], logging.NullHandler)


@pytest.mark.asyncio
async def test_debug_suppress_output_returns_tampered(
    payment_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    # Mock os.dup2
    monkeypatch.setattr(os, "dup2", lambda fd1, fd2: None)
    
    response = await payment_client.post("/debug/suppress-output")
    assert response.status_code == 200
    assert response.json()["tampered"] is True
    assert response.json()["stdout_suppressed"] is True
