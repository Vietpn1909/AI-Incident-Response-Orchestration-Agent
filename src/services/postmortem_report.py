"""Sinh báo cáo Postmortem — email body vắn tắt + file report HTML chi tiết.

CHỦ SỞ HỮU: Việt

## Hai sản phẩm từ một Incident

1. **Email body** (vắn tắt): cho manager và các bộ phận khác nắm tình hình.
   Dùng **ngôn ngữ kinh doanh**, tránh thuật ngữ kỹ thuật. Trả lời 3 câu:
   chuyện gì đã xảy ra, nguyên nhân là gì, đã xử lý chưa.

2. **File HTML đính kèm** (chi tiết): cho đội IT/kỹ thuật hiểu sâu. Bao gồm
   timeline đầy đủ, bằng chứng metric, log evidence, deploy liên quan, hành
   động đã thực hiện, action items cải thiện, và phân tích 5 Whys.

## Nguyên tắc blameless

Theo văn hoá blameless — mô tả hệ thống và quy trình, không chỉ trích cá nhân.

## Cải tiến v2 (11/08/2026) — theo feedback review

1. Ngôn ngữ kinh doanh cho email body (không dùng thuật ngữ kỹ thuật)
2. Làm nổi bật "Không mất dữ liệu" bằng badge xanh (success color)
3. Hiển thị giờ địa phương UTC+7 song song UTC
4. Thêm MTTD / MTTR incident metrics
5. Cấu trúc 5 Whys cho Root Cause Analysis
6. Action items có Jira hyperlink
7. Copy-to-clipboard cho log và runbook trong detailed report
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone, UTC

from src.models.incident import Incident, Postmortem


# ---------------------------------------------------------------------------
# Timezone helpers
# ---------------------------------------------------------------------------
_TZ_LOCAL = timezone(timedelta(hours=7))  # UTC+7


def _fmt_time(dt: datetime | None, *, local: bool = True) -> str:
    """Format datetime thành chuỗi đọc được.

    Mặc định hiển thị song song: ``22:32 (UTC+7) / 15:32 UTC``.
    """
    if dt is None:
        return "—"
    utc_str = dt.strftime("%H:%M UTC")
    if not local:
        return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
    local_dt = dt.astimezone(_TZ_LOCAL)
    return f"{local_dt.strftime('%H:%M')} (UTC+7) / {utc_str}"


def _fmt_time_full(dt: datetime | None) -> str:
    """Format đầy đủ ngày + giờ song song."""
    if dt is None:
        return "—"
    local_dt = dt.astimezone(_TZ_LOCAL)
    return f"{local_dt.strftime('%Y-%m-%d %H:%M')} (UTC+7) / {dt.strftime('%H:%M')} UTC"


def _fmt_duration(detected: datetime, resolved: datetime | None) -> str:
    """Thời gian xử lý sự cố."""
    if resolved is None:
        return "Chưa resolved"
    delta = resolved - detected
    minutes = int(delta.total_seconds() / 60)
    if minutes < 60:
        return f"{minutes} phút"
    hours = minutes // 60
    remaining = minutes % 60
    return f"{hours} giờ {remaining} phút"


# ---------------------------------------------------------------------------
# Incident Metrics — MTTD / MTTR
# ---------------------------------------------------------------------------


def _compute_mttd(incident: Incident) -> str:
    """Mean Time To Detect — từ lúc deploy (nếu có) đến lúc phát hiện."""
    if not incident.hypotheses:
        return "—"
    best = max(incident.hypotheses, key=lambda h: h.confidence)
    if best.related_deploy:
        delta = incident.detected_at - best.related_deploy.deployed_at
        minutes = int(delta.total_seconds() / 60)
        return f"{minutes} phút"
    return "—"


def _compute_mttr(incident: Incident) -> str:
    """Mean Time To Recovery — từ lúc phát hiện đến lúc resolved."""
    if incident.resolved_at is None:
        return "Chưa resolved"
    delta = incident.resolved_at - incident.detected_at
    minutes = int(delta.total_seconds() / 60)
    return f"{minutes} phút"


def _compute_approval_wait(incident: Incident) -> str:
    """Thời gian chờ phê duyệt — từ propose đến approve trong timeline."""
    propose_at = None
    approve_at = None
    events = incident.timeline or (incident.postmortem.timeline if incident.postmortem else [])
    for evt in events:
        if evt.action in ("propose_remediation", "propose") and propose_at is None:
            propose_at = evt.at
        if evt.action in ("approve",) and approve_at is None:
            approve_at = evt.at
    if propose_at and approve_at:
        delta = approve_at - propose_at
        minutes = int(delta.total_seconds() / 60)
        return f"{minutes} phút"
    return "—"


# ---------------------------------------------------------------------------
# Email body — vắn tắt cho manager (ngôn ngữ kinh doanh)
# ---------------------------------------------------------------------------


def build_email_body(incident: Incident) -> str:
    """Sinh email body HTML vắn tắt — cho manager và các bộ phận phi kỹ thuật.

    **Ngôn ngữ kinh doanh**: tránh thuật ngữ kỹ thuật, tập trung vào tác động
    lên khách hàng và dịch vụ.
    """
    postmortem = incident.postmortem
    severity = incident.severity.value
    services = ", ".join(incident.affected_services) or "—"
    duration = _fmt_duration(incident.detected_at, incident.resolved_at)
    mttd = _compute_mttd(incident)
    mttr = _compute_mttr(incident)
    approval_wait = _compute_approval_wait(incident)

    # Hypothesis tốt nhất
    best_hyp = max(incident.hypotheses, key=lambda h: h.confidence) if incident.hypotheses else None
    root_cause = postmortem.root_cause if postmortem else (best_hyp.statement if best_hyp else "Chưa xác định")
    impact = postmortem.impact if postmortem else "Đang đánh giá"
    summary = postmortem.summary if postmortem else f"Sự cố {severity} trên {services}"

    # Remediation info — ngôn ngữ kinh doanh
    remedy = "Chưa thực hiện"
    if incident.proposal:
        action_map = {
            "rollback": "Khôi phục phiên bản trước",
            "restart": "Khởi động lại dịch vụ",
            "scale_up": "Tăng tài nguyên hệ thống",
        }
        remedy = action_map.get(incident.proposal.action, incident.proposal.action)
        remedy += f" ({incident.proposal.target})"

    # Phát hiện nếu có thông tin "không mất dữ liệu"
    data_safe = False
    data_safe_msg = ""
    if impact and ("không mất dữ liệu" in impact.lower() or "no data loss" in impact.lower()):
        data_safe = True
        data_safe_msg = "Không có dữ liệu bị mất — các giao dịch lỗi đã được xử lý thành công sau khắc phục"

    # Badge reassurance
    reassurance_html = ""
    if data_safe:
        reassurance_html = f"""
        <div style="background:#f0fdf4;border:1px solid #86efac;border-radius:8px;padding:12px 16px;margin:0 0 16px">
            <span style="color:#16a34a;font-weight:700;font-size:15px">✅ {data_safe_msg}</span>
        </div>"""

    # Action items
    action_items_html = ""
    if postmortem and postmortem.action_items:
        items = ""
        for ai in postmortem.action_items:
            jira_link = f' <a href="#" style="color:#2563eb">[{ai.jira_key}]</a>' if ai.jira_key else ""
            items += f"<li>{ai.title}{jira_link}</li>"
        action_items_html = f"""
        <tr>
            <td style="padding:8px 12px;color:#6b7280;font-weight:600;vertical-align:top;width:160px">Cải thiện</td>
            <td style="padding:8px 12px"><ul style="margin:0;padding-left:20px">{items}</ul></td>
        </tr>"""

    # Incident metrics row
    metrics_html = f"""
        <tr style="border-bottom:1px solid #f3f4f6">
            <td style="padding:8px 12px;color:#6b7280;font-weight:600">Phát hiện sau</td>
            <td style="padding:8px 12px">{mttd} <span style="color:#9ca3af;font-size:12px">(MTTD)</span></td>
        </tr>
        <tr style="border-bottom:1px solid #f3f4f6">
            <td style="padding:8px 12px;color:#6b7280;font-weight:600">Phục hồi trong</td>
            <td style="padding:8px 12px">{mttr} <span style="color:#9ca3af;font-size:12px">(MTTR)</span></td>
        </tr>"""
    if approval_wait != "—":
        metrics_html += f"""
        <tr style="border-bottom:1px solid #f3f4f6">
            <td style="padding:8px 12px;color:#6b7280;font-weight:600">Chờ phê duyệt</td>
            <td style="padding:8px 12px">{approval_wait}</td>
        </tr>"""

    return f"""\
