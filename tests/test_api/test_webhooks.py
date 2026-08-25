"""Test `POST /webhooks/jira` — cổng vào của luồng thực thi khắc phục.

Endpoint này kích được hành động ảnh hưởng production, nên test ở đây kiểm cả
ba lớp bảo vệ. `test_agent_tu_duyet_bi_tu_choi_qua_webhook` là test tương ứng
với ràng buộc bắt buộc của đề bài, ở tầng HTTP.
"""

import os
from datetime import UTC, datetime
from unittest.mock import patch

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


# ------------------------------------------------------- nhãn ai đã khắc phục


def test_duyet_qua_webhook_thi_gan_nhan_nguoi(jira: FakeJiraClient, incident_key: str):
    """Khắc phục qua webhook = có người duyệt → nhãn NGƯỜI, không phải Agent.

    Nhãn là thứ duy nhất **đếm được bằng JQL**; comment war room đọc bằng mắt
    thì rõ nhưng không truy vấn được. Thiếu lời gọi ở đây là thủng dữ liệu, vì
    webhook là một trong ba đường thi hành thật.
    """
    from src.services.jira.mapping import FIXED_BY_AGENT_LABEL, FIXED_BY_HUMAN_LABEL

    jira.approve_as_human(incident_key)

    assert _post({"issue": {"key": incident_key}}).status_code == 200

    nhan = jira.get_labels(incident_key)
    assert FIXED_BY_HUMAN_LABEL in nhan
    assert FIXED_BY_AGENT_LABEL not in nhan
    # Nhãn cũ còn nguyên — issue không được rơi khỏi JQL tìm war room.
    assert "incident" in nhan
    assert "severity-P2" in nhan


def test_loi_jira_luc_gan_nhan_khong_pha_webhook(
    jira: FakeJiraClient, incident_key: str, monkeypatch: pytest.MonkeyPatch
):
    """Jira ném lỗi lúc gắn nhãn → nuốt, webhook vẫn trả 200.

    Ném ra đây là HTTP 5xx, mà Jira Automation thấy 5xx thì gọi lại webhook —
    tức thi hành remediation lần hai. Đổi một dòng thống kê lấy một lần
    remediation trùng là đánh đổi sai.
    """
    def hong(jira_key: str, label: str) -> None:
        raise JiraApiError("PUT /issue → HTTP 429", status_code=429)

    monkeypatch.setattr(jira, "add_label", hong)
    jira.approve_as_human(incident_key)

    response = _post({"issue": {"key": incident_key}})

    assert response.status_code == 200
    assert response.json()["succeeded"] is True


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


# ──────────────────────────────── postmortem tự động sau remediation


@pytest.fixture
def jira_with_smtp(monkeypatch: pytest.MonkeyPatch) -> FakeJiraClient:
    """Fixture có đủ SMTP config để postmortem email chạy được."""
    client = FakeJiraClient(verbose=False)

    def fake_settings() -> Settings:
        return Settings(
            jira_webhook_secret=SECRET,
            jira_agent_account_id=AGENT,
            jira_base_url="https://example.atlassian.net",
            jira_email="agent@example.com",
            jira_api_token="token",
            jira_project_key="KAN",
            smtp_email="test@gmail.com",
            smtp_app_password="xxxx-xxxx-xxxx-xxxx",
            postmortem_recipients="leader@gmail.com,oncall@gmail.com",
        )

    get_settings.cache_clear()
    monkeypatch.setattr(webhooks, "get_settings", fake_settings)
    monkeypatch.setattr(webhooks, "build_jira_client", lambda: client)
    # Mock GmailClient để không gửi email thật
    monkeypatch.setattr(
        webhooks,
        "GmailClient",
        lambda email, password: _FakeGmailClient(),
    )
    return client


class _FakeGmailClient:
    """Mock GmailClient — trả success mà không gọi SMTP."""

    def send(self, **kwargs):
        from src.services.email_client import EmailResult
        return EmailResult(
            success=True,
            recipients=kwargs.get("to", []),
            subject=kwargs.get("subject", ""),
        )


