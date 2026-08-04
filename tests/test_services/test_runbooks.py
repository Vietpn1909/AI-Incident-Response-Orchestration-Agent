"""Test chọn hành động khắc phục.

Mỗi bộ số ở đây chỉ kích hoạt **đúng một** nhánh runbook, để khi test đỏ thì
biết nhánh nào hỏng — bài học từ `test_detection.py` ngày 02/08, nơi một fixture
kích hoạt hai đường cùng lúc và test xanh vì lý do khác với tên nó ghi.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from src.models.incident import DeployRecord, Hypothesis, IncidentSignal, MetricEvidence, Severity
from src.services import remediation, rules, runbooks

LUC = datetime(2026, 8, 4, 16, 30, tzinfo=UTC)
SERVICE = "service-thanh-toan"

LICH_SU_DEPLOY = [
    DeployRecord(service=SERVICE, version="v1.4.0", deployed_at=LUC - timedelta(days=3)),
    DeployRecord(service=SERVICE, version="v1.4.1", deployed_at=LUC - timedelta(days=1)),
    DeployRecord(service=SERVICE, version="v1.4.2", deployed_at=LUC - timedelta(minutes=4)),
]
NGHI_PHAM = LICH_SU_DEPLOY[2]


def _signal(*evidence: MetricEvidence, metric_name: str = "http_request_duration_seconds p95") -> IncidentSignal:
    return IncidentSignal(
        affected_service=SERVICE,
        severity=Severity.P2,
        detected_at=LUC,
        metric_name=metric_name,
        metric_value=3.3,
        threshold=2.0,
        breached_for_seconds=60.0,
        evidence=list(evidence),
    )


def _hypothesis(deploy: DeployRecord | None = None) -> Hypothesis:
    return Hypothesis(statement="Pool cạn", confidence=0.9, related_deploy=deploy)


BC_POOL_CAN = MetricEvidence(name=runbooks.EVIDENCE_POOL, value=1.0)
BC_POOL_RANH = MetricEvidence(name=runbooks.EVIDENCE_POOL, value=0.3)
BC_UP = MetricEvidence(name=runbooks.EVIDENCE_UP, value=0.0)
BC_AUTH = MetricEvidence(name=runbooks.EVIDENCE_AUTH, value=200.0)


# ─────────────────────────────────── canh chuỗi tên bằng chứng


def test_ten_bang_chung_con_khop_voi_rules():
    """Ba chuỗi nhận diện use case phải khớp thứ `rules.py` thật sự sinh ra.

    `runbooks.py` phân nhánh theo tên bằng chứng, mà tên đó là chuỗi literal
    trong `rules.py` của Việt. Việt sửa một chữ là `runbooks` lặng lẽ không nhận
    ra use case nữa, rồi MỌI sự cố rơi vào nhánh mặc định `scale_up` — sai hành
    động lên production mà không có gì đỏ lên. Nên gọi thẳng `rules` rồi đối
    chiếu, không hardcode kỳ vọng ở hai nơi.
    """
    uc1 = rules.detect(
        p95_now=3.3, p95_baseline=0.7, error_rate=0.0, pool_saturation=1.0,
        service=SERVICE, breached_for_seconds=60.0,
    )
    uc2 = rules.detect_crashloop(service_up=0.0, restarts=7.0, down_for_seconds=60.0, service=SERVICE)
    uc3 = rules.detect_auth_burst(failures_per_second=200.0, breached_for_seconds=60.0, service=SERVICE)

    assert uc1 and uc2 and uc3, "rules không sinh tín hiệu — bộ số trong test này đã lạc hậu"
    assert runbooks.EVIDENCE_POOL in {e.name for e in uc1.evidence}
    assert runbooks.EVIDENCE_UP in {e.name for e in uc2.evidence}
    assert runbooks.EVIDENCE_AUTH in {e.name for e in uc3.evidence}


# ─────────────────────────────────────────────── từng nhánh runbook


def test_uc1_pool_can_va_co_deploy_thi_rollback_ve_ban_truoc_do():
    proposal = runbooks.choose(_signal(BC_POOL_CAN), _hypothesis(NGHI_PHAM), LICH_SU_DEPLOY)

    assert proposal.action == "rollback"
    # v1.4.1 chứ không phải v1.4.0 hay v1.4.2 — đích rollback là bản NGAY TRƯỚC.
    assert proposal.params["to_version"] == "v1.4.1"
    assert proposal.params["from_version"] == "v1.4.2"


def test_uc1_pool_can_khong_co_deploy_thi_noi_pool():
    proposal = runbooks.choose(_signal(BC_POOL_CAN), _hypothesis(None), LICH_SU_DEPLOY)

    assert proposal.action == "increase_pool"
    assert proposal.params["pool_size"] == runbooks.POOL_SIZE_DE_XUAT


def test_uc1_pool_con_ranh_va_khong_deploy_thi_ve_nhanh_mac_dinh():
    proposal = runbooks.choose(_signal(BC_POOL_RANH), _hypothesis(None), LICH_SU_DEPLOY)

    assert proposal.action == "scale_up"
    assert "MẶC ĐỊNH" in proposal.risk


def test_uc2_service_chet_co_deploy_thi_rollback():
    signal = _signal(BC_UP, metric_name="up (service còn sống không)")
    proposal = runbooks.choose(signal, _hypothesis(NGHI_PHAM), LICH_SU_DEPLOY)

    assert proposal.action == "rollback"
    assert proposal.params["to_version"] == "v1.4.1"


def test_uc2_service_chet_khong_deploy_thi_scale_up_va_noi_ro_la_giam_nhe():
    """Không được im lặng đề xuất một phương án không sửa gốc.

    Service chết vì hết RAM thì cách đúng là tăng `mem_limit` hoặc sửa rò rỉ —
    cả hai KHÔNG nằm trong `SUPPORTED_ACTIONS`. Người duyệt phải đọc được điều
    đó trong phần rủi ro, không phải tự đoán.
    """
    signal = _signal(BC_UP, metric_name="up (service còn sống không)")
    proposal = runbooks.choose(signal, _hypothesis(None), LICH_SU_DEPLOY)

    assert proposal.action == "scale_up"
    assert "GIẢM NHẸ" in proposal.risk


def test_uc3_tan_cong_thi_rate_limit_chu_khong_rollback_du_co_deploy():
    """Rollback không chặn được một cuộc tấn công.

    Đây là lý do UC-3 phải xét TRƯỚC nhánh deploy: burst credential-stuffing
    xảy ra đúng lúc vừa deploy thì rollback chỉ mất thời gian và thêm một lần
    đổi phiên bản vô ích giữa lúc đang có sự cố.
    """
    signal = _signal(BC_AUTH, metric_name=runbooks.EVIDENCE_AUTH)
    proposal = runbooks.choose(signal, _hypothesis(NGHI_PHAM), LICH_SU_DEPLOY)

    assert proposal.action == "rate_limit"
    assert proposal.params["scope"] == "/login"


def test_uc3_khong_chon_block_ip_vi_chua_thu_thap_ip():
    """`block_ip` nằm trong SUPPORTED_ACTIONS nhưng Agent chưa có dữ liệu để dùng."""
    signal = _signal(BC_AUTH, metric_name=runbooks.EVIDENCE_AUTH)
    proposal = runbooks.choose(signal, _hypothesis(NGHI_PHAM), LICH_SU_DEPLOY)

    assert proposal.action != "block_ip"
    assert "IP nguồn" in proposal.risk


# ────────────────────────────────────── ràng buộc chung mọi đề xuất


@pytest.mark.parametrize(
    "evidence,deploy",
    [
        (BC_POOL_CAN, NGHI_PHAM),
        (BC_POOL_CAN, None),
        (BC_POOL_RANH, None),
        (BC_UP, NGHI_PHAM),
        (BC_UP, None),
        (BC_AUTH, NGHI_PHAM),
    ],
)
def test_moi_de_xuat_deu_hop_le_va_deu_can_nguoi_duyet(evidence: MetricEvidence, deploy: DeployRecord | None):
    """Ràng buộc bắt buộc của đề bài, kiểm trên MỌI nhánh.

    `action` phải nằm trong danh sách trắng — hành động lạ thì
    `remediation.execute()` từ chối, tức đề xuất thành vô dụng. Và
    `requires_approval` luôn `True`: không nhánh nào được tự cho mình quyền bỏ
    qua cổng HITL.
    """
    proposal = runbooks.choose(_signal(evidence), _hypothesis(deploy), LICH_SU_DEPLOY)

    assert proposal.action in remediation.SUPPORTED_ACTIONS
    assert proposal.requires_approval is True
    assert proposal.target == SERVICE
    assert proposal.runbook.strip(), "thiếu runbook thì người trực không biết làm gì sau khi duyệt"
    assert proposal.risk.strip(), "thiếu phần rủi ro thì người duyệt không có gì để cân nhắc"


def test_thieu_lich_su_deploy_thi_khong_de_xuat_rollback():
    """Không biết rollback về đâu thì đừng đề xuất rollback.

    Đề xuất "rollback" mà không nói rõ đích đến là đẩy việc đoán xuống lúc thi
    hành — `remediation._describe()` sẽ điền "phiên bản trước", một chuỗi không
    ai kiểm chứng được.
    """
    proposal = runbooks.choose(_signal(BC_POOL_CAN), _hypothesis(NGHI_PHAM), deploy_history=[])

    assert proposal.action == "increase_pool"


def test_nghi_pham_la_ban_deploy_dau_tien_thi_khong_rollback():
    """Không có bản nào trước nó để về."""
    ban_dau_tien = LICH_SU_DEPLOY[0]
    proposal = runbooks.choose(_signal(BC_POOL_CAN), _hypothesis(ban_dau_tien), LICH_SU_DEPLOY)

    assert proposal.action == "increase_pool"
