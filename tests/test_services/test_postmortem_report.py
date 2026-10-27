"""Test `src/services/postmortem_report.py` v2 — email body + file HTML + metrics."""

from __future__ import annotations

from datetime import UTC, datetime

from src.models.incident import (
    ActionItem,
    DeployRecord,
    Hypothesis,
    Incident,
    IncidentSignal,
    IncidentState,
    LogEvidence,
    MetricEvidence,
    Postmortem,
    RemediationProposal,
    Severity,
    TimelineEvent,
)
from src.services import prometheus, rules
from src.services.email_client import Attachment, FakeEmailClient
from src.services.postmortem_report import (
    _compute_approval_wait,
    _compute_mttd,
    _compute_mttr,
    _fmt_khoang,
    _fmt_time,
    _fmt_time_full,
    build_detailed_report,
    build_email_body,
)


def _o_trong(html: str) -> list[str]:
    """Các ô chỉ chứa dấu gạch ngang hoặc câu "chưa có số".

    Bóc thẻ rồi soi từng ô, thay vì tìm chuỗi "—" trong cả trang: dấu gạch ngang
    còn xuất hiện hợp lệ GIỮA câu (vd. "Không mất dữ liệu — các giao dịch…"),
    nên tìm thô sẽ báo nhầm.
    """
    import re

    txt = re.sub(r"<(script|style)[\s\S]*?</\1>", "", html)
    o = [c.strip() for c in re.sub(r"<[^>]+>", "\x00", txt).split("\x00")]
    return [c for c in o if c in ("—", "Chưa resolved", "Chưa xác định", "Chưa thực hiện")]


def _incident_uc3() -> Incident:
    """UC-3 brute-force: KHÔNG deploy, KHÔNG baseline — ca từng để trống nhiều ô nhất."""
    detected = datetime(2026, 8, 24, 15, 31, 0, tzinfo=UTC)
    signal = IncidentSignal(
        affected_service="service-thanh-toan",
        severity=Severity.P3,
        detected_at=detected,
        metric_name="số request /login thất bại mỗi giây",
        metric_value=6.207,
        threshold=rules.AUTH_FAILURE_P3,
        breached_for_seconds=300.0,
        evidence=[
            MetricEvidence(
                name="số request /login thất bại mỗi giây",
                value=6.207,
                promql=prometheus.AUTH_FAILURE_RATE,
            ),
            MetricEvidence(
                name="số IP nguồn khác nhau (1 phút)",
                value=1.0,
                promql=prometheus.AUTH_UNIQUE_SOURCE_IPS,
            ),
            MetricEvidence(
                name="số tài khoản bị thử (1 phút)",
                value=100.0,
                promql=prometheus.AUTH_UNIQUE_ACCOUNTS,
            ),
            MetricEvidence(
                name="tỷ lệ từ IP nguồn lớn nhất",
                value=1.0,
                promql=prometheus.AUTH_TOP_SOURCE_RATIO,
            ),
        ],
    )
    return Incident(
        jira_key="KAN-104",
        title="[P3] service-thanh-toan: brute-force",
        severity=Severity.P3,
        state=IncidentState.RESOLVED,
        affected_services=["service-thanh-toan"],
        detected_at=detected,
        resolved_at=datetime(2026, 8, 24, 15, 33, 0, tzinfo=UTC),
        signal=signal,
        hypotheses=[
            Hypothesis(
                statement="Tấn công brute-force từ IP 172.18.0.1",
                confidence=0.4,
                evidence=signal.evidence,
            )
        ],
        proposal=RemediationProposal(
            action="rate_limit",
            target="service-thanh-toan",
            params={"limit": 60},
            runbook="1. Bật rate limit",
            risk="Chặn oan người dùng thật",
        ),
        timeline=[
            TimelineEvent(
                at=datetime(2026, 8, 24, 15, 31, 30, tzinfo=UTC),
                actor="agent",
                action="chuyển trạng thái",
                detail="Investigating → Awaiting Approval",
            ),
            TimelineEvent(
                at=datetime(2026, 8, 24, 15, 31, 31, tzinfo=UTC),
                actor="agent",
                action="chuyển trạng thái",
                detail="Awaiting Approval → Awaiting Approval",
            ),
            TimelineEvent(
                at=datetime(2026, 8, 24, 15, 33, 0, tzinfo=UTC),
                actor="vietpn04",
                action="chuyển trạng thái",
                detail="Awaiting Approval → Resolved",
            ),
        ],
        postmortem=Postmortem(
            summary="Brute-force vào /login",
            root_cause="Tấn công brute-force từ một IP",
            impact="Không mất dữ liệu",
            actions_taken=["rate_limit service-thanh-toan"],
            action_items=[ActionItem(title="Thêm rate limit mặc định", owner="vietpn04")],
        ),
    )


