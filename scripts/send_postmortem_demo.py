"""Chạy full lifecycle: Incident → Postmortem → Gửi email thật.

Dùng để demo/kiểm tra nội dung email body + report HTML đính kèm.
Tất cả dữ liệu trong report đều sinh từ Incident thật, không hardcode.

Usage:
    python -m scripts.send_postmortem_demo
"""

from __future__ import annotations

import logging
import sys
from datetime import UTC, datetime

# Đảm bảo src/ nằm trong path
sys.path.insert(0, ".")

from src.config import get_settings
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
from src.services.email_client import Attachment, GmailClient
from src.services.jira.client import FakeJiraClient
from src.services.postmortem_generator import generate_postmortem
from src.services.postmortem_report import build_detailed_report, build_email_body

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def _build_realistic_incident() -> Incident:
    """Tạo Incident giả lập giống thực tế nhất — mô phỏng sự cố thật."""
    now = datetime.now(UTC)

    signal = IncidentSignal(
        affected_service="service-thanh-toan",
        severity=Severity.P2,
        detected_at=datetime(2026, 8, 11, 15, 32, 0, tzinfo=UTC),
        metric_name="http_request_duration_seconds p95",
        metric_value=3.30,
        threshold=2.00,
        breached_for_seconds=65.0,
        evidence=[
            MetricEvidence(
                name="db_pool_active_connections",
                value=48,
                unit=" / 50",
                baseline=15,
                promql='pg_stat_activity_count{datname="production"}',
            ),
            MetricEvidence(
                name="http_request_duration_seconds p95",
                value=3.30,
                unit="s",
                baseline=0.30,
                promql='histogram_quantile(0.95, rate(http_request_duration_seconds_bucket{service="thanh-toan"}[5m]))',
            ),
            MetricEvidence(
                name="http_requests_total 5xx rate",
                value=12.5,
                unit="%",
                baseline=0.1,
                promql='rate(http_requests_total{status=~"5.."}[5m]) / rate(http_requests_total[5m]) * 100',
            ),
        ],
    )

    hypothesis = Hypothesis(
        statement="Connection pool DB cạn kiệt do retry logic không giới hạn trong v1.4.2",
        confidence=0.92,
        evidence=signal.evidence,
        related_deploy=DeployRecord(
            service="service-thanh-toan",
            version="v1.4.2",
            deployed_at=datetime(2026, 8, 11, 15, 15, 0, tzinfo=UTC),
            deployed_by="ci-pipeline",
            commit_sha="a1b2c3d",
            change_note="Thêm retry logic cho payment gateway timeout",
        ),
        reasoning=(
            "1. Deploy v1.4.2 lúc 22:15 thêm retry logic cho payment gateway\n"
            "2. Retry không giới hạn → mỗi request timeout sinh thêm 3-5 connection mới\n"
            "3. Pool 50 connection cạn kiệt trong 17 phút (48/50 = 96%)\n"
            "4. Request mới phải chờ connection → p95 tăng từ 0.3s lên 3.3s (11×)\n"
            "5. Sau 2s timeout → 5xx error rate tăng từ 0.1% lên 12.5%"
        ),
    )

    proposal = RemediationProposal(
        action="rollback",
        target="service-thanh-toan",
        params={"to_version": "v1.4.1", "from_version": "v1.4.2"},
        runbook=(
            "1. kubectl get deployment service-thanh-toan -o jsonpath='{.spec.template.spec.containers[0].image}'\n"
            "2. kubectl rollout undo deployment/service-thanh-toan\n"
            "3. kubectl rollout status deployment/service-thanh-toan --timeout=120s\n"
            "4. Theo dõi p95 latency trong 5 phút, kỳ vọng < 0.5s"
        ),
        risk="Mất tính năng retry mới cho payment gateway timeout. Cần fix retry logic trước khi deploy lại.",
    )

    timeline = [
        TimelineEvent(
            at=datetime(2026, 8, 11, 15, 15, 0, tzinfo=UTC),
            actor="ci-pipeline",
            action="deploy",
            detail="Deploy v1.4.2 service-thanh-toan — thêm retry logic",
        ),
        TimelineEvent(
            at=datetime(2026, 8, 11, 15, 32, 0, tzinfo=UTC),
            actor="agent",
            action="detect",
            detail="🔴 Phát hiện p95 = 3.30s (ngưỡng 2.00s), vượt ngưỡng 65s",
        ),
        TimelineEvent(
            at=datetime(2026, 8, 11, 15, 33, 0, tzinfo=UTC),
            actor="agent",
            action="collect_logs",
            detail="Thu thập 847 dòng log, 23 dòng chứa ERROR",
        ),
        TimelineEvent(
            at=datetime(2026, 8, 11, 15, 35, 0, tzinfo=UTC),
            actor="agent",
            action="diagnose",
            detail="Chẩn đoán: Connection pool cạn kiệt do retry vô hạn (92% tin cậy)",
        ),
        TimelineEvent(
            at=datetime(2026, 8, 11, 15, 36, 0, tzinfo=UTC),
            actor="agent",
            action="propose",
            detail="Đề xuất rollback v1.4.2 → v1.4.1 — CHỜ NGƯỜI DUYỆT",
        ),
        TimelineEvent(
            at=datetime(2026, 8, 11, 15, 49, 0, tzinfo=UTC),
            actor="oncall-duc",
            action="approve",
            detail="Phê duyệt rollback",
        ),
        TimelineEvent(
            at=datetime(2026, 8, 11, 15, 50, 0, tzinfo=UTC),
            actor="agent",
            action="execute",
            detail="Bắt đầu thi hành rollback",
        ),
        TimelineEvent(
            at=datetime(2026, 8, 11, 16, 2, 0, tzinfo=UTC),
            actor="agent",
            action="verify",
            detail="p95 về bình thường (0.28s), pool 12/50, error rate 0.08%",
        ),
    ]

    return Incident(
        jira_key="INC-7",
        title="[P2] service-thanh-toan: http_request_duration_seconds p95 = 3.30 (ngưỡng 2.00)",
        severity=Severity.P2,
        state=IncidentState.RESOLVED,
        affected_services=["service-thanh-toan"],
        detected_at=datetime(2026, 8, 11, 15, 32, 0, tzinfo=UTC),
        resolved_at=datetime(2026, 8, 11, 16, 2, 0, tzinfo=UTC),
        signal=signal,
        hypotheses=[hypothesis],
        proposal=proposal,
        timeline=timeline,
    )