def _create_incident_with_hypothesis(jira: FakeJiraClient) -> str:
    """Tạo incident có đầy đủ signal + hypothesis + proposal để postmortem sinh được."""
    from src.models.incident import (
        DeployRecord,
        Hypothesis,
        MetricEvidence,
    )

    signal = IncidentSignal(
        affected_service="service-thanh-toan",
        severity=Severity.P2,
        detected_at=datetime(2026, 8, 12, 10, 0, tzinfo=UTC),
        metric_name="p95_latency",
        metric_value=3.3,
        threshold=2.0,
        evidence=[
            MetricEvidence(name="db_pool", value=48, unit="/50", baseline=15),
        ],
    )
    key = jira.create_incident(signal)

    # Thêm hypothesis
    hypothesis = Hypothesis(
        statement="Connection pool cạn kiệt do retry logic",
        confidence=0.9,
        evidence=signal.evidence,
        related_deploy=DeployRecord(
            service="service-thanh-toan",
            version="v1.4.2",
            deployed_at=datetime(2026, 8, 12, 9, 45, tzinfo=UTC),
            deployed_by="ci",
            commit_sha="abc",
            change_note="retry logic",
        ),
    )
    jira.post_hypothesis(key, hypothesis)

    # Thêm proposal
    jira.post_proposal(
        key,
        RemediationProposal(
            action="rollback",
            target="service-thanh-toan",
            params={"to_version": "v1.4.1"},
        ),
    )

    return key


def test_postmortem_gui_sau_remediation_thanh_cong(jira_with_smtp: FakeJiraClient):
    """Pipeline đầy đủ: approve → execute → postmortem email gửi thành công."""
    key = _create_incident_with_hypothesis(jira_with_smtp)
    jira_with_smtp.approve_as_human(key)

    response = _post({"issue": {"key": key}})

    assert response.status_code == 200
    body = response.json()
    assert body["succeeded"] is True
    assert body["postmortem_sent"] is True

    # Kiểm tra có comment ghi nhận đã gửi postmortem
    timeline = jira_with_smtp.get_incident(key).timeline
    assert any("postmortem" in e.detail.lower() for e in timeline)


def test_postmortem_bo_qua_khi_thieu_smtp(jira: FakeJiraClient, incident_key: str):
    """Thiếu SMTP config → bỏ qua postmortem, không lỗi."""
    jira.approve_as_human(incident_key)

    response = _post({"issue": {"key": incident_key}})

    assert response.status_code == 200
    body = response.json()
    assert body["succeeded"] is True
    assert body["postmortem_sent"] is False


def test_postmortem_bo_qua_khi_remediation_that_bai(
    monkeypatch: pytest.MonkeyPatch, jira_with_smtp: FakeJiraClient
):
    """Remediation thất bại → không gửi postmortem."""
    key = _create_incident_with_hypothesis(jira_with_smtp)
    jira_with_smtp.approve_as_human(key)

    # Mock execute để trả thất bại
    from src.services.remediation import RemediationResult

    def fake_execute(*args, **kwargs):
        return RemediationResult(
            action="rollback",
            target="service-thanh-toan",
            succeeded=False,
            detail="Rollback failed",
            approved_by="human",
        )

    monkeypatch.setattr(webhooks, "execute", fake_execute)

    response = _post({"issue": {"key": key}})

    assert response.status_code == 200
    body = response.json()
    assert body["succeeded"] is False
    assert body["postmortem_sent"] is False


def test_postmortem_loi_khong_pha_webhook(
    monkeypatch: pytest.MonkeyPatch, jira_with_smtp: FakeJiraClient
):
    """Postmortem lỗi → webhook vẫn trả 200 (remediation đã thành công)."""
    key = _create_incident_with_hypothesis(jira_with_smtp)
    jira_with_smtp.approve_as_human(key)

    # Mock generate_postmortem để ném exception
    def broken_generator(*args, **kwargs):
        raise RuntimeError("Postmortem service down")

    monkeypatch.setattr(webhooks, "generate_postmortem", broken_generator)

    response = _post({"issue": {"key": key}})

    assert response.status_code == 200
    body = response.json()
    assert body["succeeded"] is True
    assert body["postmortem_sent"] is False