def _incident_day_du() -> Incident:
    """Incident đầy đủ data — UC-1 pool cạn."""
    detected = datetime(2026, 8, 11, 10, 0, 0, tzinfo=UTC)
    resolved = datetime(2026, 8, 11, 10, 45, 0, tzinfo=UTC)

    signal = IncidentSignal(
        affected_service="service-thanh-toan",
        severity=Severity.P2,
        detected_at=detected,
        metric_name="p95_latency_seconds",
        metric_value=3.3,
        threshold=2.0,
        breached_for_seconds=60.0,
        evidence=[
            MetricEvidence(name="db_pool_in_use / db_pool_size", value=0.97, unit="", baseline=0.3),
            MetricEvidence(name="p95_latency_10m", value=3.3, unit="s", baseline=0.3),
        ],
    )

    deploy = DeployRecord(
        service="service-thanh-toan",
        version="v1.4.2",
        deployed_at=datetime(2026, 8, 11, 9, 45, 0, tzinfo=UTC),
        deployed_by="ci-pipeline",
        commit_sha="abc1234",
        change_note="Thêm retry logic cho payment gateway",
    )

    hypothesis = Hypothesis(
        statement="Connection pool DB cạn kiệt nên request phải xếp hàng, gây tăng latency.",
        confidence=0.9,
        evidence=signal.evidence,
        related_deploy=deploy,
        reasoning=(
            "1. Deploy v1.4.2 thêm retry logic không giới hạn\n"
            "2. Payment gateway timeout → retry giữ connection\n"
            "3. Pool gần cạn 48/50\n"
            "4. Request mới xếp hàng → p95 tăng 11x\n"
            "5. Code review không bắt được vì thiếu checklist retry"
        ),
        log_evidence=[
            LogEvidence(
                source="service-thanh-toan",
                timestamp="2026-08-11T10:01:00Z",
                level="WARNING",
                message="Connection pool exhausted, waiting 3200ms for available connection",
            ),
        ],
    )

    return Incident(
        jira_key="INC-42",
        title="[P2] service-thanh-toan: p95 = 3.30s",
        severity=Severity.P2,
        state=IncidentState.RESOLVED,
        affected_services=["service-thanh-toan"],
        detected_at=detected,
        resolved_at=resolved,
        signal=signal,
        hypotheses=[hypothesis],
        proposal=RemediationProposal(
            action="rollback",
            target="service-thanh-toan",
            params={"to_version": "v1.4.1"},
            runbook="kubectl rollout undo deployment/service-thanh-toan",
            risk="Mất tính năng mới của v1.4.2",
        ),
        timeline=[
            TimelineEvent(at=detected, actor="agent", action="detect", detail="p95 = 3.3s > 2.0s"),
            TimelineEvent(
                at=datetime(2026, 8, 11, 10, 5, 0, tzinfo=UTC),
                actor="agent",
                action="propose",
                detail="Đề xuất rollback v1.4.1",
            ),
            TimelineEvent(
                at=datetime(2026, 8, 11, 10, 22, 0, tzinfo=UTC),
                actor="oncall-duc",
                action="approve",
                detail="Duyệt rollback v1.4.1",
            ),
            TimelineEvent(at=resolved, actor="agent", action="resolve", detail="Rollback OK"),
        ],
        postmortem=Postmortem(
            summary="Pool DB cạn kiệt sau deploy v1.4.2 gây latency tăng 11x",
            root_cause="Deploy v1.4.2 thêm retry logic không giới hạn, giữ connection quá lâu",
            impact=(
                "p95 latency tăng từ 0.3s lên 3.3s trong 45 phút\n"
                "Không mất dữ liệu — các giao dịch lỗi retry thành công sau rollback"
            ),
            timeline=[
                TimelineEvent(at=detected, actor="agent", action="detect", detail="p95 vượt ngưỡng"),
                TimelineEvent(
                    at=datetime(2026, 8, 11, 10, 5, 0, tzinfo=UTC),
                    actor="agent",
                    action="propose",
                    detail="Đề xuất rollback",
                ),
                TimelineEvent(
                    at=datetime(2026, 8, 11, 10, 22, 0, tzinfo=UTC),
                    actor="oncall-duc",
                    action="approve",
                    detail="Duyệt rollback",
                ),
            ],
            actions_taken=["Rollback về v1.4.1", "Xác nhận latency về bình thường"],
            action_items=[
                ActionItem(title="Thêm max_retries=3", owner="Việt", jira_key="ENG-1042"),
                ActionItem(title="Alert cho pool saturation > 80%", owner="Trung"),
            ],
        ),
    )


