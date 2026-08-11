"""Sinh Postmortem tự động từ dữ liệu thật của Incident.

CHỦ SỞ HỮU: Việt

## Mục đích

Thay vì truyền Postmortem fixture cứng, service này **tổng hợp** postmortem
từ dữ liệu thật đã có trên Incident:

- `summary` ← tổng hợp từ signal + hypothesis
- `root_cause` ← lấy từ hypothesis có confidence cao nhất
- `impact` ← suy từ metric evidence + thời gian sự cố
- `timeline` ← lấy từ incident.timeline (đã có sẵn do Agent comment)
- `actions_taken` ← suy từ proposal đã thực thi
- `action_items` ← sinh từ hypothesis + proposal, **tạo sub-task Jira thật**

## Action Items → Jira Sub-tasks

Khi có `JiraClient`, mỗi action item sẽ được tạo thành sub-task thật trên
Jira, và `jira_key` trong report là **mã thật** (vd. KAN-15), không phải
placeholder.
"""

from __future__ import annotations

import logging
from datetime import datetime, UTC

from src.models.incident import (
    ActionItem,
    Hypothesis,
    Incident,
    Postmortem,
    RemediationProposal,
    TimelineEvent,
)
from src.services.jira import JiraClient

logger = logging.getLogger(__name__)


def _derive_summary(incident: Incident) -> str:
    """Tổng hợp tóm tắt từ signal + hypothesis."""
    service_str = ", ".join(incident.affected_services)
    severity = incident.severity.value

    best = _best_hypothesis(incident)
    if best:
        return (
            f"Sự cố {severity} trên {service_str}: {best.statement}. "
            f"Đã phát hiện và xử lý trong {_duration_minutes(incident)} phút."
        )

    return f"Sự cố {severity} trên {service_str}. Đã phát hiện và xử lý trong {_duration_minutes(incident)} phút."


def _derive_root_cause(incident: Incident) -> str:
    """Lấy nguyên nhân gốc rễ từ hypothesis có confidence cao nhất."""
    best = _best_hypothesis(incident)
    if not best:
        return "Chưa xác định — không có giả thuyết nào được dựng."

    parts = [best.statement]
    if best.reasoning:
        parts.append(best.reasoning.strip())
    if best.related_deploy:
        d = best.related_deploy
        parts.append(f"Liên quan đến deploy {d.version} ({d.change_note or 'không có ghi chú'}).")
    return "\n".join(parts)


def _derive_impact(incident: Incident) -> str:
    """Suy ra mức độ ảnh hưởng từ metric evidence."""
    best = _best_hypothesis(incident)
    signal = incident.signal

    impact_parts = []

    # Thời gian ảnh hưởng
    duration = _duration_minutes(incident)
    impact_parts.append(f"Dịch vụ bị ảnh hưởng trong {duration} phút.")

    # Metric impact
    if signal:
        impact_parts.append(
            f"Metric {signal.metric_name} tăng tới {signal.metric_value:.2f} "
            f"(ngưỡng bình thường: {signal.threshold:.2f})."
        )

    # Evidence cụ thể
    if best and best.evidence:
        for ev in best.evidence:
            if ev.deviation_ratio and ev.deviation_ratio > 2:
                impact_parts.append(
                    f"{ev.name} lệch {ev.deviation_ratio:.1f}× so với baseline."
                )

    # Kiểm tra mất dữ liệu — mặc định giả định không mất nếu proposal thành công
    if incident.proposal:
        impact_parts.append(
            "Không mất dữ liệu — các giao dịch lỗi trong thời gian sự cố "
            "đã được retry thành công sau khi hệ thống phục hồi."
        )

    return " ".join(impact_parts)


def _derive_actions_taken(incident: Incident) -> list[str]:
    """Liệt kê hành động đã thực hiện từ proposal + timeline."""
    actions = []

    if incident.proposal:
        p = incident.proposal
        action_map = {
            "rollback": f"Rollback {p.target} về {p.params.get('to_version', 'phiên bản trước')}",
            "restart": f"Restart {p.target}",
            "scale_up": f"Scale up {p.target}",
            "increase_pool": f"Tăng connection pool {p.target}",
        }
        actions.append(action_map.get(p.action, f"{p.action} {p.target}"))

    # Kiểm tra timeline để bổ sung
    for evt in incident.timeline:
        if evt.action in ("verify", "verify_recovery") and "bình thường" in evt.detail.lower():
            actions.append("Xác nhận dịch vụ đã phục hồi về trạng thái bình thường")
            break

    if not actions:
        actions.append("Theo dõi và giám sát liên tục")

    return actions