<div style="font-family:'Segoe UI',Arial,sans-serif;max-width:640px;margin:0 auto;color:#1f2937">

    <div style="background:linear-gradient(135deg,#1e3a5f,#2563eb);padding:24px 28px;border-radius:12px 12px 0 0">
        <h1 style="color:#ffffff;margin:0;font-size:20px">📋 Báo cáo sự cố</h1>
        <p style="color:#93c5fd;margin:6px 0 0;font-size:14px">{incident.jira_key} — {severity}</p>
    </div>

    <div style="background:#ffffff;border:1px solid #e5e7eb;border-top:none;padding:20px 28px;border-radius:0 0 12px 12px">

        {reassurance_html}

        <h2 style="color:#1e3a5f;font-size:16px;margin:0 0 16px">{summary}</h2>

        <table style="width:100%;border-collapse:collapse;font-size:14px">
            <tr style="border-bottom:1px solid #f3f4f6">
                <td style="padding:8px 12px;color:#6b7280;font-weight:600;width:160px">Dịch vụ ảnh hưởng</td>
                <td style="padding:8px 12px">{services}</td>
            </tr>
            <tr style="border-bottom:1px solid #f3f4f6">
                <td style="padding:8px 12px;color:#6b7280;font-weight:600">Phát hiện lúc</td>
                <td style="padding:8px 12px">{_fmt_time(incident.detected_at)}</td>
            </tr>
            <tr style="border-bottom:1px solid #f3f4f6">
                <td style="padding:8px 12px;color:#6b7280;font-weight:600">Tổng thời gian gián đoạn</td>
                <td style="padding:8px 12px;font-weight:600">{duration}</td>
            </tr>
            {metrics_html}
            <tr style="border-bottom:1px solid #f3f4f6">
                <td style="padding:8px 12px;color:#6b7280;font-weight:600">Nguyên nhân</td>
                <td style="padding:8px 12px"><strong>{root_cause}</strong></td>
            </tr>
            <tr style="border-bottom:1px solid #f3f4f6">
                <td style="padding:8px 12px;color:#6b7280;font-weight:600">Mức độ ảnh hưởng</td>
                <td style="padding:8px 12px">{impact}</td>
            </tr>
            <tr style="border-bottom:1px solid #f3f4f6">
                <td style="padding:8px 12px;color:#6b7280;font-weight:600">Biện pháp khắc phục</td>
                <td style="padding:8px 12px">{remedy}</td>
            </tr>{action_items_html}
        </table>

        <p style="margin:20px 0 0;font-size:13px;color:#9ca3af">
            📎 Báo cáo kỹ thuật chi tiết được đính kèm:
            <strong>postmortem_{incident.jira_key}.html</strong>
        </p>
    </div>

    <p style="text-align:center;font-size:11px;color:#9ca3af;margin:12px 0 0">
        Báo cáo tự động bởi AI20K Incident Agent — blameless postmortem
    </p>