def _incident_toi_thieu() -> Incident:
    """Incident chỉ có dữ liệu tối thiểu."""
    return Incident(
        jira_key="INC-1",
        title="[P3] api-gateway: error_rate tăng",
        severity=Severity.P3,
        state=IncidentState.INVESTIGATING,
        affected_services=["api-gateway"],
        detected_at=datetime(2026, 8, 11, 12, 0, 0, tzinfo=UTC),
    )


# ────────── Timezone formatting ──────────


class TestTimeFormatting:
    def test_fmt_time_hien_thi_utc7(self):
        """Phải hiển thị giờ UTC+7 song song UTC."""
        dt = datetime(2026, 8, 11, 10, 0, 0, tzinfo=UTC)
        result = _fmt_time(dt)
        assert "UTC+7" in result
        assert "17:00" in result  # 10:00 UTC = 17:00 UTC+7
        assert "10:00 UTC" in result

    def test_fmt_time_full_co_ngay(self):
        dt = datetime(2026, 8, 11, 15, 30, 0, tzinfo=UTC)
        result = _fmt_time_full(dt)
        assert "2026-08-11" in result
        assert "22:30" in result  # 15:30 UTC = 22:30 UTC+7
        assert "UTC+7" in result

    def test_fmt_time_none(self):
        assert _fmt_time(None) == "—"
        assert _fmt_time_full(None) == "—"


# ────────── Incident Metrics ──────────


