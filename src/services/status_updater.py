"""Agent Status Updater — tự động comment lên Jira mỗi khi incident thay đổi.

CHỦ SỞ HỮU: Việt

## Mục đích

Thay vì con người phải vừa xử lý sự cố vừa comment lên Jira, Agent sẽ tự động
post **structured status update** mỗi khi incident chuyển trạng thái:

    🔴 PHÁT HIỆN → 🔍 THU THẬP LOG → 🧠 CHẨN ĐOÁN → ⚡ ĐỀ XUẤT →
    ✅ PHÊ DUYỆT → 🔧 ĐANG THỰC THI → 📈 XÁC NHẬN → ✅ RESOLVED

Con người chỉ cần đọc comment và bấm Approve/Reject — không cần viết gì.

## Thiết kế

Mỗi hàm sinh **chuỗi text thuần** (plain text, không Markdown) vì Jira Cloud
API chấp nhận plain text hoặc ADF. Dùng emoji Unicode để cấu trúc trực quan.

Thời gian hiển thị song song UTC+7 và UTC để đồng bộ với báo cáo postmortem.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone, UTC

from src.models.incident import (
    Hypothesis,
    IncidentSignal,
    LogEvidence,
    RemediationProposal,
    Severity,
)

_TZ_LOCAL = timezone(timedelta(hours=7))


def _ts(dt: datetime | None = None) -> str:
    """Format timestamp song song UTC+7 / UTC."""
    dt = dt or datetime.now(UTC)
    local = dt.astimezone(_TZ_LOCAL)
    return f"{local.strftime('%H:%M')} (UTC+7) / {dt.strftime('%H:%M')} UTC"


def _ts_full(dt: datetime | None = None) -> str:
    """Format timestamp đầy đủ có ngày."""
    dt = dt or datetime.now(UTC)
    local = dt.astimezone(_TZ_LOCAL)
    return f"{local.strftime('%Y-%m-%d %H:%M')} (UTC+7)"


# ---------------------------------------------------------------------------
# Từng loại status update
# ---------------------------------------------------------------------------


def status_detected(signal: IncidentSignal) -> str:
    """🔴 PHÁT HIỆN — comment khi mở war room mới."""
    lines = [
        f"🔴 [{_ts(signal.detected_at)}] PHÁT HIỆN SỰ CỐ",
        "",
        f"Dịch vụ: {signal.affected_service}",
        f"Mức độ: {signal.severity.value}",
        f"Metric: {signal.metric_name} = {signal.metric_value:.2f} (ngưỡng {signal.threshold:.2f})",
        f"Vượt ngưỡng liên tục: {signal.breached_for_seconds:.0f} giây",
    ]

    if signal.evidence:
        lines.append("")
        lines.append("Bối cảnh metric thu thập được:")
        for ev in signal.evidence:
            baseline = f" (baseline: {ev.baseline:.4g}{ev.unit})" if ev.baseline is not None else ""
            deviation = f" — lệch {ev.deviation_ratio:.1f}×" if ev.deviation_ratio else ""
            lines.append(f"  • {ev.name}: {ev.value:.4g}{ev.unit}{baseline}{deviation}")

    lines.append("")
    lines.append("Agent đang tiến hành thu thập log và chẩn đoán nguyên nhân...")

    return "\n".join(lines)


def status_logs_collected(
    signal: IncidentSignal,
    logs_collected: int,
    logs_relevant: int,
    sample_logs: list[LogEvidence] | None = None,
) -> str:
    """🔍 THU THẬP LOG — comment khi đã collect và phân tích log."""
    lines = [
        f"🔍 [{_ts()}] THU THẬP LOG",
        "",
        f"Dịch vụ: {signal.affected_service}",
        f"Tổng log thu thập: {logs_collected} dòng",
        f"Log liên quan: {logs_relevant} dòng",
    ]

    if sample_logs:
        lines.append("")
        lines.append("Các dòng log đáng chú ý:")
        for le in sample_logs[:5]:  # Tối đa 5 dòng sample
            ts = f" [{le.timestamp}]" if le.timestamp else ""
            lines.append(f"  [{le.level}]{ts} {le.message}")

    lines.append("")
    lines.append("Agent đang xây dựng giả thuyết nguyên nhân...")

    return "\n".join(lines)


def status_diagnosed(
    signal: IncidentSignal,
    hypothesis: Hypothesis,
) -> str:
    """🧠 CHẨN ĐOÁN — comment khi đã xác định nguyên nhân."""
    lines = [
        f"🧠 [{_ts()}] CHẨN ĐOÁN NGUYÊN NHÂN",
        "",
        f"Nguyên nhân: {hypothesis.statement}",
        f"Độ tin cậy: {hypothesis.confidence:.0%}",
    ]

    if hypothesis.related_deploy:
        d = hypothesis.related_deploy
        lines.append("")
        lines.append("Deploy liên quan:")
        lines.append(f"  • Version: {d.version}")
        lines.append(f"  • Deploy lúc: {_ts(d.deployed_at)}")
        lines.append(f"  • Thay đổi: {d.change_note or '—'}")

    if hypothesis.reasoning:
        lines.append("")
        lines.append("Chuỗi nhân quả:")
        for line in hypothesis.reasoning.strip().split("\n"):
            clean = line.strip()
            if clean:
                lines.append(f"  {clean}")

    lines.append("")
    lines.append("Agent đang xây dựng đề xuất khắc phục...")

    return "\n".join(lines)


def status_proposed(
    proposal: RemediationProposal,
) -> str:
    """⚡ ĐỀ XUẤT — comment khi đề xuất remediation và chờ duyệt."""
    action_map = {
        "rollback": "Khôi phục phiên bản trước (rollback)",
        "restart": "Khởi động lại dịch vụ (restart)",
        "scale_up": "Tăng tài nguyên hệ thống (scale up)",
    }
    action_display = action_map.get(proposal.action, proposal.action)

    params_str = ", ".join(f"{k}={v}" for k, v in proposal.params.items()) if proposal.params else "—"

    lines = [
        f"⚡ [{_ts()}] ĐỀ XUẤT KHẮC PHỤC",
        "",
        f"Hành động: {action_display}",
        f"Đối tượng: {proposal.target}",
        f"Tham số: {params_str}",
        f"Rủi ro: {proposal.risk or '—'}",
    ]

    if proposal.runbook:
        lines.append("")
        lines.append("Runbook:")
        for step in proposal.runbook.strip().split("\n"):
            lines.append(f"  {step.strip()}")

    lines.append("")
    lines.append("─" * 50)
    lines.append("CHỜ NGƯỜI DUYỆT — Agent không tự thực thi.")
    lines.append("Chuyển issue sang trạng thái 'Remediating' để phê duyệt.")
    lines.append("─" * 50)

    return "\n".join(lines)


def status_approved(approved_by: str) -> str:
    """✅ PHÊ DUYỆT — comment khi on-call đã duyệt."""
    return (
        f"✅ [{_ts()}] ĐÃ PHÊ DUYỆT\n"
        f"\n"
        f"Người phê duyệt: {approved_by}\n"
        f"Agent bắt đầu thực thi hành động khắc phục..."
    )


def status_executing(proposal: RemediationProposal) -> str:
    """🔧 ĐANG THỰC THI — comment khi bắt đầu remediation."""
    action_map = {
        "rollback": "Đang khôi phục phiên bản trước",
        "restart": "Đang khởi động lại dịch vụ",
        "scale_up": "Đang tăng tài nguyên hệ thống",
    }
    action_display = action_map.get(proposal.action, f"Đang thực thi: {proposal.action}")

    return (
        f"🔧 [{_ts()}] ĐANG THỰC THI\n"
        f"\n"
        f"{action_display} — {proposal.target}\n"
        f"Vui lòng đợi xác nhận..."
    )


def status_improving(
    metric_name: str,
    current_value: float,
    previous_value: float,
    baseline: float | None = None,
) -> str:
    """📈 CẢI THIỆN — comment khi metric bắt đầu tốt lên."""
    baseline_str = f" (baseline: {baseline:.2f})" if baseline is not None else ""

    return (
        f"📈 [{_ts()}] CẢI THIỆN\n"
        f"\n"
        f"Metric: {metric_name}\n"
        f"Trước khắc phục: {previous_value:.2f}\n"
        f"Hiện tại: {current_value:.2f}{baseline_str}\n"
        f"\n"
        f"Agent đang tiếp tục theo dõi để xác nhận ổn định..."
    )


def status_worsening(
    metric_name: str,
    current_value: float,
    previous_value: float,
    detail: str = "",
) -> str:
    """🔴 CHUYỂN BIẾN XẤU — comment khi metric xấu đi sau remediation."""
    lines = [
        f"🔴 [{_ts()}] CHUYỂN BIẾN XẤU",
        "",
        f"Metric: {metric_name}",
        f"Trước: {previous_value:.2f}",
        f"Hiện tại: {current_value:.2f} ⚠️ TĂNG",
    ]
    if detail:
        lines.append(f"Chi tiết: {detail}")
    lines.append("")
    lines.append("Agent đang đánh giá lại tình hình và có thể đề xuất hành động bổ sung.")

    return "\n".join(lines)


def status_resolved(
    duration_minutes: int,
    summary: str = "",
) -> str:
    """✅ RESOLVED — comment khi incident được đóng."""
    lines = [
        f"✅ [{_ts()}] INCIDENT RESOLVED",
        "",
        f"Tổng thời gian xử lý: {duration_minutes} phút",
    ]
    if summary:
        lines.append(f"Tóm tắt: {summary}")
    lines.append("")
    lines.append("Báo cáo postmortem chi tiết sẽ được gửi qua email tới các bên liên quan.")
    lines.append("Incident sẽ được chuyển sang trạng thái 'Resolved'.")

    return "\n".join(lines)


def status_escalated(
    severity_from: Severity,
    severity_to: Severity,
    waiting_minutes: float,
) -> str:
    """⏰ NÂNG MỨC — comment khi escalate do chờ duyệt quá lâu."""
    return (
        f"⏰ [{_ts()}] NÂNG MỨC ĐỘ\n"
        f"\n"
        f"Đề xuất khắc phục đã chờ duyệt {waiting_minutes:.0f} phút mà chưa ai phê duyệt.\n"
        f"Nâng mức: {severity_from.value} → {severity_to.value}\n"
        f"\n"
        f"Sự cố vẫn đang diễn ra. Agent KHÔNG tự thực thi — vẫn chờ người phê duyệt."
    )