</div>"""


# ---------------------------------------------------------------------------
# File HTML đính kèm — chi tiết cho đội kỹ thuật
# ---------------------------------------------------------------------------

# JavaScript snippet cho copy-to-clipboard
_COPY_JS = """\
function copyText(btn) {
    const block = btn.closest('.copy-block');
    const text = block.querySelector('.copy-content').innerText;
    navigator.clipboard.writeText(text).then(function() {
        btn.textContent = '✓ Copied';
        btn.style.color = '#16a34a';
        setTimeout(function() { btn.textContent = '📋 Copy'; btn.style.color = '#6b7280'; }, 2000);
    });
}"""


def _copy_block(content: str, lang: str = "log") -> str:
    """Wrap nội dung trong khối có nút copy-to-clipboard."""
    bg = "#1e293b" if lang == "log" else "#f8fafc"
    color = "#e2e8f0" if lang == "log" else "#1f2937"
    return f"""\
<div class="copy-block" style="position:relative;margin-bottom:8px">
    <button onclick="copyText(this)" style="position:absolute;top:6px;right:8px;background:none;border:1px solid #475569;border-radius:4px;padding:2px 8px;font-size:11px;color:#6b7280;cursor:pointer">📋 Copy</button>
    <pre class="copy-content" style="background:{bg};color:{color};padding:10px 12px;border-radius:6px;font-size:12px;font-family:'Consolas','Courier New',monospace;overflow-x:auto;margin:0;white-space:pre-wrap">{content}</pre>