class TestIncidentMetrics:
    def test_mttd(self):
        """MTTD = detected_at - deploy_at = 15 phút."""
        result = _compute_mttd(_incident_day_du())
        assert "15" in result
        assert "phút" in result

    def test_mttr(self):
        """MTTR = resolved_at - detected_at = 45 phút."""
        result = _compute_mttr(_incident_day_du())
        assert "45" in result
        assert "phút" in result

    def test_approval_wait(self):
        """Chờ phê duyệt = approve_at - propose_at = 17 phút."""
        result = _compute_approval_wait(_incident_day_du())
        assert "17" in result
        assert "phút" in result

    def test_mttd_khong_deploy_thi_dung_breached_for_seconds(self):
        """Không có deploy vẫn phải ra số — lấy quãng metric vượt ngưỡng."""
        result = _compute_mttd(_incident_uc3())
        assert result == "5 phút"

    def test_mttd_khong_co_tin_hieu(self):
        """Không signal, không deploy — nói rõ vì sao, không để gạch ngang."""
        assert _compute_mttd(_incident_toi_thieu()) == "Không đo được (thiếu tín hiệu)"

    def test_mttr_chua_resolved_van_co_so(self):
        result = _compute_mttr(_incident_toi_thieu())
        assert "chưa phục hồi" in result
        assert "—" not in result

    def test_approval_wait_suy_tu_changelog(self):
        """Jira thật chỉ ghi 'chuyển trạng thái' — vẫn phải tính được."""
        assert _compute_approval_wait(_incident_uc3()) == "1 phút"

    def test_approval_wait_bo_qua_moc_tu_tro_chinh_no(self):
        """`Awaiting Approval → Awaiting Approval` không phải lúc rời hàng chờ."""
        inc = _incident_uc3()
        # Mốc tự trỏ nằm ngay sau mốc vào; nếu bị tính là "ra" thì kết quả là 1 giây.
        assert _compute_approval_wait(inc) != "1 giây"

    def test_approval_wait_khi_chua_co_moc_roi_hang_cho(self):
        """Auto-fix dựng báo cáo trước khi chuyển Resolved — không được nói 'vẫn đang chờ'."""
        inc = _incident_uc3()
        inc.timeline = [evt for evt in inc.timeline if "→ Resolved" not in evt.detail]
        result = _compute_approval_wait(inc)
        assert result == "1 phút"  # 15:31:30 vào hàng chờ → resolved_at 15:33:00, 90 giây
        assert "đang chờ" not in result

    def test_fmt_khoang_duoi_mot_phut(self):
        """30–59 giây từng bị làm tròn thành '0 phút' — vô nghĩa với người đọc."""
        assert _fmt_khoang(45) == "45 giây"
        assert _fmt_khoang(90) == "1 phút"
        assert _fmt_khoang(3900) == "1 giờ 5 phút"


# ────────── Email body ──────────


class TestEmailBody:
    def test_du_du_lieu(self):
        html = build_email_body(_incident_day_du())
        assert "INC-42" in html
        assert "P2" in html
        assert "service-thanh-toan" in html

    def test_co_mttd_mttr(self):
        """Email body phải có MTTD và MTTR."""
        html = build_email_body(_incident_day_du())
        assert "MTTD" in html
        assert "MTTR" in html

    def test_data_safe_badge(self):
        """Impact có 'không mất dữ liệu' → hiện badge xanh."""
        html = build_email_body(_incident_day_du())
        assert "✅" in html
        assert "#f0fdf4" in html or "#16a34a" in html  # success green

    def test_business_language_remedy(self):
        """Remediation phải dùng ngôn ngữ kinh doanh."""
        html = build_email_body(_incident_day_du())
        assert "Khôi phục phiên bản trước" in html

    def test_co_approval_wait(self):
        html = build_email_body(_incident_day_du())
        assert "phê duyệt" in html.lower()

    def test_toi_thieu(self):
        html = build_email_body(_incident_toi_thieu())
        assert "INC-1" in html
        assert "P3" in html

    def test_co_action_items_voi_jira_link(self):
        html = build_email_body(_incident_day_du())
        assert "max_retries" in html
        assert "ENG-1042" in html

    def test_utc7_trong_email(self):
        html = build_email_body(_incident_day_du())
        assert "UTC+7" in html


# ────────── File HTML chi tiết ──────────


