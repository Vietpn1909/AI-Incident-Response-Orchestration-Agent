"""Tests cho `src/services/auto_remediation.py` — auto-fix khi HITL timeout.

Không gọi mạng, không cần key: dùng `FakeJiraClient` và monkeypatch config.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from src.agents.nodes.verify import VerifyResult
from src.models.incident import (
    DeployRecord,
    IncidentSignal,
    IncidentState,
    RemediationProposal,
    Severity,
)
from src.services.auto_remediation import (
    AUTO_APPROVED_BY,
    AUTO_MARKER,
    FALLBACK_MARKER,
    NGUONG_CHO_DO_LAI_PHUT,
    AutoFixRecord,
    AutoRemediationPolicy,
    execute_auto_remediation,
    execute_fallback_rollback,
    should_auto_remediate,
    should_fallback_rollback,
)
from src.services.jira import FakeJiraClient


@pytest.fixture(autouse=True)
def khong_thi_hanh_that(monkeypatch: pytest.MonkeyPatch):
    """Chặn mọi test trong file này chạm vào Docker thật.

    `remediation.execute()` gọi `executors.thi_hanh_that()`, và cặp
    `("rollback", "service-thanh-toan")` — đúng cặp các test rollback dưới đây
    dùng — NẰM TRONG danh sách trắng của `executors`. Máy nào đang export
    `REMEDIATION_REAL=1` để chạy demo UC-4 thì chạy pytest sẽ khởi động lại
    container thật.

    `conftest.py` không chặn giúp: nó chỉ xoá các biến đọc qua `Settings`, còn
    biến này `executors` đọc thẳng từ `os.environ`.
    """
    monkeypatch.setenv("REMEDIATION_REAL", "")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

#: Mốc dựng lịch sử deploy giả. Cố định (không phải `now()`) để thứ tự các bản
#: deploy không phụ thuộc lúc chạy test.
_LUC_DEPLOY = datetime(2026, 8, 18, 3, 0, tzinfo=UTC)


def _lich_su(service: str = "service-thanh-toan") -> list[DeployRecord]:
    """Lịch sử deploy **mới nhất trước**, y như `deploys.recent_deploys()` trả.

    `v1.4.3` là bản đang chạy tức nghi phạm, nên đích rollback đúng là `v1.4.2`.
    """
    return [
        DeployRecord(service=service, version="v1.4.3", deployed_at=_LUC_DEPLOY),
        DeployRecord(
            service=service, version="v1.4.2", deployed_at=_LUC_DEPLOY - timedelta(hours=1)
        ),
        DeployRecord(
            service=service, version="v1.4.1", deployed_at=_LUC_DEPLOY - timedelta(hours=2)
        ),
    ]


def _patch_deploys(history: list[DeployRecord]):
    """Patch `recent_deploys()` — pytest chạy không có Postgres.

    BẮT BUỘC với mọi test đi vào nhánh rollback. Không patch thì
    `recent_deploys()` nuốt lỗi kết nối và trả `[]`, nhánh đọc lịch sử deploy
    không bao giờ chạy, và test "tự rollback" xanh mà chẳng nghiệm thu gì —
    đúng lỗi mà `test_tu_rollback_p1`/`p2` mắc phải cho tới 18/08.
    """
    return patch("src.services.deploys.recent_deploys", return_value=history)


def _tin_hieu_con_lai(service: str = "service-thanh-toan") -> IncidentSignal:
    """Tín hiệu `verify()` còn đo được khi sự cố chưa đỡ."""
    return IncidentSignal(
        metric_name="tỷ lệ request lỗi",
        metric_value=0.97,
        threshold=0.10,
        affected_service=service,
        severity=Severity.P2,
        breached_for_seconds=300,
        detected_at=datetime.now(UTC),
    )


def _ket_qua_verify(
    *, hoi_phuc: bool = False, te_hon: bool = False, service: str = "service-thanh-toan"
) -> VerifyResult:
    """Dựng `VerifyResult` như node `verify` trả về."""
    return VerifyResult(
        hoi_phuc=hoi_phuc,
        con_lai=None if hoi_phuc else _tin_hieu_con_lai(service),
        te_hon=te_hon,
        ket_luan="(kết luận verify)",
    )


def _auto_fix(
    *,
    jira_key: str = "INC-1",
    action: str = "restart",
    target: str = "service-thanh-toan",
    phut_truoc: float = NGUONG_CHO_DO_LAI_PHUT + 1,
) -> AutoFixRecord:
    """Dấu vết một lần Agent tự thi hành, mặc định là đã đủ thời gian đo lại."""
    return AutoFixRecord(
        jira_key=jira_key,
        action=action,
        target=target,
        at=datetime.now(UTC) - timedelta(minutes=phut_truoc),
    )


def _setup_incident(
    jira: FakeJiraClient,
    severity: Severity = Severity.P3,
    action: str = "restart",
    target: str = "service-thanh-toan",
    awaiting_minutes_ago: int = 40,
) -> str:
    """Tạo một incident đã đề xuất và đang chờ duyệt."""
    from src.models.incident import IncidentSignal

    signal = IncidentSignal(
        metric_name="http_request_duration_seconds p95",
        metric_value=5.0,
        threshold=2.0,
        affected_service=target,
        severity=severity,
        breached_for_seconds=120,
        detected_at=datetime.now(UTC),
    )
    jira_key = jira.create_incident(signal)

    proposal = RemediationProposal(
        action=action,
        target=target,
        params={"to_version": "v1.4.1"} if action == "rollback" else {},
        risk="rủi ro test",
    )
    jira.post_proposal(jira_key, proposal)

    # Giả lập thời điểm chuyển sang Awaiting Approval — lùi về quá khứ.
    luc_chuyen = datetime.now(UTC) - timedelta(minutes=awaiting_minutes_ago)
    jira._transition_times[(jira_key, IncidentState.AWAITING_APPROVAL)] = luc_chuyen

    return jira_key


def _policy_bat(**overrides):
    """Patch config settings để bật auto-remediation."""
    defaults = {
        "auto_remediation_enabled": True,
        "auto_remediation_timeout_minutes": 30,
    }
    defaults.update(overrides)

    class FakeSettings:
        def __getattr__(self, name):
            return defaults.get(name, "")

    return patch(
        "src.services.auto_remediation.get_settings",
        return_value=FakeSettings(),
    )


def _policy_tat():
    """Patch config settings để tắt auto-remediation."""
    return _policy_bat(auto_remediation_enabled=False)


# ---------------------------------------------------------------------------
# Tests: should_auto_remediate()
# ---------------------------------------------------------------------------


class TestShouldAutoRemediate:
    """Quyết định có nên auto-fix không."""

    def test_khong_tu_sua_khi_tat(self):
        """Feature tắt → trả None."""
        jira = FakeJiraClient(verbose=False)
        jira_key = _setup_incident(jira, awaiting_minutes_ago=60)

        with _policy_tat():
            result = should_auto_remediate(
                jira, jira_key,
                severity=Severity.P3,
                proposal_action="restart",
                proposal_target="service-thanh-toan",
            )
        assert result is None

    def test_khong_tu_sua_khi_chua_du_30_phut(self):
        """Mới chờ 10 phút → chưa timeout."""
        jira = FakeJiraClient(verbose=False)
        jira_key = _setup_incident(jira, awaiting_minutes_ago=10)

        with _policy_bat():
            result = should_auto_remediate(
                jira, jira_key,
                severity=Severity.P3,
                proposal_action="restart",
                proposal_target="service-thanh-toan",
            )
        assert result is None

    def test_tu_sua_p3_dung_de_xuat(self):
        """P3 + 40 phút → dùng action đã đề xuất (restart)."""
        jira = FakeJiraClient(verbose=False)
        jira_key = _setup_incident(
            jira, severity=Severity.P3, action="restart",
            awaiting_minutes_ago=40,
        )

        with _policy_bat():
            result = should_auto_remediate(
                jira, jira_key,
                severity=Severity.P3,
                proposal_action="restart",
                proposal_target="service-thanh-toan",
            )
        assert result is not None
        assert result.action == "restart"
        assert result.forced_rollback is False

    def test_tu_sua_p4_dung_de_xuat(self):
        """P4 + 35 phút → dùng action đã đề xuất."""
        jira = FakeJiraClient(verbose=False)
        jira_key = _setup_incident(
            jira, severity=Severity.P4, action="increase_pool",
            awaiting_minutes_ago=35,
        )

        with _policy_bat():
            result = should_auto_remediate(
                jira, jira_key,
                severity=Severity.P4,
                proposal_action="increase_pool",
                proposal_target="service-thanh-toan",
            )
        assert result is not None
        assert result.action == "increase_pool"
        assert result.forced_rollback is False

    def test_tu_rollback_p1(self):
        """P1 + 40 phút → ép rollback về ĐÚNG phiên bản ngay trước bản đang chạy.

        Patch `recent_deploys` là phần quan trọng nhất của test này: trước 18/08
        nó không patch, nên khi chạy pytest (không có Postgres) hàm kia trả `[]`
        và nhánh đọc lịch sử — chỗ chứa cả hai lỗi `.get()` trên pydantic model
        lẫn việc lấy nhầm bản mới nhất — không bao giờ được chạy.
        """
        jira = FakeJiraClient(verbose=False)
        jira_key = _setup_incident(
            jira, severity=Severity.P1, action="scale_up",
            awaiting_minutes_ago=40,
        )

        with _policy_bat(), _patch_deploys(_lich_su()):
            result = should_auto_remediate(
                jira, jira_key,
                severity=Severity.P1,
                proposal_action="scale_up",
                proposal_target="service-thanh-toan",
            )
        assert result is not None
        assert result.action == "rollback"
        assert result.forced_rollback is True
        # v1.4.3 là bản ĐANG CHẠY (nghi phạm), lùi về nó là không lùi gì cả.
        assert result.params["to_version"] == "v1.4.2"

    def test_tu_rollback_p2(self):
        """P2 + 45 phút → ép rollback, cùng phép chọn phiên bản với P1."""
        jira = FakeJiraClient(verbose=False)
        jira_key = _setup_incident(
            jira, severity=Severity.P2, action="restart",
            awaiting_minutes_ago=45,
        )

        with _policy_bat(), _patch_deploys(_lich_su()):
            result = should_auto_remediate(
                jira, jira_key,
                severity=Severity.P2,
                proposal_action="restart",
                proposal_target="service-thanh-toan",
            )
        assert result is not None
        assert result.action == "rollback"
        assert result.forced_rollback is True
        assert result.params["to_version"] == "v1.4.2"

    def test_tu_rollback_dung_de_xuat_goc_khi_de_xuat_von_da_la_rollback(self):
        """Đề xuất gốc đã là rollback thì tin `to_version` của nó.

        `runbooks` tính giá trị đó từ **nghi phạm thật** — bản deploy trùng thời
        gian với lúc sự cố bắt đầu — chứ không phải từ bản mới nhất. Đó là thông
        tin nhiều hơn thứ `resolve_rollback_version()` tự suy ra được, nên khi có
        thì dùng: ở đây `v1.4.1` chứ không phải `v1.4.2`.
        """
        jira = FakeJiraClient(verbose=False)
        jira_key = _setup_incident(
            jira, severity=Severity.P1, action="rollback",
            awaiting_minutes_ago=40,
        )

        with _policy_bat(), _patch_deploys(_lich_su()):
            result = should_auto_remediate(
                jira, jira_key,
                severity=Severity.P1,
                proposal_action="rollback",
                proposal_target="service-thanh-toan",
                proposal_params={"to_version": "v1.4.1"},
            )
        assert result is not None
        assert result.params["to_version"] == "v1.4.1"

    def test_khong_co_lich_su_deploy_thi_khong_ra_quyet_dinh_rollback(self):
        """Không biết lùi về đâu → `None`, KHÔNG phải rollback "phiên bản trước".

        Chuỗi "phiên bản trước" đi thẳng vào comment Jira và vào `params` của
        lệnh thi hành. Một mệnh lệnh rollback không nói rõ về đâu thì không thi
        hành được và cũng không kiểm chứng được — thà không quyết định.
        """
        jira = FakeJiraClient(verbose=False)
        jira_key = _setup_incident(
            jira, severity=Severity.P1, action="scale_up",
            awaiting_minutes_ago=40,
        )

        with _policy_bat(), _patch_deploys([]):
            result = should_auto_remediate(
                jira, jira_key,
                severity=Severity.P1,
                proposal_action="scale_up",
                proposal_target="service-thanh-toan",
            )
        assert result is None

    def test_tra_lich_su_dung_service_sap_bi_rollback(self):
        """Lịch sử deploy và đích thi hành phải là CÙNG một service.

        `deploy_service` (service đang có sự cố) và `proposal_target` có thể
        khác nhau. Tra lịch sử của cái này rồi gửi lệnh tới cái kia là hạ một
        service về phiên bản chưa từng tồn tại của nó.
        """
        jira = FakeJiraClient(verbose=False)
        jira_key = _setup_incident(
            jira, severity=Severity.P1, action="scale_up",
            awaiting_minutes_ago=40,
        )

        with _policy_bat(), _patch_deploys(_lich_su("service-kho-hang")) as doc_lich_su:
            result = should_auto_remediate(
                jira, jira_key,
                severity=Severity.P1,
                proposal_action="scale_up",
                proposal_target="service-thanh-toan",
                deploy_service="service-kho-hang",
            )
        assert result is not None
        assert result.target == "service-kho-hang"
        doc_lich_su.assert_called_once_with("service-kho-hang")

    def test_de_xuat_rollback_cua_service_khac_thi_khong_tin(self):
        """`to_version` của đề xuất chỉ dùng được khi đề xuất nói về đúng service.

        Cùng lý do với test trên, chỉ khác là giá trị sai đến từ đề xuất chứ
        không từ lịch sử deploy.
        """
        jira = FakeJiraClient(verbose=False)
        jira_key = _setup_incident(
            jira, severity=Severity.P1, action="rollback",
            awaiting_minutes_ago=40,
        )

        with _policy_bat(), _patch_deploys(_lich_su("service-kho-hang")):
            result = should_auto_remediate(
                jira, jira_key,
                severity=Severity.P1,
                proposal_action="rollback",
                proposal_target="service-thanh-toan",
                proposal_params={"to_version": "v9.9.9"},
                deploy_service="service-kho-hang",
            )
        assert result is not None
        assert result.target == "service-kho-hang"
        assert result.params["to_version"] == "v1.4.2"

    def test_khong_tu_sua_khi_da_co_nguoi_phan_hoi(self):
        """Issue đã được chuyển sang Remediating bởi human → không auto."""
        jira = FakeJiraClient(verbose=False)
        jira_key = _setup_incident(jira, awaiting_minutes_ago=60)
        # Mô phỏng human đã duyệt
        jira.approve_as_human(jira_key)

        with _policy_bat():
            result = should_auto_remediate(
                jira, jira_key,
                severity=Severity.P3,
                proposal_action="restart",
                proposal_target="service-thanh-toan",
            )
        assert result is None

    def test_timeout_tuy_chinh(self):
        """Timeout 60 phút → 40 phút chưa đủ, 65 phút đủ."""
        jira = FakeJiraClient(verbose=False)
        key_40 = _setup_incident(jira, awaiting_minutes_ago=40)
        key_65 = _setup_incident(jira, awaiting_minutes_ago=65)

        with _policy_bat(auto_remediation_timeout_minutes=60):
            result_40 = should_auto_remediate(
                jira, key_40,
                severity=Severity.P3,
                proposal_action="restart",
                proposal_target="service-thanh-toan",
            )
            result_65 = should_auto_remediate(
                jira, key_65,
                severity=Severity.P3,
                proposal_action="restart",
                proposal_target="service-thanh-toan",
            )
        assert result_40 is None
        assert result_65 is not None


# ---------------------------------------------------------------------------
# Tests: execute_auto_remediation()
# ---------------------------------------------------------------------------


class TestExecuteAutoRemediation:
    """Thi hành auto-fix và ghi comment."""

    def test_comment_ghi_ro_ly_do(self):
        """Comment trên Jira phải chứa marker AUTO_MARKER."""
        from src.services.auto_remediation import AutoRemediationDecision

        jira = FakeJiraClient(verbose=False)
        jira_key = _setup_incident(jira)

        decision = AutoRemediationDecision(
            jira_key=jira_key,
            action="restart",
            target="service-thanh-toan",
            params={},
            reason="Sự cố P3 đã chờ 40 phút mà không có phản hồi.",
            forced_rollback=False,
        )

        result = execute_auto_remediation(jira, decision)

        assert result.succeeded is True
        # Kiểm tra comment có marker
        comments = jira.get_comment_bodies(jira_key)
        assert any(AUTO_MARKER in c for c in comments), (
            f"Comment phải chứa '{AUTO_MARKER}'. Các comment: {comments}"
        )

    def test_approved_by_la_auto_timeout(self):
        """approved_by phải là AUTO_APPROVED_BY, không phải human."""
        from src.services.auto_remediation import AutoRemediationDecision

        jira = FakeJiraClient(verbose=False)
        jira_key = _setup_incident(jira)

        decision = AutoRemediationDecision(
            jira_key=jira_key,
            action="restart",
            target="service-thanh-toan",
            params={},
            reason="test",
            forced_rollback=False,
        )

        result = execute_auto_remediation(jira, decision)

        assert result.approved_by == AUTO_APPROVED_BY
        assert result.approved_by != FakeJiraClient.HUMAN_ACCOUNT_ID

    def test_chuyen_sang_remediating(self):
        """Sau auto-fix, issue phải ở trạng thái Remediating."""
        from src.services.auto_remediation import AutoRemediationDecision

        jira = FakeJiraClient(verbose=False)
        jira_key = _setup_incident(jira)

        decision = AutoRemediationDecision(
            jira_key=jira_key,
            action="restart",
            target="service-thanh-toan",
            params={},
            reason="test",
            forced_rollback=False,
        )

        execute_auto_remediation(jira, decision)

        incident = jira.get_incident(jira_key)
        assert incident is not None
        # Auto-fix THÀNH CÔNG phải khép vòng: chuyển thẳng Resolved, KHÔNG dừng ở
        # Remediating. Dừng ở Remediating vừa bỏ dở vừa kích hoạt cổng HITL rồi
        # bị chính nó từ chối — xem `_sinh_postmortem_va_dong`.
        assert incident.state == IncidentState.RESOLVED


# ---------------------------------------------------------------------------
# Tests: AutoRemediationPolicy
# ---------------------------------------------------------------------------


class TestPolicy:
    """Đọc config đúng."""

    def test_mac_dinh_tat(self):
        """Mặc định feature tắt."""
        with _policy_tat():
            policy = AutoRemediationPolicy.from_settings()
        assert policy.enabled is False

    def test_bat_va_doc_timeout(self):
        """Bật feature và đọc đúng timeout."""
        with _policy_bat(auto_remediation_timeout_minutes=45):
            policy = AutoRemediationPolicy.from_settings()
        assert policy.enabled is True
        assert policy.timeout_minutes == 45


# ---------------------------------------------------------------------------
# Tests: should_fallback_rollback() — vế 3, rollback dự phòng
# ---------------------------------------------------------------------------


class TestShouldFallbackRollback:
    """Auto-fix xong mà đo lại vẫn chưa đỡ thì có rollback không."""

    def test_chua_du_thoi_gian_cho_thi_khong_rollback(self):
        """Mới thi hành 1 phút → chưa được kết luận là "không ăn".

        Cửa sổ PromQL `[1m]` còn nguyên phần dữ liệu lúc đang hỏng, nên đo ngay
        gần như luôn ra "chưa đỡ" — rollback lúc này là lùi đúng một hành động
        đang có tác dụng.
        """
        with _patch_deploys(_lich_su()):
            quyet_dinh = should_fallback_rollback(
                _auto_fix(phut_truoc=1),
                hoi_phuc=False,
                te_hon=False,
                con_lai=_tin_hieu_con_lai(),
            )
        assert quyet_dinh is None

    def test_du_dieu_kien_va_chua_do_thi_rollback_dung_phien_ban(self):
        """Đủ thời gian chờ + đo lại CHƯA ĐỠ → rollback về v1.4.2."""
        with _patch_deploys(_lich_su()):
            quyet_dinh = should_fallback_rollback(
                _auto_fix(action="restart"),
                hoi_phuc=False,
                te_hon=False,
                con_lai=_tin_hieu_con_lai(),
            )
        assert quyet_dinh is not None
        assert quyet_dinh.to_version == "v1.4.2"
        assert quyet_dinh.target == "service-thanh-toan"
        assert quyet_dinh.attempted_action == "restart"

    def test_te_hon_thi_tuyet_doi_khong_rollback(self):
        """Đo lại TỆ HƠN → dừng tay.

        `verify.py` vừa ghi lên war room: "Đừng thi hành thêm hành động nào cho
        tới khi có người xem". Rollback ngay sau câu đó là Agent tự mâu thuẫn
        với lời nó vừa nói.
        """
        with _patch_deploys(_lich_su()):
            quyet_dinh = should_fallback_rollback(
                _auto_fix(),
                hoi_phuc=False,
                te_hon=True,
                con_lai=_tin_hieu_con_lai(),
            )
        assert quyet_dinh is None

    def test_da_hoi_phuc_thi_khong_rollback(self):
        """Auto-fix ăn rồi → không được lùi lại thứ vừa cứu hệ thống."""
        with _patch_deploys(_lich_su()):
            quyet_dinh = should_fallback_rollback(
                _auto_fix(),
                hoi_phuc=True,
                te_hon=False,
                con_lai=None,
            )
        assert quyet_dinh is None

    def test_issue_do_nguoi_duyet_thi_khong_rollback(self):
        """Không có dấu vết auto-fix → hành động là của người duyệt.

        Agent chỉ tự dọn phần chính nó tự quyết. Người duyệt chọn hành động thì
        người đó theo tới cùng — tự lùi giúp là lấy mất quyền quyết định, đúng
        thứ cổng HITL sinh ra để bảo vệ.
        """
        with _patch_deploys(_lich_su()):
            quyet_dinh = should_fallback_rollback(
                None,
                hoi_phuc=False,
                te_hon=False,
                con_lai=_tin_hieu_con_lai(),
            )
        assert quyet_dinh is None

    def test_auto_fix_von_da_la_rollback_thi_khong_rollback_lan_hai(self):
        """P1/P2 đã bị ép rollback ở vế 1 → không lùi thêm một phiên bản nữa."""
        with _patch_deploys(_lich_su()):
            quyet_dinh = should_fallback_rollback(
                _auto_fix(action="rollback"),
                hoi_phuc=False,
                te_hon=False,
                con_lai=_tin_hieu_con_lai(),
            )
        assert quyet_dinh is None

    def test_da_rollback_du_phong_roi_thi_thoi(self):
        """Mỗi issue đúng MỘT lần — không lặp vòng này qua vòng khác."""
        with _patch_deploys(_lich_su()):
            quyet_dinh = should_fallback_rollback(
                _auto_fix(),
                hoi_phuc=False,
                te_hon=False,
                con_lai=_tin_hieu_con_lai(),
                da_rollback_du_phong=True,
            )
        assert quyet_dinh is None

    def test_khong_co_lich_su_thi_van_quyet_dinh_nhung_khong_co_phien_ban(self):
        """Không tra được phiên bản → vẫn trả quyết định, `to_version=None`.

        "Có nên rollback" và "rollback về đâu" là hai câu hỏi khác nhau. Câu đầu
        đã trả lời là CÓ, nên người trực phải được biết — họ là người duy nhất
        tra lịch sử deploy bằng tay được lúc 3 giờ sáng.
        """
        with _patch_deploys([]):
            quyet_dinh = should_fallback_rollback(
                _auto_fix(),
                hoi_phuc=False,
                te_hon=False,
                con_lai=_tin_hieu_con_lai(),
            )
        assert quyet_dinh is not None
        assert quyet_dinh.to_version is None


# ---------------------------------------------------------------------------
# Tests: execute_fallback_rollback()
# ---------------------------------------------------------------------------


class TestExecuteFallbackRollback:
    """Thi hành rollback dự phòng và ghi comment."""

    def _quyet_dinh(self, jira_key: str, to_version: str | None):
        from src.services.auto_remediation import FallbackRollbackDecision

        return FallbackRollbackDecision(
            jira_key=jira_key,
            target="service-thanh-toan",
            to_version=to_version,
            attempted_action="restart",
            con_lai=_tin_hieu_con_lai(),
        )

    def test_comment_phan_biet_duoc_voi_auto_fix_lan_dau(self):
        """Comment phải nêu: đã thử gì, đo lại ra sao, lùi về phiên bản nào.

        Ba đường đi tới production (người duyệt, Agent tự thi hành, Agent lùi
        lại) dẫn tới ba kết luận khác nhau khi viết postmortem, nên đọc Jira
        phải phân biệt được.
        """
        jira = FakeJiraClient(verbose=False)
        jira_key = _setup_incident(jira)

        ket_qua = execute_fallback_rollback(jira, self._quyet_dinh(jira_key, "v1.4.2"))

        assert ket_qua is not None
        assert ket_qua.succeeded is True
        assert ket_qua.approved_by == AUTO_APPROVED_BY
        comment = "\n".join(jira.get_comment_bodies(jira_key))
        assert FALLBACK_MARKER in comment
        assert AUTO_MARKER not in comment  # khác hẳn comment auto-fix lần đầu
        assert "restart" in comment  # hành động đã thử
        assert "0.97" in comment  # chỉ số đo lại
        assert "v1.4.2" in comment  # lùi về đâu

    def test_khong_co_phien_ban_thi_chi_comment_giai_thich(self):
        """`to_version=None` → không thi hành gì, nhưng phải nói vì sao."""
        jira = FakeJiraClient(verbose=False)
        jira_key = _setup_incident(jira)

        ket_qua = execute_fallback_rollback(jira, self._quyet_dinh(jira_key, None))

        assert ket_qua is None
        comment = "\n".join(jira.get_comment_bodies(jira_key))
        assert FALLBACK_MARKER in comment
        assert "không xác định được phiên bản" in comment.lower()


# ---------------------------------------------------------------------------
# Tests: tích hợp trong `scripts/run_agent.py`
#
# Đặt trong file này vì chúng nghiệm thu cùng một tính năng, và `run_agent.py`
# chỉ là chỗ nối dây — không có test riêng cho nó.
# ---------------------------------------------------------------------------


def _incident_da_thi_hanh(jira: FakeJiraClient) -> str:
    """Một issue Agent đã tự thi hành xong, đang chờ đo lại."""
    jira_key = _setup_incident(jira, severity=Severity.P3, action="restart")
    jira.transition(jira_key, IncidentState.REMEDIATING)
    return jira_key


class TestNoiVaoRunAgent:
    """`_kiem_tra_auto_remediation()` và `_verify_da_thi_hanh()`."""

    def test_loi_khi_xet_auto_remediation_khong_giet_ca_tien_trinh(self):
        """`should_auto_remediate()` ném lỗi → nuốt, đi tiếp issue khác.

        Hàm đó đi hỏi changelog Jira và đọc `deploy_history` — hai đường ra
        ngoài. `main()` chỉ bắt `KeyboardInterrupt`, nên một exception lọt tới
        đây là giết cả tiến trình Agent giữa lúc đang có sự cố. Cùng lập luận
        với `_xet_nang_muc()` trong `incident_graph.py`.
        """
        from scripts.run_agent import _kiem_tra_auto_remediation

        jira = FakeJiraClient(verbose=False)
        key_loi = _setup_incident(jira)
        key_lanh = _setup_incident(jira)
        awaiting = {key_loi, key_lanh}
        da_thi_hanh: set[str] = set()

        def hong(_jira, jira_key, **_kwargs):
            if jira_key == key_loi:
                raise RuntimeError("Jira 429 Too Many Requests")
            return None

        with patch("scripts.run_agent.should_auto_remediate", side_effect=hong) as xet:
            _kiem_tra_auto_remediation(jira, awaiting, da_thi_hanh)

        # Không ném ra ngoài, và issue lành trong cùng vòng vẫn được xét.
        assert xet.call_count == 2
        # Issue lỗi không bị đánh dấu đã thi hành — vòng sau còn thử lại.
        assert da_thi_hanh == set()
        assert awaiting == {key_loi, key_lanh}

    def test_chua_du_thoi_gian_cho_thi_chua_do_lai(self):
        """Issue mới auto-fix → chưa đo, chưa kết luận, chưa rollback.

        Bỏ qua chứ không kết luận: `da_verify` để trống nên vòng sau xét lại.
        """
        from scripts.run_agent import _verify_da_thi_hanh

        jira = FakeJiraClient(verbose=False)
        jira_key = _incident_da_thi_hanh(jira)
        da_verify: set[str] = set()
        da_rollback: set[str] = set()
        auto = {jira_key: _auto_fix(jira_key=jira_key, phut_truoc=1)}

        with patch("scripts.run_agent.verify") as do_lai, _patch_deploys(_lich_su()):
            _verify_da_thi_hanh(None, jira, {jira_key}, da_verify, auto, da_rollback)

        do_lai.assert_not_called()
        assert da_verify == set()
        assert da_rollback == set()

    def test_chua_do_thi_rollback_va_do_lai_dung_mot_lan_nua(self):
        """Đủ điều kiện → rollback, rồi cho `verify()` chạy lại đúng một lần."""
        from scripts.run_agent import _verify_da_thi_hanh

        jira = FakeJiraClient(verbose=False)
        jira_key = _incident_da_thi_hanh(jira)
        da_verify: set[str] = set()
        da_rollback: set[str] = set()
        auto = {jira_key: _auto_fix(jira_key=jira_key, action="restart")}

        with patch(
            "scripts.run_agent.verify", return_value=_ket_qua_verify()
        ), _patch_deploys(_lich_su()):
            _verify_da_thi_hanh(None, jira, {jira_key}, da_verify, auto, da_rollback)

        comment = "\n".join(jira.get_comment_bodies(jira_key))
        assert FALLBACK_MARKER in comment
        assert "v1.4.2" in comment
        assert da_rollback == {jira_key}
        # Chưa kết luận xong: còn phải đo lại sau khi rollback.
        assert da_verify == set()
        # Dấu vết được cập nhật thành `rollback` để chính nó chặn lần hai.
        assert auto[jira_key].action == "rollback"

    def test_hai_vong_lien_tiep_chi_rollback_mot_lan(self):
        """Gọi lại ngay vòng sau → không rollback thêm lần nào nữa."""
        from scripts.run_agent import _verify_da_thi_hanh

        jira = FakeJiraClient(verbose=False)
        jira_key = _incident_da_thi_hanh(jira)
        da_verify: set[str] = set()
        da_rollback: set[str] = set()
        auto = {jira_key: _auto_fix(jira_key=jira_key, action="restart")}

        with patch(
            "scripts.run_agent.verify", return_value=_ket_qua_verify()
        ), _patch_deploys(_lich_su()):
            _verify_da_thi_hanh(None, jira, {jira_key}, da_verify, auto, da_rollback)
            # Vòng hai: giả lập đã đủ thời gian đo lại sau rollback, để lần này
            # thật sự đi tới `should_fallback_rollback()` chứ không dừng ở cổng
            # thời gian — tức là kiểm đúng cái chốt "chỉ một lần".
            auto[jira_key] = dataclasses.replace(
                auto[jira_key],
                at=datetime.now(UTC) - timedelta(minutes=NGUONG_CHO_DO_LAI_PHUT + 1),
            )
            _verify_da_thi_hanh(None, jira, {jira_key}, da_verify, auto, da_rollback)

        so_lan = sum(
            1 for c in jira.get_comment_bodies(jira_key) if FALLBACK_MARKER in c
        )
        assert so_lan == 1
        # Vòng hai đã kết luận xong — không đo nữa.
        assert da_verify == {jira_key}

    def test_khong_co_lich_su_thi_khong_rollback_nhung_van_giai_thich(self):
        """Không tra được phiên bản → không thi hành, nhưng comment nói rõ."""
        from scripts.run_agent import _verify_da_thi_hanh

        jira = FakeJiraClient(verbose=False)
        jira_key = _incident_da_thi_hanh(jira)
        da_verify: set[str] = set()
        da_rollback: set[str] = set()
        auto = {jira_key: _auto_fix(jira_key=jira_key, action="restart")}

        with patch(
            "scripts.run_agent.verify", return_value=_ket_qua_verify()
        ), _patch_deploys([]):
            _verify_da_thi_hanh(None, jira, {jira_key}, da_verify, auto, da_rollback)

        comment = "\n".join(jira.get_comment_bodies(jira_key))
        assert FALLBACK_MARKER in comment
        assert "không xác định được phiên bản" in comment.lower()
        # Không có gì đổi trên production → không cần đo lại lần nữa.
        assert da_verify == {jira_key}
        assert da_rollback == {jira_key}

    def test_issue_do_nguoi_duyet_khong_bi_dong_toi(self):
        """Không có dấu vết auto-fix → luồng verify y hệt trước 18/08."""
        from scripts.run_agent import _verify_da_thi_hanh

        jira = FakeJiraClient(verbose=False)
        jira_key = _incident_da_thi_hanh(jira)
        da_verify: set[str] = set()

        with patch(
            "scripts.run_agent.verify", return_value=_ket_qua_verify()
        ), _patch_deploys(_lich_su()):
            _verify_da_thi_hanh(None, jira, {jira_key}, da_verify)

        comment = "\n".join(jira.get_comment_bodies(jira_key))
        assert FALLBACK_MARKER not in comment
        assert da_verify == {jira_key}

    def test_loi_khi_rollback_du_phong_khong_giet_ca_tien_trinh(self):
        """Lỗi ở bước rollback dự phòng → nuốt, issue vẫn được kết luận."""
        from scripts.run_agent import _verify_da_thi_hanh

        jira = FakeJiraClient(verbose=False)
        jira_key = _incident_da_thi_hanh(jira)
        da_verify: set[str] = set()
        da_rollback: set[str] = set()
        auto = {jira_key: _auto_fix(jira_key=jira_key, action="restart")}

        with patch(
            "scripts.run_agent.verify", return_value=_ket_qua_verify()
        ), patch(
            "scripts.run_agent.should_fallback_rollback",
            side_effect=RuntimeError("Postgres timeout"),
        ):
            _verify_da_thi_hanh(None, jira, {jira_key}, da_verify, auto, da_rollback)

        assert da_verify == {jira_key}
        assert da_rollback == set()


# ---------------------------------------------------------------------------
# Tests: B1 regression — escalate KHÔNG phá nhánh P3/P4
# ---------------------------------------------------------------------------


class TestB1EscalationBypass:
    """B1: `escalate` nâng P3→P1 trước phút 30, nhưng auto-remediation phải
    dùng severity GỐC (lúc phát hiện) chứ không phải severity hiện tại.

    Trước fix: `_kiem_tra_auto_remediation` truyền `incident.severity` (đã
    bị escalate) → P3 vào nhánh P1 → ép rollback thay vì dùng đề xuất gốc.

    Sau fix: dùng `incident.signal.severity` — mức Rule Engine ban đầu.
    """

    def test_p3_bi_nang_len_p1_van_dung_de_xuat_goc(self):
        """P3 bị escalate lên P1 → auto-remediation vẫn dùng restart (đề xuất
        gốc), KHÔNG ép rollback."""
        from scripts.run_agent import _kiem_tra_auto_remediation

        jira = FakeJiraClient(verbose=False)
        # Tạo incident P3, đề xuất restart
        jira_key = _setup_incident(
            jira, severity=Severity.P3, action="restart",
            target="service-thanh-toan", awaiting_minutes_ago=40,
        )

        # Giả lập escalate: nâng severity lên P1 (như escalate node làm)
        jira.set_severity(jira_key, Severity.P1)

        # Xác nhận severity hiện tại đã là P1
        incident = jira.get_incident(jira_key)
        assert incident.severity == Severity.P1
        # Nhưng severity gốc vẫn là P3
        assert incident.signal.severity == Severity.P3

        awaiting = {jira_key}
        already_executed: set[str] = set()
        auto_records: dict[str, AutoFixRecord] = {}

        with _policy_bat(), _patch_deploys(_lich_su()):
            _kiem_tra_auto_remediation(
                jira, awaiting, already_executed, auto_records
            )

        # PHẢI đã thi hành
        assert jira_key in already_executed

        # PHẢI dùng hành động gốc (restart), KHÔNG phải rollback
        assert jira_key in auto_records
        record = auto_records[jira_key]
        assert record.action == "restart", (
            f"Mong restart (đề xuất gốc P3) nhưng nhận {record.action} — "
            "nghĩa là severity bị escalate vẫn chi phối quyết định"
        )

    def test_p4_bi_nang_len_p2_van_dung_de_xuat_goc(self):
        """P4 bị escalate lên P2 → vẫn dùng đề xuất gốc, không ép rollback."""
        from scripts.run_agent import _kiem_tra_auto_remediation

        jira = FakeJiraClient(verbose=False)
        jira_key = _setup_incident(
            jira, severity=Severity.P4, action="scale_up",
            target="service-thanh-toan", awaiting_minutes_ago=40,
        )

        # Escalate P4 → P2
        jira.set_severity(jira_key, Severity.P2)

        awaiting = {jira_key}
        already_executed: set[str] = set()
        auto_records: dict[str, AutoFixRecord] = {}

        with _policy_bat(), _patch_deploys(_lich_su()):
            _kiem_tra_auto_remediation(
                jira, awaiting, already_executed, auto_records
            )

        assert jira_key in already_executed
        assert auto_records[jira_key].action == "scale_up"

    def test_p1_thuc_su_van_ep_rollback(self):
        """P1 thật (không phải bị escalate lên) → vẫn ép rollback."""
        from scripts.run_agent import _kiem_tra_auto_remediation

        jira = FakeJiraClient(verbose=False)
        jira_key = _setup_incident(
            jira, severity=Severity.P1, action="restart",
            target="service-thanh-toan", awaiting_minutes_ago=40,
        )

        # Severity gốc = P1, severity hiện tại = P1 (không escalate)
        incident = jira.get_incident(jira_key)
        assert incident.signal.severity == Severity.P1

        awaiting = {jira_key}
        already_executed: set[str] = set()
        auto_records: dict[str, AutoFixRecord] = {}

        with _policy_bat(), _patch_deploys(_lich_su()):
            _kiem_tra_auto_remediation(
                jira, awaiting, already_executed, auto_records
            )

        assert jira_key in already_executed
        assert auto_records[jira_key].action == "rollback"