</div>"""


def build_detailed_report(incident: Incident) -> str:
    """Sinh file HTML chi tiết — đính kèm email, cho đội IT đọc.

    Bao gồm 10 sections + MTTD/MTTR metrics + 5 Whys RCA + copy-to-clipboard.
    """
    postmortem = incident.postmortem
    severity = incident.severity.value
    services = ", ".join(incident.affected_services) or "—"
    duration = _fmt_duration(incident.detected_at, incident.resolved_at)
    mttd = _compute_mttd(incident)
    mttr = _compute_mttr(incident)
    approval_wait = _compute_approval_wait(incident)

    best_hyp = max(incident.hypotheses, key=lambda h: h.confidence) if incident.hypotheses else None
    root_cause = postmortem.root_cause if postmortem else (best_hyp.statement if best_hyp else "Chưa xác định")
    confidence = f"{best_hyp.confidence:.0%}" if best_hyp else "—"
    reasoning = best_hyp.reasoning if best_hyp and best_hyp.reasoning else "—"
    impact = postmortem.impact if postmortem else "Đang đánh giá"
    summary = postmortem.summary if postmortem else f"Sự cố {severity} trên {services}"

    # Data safe badge
    data_safe_html = ""
    if impact and ("không mất dữ liệu" in impact.lower() or "no data loss" in impact.lower()):
        data_safe_html = """
        <div style="background:#f0fdf4;border:1px solid #86efac;border-radius:8px;padding:12px 16px;margin:0 0 20px">
            <span style="color:#16a34a;font-weight:700;font-size:15px">✅ Không có dữ liệu bị mất — các giao dịch lỗi đã được xử lý thành công sau khắc phục</span>
        </div>"""

    # Incident Metrics
    metrics_html = f"""
        <table style="width:100%;border-collapse:collapse;font-size:14px">
            <tr><td style="padding:6px 12px;color:#6b7280;width:200px">Tổng thời gian gián đoạn</td><td style="padding:6px 12px;font-weight:600">{duration}</td></tr>
            <tr><td style="padding:6px 12px;color:#6b7280">MTTD (phát hiện)</td><td style="padding:6px 12px;font-weight:600">{mttd}</td></tr>
            <tr><td style="padding:6px 12px;color:#6b7280">MTTR (phục hồi)</td><td style="padding:6px 12px;font-weight:600">{mttr}</td></tr>
            <tr><td style="padding:6px 12px;color:#6b7280">Thời gian chờ phê duyệt</td><td style="padding:6px 12px">{approval_wait}</td></tr>
        </table>"""

    # Timeline
    timeline_rows = ""
    all_events = (postmortem.timeline if postmortem else []) or incident.timeline
    for evt in all_events:
        actor_style = 'color:#2563eb;font-weight:600' if evt.actor == 'agent' else 'font-weight:600'
        timeline_rows += f"""
            <tr>
                <td style="padding:8px 12px;white-space:nowrap;color:#6b7280;font-size:13px">{_fmt_time(evt.at)}</td>
                <td style="padding:8px 12px;{actor_style}">{evt.actor}</td>
                <td style="padding:8px 12px">{evt.action}</td>
                <td style="padding:8px 12px;color:#6b7280">{evt.detail}</td>
            </tr>"""
    if not timeline_rows:
        timeline_rows = '<tr><td colspan="4" style="padding:8px 12px;color:#9ca3af">Không có dữ liệu timeline</td></tr>'

    # Metric evidence
    metric_rows = ""
    if best_hyp:
        for ev in best_hyp.evidence:
            baseline_str = f"{ev.baseline:.4g}{ev.unit}" if ev.baseline is not None else "—"
            ratio_str = f"×{ev.deviation_ratio:.1f}" if ev.deviation_ratio else "—"
            ratio_color = "#dc2626" if ev.deviation_ratio and ev.deviation_ratio > 3 else "#ea580c"
            metric_rows += f"""
            <tr>
                <td style="padding:6px 12px;font-family:monospace;font-size:13px">{ev.name}</td>
                <td style="padding:6px 12px;text-align:right;font-weight:600">{ev.value:.4g}{ev.unit}</td>
                <td style="padding:6px 12px;text-align:right">{baseline_str}</td>
                <td style="padding:6px 12px;text-align:right;color:{ratio_color};font-weight:600">{ratio_str}</td>
            </tr>"""
    if not metric_rows:
        metric_rows = '<tr><td colspan="4" style="padding:6px 12px;color:#9ca3af">Không có metric evidence</td></tr>'

    # Log evidence — với copy-to-clipboard
    log_blocks = ""
    if best_hyp:
        for le in best_hyp.log_evidence:
            ts = f" [{le.timestamp}]" if le.timestamp else ""
            log_content = f"[{le.level}]{ts} [{le.source}] {le.message}"
            log_blocks += _copy_block(log_content, "log")
    if not log_blocks:
        log_blocks = '<p style="color:#9ca3af">Không có log evidence</p>'

    # Deploy info
    deploy_html = ""
    if best_hyp and best_hyp.related_deploy:
        d = best_hyp.related_deploy
        deploy_html = f"""
        <table style="width:100%;border-collapse:collapse;font-size:14px;margin-bottom:8px">
            <tr><td style="padding:4px 12px;color:#6b7280;width:140px">Version</td><td style="padding:4px 12px;font-family:monospace;font-weight:600">{d.version}</td></tr>
            <tr><td style="padding:4px 12px;color:#6b7280">Deploy lúc</td><td style="padding:4px 12px">{_fmt_time(d.deployed_at)}</td></tr>
            <tr><td style="padding:4px 12px;color:#6b7280">Deploy bởi</td><td style="padding:4px 12px">{d.deployed_by or '—'}</td></tr>
            <tr><td style="padding:4px 12px;color:#6b7280">Commit</td><td style="padding:4px 12px;font-family:monospace">{d.commit_sha or '—'}</td></tr>
            <tr><td style="padding:4px 12px;color:#6b7280">Ghi chú thay đổi</td><td style="padding:4px 12px">{d.change_note or '—'}</td></tr>
        </table>"""
    else:
        deploy_html = '<p style="color:#9ca3af">Không có deploy nào liên quan trong khung thời gian sự cố.</p>'

    # 5 Whys RCA
    five_whys_html = ""
    if reasoning and reasoning != "—":
        # Parse reasoning thành các bước — nếu có dạng số 1. 2. 3.
        lines = [l.strip() for l in reasoning.strip().split("\n") if l.strip()]
        if len(lines) >= 2:
            why_items = ""
            for i, line in enumerate(lines, 1):
                # Bỏ prefix "1." nếu có
                clean = line.lstrip("0123456789.").strip()
                if clean:
                    label = f"Why #{i}"
                    why_items += f"""
                <div style="margin-bottom:10px;padding-left:16px;border-left:3px solid {'#dc2626' if i == len(lines) else '#e5e7eb'}">
                    <span style="color:#6b7280;font-size:12px;font-weight:600">{label}</span><br/>
                    <span style="font-size:14px">{clean}</span>
                </div>"""
            five_whys_html = f"""
            <div style="margin-top:12px">
                <h4 style="color:#1e3a5f;font-size:14px;margin:0 0 8px">Phân tích 5 Whys</h4>
                {why_items}
            </div>"""
        else:
            five_whys_html = f'<p style="font-size:14px;margin-top:8px">{reasoning}</p>'

    # Remediation — với copy-to-clipboard cho runbook
    remedy_html = ""
    if incident.proposal:
        p = incident.proposal
        params_str = ", ".join(f"{k}={v}" for k, v in p.params.items()) if p.params else "—"

        runbook_html = '<span style="color:#9ca3af">—</span>'
        if p.runbook:
            runbook_html = _copy_block(p.runbook, "cmd")

        remedy_html = f"""
        <table style="width:100%;border-collapse:collapse;font-size:14px;margin-bottom:12px">
            <tr><td style="padding:4px 12px;color:#6b7280;width:140px">Hành động</td><td style="padding:4px 12px;font-weight:600">{p.action}</td></tr>
            <tr><td style="padding:4px 12px;color:#6b7280">Đối tượng</td><td style="padding:4px 12px;font-family:monospace">{p.target}</td></tr>
            <tr><td style="padding:4px 12px;color:#6b7280">Tham số</td><td style="padding:4px 12px">{params_str}</td></tr>
            <tr><td style="padding:4px 12px;color:#6b7280">Rủi ro</td><td style="padding:4px 12px">{p.risk or '—'}</td></tr>
        </table>
        <h4 style="color:#1e3a5f;font-size:14px;margin:8px 0">Runbook</h4>
        {runbook_html}"""
    else:
        remedy_html = '<p style="color:#9ca3af">Chưa có đề xuất khắc phục.</p>'

    # Actions taken
    actions_taken_html = ""
    if postmortem and postmortem.actions_taken:
        items = "".join(f"<li>{a}</li>" for a in postmortem.actions_taken)
        actions_taken_html = f'<ul style="margin:0;padding-left:20px;font-size:14px">{items}</ul>'
    else:
        actions_taken_html = '<p style="color:#9ca3af">—</p>'

    # Action items — với Jira hyperlink
    action_items_html = ""
    if postmortem and postmortem.action_items:
        rows = ""
        for ai in postmortem.action_items:
            jira_cell = '—'
            if ai.jira_key:
                jira_cell = f'<a href="#" style="color:#2563eb;text-decoration:none;font-weight:600">{ai.jira_key}</a>'
            rows += f"""
            <tr>
                <td style="padding:6px 12px">{ai.title}</td>
                <td style="padding:6px 12px;text-align:center">{ai.owner or '—'}</td>
                <td style="padding:6px 12px;text-align:center;font-family:monospace">{jira_cell}</td>
            </tr>"""
        action_items_html = f"""
        <table style="width:100%;border-collapse:collapse;font-size:14px">
            <tr style="background:#f8fafc">
                <th style="padding:8px 12px;text-align:left;color:#374151">Việc cần làm</th>
                <th style="padding:8px 12px;text-align:center;color:#374151;width:120px">Người phụ trách</th>
                <th style="padding:8px 12px;text-align:center;color:#374151;width:100px">Jira</th>
            </tr>
            {rows}
        </table>"""
    else:
        action_items_html = '<p style="color:#9ca3af">Chưa có action item.</p>'

    # Signal info
    signal_html = ""
    if incident.signal:
        s = incident.signal
        signal_html = f"""
        <table style="width:100%;border-collapse:collapse;font-size:14px">
            <tr><td style="padding:4px 12px;color:#6b7280;width:180px">Metric kích hoạt</td><td style="padding:4px 12px;font-family:monospace">{s.metric_name}</td></tr>
            <tr><td style="padding:4px 12px;color:#6b7280">Giá trị</td><td style="padding:4px 12px;font-weight:600">{s.metric_value:.4g} (ngưỡng: {s.threshold:.4g})</td></tr>
            <tr><td style="padding:4px 12px;color:#6b7280">Vượt ngưỡng liên tục</td><td style="padding:4px 12px">{s.breached_for_seconds:.0f} giây</td></tr>
        </table>"""

    now_str = datetime.now(_TZ_LOCAL).strftime("%Y-%m-%d %H:%M (UTC+7)")

    return f"""\
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Postmortem — {incident.jira_key}</title>
    <style>
        body {{ font-family: 'Segoe UI', Arial, sans-serif; color: #1f2937; background: #f9fafb; margin: 0; padding: 20px; }}
        .container {{ max-width: 900px; margin: 0 auto; background: #ffffff; border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); overflow: hidden; }}
        .header {{ background: linear-gradient(135deg, #1e3a5f, #2563eb); color: white; padding: 32px; }}
        .header h1 {{ margin: 0; font-size: 24px; }}
        .header p {{ color: #93c5fd; margin: 8px 0 0; }}
        .content {{ padding: 28px 32px; }}
        .section {{ margin-bottom: 28px; }}
        .section-title {{ color: #1e3a5f; font-size: 16px; font-weight: 700; border-bottom: 2px solid #2563eb; padding-bottom: 6px; margin-bottom: 12px; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th {{ text-align: left; background: #f8fafc; }}
        tr:nth-child(even) {{ background: #f9fafb; }}
        td, th {{ border-bottom: 1px solid #f3f4f6; }}
        .badge {{ display: inline-block; padding: 2px 10px; border-radius: 12px; font-size: 12px; font-weight: 600; }}
        .badge-p1 {{ background: #fef2f2; color: #dc2626; }}
        .badge-p2 {{ background: #fff7ed; color: #ea580c; }}
        .badge-p3 {{ background: #fefce8; color: #ca8a04; }}
        .badge-p4 {{ background: #f0fdf4; color: #16a34a; }}
        .footer {{ text-align: center; padding: 16px; color: #9ca3af; font-size: 12px; border-top: 1px solid #f3f4f6; }}
        code {{ background: #f1f5f9; padding: 2px 6px; border-radius: 4px; font-size: 13px; }}
        .metric-card {{ display: inline-block; text-align: center; padding: 12px 20px; margin: 0 8px 8px 0; border-radius: 8px; border: 1px solid #e5e7eb; min-width: 120px; }}
        .metric-value {{ font-size: 22px; font-weight: 700; color: #1e3a5f; }}
        .metric-label {{ font-size: 11px; color: #6b7280; margin-top: 2px; }}
    </style>
    <script>{_COPY_JS}</script>
</head>
<body>
<div class="container">

    <div class="header">
        <h1>📋 Postmortem Report</h1>
        <p>{incident.jira_key} &mdash; <span class="badge badge-{severity.lower()}">{severity}</span></p>
    </div>

    <div class="content">

        {data_safe_html}

        <!-- 1. Tổng quan -->
        <div class="section">
            <div class="section-title">1. Tổng quan</div>
            <table style="font-size:14px">
                <tr><td style="padding:6px 12px;color:#6b7280;width:180px">Tóm tắt</td><td style="padding:6px 12px;font-weight:600">{summary}</td></tr>
                <tr><td style="padding:6px 12px;color:#6b7280">Dịch vụ ảnh hưởng</td><td style="padding:6px 12px">{services}</td></tr>
                <tr><td style="padding:6px 12px;color:#6b7280">Mức độ</td><td style="padding:6px 12px"><span class="badge badge-{severity.lower()}">{severity}</span></td></tr>
                <tr><td style="padding:6px 12px;color:#6b7280">Phát hiện lúc</td><td style="padding:6px 12px">{_fmt_time_full(incident.detected_at)}</td></tr>
                <tr><td style="padding:6px 12px;color:#6b7280">Resolved lúc</td><td style="padding:6px 12px">{_fmt_time_full(incident.resolved_at)}</td></tr>
            </table>
        </div>

        <!-- 2. Incident Metrics -->
        <div class="section">
            <div class="section-title">2. Chỉ số hiệu suất xử lý (Incident Metrics)</div>
            <div style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:8px">
                <div class="metric-card">
                    <div class="metric-value">{mttd}</div>
                    <div class="metric-label">MTTD — Thời gian phát hiện</div>
                </div>
                <div class="metric-card">
                    <div class="metric-value">{mttr}</div>
                    <div class="metric-label">MTTR — Thời gian phục hồi</div>
                </div>
                <div class="metric-card">
                    <div class="metric-value">{duration}</div>
                    <div class="metric-label">Tổng thời gian gián đoạn</div>
                </div>
                <div class="metric-card">
                    <div class="metric-value">{approval_wait}</div>
                    <div class="metric-label">Thời gian chờ phê duyệt</div>
                </div>
            </div>
            {metrics_html}
        </div>

        <!-- 3. Tín hiệu kích hoạt -->
        <div class="section">
            <div class="section-title">3. Tín hiệu kích hoạt (Trigger Signal)</div>
            {signal_html or '<p style="color:#9ca3af">—</p>'}
        </div>

        <!-- 4. Chẩn đoán nguyên nhân gốc -->
        <div class="section">
            <div class="section-title">4. Chẩn đoán nguyên nhân gốc (Root Cause Analysis)</div>
            <table style="font-size:14px">
                <tr><td style="padding:6px 12px;color:#6b7280;width:180px">Nguyên nhân</td><td style="padding:6px 12px;font-weight:600">{root_cause}</td></tr>
                <tr><td style="padding:6px 12px;color:#6b7280">Độ tin cậy</td><td style="padding:6px 12px">{confidence}</td></tr>
                <tr><td style="padding:6px 12px;color:#6b7280">Tác động</td><td style="padding:6px 12px">{impact}</td></tr>
            </table>
            {five_whys_html}
        </div>

        <!-- 5. Bằng chứng Metric -->
        <div class="section">
            <div class="section-title">5. Bằng chứng Metric (Metric Evidence)</div>
            <table style="font-size:14px">
                <tr style="background:#f8fafc">
                    <th style="padding:8px 12px">Tên metric</th>
                    <th style="padding:8px 12px;text-align:right">Giá trị đo</th>
                    <th style="padding:8px 12px;text-align:right">Baseline</th>
                    <th style="padding:8px 12px;text-align:right">Độ lệch</th>
                </tr>
                {metric_rows}
            </table>
        </div>

        <!-- 6. Bằng chứng Log -->
        <div class="section">
            <div class="section-title">6. Bằng chứng Log (Log Evidence)</div>
            {log_blocks}
        </div>

        <!-- 7. Deploy liên quan -->
        <div class="section">
            <div class="section-title">7. Deploy liên quan</div>
            {deploy_html}
        </div>

        <!-- 8. Timeline -->
        <div class="section">
            <div class="section-title">8. Dòng thời gian (Timeline)</div>
            <table style="font-size:14px">
                <tr style="background:#f8fafc">
                    <th style="padding:8px 12px">Thời gian</th>
                    <th style="padding:8px 12px">Actor</th>
                    <th style="padding:8px 12px">Hành động</th>
                    <th style="padding:8px 12px">Chi tiết</th>
                </tr>
                {timeline_rows}
            </table>
        </div>

        <!-- 9. Hành động khắc phục -->
        <div class="section">
            <div class="section-title">9. Hành động khắc phục (Remediation)</div>
            {remedy_html}
        </div>

        <!-- 10. Các bước đã thực hiện -->
        <div class="section">
            <div class="section-title">10. Các bước đã thực hiện</div>
            {actions_taken_html}
        </div>

        <!-- 11. Action Items cải thiện -->
        <div class="section">
            <div class="section-title">11. Action Items — Cải thiện sau sự cố</div>
            {action_items_html}
        </div>

    </div>

    <div class="footer">
        Báo cáo tự động bởi AI20K Incident Agent — Blameless Postmortem<br/>
        Sinh lúc: {now_str}
    </div>

</div>
</body>
</html>"""
