"""Test `src/services/status_updater.py` — structured Jira status comments."""

from __future__ import annotations

from datetime import UTC, datetime

from src.models.incident import (
    DeployRecord,
    Hypothesis,
    IncidentSignal,
    LogEvidence,
    MetricEvidence,
    RemediationProposal,
    Severity,
)
from src.services.status_updater import (
    status_approved,
    status_detected,
    status_diagnosed,
    status_escalated,
    status_executing,
    status_improving,
    status_logs_collected,
    status_proposed,
    status_resolved,
    status_worsening,
)


def _signal() -> IncidentSignal:
    return IncidentSignal(
        affected_service="service-thanh-toan",
        severity=Severity.P2,
        detected_at=datetime(2026, 8, 11, 15, 32, 0, tzinfo=UTC),
        metric_name="p95_latency_seconds",
        metric_value=3.3,
        threshold=2.0,
        breached_for_seconds=65.0,
        evidence=[
            MetricEvidence(name="db_pool_in_use", value=0.97, unit="", baseline=0.3),
            MetricEvidence(name="p95_latency_10m", value=3.3, unit="s", baseline=0.3),
        ],
    )


def _hypothesis() -> Hypothesis:
    return Hypothesis(
        statement="Connection pool DB cạn kiệt do retry logic mới",
        confidence=0.92,
        evidence=_signal().evidence,
        related_deploy=DeployRecord(
            service="service-thanh-toan",
            version="v1.4.2",
            deployed_at=datetime(2026, 8, 11, 15, 15, 0, tzinfo=UTC),
            deployed_by="ci-pipeline",
            commit_sha="abc123",
            change_note="Thêm retry logic cho payment gateway",
        ),
        reasoning="1. Deploy v1.4.2 thêm retry logic\n2. Pool gần cạn 48/50\n3. p95 tăng 11x",
        log_evidence=[
            LogEvidence(
                source="service-thanh-toan",
                timestamp="2026-08-11T15:33:12Z",
                level="WARNING",
                message="Connection pool exhausted: 48/50",
            ),
        ],
    )


def _proposal() -> RemediationProposal:
    return RemediationProposal(
        action="rollback",
        target="service-thanh-toan",
        params={"to_version": "v1.4.1"},
        runbook="1. Verify current version\n2. kubectl rollout undo\n3. Monitor p95",
        risk="Mất tính năng retry mới",
    )


# ────────── PHÁT HIỆN ──────────


class TestStatusDetected:
    def test_co_emoji_va_header(self):
        result = status_detected(_signal())
        assert "🔴" in result
        assert "PHÁT HIỆN" in result

    def test_co_thong_tin_signal(self):
        result = status_detected(_signal())
        assert "service-thanh-toan" in result
        assert "P2" in result
        assert "p95_latency_seconds" in result
        assert "3.30" in result

    def test_co_utc7(self):
        result = status_detected(_signal())
        assert "UTC+7" in result

    def test_co_metric_evidence(self):
        result = status_detected(_signal())
        assert "db_pool_in_use" in result
        assert "0.97" in result

    def test_co_call_to_action(self):
        result = status_detected(_signal())
        assert "thu thập log" in result.lower() or "chẩn đoán" in result.lower()


# ────────── THU THẬP LOG ──────────


class TestStatusLogsCollected:
    def test_co_emoji_va_header(self):
        result = status_logs_collected(_signal(), 150, 12)
        assert "🔍" in result
        assert "THU THẬP LOG" in result

    def test_co_so_lieu_log(self):
        result = status_logs_collected(_signal(), 150, 12)
        assert "150" in result
        assert "12" in result

    def test_co_sample_logs(self):
        samples = [
            LogEvidence(source="svc", timestamp="T1", level="ERROR", message="Pool exhausted"),
        ]
        result = status_logs_collected(_signal(), 150, 12, sample_logs=samples)
        assert "Pool exhausted" in result
        assert "ERROR" in result

    def test_gioi_han_5_sample(self):
        samples = [
            LogEvidence(source="svc", level="ERROR", message=f"Log #{i}")
            for i in range(10)
        ]
        result = status_logs_collected(_signal(), 100, 50, sample_logs=samples)
        # Chỉ hiện 5 dòng đầu
        assert "Log #4" in result
        assert "Log #5" not in result


# ────────── CHẨN ĐOÁN ──────────


class TestStatusDiagnosed:
    def test_co_emoji_va_header(self):
        result = status_diagnosed(_signal(), _hypothesis())
        assert "🧠" in result
        assert "CHẨN ĐOÁN" in result

    def test_co_nguyen_nhan(self):
        result = status_diagnosed(_signal(), _hypothesis())
        assert "Connection pool" in result
        assert "92%" in result

    def test_co_deploy_info(self):
        result = status_diagnosed(_signal(), _hypothesis())
        assert "v1.4.2" in result

    def test_co_reasoning(self):
        result = status_diagnosed(_signal(), _hypothesis())
        assert "retry logic" in result


# ────────── ĐỀ XUẤT ──────────


