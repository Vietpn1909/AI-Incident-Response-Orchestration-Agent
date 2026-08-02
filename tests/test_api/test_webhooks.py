"""Test `POST /webhooks/jira` — cổng vào của luồng thực thi khắc phục.

Endpoint này kích được hành động ảnh hưởng production, nên test ở đây kiểm cả
ba lớp bảo vệ. `test_agent_tu_duyet_bi_tu_choi_qua_webhook` là test tương ứng
với ràng buộc bắt buộc của đề bài, ở tầng HTTP.
"""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

import src.api.webhooks as webhooks
from src.config import Settings, get_settings
from src.main import app
from src.models.incident import (
    IncidentSignal,
    IncidentState,
    RemediationProposal,
    Severity,
)
from src.services.jira import FakeJiraClient, JiraApiError

SECRET = "test-secret-123"
AGENT = FakeJiraClient.AGENT_ACCOUNT_ID


@pytest.fixture
def jira(monkeypatch: pytest.MonkeyPatch) -> FakeJiraClient:
    """Ghi đè cấu hình và Jira client để không gọi Jira thật."""
    client = FakeJiraClient(verbose=False)

    def fake_settings() -> Settings:
        return Settings(
            jira_webhook_secret=SECRET,
            jira_agent_account_id=AGENT,
            jira_base_url="https://example.atlassian.net",
            jira_email="agent@example.com",
            jira_api_token="token",
            jira_project_key="KAN",
        )

    get_settings.cache_clear()
    monkeypatch.setattr(webhooks, "get_settings", fake_settings)
    monkeypatch.setattr(webhooks, "build_jira_client", lambda: client)
    return client


@pytest.fixture
def incident_key(jira: FakeJiraClient) -> str:
    key = jira.create_incident(
        IncidentSignal(
            affected_service="service-thanh-toan",
            severity=Severity.P2,
            detected_at=datetime(2026, 7, 29, 14, 32, tzinfo=UTC),
            metric_name="http_request_duration_seconds p95",
            metric_value=5.1,
            threshold=2.0,
        )
    )
    jira.post_proposal(
        key,
        RemediationProposal(action="rollback", target="service-thanh-toan", params={"to_version": "v1.4.1"}),
    )
    return key


client = TestClient(app)


def _post(body: dict, secret: str | None = SECRET):
    headers = {"X-Webhook-Secret": secret} if secret else {}
    return client.post("/webhooks/jira", json=body, headers=headers)


# ---------------------------------------------------------------- lớp 1: secret


def test_thieu_secret_thi_401(incident_key: str):
    assert _post({"issue": {"key": incident_key}}, secret=None).status_code == 401


def test_sai_secret_thi_401(incident_key: str):
    assert _post({"issue": {"key": incident_key}}, secret="sai").status_code == 401


def test_chua_cau_hinh_secret_thi_503(monkeypatch: pytest.MonkeyPatch):
    """Không có secret thì từ chối hẳn, không chạy ở chế độ mở."""
    monkeypatch.setattr(webhooks, "get_settings", lambda: Settings(jira_webhook_secret=""))
    assert _post({"issue": {"key": "KAN-1"}}).status_code == 503


# ------------------------------------------------------------------ lớp 2: HITL


def test_agent_tu_duyet_bi_tu_choi_qua_webhook(jira: FakeJiraClient, incident_key: str):
    """Ràng buộc bắt buộc của đề bài, kiểm ở tầng HTTP.

    Agent tự chuyển sang Remediating rồi webhook bị kích → phải trả 403 và
    KHÔNG thi hành gì.
    """
    jira.transition(incident_key, IncidentState.REMEDIATING)

    response = _post({"issue": {"key": incident_key}})

    assert response.status_code == 403
    assert "chính account Agent" in response.json()["detail"]


def test_bi_tu_choi_thi_canh_bao_tren_war_room(jira: FakeJiraClient, incident_key: str):
    """Trạng thái Remediating trên Jira không được khiến người xem hiểu nhầm."""
    jira.transition(incident_key, IncidentState.REMEDIATING)

    _post({"issue": {"key": incident_key}})

    timeline = jira.get_incident(incident_key).timeline
    assert any("TỪ CHỐI THỰC THI" in event.detail for event in timeline)


