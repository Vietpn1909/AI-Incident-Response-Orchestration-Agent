"""`RealJiraClient` — cài đặt [contract ③](client.py) trên Jira Cloud thật.

Thay `FakeJiraClient` bằng class này là Agent chạy với Jira thật, không phải sửa
code Agent (đó là mục đích của Protocol).

Ràng buộc của team-managed project đã kiểm chứng ngày 2026-07-29 và xử lý ở đây:

- Không dùng được custom field → severity và affected_service lưu bằng **label**,
  quy ước ở [mapping.py](mapping.py)
- Không đặt được điều kiện phân quyền lên transition → cổng phê duyệt nằm ở
  [hitl.py](../hitl.py), dựa trên `get_transition_author()` đọc changelog

Giới hạn hiện tại của đường đọc: `get_incident()` dựng lại được vòng đời
(trạng thái, severity, service, timeline từ changelog) nhưng **chưa** dựng lại
`hypotheses` và `proposal` — chúng đang nằm trong comment dưới dạng văn bản cho
người đọc. Muốn đọc lại có cấu trúc thì nhúng thêm một block JSON có marker vào
comment và parse ngược; chưa làm vì war-room view hiện đọc từ fixture.
"""

from __future__ import annotations

import base64
from datetime import datetime
from typing import Any

import httpx

from src.models.incident import (
    ActionItem,
    Hypothesis,
    Incident,
    IncidentSignal,
    IncidentState,
    Postmortem,
    RemediationProposal,
    Severity,
    TimelineEvent,
)
from src.services.jira.mapping import (
    INCIDENT_LABEL,
    jira_status_for,
    jql_open_incidents,
    labels_for,
    service_from_labels,
    service_label,
    severity_from_labels,
    state_from_jira_status,
)

# Severity khi issue không có label severity (vd. issue người tạo tay lạc vào
# kết quả JQL). Lấy mức thấp nhất thay vì raise, để một issue lạc không làm vỡ
# cả danh sách incident.
_FALLBACK_SEVERITY = Severity.P4


class JiraApiError(RuntimeError):
    """Jira trả lỗi. Giữ nguyên body để debug được, vì message của Jira khá kín."""


def _adf(text: str) -> dict[str, Any]:
    """Chuyển text thường sang Atlassian Document Format.

    Jira Cloud API v3 chỉ nhận ADF cho description và comment, không nhận string.
    Mỗi dòng trống tách thành một paragraph.
    """
    paragraphs = [p for p in text.split("\n\n") if p.strip()] or [""]
    return {
        "type": "doc",
        "version": 1,
        "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": p}] if p else []}
            for p in paragraphs
        ],
    }