class TestStatusProposed:
    def test_co_emoji_va_header(self):
        result = status_proposed(_proposal())
        assert "⚡" in result
        assert "ĐỀ XUẤT" in result

    def test_dung_ngon_ngu_kinh_doanh(self):
        """Rollback → 'Khôi phục phiên bản trước'."""
        result = status_proposed(_proposal())
        assert "Khôi phục phiên bản trước" in result

    def test_co_runbook(self):
        result = status_proposed(_proposal())
        assert "kubectl rollout undo" in result

    def test_co_canh_bao_cho_duyet(self):
        result = status_proposed(_proposal())
        assert "CHỜ NGƯỜI DUYỆT" in result
        assert "Agent không tự thực thi" in result

    def test_co_tham_so(self):
        result = status_proposed(_proposal())
        assert "to_version=v1.4.1" in result


# ────────── PHÊ DUYỆT ──────────


class TestStatusApproved:
    def test_co_emoji_va_header(self):
        result = status_approved("oncall-duc")
        assert "✅" in result
        assert "PHÊ DUYỆT" in result

    def test_co_nguoi_duyet(self):
        result = status_approved("oncall-duc")
        assert "oncall-duc" in result


# ────────── ĐANG THỰC THI ──────────


class TestStatusExecuting:
    def test_co_emoji_va_header(self):
        result = status_executing(_proposal())
        assert "🔧" in result
        assert "ĐANG THỰC THI" in result

    def test_dung_ngon_ngu_kinh_doanh(self):
        result = status_executing(_proposal())
        assert "Đang khôi phục phiên bản trước" in result


# ────────── CẢI THIỆN / XẤU ĐI ──────────


class TestStatusImproving:
    def test_co_emoji(self):
        result = status_improving("p95_latency", 0.28, 3.3, baseline=0.3)
        assert "📈" in result
        assert "CẢI THIỆN" in result

    def test_co_so_lieu(self):
        result = status_improving("p95_latency", 0.28, 3.3, baseline=0.3)
        assert "0.28" in result
        assert "3.30" in result
        assert "0.30" in result


class TestStatusWorsening:
    def test_co_canh_bao(self):
        result = status_worsening("error_rate", 0.15, 0.12, "Tăng sau remediation")
        assert "🔴" in result
        assert "XẤU" in result
        assert "TĂNG" in result

    def test_co_detail(self):
        result = status_worsening("error_rate", 0.15, 0.12, "Cần hành động bổ sung")
        assert "Cần hành động bổ sung" in result


# ────────── RESOLVED ──────────


class TestStatusResolved:
    def test_co_emoji(self):
        result = status_resolved(46, "Pool DB cạn kiệt")
        assert "✅" in result
        assert "RESOLVED" in result

    def test_co_thoi_gian(self):
        result = status_resolved(46)
        assert "46 phút" in result

    def test_co_summary(self):
        result = status_resolved(46, "Pool DB cạn kiệt do retry logic")
        assert "Pool DB cạn kiệt" in result

    def test_co_thong_bao_postmortem(self):
        result = status_resolved(46)
        assert "postmortem" in result.lower()


# ────────── NÂNG MỨC ──────────


class TestStatusEscalated:
    def test_co_emoji(self):
        result = status_escalated(Severity.P3, Severity.P2, 12.5)
        assert "⏰" in result
        assert "NÂNG MỨC" in result

    def test_co_muc_cu_moi(self):
        result = status_escalated(Severity.P3, Severity.P2, 12.5)
        assert "P3" in result
        assert "P2" in result

    def test_khong_tu_thuc_thi(self):
        result = status_escalated(Severity.P2, Severity.P1, 15.0)
        assert "Agent KHÔNG tự thực thi" in result


def test_nang_muc_ghi_ro_nguong():
    """Comment nâng mức phải nói ngưỡng, không chỉ nói đã chờ bao lâu.

    Bản comment cũ trong escalate.py có ghi ngưỡng; khi chuyển sang
    status_escalated() nó bị bỏ mất. Thiếu con số đó thì người trực đọc "đã chờ
    12 phút" mà không biết vì sao Agent nâng đúng lúc đó — đúng thứ biến một
    hành động tự động thành hành động giải thích được.
    """
    from src.models.incident import Severity
    from src.services.status_updater import status_escalated

    co_nguong = status_escalated(Severity.P3, Severity.P2, 12.0, 10.0)
    assert "12 phút" in co_nguong
    assert "ngưỡng 10 phút" in co_nguong

    # Không truyền ngưỡng thì bỏ hẳn cụm đó, không in "ngưỡng None"
    khong_nguong = status_escalated(Severity.P3, Severity.P2, 12.0)
    assert "ngưỡng" not in khong_nguong
    assert "None" not in khong_nguong


def test_thu_thap_log_chay_duoc_khi_khong_co_sample():
    """Chốt lỗi che tên: biến cục bộ trùng tên hàm `ts()` của chính module.

    Python coi hàm là biến cục bộ ngay từ dòng đầu, nên lời gọi `ts()` ở đầu hàm
    chết bằng UnboundLocalError KỂ CẢ khi nhánh gán biến không bao giờ chạy.
    """
    from datetime import UTC, datetime

    from src.models.incident import IncidentSignal, Severity
    from src.services.status_updater import status_logs_collected

    signal = IncidentSignal(
        affected_service="service-thanh-toan",
        severity=Severity.P2,
        detected_at=datetime.now(UTC),
        metric_name="p95",
        metric_value=4.0,
        threshold=2.0,
        breached_for_seconds=60.0,
    )
    assert "THU THẬP LOG" in status_logs_collected(signal, 100, 5, None)
