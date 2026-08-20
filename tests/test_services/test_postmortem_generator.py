"""Test `src/services/postmortem_generator.py` — postmortem từ dữ liệu thật."""

from __future__ import annotations

from datetime import UTC, datetime

from src.models.incident import (
    DeployRecord,
    Hypothesis,
    Incident,
    IncidentSignal,
    IncidentState,
    MetricEvidence,
    RemediationProposal,
    Severity,
    TimelineEvent,
)
from src.services.jira.client import FakeJiraClient
from src.services.postmortem_generator import (
    _derive_action_items,
    _derive_impact,
    _derive_root_cause,
    _derive_summary,
    generate_postmortem,
)


def _full_incident() -> Incident:
    """Incident đầy đủ — giống thực tế nhất."""
    signal = IncidentSignal(
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
    hypothesis = Hypothesis(
        statement="Connection pool DB cạn kiệt do retry logic mới trong v1.4.2",
        confidence=0.92,
        evidence=signal.evidence,
        related_deploy=DeployRecord(
            service="service-thanh-toan",
            version="v1.4.2",
            deployed_at=datetime(2026, 8, 11, 15, 15, 0, tzinfo=UTC),
            deployed_by="ci-pipeline",
            commit_sha="abc123",
            change_note="Thêm retry logic cho payment gateway",
        ),
        reasoning="1. Deploy v1.4.2 thêm retry logic\n2. Pool gần cạn 48/50\n3. p95 tăng 11x",
    )
    proposal = RemediationProposal(
        action="rollback",
        target="service-thanh-toan",
        params={"to_version": "v1.4.1", "from_version": "v1.4.2"},
        runbook="1. Verify current version\n2. kubectl rollout undo\n3. Monitor p95",
        risk="Mất tính năng retry mới",
    )
    return Incident(
        jira_key="INC-7",
        title="[P2] service-thanh-toan: p95_latency_seconds = 3.30 (ngưỡng 2.00)",
        severity=Severity.P2,
        state=IncidentState.RESOLVED,
        affected_services=["service-thanh-toan"],
        detected_at=datetime(2026, 8, 11, 15, 32, 0, tzinfo=UTC),
        resolved_at=datetime(2026, 8, 11, 16, 18, 0, tzinfo=UTC),
        signal=signal,
        hypotheses=[hypothesis],
        proposal=proposal,
        timeline=[
            TimelineEvent(
                at=datetime(2026, 8, 11, 15, 32, 0, tzinfo=UTC),
                actor="agent",
                action="detect",
                detail="Phát hiện sự cố",
            ),
            TimelineEvent(
                at=datetime(2026, 8, 11, 15, 45, 0, tzinfo=UTC),
                actor="oncall-duc",
                action="approve",
                detail="Duyệt rollback",
            ),
            TimelineEvent(
                at=datetime(2026, 8, 11, 16, 18, 0, tzinfo=UTC),
                actor="agent",
                action="verify",
                detail="Metric về bình thường",
            ),
        ],
    )


def _minimal_incident() -> Incident:
    """Incident tối thiểu — không có hypothesis, không có proposal."""
    return Incident(
        jira_key="INC-99",
        title="[P3] api-gateway: error_rate tăng",
        severity=Severity.P3,
        state=IncidentState.RESOLVED,
        affected_services=["api-gateway"],
        detected_at=datetime(2026, 8, 11, 12, 0, 0, tzinfo=UTC),
        resolved_at=datetime(2026, 8, 11, 12, 30, 0, tzinfo=UTC),
    )


# ────────── SUMMARY ──────────


class TestDeriveSummary:
    def test_co_severity_va_service(self):
        result = _derive_summary(_full_incident())
        assert "P2" in result
        assert "service-thanh-toan" in result

    def test_co_hypothesis_statement(self):
        result = _derive_summary(_full_incident())
        assert "Connection pool" in result

    def test_co_duration(self):
        result = _derive_summary(_full_incident())
        assert "46 phút" in result

    def test_khong_co_hypothesis(self):
        result = _derive_summary(_minimal_incident())
        assert "P3" in result
        assert "api-gateway" in result


# ────────── ROOT CAUSE ──────────


class TestDeriveRootCause:
    def test_co_statement(self):
        result = _derive_root_cause(_full_incident())
        assert "Connection pool" in result

    def test_co_reasoning(self):
        result = _derive_root_cause(_full_incident())
        assert "retry logic" in result

    def test_co_deploy_info(self):
        result = _derive_root_cause(_full_incident())
        assert "v1.4.2" in result

    def test_khong_co_hypothesis(self):
        result = _derive_root_cause(_minimal_incident())
        assert "Chưa xác định" in result


# ────────── IMPACT ──────────


class TestDeriveImpact:
    def test_co_duration(self):
        result = _derive_impact(_full_incident())
        assert "46 phút" in result

    def test_co_metric_info(self):
        result = _derive_impact(_full_incident())
        assert "p95_latency" in result
        assert "3.30" in result

    def test_co_deviation(self):
        result = _derive_impact(_full_incident())
        assert "lệch" in result

    def test_co_khong_mat_du_lieu(self):
        result = _derive_impact(_full_incident())
        assert "Không mất dữ liệu" in result


# ────────── ACTION ITEMS ──────────


class TestDeriveActionItems:
    def test_pool_issue_sinh_alert_item(self):
        items = _derive_action_items(_full_incident())
        titles = [i.title for i in items]
        assert any("pool" in t.lower() or "alert" in t.lower() for t in titles)

    def test_retry_issue_sinh_retry_item(self):
        items = _derive_action_items(_full_incident())
        titles = [i.title for i in items]
        assert any("retry" in t.lower() or "max_retries" in t.lower() for t in titles)

    def test_latency_issue_sinh_circuit_breaker(self):
        items = _derive_action_items(_full_incident())
        titles = [i.title for i in items]
        assert any("circuit breaker" in t.lower() for t in titles)

    def test_mttd_improvement(self):
        items = _derive_action_items(_full_incident())
        titles = [i.title for i in items]
        assert any("MTTD" in t for t in titles)

    def test_minimal_incident_van_co_item(self):
        items = _derive_action_items(_minimal_incident())
        assert len(items) >= 1
        assert items[0].jira_key == ""  # Chưa tạo sub-task


# ────────── GENERATE POSTMORTEM (INTEGRATION) ──────────


class TestGeneratePostmortem:
    def test_tat_ca_field_co_du_lieu(self):
        pm = generate_postmortem(_full_incident())
        assert pm.summary
        assert pm.root_cause
        assert pm.impact
        assert len(pm.action_items) > 0
        assert len(pm.actions_taken) > 0

    def test_khong_co_jira_thi_jira_key_rong(self):
        pm = generate_postmortem(_full_incident(), jira=None)
        for item in pm.action_items:
            assert item.jira_key == ""

    def test_co_jira_thi_tao_subtask_that(self):
        """FakeJiraClient tạo sub-task key = parent-1, parent-2, ..."""
        jira = FakeJiraClient(verbose=False)
        incident = _full_incident()

        # Tạo incident trên Jira trước
        jira.create_incident(incident.signal)

        pm = generate_postmortem(incident, jira=jira)

        # Mọi action item PHẢI có jira_key thật
        for item in pm.action_items:
            assert item.jira_key != "", f"Action item '{item.title}' thiếu jira_key"
            assert item.jira_key.startswith("INC-7-")

    def test_timeline_lay_tu_incident(self):
        pm = generate_postmortem(_full_incident())
        assert len(pm.timeline) == 3  # detect, approve, verify

    def test_actions_taken_co_rollback(self):
        pm = generate_postmortem(_full_incident())
        assert any("v1.4.1" in a for a in pm.actions_taken)

    def test_verify_recovery_in_actions(self):
        pm = generate_postmortem(_full_incident())
        assert any("phục hồi" in a.lower() for a in pm.actions_taken)

    def test_minimal_incident_van_ok(self):
        pm = generate_postmortem(_minimal_incident())
        assert pm.summary
        assert "Chưa xác định" in pm.root_cause
        assert len(pm.action_items) >= 1

    def test_jira_loi_van_tra_postmortem(self):
        """Lỗi Jira khi tạo sub-task không được phá vỡ postmortem."""

        class BrokenJira(FakeJiraClient):
            def create_subtasks(self, *args, **kwargs):
                raise RuntimeError("Jira down")

        jira = BrokenJira(verbose=False)
        pm = generate_postmortem(_full_incident(), jira=jira)

        # Postmortem vẫn phải có, chỉ thiếu jira_key
        assert pm.summary
        assert len(pm.action_items) > 0


# ────────── REPORT INTEGRATION ──────────


class TestReportIntegration:
    """Kiểm tra postmortem_generator + postmortem_report tích hợp đúng."""

    def test_email_body_co_du_lieu_that(self):
        from src.services.postmortem_report import build_email_body

        incident = _full_incident()
        pm = generate_postmortem(incident)
        incident.postmortem = pm

        html = build_email_body(incident)
        assert "Connection pool" in html
        assert "P2" in html
        assert "service-thanh-toan" in html

    def test_detailed_report_co_du_lieu_that(self):
        from src.services.postmortem_report import build_detailed_report

        incident = _full_incident()
        pm = generate_postmortem(incident)
        incident.postmortem = pm

        html = build_detailed_report(incident)
        assert "Connection pool" in html
        assert "retry" in html.lower()

    def test_report_co_jira_key_that_khi_co_jira(self):
        from src.services.postmortem_report import build_detailed_report, build_email_body

        jira = FakeJiraClient(verbose=False)
        incident = _full_incident()
        jira.create_incident(incident.signal)

        pm = generate_postmortem(incident, jira=jira)
        incident.postmortem = pm

        email_html = build_email_body(incident)
        detail_html = build_detailed_report(incident)

        # Ít nhất một action item có jira_key hiển thị trong report
        has_key_in_email = any(item.jira_key in email_html for item in pm.action_items if item.jira_key)
        has_key_in_detail = any(item.jira_key in detail_html for item in pm.action_items if item.jira_key)

        assert has_key_in_email, "Email body phải hiển thị jira_key thật"
        assert has_key_in_detail, "Detailed report phải hiển thị jira_key thật"