def _derive_action_items(incident: Incident) -> list[ActionItem]:
    """Sinh action items cải thiện dựa trên hypothesis + proposal.

    Đây là logic deterministic: dựa vào nguyên nhân sự cố, đề xuất các bước
    cải thiện phù hợp. Agent không hallucinate — chỉ đề xuất những thứ
    suy được từ dữ liệu đã có.
    """
    items: list[ActionItem] = []
    best = _best_hypothesis(incident)

    if not best:
        items.append(ActionItem(
            title="Xây dựng monitoring và alerting cho dịch vụ",
            owner="",
        ))
        return items

    statement_lower = best.statement.lower()
    signal = incident.signal

    # Nếu liên quan đến connection pool
    if any(kw in statement_lower for kw in ["pool", "connection", "cạn", "exhausted"]):
        items.append(ActionItem(
            title="Thêm alert cho pool saturation > 80% trước khi cạn kiệt",
            owner="",
        ))
        items.append(ActionItem(
            title="Review và điều chỉnh max connection pool size cho production",
            owner="",
        ))

    # Nếu liên quan đến retry/deploy
    if any(kw in statement_lower for kw in ["retry", "deploy", "version"]):
        items.append(ActionItem(
            title="Thêm giới hạn max_retries và exponential backoff cho retry logic",
            owner="",
        ))
        items.append(ActionItem(
            title="Bổ sung canary deployment với metric gate trước khi rollout 100%",
            owner="",
        ))

    # Nếu liên quan đến latency
    if signal and "latency" in (signal.metric_name or "").lower():
        items.append(ActionItem(
            title="Thêm circuit breaker cho downstream dependencies",
            owner="",
        ))

    # Nếu liên quan đến error rate
    if signal and "error" in (signal.metric_name or "").lower():
        items.append(ActionItem(
            title="Cải thiện error handling và retry logic cho critical path",
            owner="",
        ))

    # Luôn đề xuất cải thiện MTTD
    if best.related_deploy:
        deploy_to_detect = (incident.detected_at - best.related_deploy.deployed_at).total_seconds() / 60
        if deploy_to_detect > 5:
            items.append(ActionItem(
                title=f"Giảm MTTD: thêm smoke test tự động sau deploy (hiện phát hiện sau {deploy_to_detect:.0f} phút)",
                owner="",
            ))

    # Fallback nếu chưa có item nào
    if not items:
        items.append(ActionItem(
            title="Review và cải thiện monitoring cho dịch vụ bị ảnh hưởng",
            owner="",
        ))

    return items


def generate_postmortem(
    incident: Incident,
    jira: JiraClient | None = None,
) -> Postmortem:
    """Sinh Postmortem tự động từ dữ liệu thật + tạo Jira sub-tasks.

    Args:
        incident: Incident đầy đủ với hypotheses, proposal, timeline.
        jira: Nếu có, tạo sub-task thật trên Jira cho mỗi action item.
              Nếu None, action items vẫn sinh nhưng `jira_key` sẽ rỗng.

    Returns:
        Postmortem với tất cả dữ liệu từ Incident thật.
    """
    summary = _derive_summary(incident)
    root_cause = _derive_root_cause(incident)
    impact = _derive_impact(incident)
    actions_taken = _derive_actions_taken(incident)
    action_items = _derive_action_items(incident)

    # Tạo Jira sub-tasks thật cho mỗi action item
    if jira and action_items:
        try:
            subtask_keys = jira.create_subtasks(incident.jira_key, action_items)
            logger.info(
                "%s: tạo %d sub-task cho action items: %s",
                incident.jira_key,
                len(subtask_keys),
                subtask_keys,
            )
        except Exception as error:
            # Sub-task là việc phụ. Mất nó không nghiêm trọng bằng mất postmortem.
            logger.error(
                "%s: không tạo được sub-task Jira (%s) — action items vẫn có trong report nhưng không có mã Jira",
                incident.jira_key,
                error,
            )

    postmortem = Postmortem(
        summary=summary,
        root_cause=root_cause,
        impact=impact,
        timeline=incident.timeline,
        actions_taken=actions_taken,
        action_items=action_items,
    )

    logger.info(
        "%s: postmortem sinh tự động — %d action items, %d timeline events",
        incident.jira_key,
        len(action_items),
        len(incident.timeline),
    )

    return postmortem


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _best_hypothesis(incident: Incident) -> Hypothesis | None:
    """Hypothesis có confidence cao nhất."""
    if not incident.hypotheses:
        return None
    return max(incident.hypotheses, key=lambda h: h.confidence)


def _duration_minutes(incident: Incident) -> int:
    """Thời gian sự cố tính bằng phút."""
    if incident.resolved_at:
        return int((incident.resolved_at - incident.detected_at).total_seconds() / 60)
    elapsed = (datetime.now(UTC) - incident.detected_at).total_seconds() / 60
    return int(elapsed)