def test_postmortem_response_co_flag(jira: FakeJiraClient, incident_key: str):
    """Response luôn có trường postmortem_sent."""
    jira.approve_as_human(incident_key)

    response = _post({"issue": {"key": incident_key}})

    assert response.status_code == 200
    assert "postmortem_sent" in response.json()


# ──────────────────────── POST /webhooks/jira/resolved (manual resolution)


def _post_resolved(body: dict, secret: str | None = SECRET):
    headers = {"X-Webhook-Secret": secret} if secret else {}
    return client.post("/webhooks/jira/resolved", json=body, headers=headers)


def test_resolved_thieu_secret_thi_401(jira: FakeJiraClient, incident_key: str):
    assert _post_resolved({"issue": {"key": incident_key}}, secret=None).status_code == 401


def test_resolved_sai_secret_thi_401(jira: FakeJiraClient, incident_key: str):
    assert _post_resolved({"issue": {"key": incident_key}}, secret="sai").status_code == 401


def test_resolved_khong_co_key_thi_422(jira: FakeJiraClient):
    assert _post_resolved({"foo": "bar"}).status_code == 422


def test_resolved_issue_khong_ton_tai(jira: FakeJiraClient):
    response = _post_resolved({"issue": {"key": "KAN-99999"}})
    assert response.status_code == 404


def test_resolved_manual_thanh_cong(jira_with_smtp: FakeJiraClient):
    """Happy path: incident resolved thủ công, có ghi chú."""
    key = _create_incident_with_hypothesis(jira_with_smtp)
    # Chuyển thẳng sang Resolved bằng account người (bỏ qua Remediating)
    jira_with_smtp.transition(key, IncidentState.RESOLVED, actor=FakeJiraClient.HUMAN_ACCOUNT_ID)

    response = _post_resolved({
        "issue": {"key": key},
        "resolution_note": "Tự restart lại service bằng kubectl rollout restart",
    })

    assert response.status_code == 200
    body = response.json()
    assert body["resolution"] == "manual"
    assert body["resolution_note"] == "Tự restart lại service bằng kubectl rollout restart"
    assert body["postmortem_sent"] is True


def test_resolved_manual_khong_co_ghi_chu(jira_with_smtp: FakeJiraClient):
    """Resolved mà không ghi chú — vẫn gửi postmortem, ghi 'thủ công'."""
    key = _create_incident_with_hypothesis(jira_with_smtp)
    jira_with_smtp.transition(key, IncidentState.RESOLVED, actor=FakeJiraClient.HUMAN_ACCOUNT_ID)

    response = _post_resolved({"issue": {"key": key}})

    assert response.status_code == 200
    body = response.json()
    assert body["resolution"] == "manual"
    assert body["resolution_note"] is None
    assert body["postmortem_sent"] is True


def test_resolved_bo_qua_khi_thieu_smtp(jira: FakeJiraClient, incident_key: str):
    """Thiếu SMTP → bỏ qua postmortem, không lỗi."""
    jira.transition(incident_key, IncidentState.RESOLVED, actor=FakeJiraClient.HUMAN_ACCOUNT_ID)

    response = _post_resolved({"issue": {"key": incident_key}})

    assert response.status_code == 200
    assert response.json()["postmortem_sent"] is False


def test_resolved_comment_ghi_chu_tren_war_room(jira_with_smtp: FakeJiraClient):
    """Ghi chú giải quyết phải xuất hiện trên war room."""
    key = _create_incident_with_hypothesis(jira_with_smtp)
    jira_with_smtp.transition(key, IncidentState.RESOLVED, actor=FakeJiraClient.HUMAN_ACCOUNT_ID)

    _post_resolved({
        "issue": {"key": key},
        "resolution_note": "Đã tăng connection pool lên 100",
    })

    timeline = jira_with_smtp.get_incident(key).timeline
    assert any("GHI CHÚ GIẢI QUYẾT THỦ CÔNG" in e.detail for e in timeline)


