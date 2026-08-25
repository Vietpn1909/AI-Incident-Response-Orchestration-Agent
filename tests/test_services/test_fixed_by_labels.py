"""Nhãn `fixed-by-*` — sự cố này Agent tự khắc phục hay người duyệt rồi mới khắc phục.

Vì sao gom vào một file riêng thay vì rải theo từng module: nhãn chỉ có giá trị
khi **cả ba đường thi hành** đều gắn. Thiếu một đường là số liệu thủng, mà đọc
ba file test khác nhau thì không ai thấy được là đang thiếu đường nào. Ba đường
đó là:

1. `scripts/run_agent.py::_execute_approved()` — người duyệt, phát hiện qua poll
2. `src/api/webhooks.py` — người duyệt, phát hiện qua webhook Jira
   (test ở `tests/test_api/test_webhooks.py` vì cần dựng cả app FastAPI)
3. `src/services/auto_remediation.py` — Agent tự thi hành, hai hàm

Không gọi mạng: `FakeJiraClient` giữ nhãn trong bộ nhớ đúng như Jira giữ field
`labels`, và `get_labels()` là đường đọc lại chỉ bản giả mới có.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from src.models.incident import (
    IncidentSignal,
    IncidentState,
    RemediationProposal,
    Severity,
)
from src.services.auto_remediation import (
    AutoRemediationDecision,
    FallbackRollbackDecision,
    execute_auto_remediation,
    execute_fallback_rollback,
)
from src.services.jira import FakeJiraClient
from src.services.jira.mapping import (
    FIXED_BY_AGENT_LABEL,
    FIXED_BY_HUMAN_LABEL,
    fixed_by_from_labels,
)
from src.services.remediation import RemediationResult

SERVICE = "service-thanh-toan"


@pytest.fixture(autouse=True)
def khong_thi_hanh_that(monkeypatch: pytest.MonkeyPatch):
    """Chặn test chạm Docker thật — cùng lý do đã ghi ở `test_auto_remediation.py`.

    Cặp `("rollback", "service-thanh-toan")` nằm trong danh sách trắng của
    `executors`, và `conftest.py` không chặn giúp vì biến `REMEDIATION_REAL` đọc
    thẳng từ `os.environ` chứ không qua `Settings`.
    """
    monkeypatch.setenv("REMEDIATION_REAL", "")


def _war_room(jira: FakeJiraClient, action: str = "rollback") -> str:
    """Một war room đã có đề xuất, đang chờ duyệt."""
    jira_key = jira.create_incident(
        IncidentSignal(
            affected_service=SERVICE,
            severity=Severity.P2,
            detected_at=datetime.now(UTC),
            metric_name="http_request_duration_seconds p95",
            metric_value=5.1,
            threshold=2.0,
        )
    )
    jira.post_proposal(
        jira_key,
        RemediationProposal(
            action=action,
            target=SERVICE,
            params={"to_version": "v1.4.2"} if action == "rollback" else {},
        ),
    )
    return jira_key


def _quyet_dinh_auto(jira_key: str) -> AutoRemediationDecision:
    return AutoRemediationDecision(
        jira_key=jira_key,
        action="rollback",
        target=SERVICE,
        params={"to_version": "v1.4.2"},
        reason="Sự cố P2 đã chờ 40 phút mà không có phản hồi.",
        forced_rollback=True,
    )


def _quyet_dinh_du_phong(jira_key: str) -> FallbackRollbackDecision:
    return FallbackRollbackDecision(
        jira_key=jira_key,
        target=SERVICE,
        to_version="v1.4.2",
        attempted_action="restart",
        con_lai=None,
    )


def _that_bai(action: str = "rollback") -> RemediationResult:
    """Kết quả thi hành THẤT BẠI, để kiểm điều kiện `succeeded`."""
    return RemediationResult(
        action=action,
        target=SERVICE,
        succeeded=False,
        detail="container không khởi động lại được",
        approved_by="ai-do",
        simulated=False,
    )


# ---------------------------------------------------------------------------
# Đường 1: người duyệt, phát hiện qua vòng poll của Agent
# ---------------------------------------------------------------------------


class TestNguoiDuyetQuaPoll:
    """`_execute_approved()` trong `scripts/run_agent.py`."""

    def test_gan_nhan_nguoi(self):
        """Người duyệt → nhãn NGƯỜI, và tuyệt đối không kèm nhãn Agent.

        Hai nhãn trên cùng một issue làm hỏng đúng thứ nhãn sinh ra để phục vụ:
        tổng hai nhóm không còn bằng tổng số sự cố.
        """
        from scripts.run_agent import _execute_approved

        jira = FakeJiraClient(verbose=False)
        jira_key = _war_room(jira)
        jira.approve_as_human(jira_key)

        _execute_approved(jira, jira_key, FakeJiraClient.HUMAN_ACCOUNT_ID)

        nhan = jira.get_labels(jira_key)
        assert FIXED_BY_HUMAN_LABEL in nhan
        assert FIXED_BY_AGENT_LABEL not in nhan
        assert fixed_by_from_labels(nhan) == FIXED_BY_HUMAN_LABEL

    def test_khong_lam_mat_nhan_cu(self):
        """Nhãn `incident`/`severity-*`/`service-*` phải còn nguyên sau khi gắn."""
        from scripts.run_agent import _execute_approved

        jira = FakeJiraClient(verbose=False)
        jira_key = _war_room(jira)
        jira.approve_as_human(jira_key)

        _execute_approved(jira, jira_key, FakeJiraClient.HUMAN_ACCOUNT_ID)

        nhan = jira.get_labels(jira_key)
        assert "incident" in nhan
        assert "severity-P2" in nhan
        assert f"service-{SERVICE}" in nhan

    def test_thi_hanh_that_bai_thi_khong_gan_nhan(self):
        """`succeeded=False` → không nhãn nào. Nhãn trên hành động hỏng là nhãn nói dối."""
        from scripts.run_agent import _execute_approved

        jira = FakeJiraClient(verbose=False)
        jira_key = _war_room(jira)
        jira.approve_as_human(jira_key)

        with patch("scripts.run_agent.execute", return_value=_that_bai()):
            _execute_approved(jira, jira_key, FakeJiraClient.HUMAN_ACCOUNT_ID)

        assert fixed_by_from_labels(jira.get_labels(jira_key)) is None

    def test_loi_jira_luc_gan_nhan_khong_pha_luong(self):
        """Jira ném lỗi lúc gắn nhãn → nuốt, luồng khắc phục vẫn chạy hết.

        "Chạy hết" ở đây đo bằng việc issue vẫn sang được `Resolved` — bước cuối
        cùng của `_execute_approved()`, nằm SAU chỗ gắn nhãn.
        """
        from scripts.run_agent import _execute_approved

        jira = FakeJiraClient(verbose=False)
        jira_key = _war_room(jira)
        jira.approve_as_human(jira_key)

        def hong(_jira_key: str, _label: str) -> None:
            raise RuntimeError("Jira 429 Too Many Requests")

        jira.add_label = hong  # type: ignore[method-assign]

        _execute_approved(jira, jira_key, FakeJiraClient.HUMAN_ACCOUNT_ID)

        assert jira.get_incident(jira_key).state is IncidentState.RESOLVED


# ---------------------------------------------------------------------------
# Đường 3: Agent tự thi hành
# ---------------------------------------------------------------------------


class TestAgentTuThiHanh:
    """`execute_auto_remediation()` và `execute_fallback_rollback()`."""

    def test_auto_fix_gan_nhan_agent(self):
        """Hết thời chờ, Agent tự thi hành → nhãn AGENT, không nhãn NGƯỜI."""
        jira = FakeJiraClient(verbose=False)
        jira_key = _war_room(jira)

        execute_auto_remediation(jira, _quyet_dinh_auto(jira_key))

        nhan = jira.get_labels(jira_key)
        assert FIXED_BY_AGENT_LABEL in nhan
        assert FIXED_BY_HUMAN_LABEL not in nhan
        assert fixed_by_from_labels(nhan) == FIXED_BY_AGENT_LABEL

    def test_rollback_du_phong_van_la_nhan_agent(self):
        """Rollback dự phòng KHÔNG có nhãn riêng — nó vẫn là Agent tự quyết.

        Chi tiết "lần thi hành đầu hay lần lùi lại" đã phân biệt được bằng
        `FALLBACK_MARKER` trong comment; nhãn thứ ba chỉ chia nhỏ mẫu đếm.
        """
        jira = FakeJiraClient(verbose=False)
        jira_key = _war_room(jira, action="restart")

        ket_qua = execute_fallback_rollback(jira, _quyet_dinh_du_phong(jira_key))

        assert ket_qua is not None
        assert fixed_by_from_labels(jira.get_labels(jira_key)) == FIXED_BY_AGENT_LABEL

    def test_khong_xac_dinh_duoc_phien_ban_thi_khong_gan_nhan(self):
        """`to_version=None` → không thi hành gì cả, nên cũng không có nhãn."""
        jira = FakeJiraClient(verbose=False)
        jira_key = _war_room(jira, action="restart")
        quyet_dinh = FallbackRollbackDecision(
            jira_key=jira_key,
            target=SERVICE,
            to_version=None,
            attempted_action="restart",
            con_lai=None,
        )

        assert execute_fallback_rollback(jira, quyet_dinh) is None
        assert fixed_by_from_labels(jira.get_labels(jira_key)) is None

    @pytest.mark.parametrize(
        "thi_hanh",
        [execute_auto_remediation, execute_fallback_rollback],
    )
    def test_thi_hanh_that_bai_thi_khong_gan_nhan(self, thi_hanh):
        """`succeeded=False` → không nhãn nào, ở cả hai hàm."""
        jira = FakeJiraClient(verbose=False)
        jira_key = _war_room(jira)
        quyet_dinh = (
            _quyet_dinh_auto(jira_key)
            if thi_hanh is execute_auto_remediation
            else _quyet_dinh_du_phong(jira_key)
        )

        with patch("src.services.auto_remediation.execute", return_value=_that_bai()):
            thi_hanh(jira, quyet_dinh)

        assert fixed_by_from_labels(jira.get_labels(jira_key)) is None

    def test_loi_jira_luc_gan_nhan_khong_pha_luong(self):
        """Nuốt lỗi y như `add_comment()` và `transition()` trong cùng file.

        "Chạy hết" đo bằng việc issue vẫn sang `Remediating` và comment vẫn được
        post — hai bước nằm SAU chỗ gắn nhãn.
        """
        jira = FakeJiraClient(verbose=False)
        jira_key = _war_room(jira)

        def hong(_jira_key: str, _label: str) -> None:
            raise RuntimeError("Jira 429 Too Many Requests")

        jira.add_label = hong  # type: ignore[method-assign]

        ket_qua = execute_auto_remediation(jira, _quyet_dinh_auto(jira_key))

        assert ket_qua.succeeded is True
        assert jira.get_incident(jira_key).state is IncidentState.REMEDIATING
        assert jira.get_comment_bodies(jira_key)


# ---------------------------------------------------------------------------
# Ba đường cộng lại
# ---------------------------------------------------------------------------


def test_hai_nhom_khong_giao_nhau():
    """Mỗi issue mang đúng một nhãn — đó là điều kiện để hai câu JQL cộng lại đúng.

    Không có test này thì hai nhóm vẫn "đếm được", chỉ là tổng của chúng lớn hơn
    số sự cố thật, và không ai phát hiện cho tới lúc đối chiếu báo cáo.
    """
    from scripts.run_agent import _execute_approved

    jira = FakeJiraClient(verbose=False)

    key_nguoi = _war_room(jira)
    jira.approve_as_human(key_nguoi)
    _execute_approved(jira, key_nguoi, FakeJiraClient.HUMAN_ACCOUNT_ID)

    key_agent = _war_room(jira)
    execute_auto_remediation(jira, _quyet_dinh_auto(key_agent))

    key_cho = _war_room(jira)  # chưa ai xử lý

    dem = {
        FIXED_BY_HUMAN_LABEL: 0,
        FIXED_BY_AGENT_LABEL: 0,
        None: 0,
    }
    for key in (key_nguoi, key_agent, key_cho):
        dem[fixed_by_from_labels(jira.get_labels(key))] += 1

    assert dem == {FIXED_BY_HUMAN_LABEL: 1, FIXED_BY_AGENT_LABEL: 1, None: 1}


def test_nhan_khong_phu_thuoc_thoi_diem_gan():
    """Gắn nhãn không đụng tới nhãn mức độ, kể cả khi `escalate` nâng mức sau đó.

    `escalate` chạy mỗi vòng quét và ghi đè `labels` qua `set_severity()`. Nếu
    hai đường ghi nhãn giẫm chân nhau thì nhãn `fixed-by-*` biến mất lặng lẽ —
    đúng kiểu lỗi chỉ lộ ra khi đối chiếu số liệu cuối kỳ.
    """
    jira = FakeJiraClient(verbose=False)
    jira_key = _war_room(jira)
    execute_auto_remediation(jira, _quyet_dinh_auto(jira_key))

    jira.set_severity(jira_key, Severity.P1)

    nhan = jira.get_labels(jira_key)
    assert fixed_by_from_labels(nhan) == FIXED_BY_AGENT_LABEL
    assert "severity-P1" in nhan
    assert "severity-P2" not in nhan


def test_thoi_gian_khong_lien_quan_toi_nhan():
    """Nhãn đến từ `approved_by` tại chỗ thi hành, không phải từ suy đoán sau đó.

    Chốt bằng cách dựng một issue "cũ" rồi thi hành: kết quả không đổi. Nếu có
    ngày ai đó thay lời gọi tất định này bằng một bước đoán (đọc comment, hỏi
    LLM, so mốc thời gian) thì test này là chỗ đầu tiên đỏ lên.
    """
    jira = FakeJiraClient(verbose=False)
    jira_key = _war_room(jira)
    jira._transition_times[(jira_key, IncidentState.AWAITING_APPROVAL)] = datetime.now(
        UTC
    ) - timedelta(days=3)

    execute_auto_remediation(jira, _quyet_dinh_auto(jira_key))

    assert fixed_by_from_labels(jira.get_labels(jira_key)) == FIXED_BY_AGENT_LABEL