def _parse_jira_datetime(value: str | None) -> datetime | None:
    """Jira trả `2026-07-29T14:32:04.123+0700` — Python cần `+07:00`."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        pass
    if len(value) > 5 and (value[-5] in "+-") and ":" not in value[-5:]:
        value = value[:-2] + ":" + value[-2:]
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


class RealJiraClient:
    """Gọi Jira Cloud REST API v3 bằng basic auth (email + API token)."""

    def __init__(
        self,
        base_url: str,
        email: str,
        api_token: str,
        project_key: str,
        *,
        timeout: float = 30.0,
    ) -> None:
        if not (base_url and email and api_token and project_key):
            raise ValueError("Thiếu cấu hình Jira — cần base_url, email, api_token, project_key")
        self._base = base_url.rstrip("/")
        self._project = project_key
        credentials = base64.b64encode(f"{email}:{api_token}".encode()).decode()
        self._client = httpx.Client(
            base_url=self._base,
            timeout=timeout,
            headers={
                "Authorization": f"Basic {credentials}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )

    # ---------------------------------------------------------------- helpers

    def _call(self, method: str, path: str, json: dict[str, Any] | None = None) -> Any:
        response = self._client.request(method, path, json=json)
        if response.status_code >= 400:
            raise JiraApiError(f"{method} {path} → HTTP {response.status_code}: {response.text[:400]}")
        if response.status_code == 204 or not response.content:
            return {}
        return response.json()

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> RealJiraClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _transition_id(self, jira_key: str, to_state: IncidentState) -> str:
        """Jira transition theo id, không theo tên trạng thái đích."""
        target = jira_status_for(to_state)
        data = self._call("GET", f"/rest/api/3/issue/{jira_key}/transitions")
        for transition in data.get("transitions", []):
            if transition["to"]["name"] == target:
                return transition["id"]
        available = [t["to"]["name"] for t in data.get("transitions", [])]
        raise JiraApiError(
            f"{jira_key} không có transition sang '{target}'. Đang có: {available}. "
            "Kiểm tra JIRA_STATUS trong jira/mapping.py có khớp tên status trên board không."
        )

    # ------------------------------------------------------------ ghi dữ liệu

    def create_incident(self, signal: IncidentSignal) -> str:
        body = {
            "fields": {
                "project": {"key": self._project},
                "issuetype": {"name": "Task"},
                "summary": signal.title[:250],
                "labels": labels_for(signal.severity, signal.affected_service),
                "description": _adf(
                    f"Phát hiện tự động lúc {signal.detected_at:%Y-%m-%d %H:%M:%S %Z}.\n\n"
                    f"{signal.metric_name} = {signal.metric_value:.3f} "
                    f"(ngưỡng {signal.threshold:.3f}), vượt liên tục "
                    f"{signal.breached_for_seconds:.0f}s.\n\n"
                    f"Service ảnh hưởng: {signal.affected_service}"
                ),
            }
        }
        return self._call("POST", "/rest/api/3/issue", body)["key"]

    def add_comment(self, jira_key: str, body: str) -> None:
        self._call("POST", f"/rest/api/3/issue/{jira_key}/comment", {"body": _adf(body)})

    def post_hypothesis(self, jira_key: str, hypothesis: Hypothesis) -> None:
        lines = [f"Giả thuyết nguyên nhân ({hypothesis.confidence:.0%}): {hypothesis.statement}"]
        if hypothesis.evidence:
            lines.append("Bằng chứng:")
            for item in hypothesis.evidence:
                ratio = item.deviation_ratio
                deviation = f", lệch {ratio:.1f}× baseline" if ratio else ""
                lines.append(f"- {item.name} = {item.value:g}{item.unit}{deviation}")
                if item.promql:
                    lines.append(f"  PromQL: {item.promql}")
        if hypothesis.related_deploy:
            deploy = hypothesis.related_deploy
            lines.append(f"Deploy liên quan: {deploy.service} {deploy.version} lúc {deploy.deployed_at:%H:%M:%S}")
        if hypothesis.reasoning:
            lines.append(hypothesis.reasoning)
        self.add_comment(jira_key, "\n\n".join(lines))
        self.transition(jira_key, IncidentState.INVESTIGATING)

    def post_proposal(self, jira_key: str, proposal: RemediationProposal) -> None:
        lines = [f"Đề xuất khắc phục: {proposal.action} → {proposal.target}"]
        if proposal.params:
            lines.append(f"Tham số: {proposal.params}")
        if proposal.runbook:
            lines.append(f"Runbook: {proposal.runbook}")
        if proposal.risk:
            lines.append(f"Rủi ro: {proposal.risk}")
        lines.append(
            "CHỜ NGƯỜI DUYỆT — Agent không tự thực thi. Chuyển issue sang trạng thái "
            f"'{jira_status_for(IncidentState.REMEDIATING)}' để phê duyệt."
        )
        self.add_comment(jira_key, "\n\n".join(lines))
        self.transition(jira_key, IncidentState.AWAITING_APPROVAL)

    def transition(self, jira_key: str, to_state: IncidentState) -> None:
        transition_id = self._transition_id(jira_key, to_state)
        self._call("POST", f"/rest/api/3/issue/{jira_key}/transitions", {"transition": {"id": transition_id}})

    def link_issues(self, from_key: str, to_key: str, link_type: str = "Relates") -> None:
        self._call(
            "POST",
            "/rest/api/3/issueLink",
            {
                "type": {"name": link_type},
                "inwardIssue": {"key": from_key},
                "outwardIssue": {"key": to_key},
            },
        )

    def create_subtasks(self, jira_key: str, items: list[ActionItem]) -> list[str]:
        keys: list[str] = []
        for item in items:
            created = self._call(
                "POST",
                "/rest/api/3/issue",
                {
                    "fields": {
                        "project": {"key": self._project},
                        "issuetype": {"name": "Subtask"},
                        "parent": {"key": jira_key},
                        "summary": item.title[:250],
                        "labels": [INCIDENT_LABEL],
                    }
                },
            )
            item.jira_key = created["key"]
            keys.append(created["key"])
        return keys

    def attach_postmortem(self, jira_key: str, postmortem: Postmortem) -> None:
        lines = [
            "POSTMORTEM (blameless)",
            f"Tóm tắt: {postmortem.summary}",
            f"Nguyên nhân gốc rễ: {postmortem.root_cause}",
            f"Tác động: {postmortem.impact}",
        ]
        if postmortem.timeline:
            lines.append("Timeline:")
            lines.extend(f"- {e.at:%H:%M:%S} [{e.actor}] {e.action} {e.detail}".rstrip() for e in postmortem.timeline)
        if postmortem.actions_taken:
            lines.append("Đã làm:")
            lines.extend(f"- {a}" for a in postmortem.actions_taken)
        if postmortem.action_items:
            lines.append("Action item:")
            lines.extend(f"- {i.title}" + (f" ({i.owner})" if i.owner else "") for i in postmortem.action_items)
        self.add_comment(jira_key, "\n\n".join(lines))

    # ------------------------------------------------------------ đọc dữ liệu

    def get_transition_author(self, jira_key: str, to_state: IncidentState) -> str | None:
        """Ai đã chuyển issue sang trạng thái này, lần gần nhất.

        Nền tảng của cổng HITL ở [hitl.py](../hitl.py). Dữ liệu từ Jira changelog —
        Jira tự ghi khi có thao tác, Agent không khai báo được nên không giả mạo
        được.
        """
        target = jira_status_for(to_state)
        author: str | None = None
        start = 0
        while True:
            page = self._call("GET", f"/rest/api/3/issue/{jira_key}/changelog?startAt={start}&maxResults=100")
            for entry in page.get("values", []):
                for item in entry.get("items", []):
                    if item.get("field") == "status" and item.get("toString") == target:
                        author = (entry.get("author") or {}).get("accountId") or author
            if page.get("isLast", True):
                break
            start += len(page.get("values", []))
            if not page.get("values"):
                break
        return author

    def _to_incident(self, issue: dict[str, Any]) -> Incident:
        fields = issue.get("fields", {})
        labels = fields.get("labels", [])
        status_name = (fields.get("status") or {}).get("name", "")
        service = service_from_labels(labels)
        severity = severity_from_labels(labels)
        linked = [
            (link.get("outwardIssue") or link.get("inwardIssue") or {}).get("key")
            for link in fields.get("issuelinks", [])
        ]
        return Incident(
            jira_key=issue["key"],
            title=fields.get("summary", ""),
            severity=severity or _FALLBACK_SEVERITY,
            state=state_from_jira_status(status_name) or IncidentState.OPEN,
            affected_services=[service] if service else [],
            detected_at=_parse_jira_datetime(fields.get("created")) or datetime.now().astimezone(),
            resolved_at=_parse_jira_datetime(fields.get("resolutiondate")),
            related_incidents=[k for k in linked if k],
        )

    def _search(self, jql: str, limit: int = 50) -> list[Incident]:
        data = self._call(
            "GET",
            "/rest/api/3/search/jql"
            f"?jql={httpx.QueryParams({'q': jql})['q']}"
            f"&maxResults={limit}&fields=summary,labels,status,created,resolutiondate,issuelinks",
        )
        return [self._to_incident(issue) for issue in data.get("issues", [])]

    def find_open_incident(self, affected_service: str) -> str | None:
        found = self._search(jql_open_incidents(self._project, affected_service), limit=1)
        return found[0].jira_key if found else None

    def search_similar(self, affected_service: str, limit: int = 5) -> list[Incident]:
        jql = (
            f"project = {self._project} AND labels = \"{INCIDENT_LABEL}\" "
            f"AND labels = \"{service_label(affected_service)}\" "
            f"AND status = \"{jira_status_for(IncidentState.RESOLVED)}\" ORDER BY created DESC"
        )
        return self._search(jql, limit=limit)

    def get_incident(self, jira_key: str) -> Incident | None:
        try:
            issue = self._call(
                "GET",
                f"/rest/api/3/issue/{jira_key}"
                "?fields=summary,labels,status,created,resolutiondate,issuelinks",
            )
        except JiraApiError:
            return None
        incident = self._to_incident(issue)
        incident.timeline = self._timeline_from_changelog(jira_key)
        return incident

    def list_incidents(self, only_open: bool = False) -> list[Incident]:
        if only_open:
            return self._search(jql_open_incidents(self._project))
        jql = f"project = {self._project} AND labels = \"{INCIDENT_LABEL}\" ORDER BY created DESC"
        return self._search(jql)

    def _timeline_from_changelog(self, jira_key: str) -> list[TimelineEvent]:
        page = self._call("GET", f"/rest/api/3/issue/{jira_key}/changelog?maxResults=100")
        events: list[TimelineEvent] = []
        for entry in page.get("values", []):
            at = _parse_jira_datetime(entry.get("created"))
            author = (entry.get("author") or {}).get("displayName", "?")
            for item in entry.get("items", []):
                if item.get("field") == "status" and at is not None:
                    events.append(
                        TimelineEvent(
                            at=at,
                            actor=author,
                            action="chuyển trạng thái",
                            detail=f"{item.get('fromString')} → {item.get('toString')}",
                        )
                    )
        return events