def test_resolved_co_comment_postmortem_tren_war_room(jira_with_smtp: FakeJiraClient):
    """Comment postmortem ghi nhận là manual resolution."""
    key = _create_incident_with_hypothesis(jira_with_smtp)
    jira_with_smtp.transition(key, IncidentState.RESOLVED, actor=FakeJiraClient.HUMAN_ACCOUNT_ID)

    _post_resolved({"issue": {"key": key}})

    timeline = jira_with_smtp.get_incident(key).timeline
    assert any("manual resolution" in e.detail.lower() for e in timeline)


# ────────────── Fix #1: Auto-transition sang Resolved sau execute


def test_auto_resolved_sau_execute_thanh_cong(jira: FakeJiraClient, incident_key: str):
    """Sau execute thành công, ticket phải tự chuyển sang Resolved."""
    jira.approve_as_human(incident_key)

    _post({"issue": {"key": incident_key}})

    incident = jira.get_incident(incident_key)
    assert incident.state == IncidentState.RESOLVED


def test_khong_auto_resolved_khi_execute_that_bai(
    monkeypatch: pytest.MonkeyPatch, jira_with_smtp: FakeJiraClient
):
    """Execute thất bại → KHÔNG chuyển sang Resolved."""
    key = _create_incident_with_hypothesis(jira_with_smtp)
    jira_with_smtp.approve_as_human(key)

    from src.services.remediation import RemediationResult

    def fake_execute(*args, **kwargs):
        return RemediationResult(
            action="rollback",
            target="service-thanh-toan",
            succeeded=False,
            detail="Rollback failed",
            approved_by="human",
        )

    monkeypatch.setattr(webhooks, "execute", fake_execute)

    _post({"issue": {"key": key}})

    incident = jira_with_smtp.get_incident(key)
    assert incident.state == IncidentState.REMEDIATING


# ────────────── Fix #2: Guard chống gửi postmortem 2 lần


def test_resolved_skip_khi_da_co_postmortem(jira_with_smtp: FakeJiraClient):
    """Nếu Rule #1 đã gửi postmortem, Rule #2 fire thì skip."""
    key = _create_incident_with_hypothesis(jira_with_smtp)
    jira_with_smtp.approve_as_human(key)

    # Rule #1: execute + postmortem + auto-resolve
    resp1 = _post({"issue": {"key": key}})
    assert resp1.status_code == 200
    assert resp1.json()["postmortem_sent"] is True

    # Rule #2 fire (vì ticket vừa sang Resolved)
    resp2 = _post_resolved({"issue": {"key": key}})

    assert resp2.status_code == 200
    body = resp2.json()
    assert body["resolution"] == "already_handled"
    assert body["postmortem_sent"] is False



def test_health_bao_commit_dang_chay():
    """`/health` phải nói đang chạy commit nào, không chỉ "ok".

    Trước 22/08 nó chỉ trả `status` + `env`, nên câu "Render đã deploy commit mới
    chưa" không ai trả lời được từ bên ngoài — phải mở dashboard. Và
    `docs/START-HERE.md` đã ghi sẵn một cạm bẫy có thật: merge PR trên web thì repo
    mirror tụt lại, Render chạy code cũ, mà dashboard vẫn báo deploy thành công.

    `RENDER_GIT_COMMIT` do Render tự bơm. Ngoài Render thì trả `"local"` — nói thật
    là không biết, hơn là đọc `git` lúc chạy rồi báo commit của thư mục làm việc
    chứ không phải của bản đã build.
    """
    from fastapi.testclient import TestClient

    from src.main import app

    with patch.dict(
        os.environ, {"RENDER_GIT_COMMIT": "abc1234def5678", "RENDER_GIT_BRANCH": "develop"}
    ):
        body = TestClient(app).get("/health").json()

    assert body["status"] == "ok"
    assert body["commit"] == "abc1234", "phải rút ngắn còn 7 ký tự như git short sha"
    assert body["branch"] == "develop"


def test_health_ngoai_render_khong_bao_commit_gia():
    """Không có `RENDER_GIT_COMMIT` thì trả "local", không đoán."""
    from fastapi.testclient import TestClient

    from src.main import app

    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("RENDER_GIT_COMMIT", None)
        os.environ.pop("RENDER_GIT_BRANCH", None)
        body = TestClient(app).get("/health").json()

    assert body["commit"] == "local"
    assert body["branch"] == "local"