class TestDetailedReport:
    def test_la_html_hop_le(self):
        html = build_detailed_report(_incident_day_du())
        assert html.strip().startswith("<!DOCTYPE html>")
        assert "</html>" in html

    def test_co_du_11_section(self):
        """Report phải có đủ 11 sections (thêm Incident Metrics)."""
        html = build_detailed_report(_incident_day_du())
        for section in [
            "Tổng quan",
            "Chỉ số hiệu suất",
            "Tín hiệu kích hoạt",
            "Chẩn đoán nguyên nhân gốc",
            "Bằng chứng Metric",
            "Bằng chứng Log",
            "Deploy liên quan",
            "Dòng thời gian",
            "Hành động khắc phục",
            "Các bước đã thực hiện",
            "Action Items",
        ]:
            assert section in html, f"Thiếu section: {section}"

    def test_mttd_mttr_cards(self):
        """Phải có metric cards cho MTTD và MTTR."""
        html = build_detailed_report(_incident_day_du())
        assert "MTTD" in html
        assert "MTTR" in html
        assert "metric-card" in html

    def test_five_whys(self):
        """Phải có phân tích 5 Whys."""
        html = build_detailed_report(_incident_day_du())
        assert "5 Whys" in html
        assert "Why #1" in html
        assert "Why #5" in html

    def test_copy_to_clipboard(self):
        """Phải có nút copy cho log và runbook."""
        html = build_detailed_report(_incident_day_du())
        assert "copyText" in html
        assert "📋 Copy" in html

    def test_data_safe_badge(self):
        html = build_detailed_report(_incident_day_du())
        assert "#f0fdf4" in html  # success green background
        assert "Không có dữ liệu bị mất" in html

    def test_utc7_trong_report(self):
        html = build_detailed_report(_incident_day_du())
        assert "UTC+7" in html

    def test_metric_evidence(self):
        html = build_detailed_report(_incident_day_du())
        assert "db_pool_in_use" in html
        assert "0.97" in html

    def test_log_evidence_with_copy(self):
        html = build_detailed_report(_incident_day_du())
        assert "Connection pool exhausted" in html
        assert "copy-block" in html

    def test_deploy_info(self):
        html = build_detailed_report(_incident_day_du())
        assert "v1.4.2" in html
        assert "abc1234" in html

    def test_timeline_utc7(self):
        html = build_detailed_report(_incident_day_du())
        assert "detect" in html
        assert "UTC+7" in html

    def test_runbook_with_copy(self):
        html = build_detailed_report(_incident_day_du())
        assert "kubectl rollout undo" in html
        assert "copy-block" in html

    def test_action_items_jira_link(self):
        html = build_detailed_report(_incident_day_du(), jira_base_url="https://example.atlassian.net")
        assert "ENG-1042" in html
        assert "href" in html  # hyperlink
        assert "example.atlassian.net/browse/ENG-1042" in html

    def test_toi_thieu_khong_crash(self):
        html = build_detailed_report(_incident_toi_thieu())
        assert "<!DOCTYPE html>" in html
        assert "INC-1" in html

    def test_action_items_owners(self):
        html = build_detailed_report(_incident_day_du())
        assert "Việt" in html
        assert "Trung" in html

    def test_bang_bang_chung_khong_con_o_trong(self):
        """UC-3 không có baseline — cột so sánh phải lấy NGƯỠNG, không bỏ trống."""
        html = build_detailed_report(_incident_uc3())
        assert "Mốc so sánh" in html
        assert "×6.2 ngưỡng" in html  # 6.207 / AUTH_FAILURE_P3
        assert "ngưỡng dò hàng loạt" in html  # số tài khoản bị thử
        assert "1 IP duy nhất" in html  # metric hình thái, không ép ngưỡng

    def test_khong_con_o_trong_trong_report(self):
        for incident in (_incident_uc3(), _incident_day_du(), _incident_toi_thieu()):
            assert _o_trong(build_detailed_report(incident)) == []

    def test_khong_con_o_trong_trong_email(self):
        for incident in (_incident_uc3(), _incident_day_du(), _incident_toi_thieu()):
            assert _o_trong(build_email_body(incident)) == []


# ────────── Tích hợp với EmailClient ──────────


class TestPostmortemEmail:
    def test_gui_voi_attachment(self):
        incident = _incident_day_du()
        email_body = build_email_body(incident)
        report_html = build_detailed_report(incident)

        attachment = Attachment(
            filename=f"postmortem_{incident.jira_key}.html",
            content=report_html.encode("utf-8"),
            mime_type="text/html",
        )

        client = FakeEmailClient()
        result = client.send(
            to=["leader@company.com"],
            subject=f"[Postmortem] {incident.jira_key} — {incident.severity.value}",
            body_html=email_body,
            attachments=[attachment],
        )

        assert result.success
        assert len(client.sent) == 1
        assert attachment.filename == "postmortem_INC-42.html"