def main() -> None:
    settings = get_settings()

    # Validate config
    if not settings.smtp_email or not settings.smtp_app_password:
        logger.error("Thiếu SMTP_EMAIL hoặc SMTP_APP_PASSWORD trong .env")
        sys.exit(1)

    recipients = [r.strip() for r in settings.postmortem_recipients.split(",") if r.strip()]
    if not recipients:
        logger.error("Thiếu POSTMORTEM_RECIPIENTS trong .env")
        sys.exit(1)

    logger.info("📧 Gửi tới: %s", ", ".join(recipients))

    # 1. Tạo incident giả lập
    logger.info("1️⃣ Tạo incident giả lập...")
    incident = _build_realistic_incident()

    # 2. Sinh postmortem từ dữ liệu thật + tạo sub-task Jira (FakeJiraClient)
    logger.info("2️⃣ Sinh postmortem từ dữ liệu thật...")
    jira = FakeJiraClient(verbose=True)
    # Tạo incident trên FakeJira để create_subtasks hoạt động
    jira.create_incident(incident.signal)
    postmortem = generate_postmortem(incident, jira=jira)
    incident.postmortem = postmortem

    logger.info("   Summary: %s", postmortem.summary[:80])
    logger.info("   Root cause: %s", postmortem.root_cause[:80])
    logger.info("   Action items: %d", len(postmortem.action_items))
    for item in postmortem.action_items:
        logger.info("   → [%s] %s", item.jira_key or "—", item.title)

    # 3. Sinh email body + report HTML
    logger.info("3️⃣ Sinh email body + report HTML...")
    email_body = build_email_body(incident, jira_base_url="https://jibinarybro.atlassian.net")
    report_html = build_detailed_report(incident, jira_base_url="https://jibinarybro.atlassian.net")

    # 4. Gửi email thật
    logger.info("4️⃣ Gửi email qua Gmail SMTP...")
    gmail = GmailClient(settings.smtp_email, settings.smtp_app_password)

    result = gmail.send(
        to=recipients,
        subject=f"[Postmortem] {incident.severity.value} — {', '.join(incident.affected_services)} — {incident.jira_key}",
        body_html=email_body,
        attachments=[
            Attachment(
                filename=f"postmortem_{incident.jira_key}.html",
                content=report_html.encode("utf-8"),
                mime_type="text/html",
            )
        ],
    )

    logger.info(result.summary())

    if result.success:
        logger.info("✅ Hoàn tất! Kiểm tra email tại: %s", ", ".join(recipients))
    else:
        logger.error("❌ Gửi thất bại: %s", result.error)
        sys.exit(1)


if __name__ == "__main__":
    main()