def test_chua_ai_duyet_thi_403(incident_key: str):
    assert _post({"issue": {"key": incident_key}}).status_code == 403


# ------------------------------------------------------------- lớp 3: thi hành


def test_nguoi_duyet_thi_thuc_thi(jira: FakeJiraClient, incident_key: str):
    jira.approve_as_human(incident_key)

    response = _post({"issue": {"key": incident_key}})

    assert response.status_code == 200
    body = response.json()
    assert body["action"] == "rollback"
    assert body["target"] == "service-thanh-toan"
    assert body["succeeded"] is True
    assert body["approved_by"] == FakeJiraClient.HUMAN_ACCOUNT_ID
    assert body["simulated"] is True


def test_ket_qua_duoc_ghi_len_war_room(jira: FakeJiraClient, incident_key: str):
    jira.approve_as_human(incident_key)

    _post({"issue": {"key": incident_key}})

    timeline = jira.get_incident(incident_key).timeline
    assert any("Đã thực thi khắc phục" in event.detail for event in timeline)


def test_hanh_dong_khong_duoc_phep_thi_400(jira: FakeJiraClient):
    key = jira.create_incident(
        IncidentSignal(
            affected_service="service-dat-hang",
            severity=Severity.P3,
            detected_at=datetime(2026, 7, 29, tzinfo=UTC),
            metric_name="p95",
            metric_value=2.4,
            threshold=2.0,
        )
    )
    jira.post_proposal(key, RemediationProposal(action="drop_database", target="service-dat-hang"))
    jira.approve_as_human(key)

    response = _post({"issue": {"key": key}})

    assert response.status_code == 400
    assert "không được phép" in response.json()["detail"]


# -------------------------------------------------------------- parse payload


@pytest.mark.parametrize("shape", ["issue", "issueKey", "key"])
def test_nhan_ca_ba_dang_payload_cua_jira(jira: FakeJiraClient, incident_key: str, shape: str):
    jira.approve_as_human(incident_key)
    body = {"issue": {"key": incident_key}} if shape == "issue" else {shape: incident_key}

    assert _post(body).status_code == 200


def test_payload_khong_co_issue_key_thi_422(incident_key: str):
    assert _post({"foo": "bar"}).status_code == 422


# ─────────────────────────────────── lỗi Jira

class _BrokenJira(FakeJiraClient):
    """FakeJiraClient nhưng ném JiraApiError với mã cho trước."""

    def __init__(self, status_code: int) -> None:
        super().__init__(verbose=False)
        self._code = status_code

    def get_transition_author(self, jira_key, to_state):  # noqa: ANN001, ANN201
        raise JiraApiError(f"GET /issue/{jira_key} → HTTP {self._code}", status_code=self._code)


@pytest.mark.parametrize(
    ("jira_code", "expected_http", "expected_text"),
    [
        (404, 404, "Không tìm thấy issue"),
        (401, 502, "JIRA_API_TOKEN"),
        (403, 502, "JIRA_API_TOKEN"),
        (429, 502, "rate limit"),
        (500, 502, "Jira lỗi"),
    ],
)
def test_loi_jira_khong_thanh_500_trong_rong(
    monkeypatch: pytest.MonkeyPatch, jira_code: int, expected_http: int, expected_text: str
):
    """Mỗi loại lỗi Jira phải ra HTTP riêng kèm gợi ý chỗ cần kiểm.

    Trước khi sửa, mọi lỗi Jira đều thành 500 "Internal Server Error" giống
    nhau — token sai, issue không tồn tại, Jira down đều một thông báo. Lúc demo
    thì không biết tắc ở đâu. Phát hiện khi probe bản deploy với issue KAN-99999.
    """
    broken = _BrokenJira(jira_code)

    def fake_settings() -> Settings:
        return Settings(jira_webhook_secret=SECRET, jira_agent_account_id=AGENT)

    monkeypatch.setattr(webhooks, "get_settings", fake_settings)
    monkeypatch.setattr(webhooks, "build_jira_client", lambda: broken)

    response = _post({"issue": {"key": "KAN-99999"}})

    assert response.status_code == expected_http
    assert expected_text in response.json()["detail"]
