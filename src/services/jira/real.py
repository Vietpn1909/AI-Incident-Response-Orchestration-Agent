"""`RealJiraClient` — cài đặt [contract ③](client.py) trên Jira Cloud thật.

Thay `FakeJiraClient` bằng class này là Agent chạy với Jira thật, không phải sửa
code Agent (đó là mục đích của Protocol).

Ràng buộc của team-managed project đã kiểm chứng ngày 2026-07-29 và xử lý ở đây:

- Không dùng được custom field → severity và affected_service lưu bằng **label**,
  quy ước ở [mapping.py](mapping.py)
- Không đặt được điều kiện phân quyền lên transition → cổng phê duyệt nằm ở
  [hitl.py](../hitl.py), dựa trên `get_transition_author()` đọc changelog

Đường đọc dựng lại được đầy đủ: vòng đời và timeline từ changelog, còn
`hypotheses` và `proposal` từ **khối JSON Agent nhúng vào comment**. Comment vẫn
là văn bản cho người đọc, khối JSON nằm ở cuối và người xem bỏ qua được.

Vì sao cần: webhook nhận được issue key rồi phải biết thi hành hành động gì.
Không đọc lại được `proposal` thì nó trả 422 "không có đề xuất khắc phục đọc lại
được" — lỗi gặp thật khi chạy verify end-to-end ngày 2026-08-02. Đường đọc này
cũng là thứ làm war-room view của Long hiện được dữ liệu thật thay vì fixture.
"""

from __future__ import annotations

import base64
import json as json_module
from datetime import datetime
from typing import Any

import httpx
from pydantic import ValidationError

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
    ACTION_ITEM_LABEL,
    INCIDENT_LABEL,
    jira_status_for,
    jql_open_incidents,
    labels_for,
    replace_severity_label,
    retitle_severity,
    service_from_labels,
    service_label,
    severity_from_labels,
    state_from_jira_status,
    status_candidates,
)

# Severity khi issue không có label severity (vd. issue người tạo tay lạc vào
# kết quả JQL). Lấy mức thấp nhất thay vì raise, để một issue lạc không làm vỡ
# cả danh sách incident.
_FALLBACK_SEVERITY = Severity.P4


class JiraApiError(RuntimeError):
    """Jira trả lỗi. Giữ nguyên body để debug được, vì message của Jira khá kín.

    `status_code` để chỗ gọi phân biệt được nguyên nhân mà không phải parse chuỗi:
    404 là issue không tồn tại, 401/403 là token sai hoặc thiếu quyền, 429 là
    rate limit. Không có nó thì mọi lỗi Jira đều thành HTTP 500 giống nhau và
    lúc demo không biết tắc ở đâu.
    """

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


#: Khoá đánh dấu khối JSON do Agent nhúng vào comment.
#:
#: Comment trên Jira trước hết là để NGƯỜI đọc, nên phần văn bản giữ nguyên.
#: Nhưng backend cũng cần đọc lại `proposal` để biết thi hành hành động gì —
#: không có nó thì webhook nhận được issue key mà không biết làm gì (lỗi 422
#: gặp thật khi chạy verify end-to-end). Nên đính kèm một khối JSON ở cuối
#: comment, người đọc bỏ qua được, máy parse lại được.
_PAYLOAD_KEY = "p035"


def _adf(text: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Text thường → Atlassian Document Format, kèm khối JSON máy đọc nếu có.

    Jira Cloud API v3 chỉ nhận ADF cho description và comment, không nhận
    string. Mỗi dòng trống tách thành một paragraph.
    """
    paragraphs = [p for p in text.split("\n\n") if p.strip()] or [""]
    content: list[dict[str, Any]] = [
        {"type": "paragraph", "content": [{"type": "text", "text": p}] if p else []}
        for p in paragraphs
    ]
    if payload is not None:
        content.append(
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": "— dữ liệu máy đọc, bỏ qua khi xem bằng mắt —"}
                ],
            }
        )
        content.append(
            {
                "type": "codeBlock",
                "attrs": {"language": "json"},
                "content": [{"type": "text", "text": json_module.dumps(payload, ensure_ascii=False)}],
            }
        )
    return {"type": "doc", "version": 1, "content": content}


def _adf_to_text(adf: Any) -> str:
    """Rút plain text từ ADF (Atlassian Document Format).

    Duyệt đệ quy giống ``_extract_payloads()`` nhưng thu text thay vì JSON.
    Dùng cho ``get_comment_bodies()``: chỉ cần tìm marker text trong comment,
    không cần cấu trúc đầy đủ.
    """
    parts: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if node.get("type") == "text":
                parts.append(node.get("text", ""))
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(adf)
    return " ".join(parts)


def _extract_payloads(adf: Any) -> list[dict[str, Any]]:
    """Duyệt ADF, lấy ra mọi khối JSON có khoá đánh dấu của mình.

    Bỏ qua khối không parse được thay vì raise: comment do người gõ tay có thể
    chứa code block bất kỳ, và một comment lạ không được làm vỡ cả war room.
    """
    found: list[dict[str, Any]] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if node.get("type") == "codeBlock":
                raw = "".join(c.get("text", "") for c in node.get("content", []))
                try:
                    data = json_module.loads(raw)
                except (ValueError, TypeError):
                    return
                if isinstance(data, dict) and _PAYLOAD_KEY in data:
                    found.append(data)
                return
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(adf)
    return found


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
        # Ép IPv4 khi gọi Jira.
        #
        # Đo ngày 11/08 trên mạng của máy demo: `jibinarybro.atlassian.net` phân
        # giải ra cả A và AAAA, nhưng địa chỉ IPv6 là tiền tố NAT64 (`64:ff9b::`)
        # và đường đó **hỏng** — TCP 443 bắt tay được nhưng TLS treo tới hết
        # timeout. `httpx` thử IPv6 trước nên mọi lời gọi Jira treo 30 giây rồi
        # chết, trong khi GitHub và Render vẫn bình thường.
        #
        #   curl -4 → HTTP 401 trong 0,68s     (đúng, chỉ thiếu auth header)
        #   curl -6 → treo 15s rồi chết
        #
        # Đây là lỗi hạ tầng mạng, không phải Jira sập hay token sai — và nếu gặp
        # giữa buổi demo thì cực khó đoán, vì mọi thứ khác vẫn xanh.
        #
        # `local_address="0.0.0.0"` buộc socket dùng IPv4. Máy nào có IPv6 lành
        # cũng không bị ảnh hưởng: Jira Cloud luôn có bản ghi A.
        self._client = httpx.Client(
            base_url=self._base,
            timeout=timeout,
            transport=httpx.HTTPTransport(local_address="0.0.0.0", retries=1),
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
            raise JiraApiError(
                f"{method} {path} → HTTP {response.status_code}: {response.text[:400]}",
                status_code=response.status_code,
            )
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
        """Jira transition theo id, không theo tên trạng thái đích.

        Thử tên mong muốn trước, rồi tới tên mặc định của board team-managed —
        nhờ vậy code chạy đúng cả trước lẫn sau khi đội đổi tên cột, không có
        khoảng thời gian hỏng ở giữa.
        """
        data = self._call("GET", f"/rest/api/3/issue/{jira_key}/transitions")
        available = {t["to"]["name"]: t["id"] for t in data.get("transitions", [])}

        for candidate in status_candidates(to_state):
            if candidate in available:
                return available[candidate]

        wanted = " hoặc ".join(status_candidates(to_state))
        raise JiraApiError(
            f"{jira_key} không có transition sang '{wanted}'. "
            f"Đang có: {sorted(available)}. "
            "Kiểm tra tên cột trên board có khớp JIRA_STATUS hoặc FALLBACK_STATUS "
            "trong jira/mapping.py không."
        )

    # ------------------------------------------------------------ ghi dữ liệu

    def create_incident(self, signal: IncidentSignal) -> str:
        body = {
            "fields": {
                "project": {"key": self._project},
                "issuetype": {"name": "Task"},
                "summary": signal.title[:250],
                "labels": labels_for(signal.severity, signal.affected_service),
                # Nhúng cả `IncidentSignal` dạng máy đọc vào description.
                #
                # Không có bước này thì `Incident.signal` KHÔNG BAO GIỜ dựng lại
                # được từ Jira, và war-room view của Long luôn hiện "Chưa có tín
                # hiệu gốc" — mất đúng mục trưng bằng chứng kèm PromQL kiểm chứng
                # được, tức thứ chứng minh "chẩn đoán có bằng chứng". Phát hiện
                # ngày 06/08 khi chạy thử UI: cả 6 incident trên board đều
                # `signal=None`.
                #
                # Đặt ở description chứ không thêm một comment nữa: mỗi war room
                # đã có comment bối cảnh của `open_war_room`, thêm nữa chỉ làm ồn.
                "description": _adf(
                    f"Phát hiện tự động lúc {signal.detected_at:%Y-%m-%d %H:%M:%S %Z}.\n\n"
                    f"{signal.metric_name} = {signal.metric_value:.3f} "
                    f"(ngưỡng {signal.threshold:.3f}), vượt liên tục "
                    f"{signal.breached_for_seconds:.0f}s.\n\n"
                    f"Service ảnh hưởng: {signal.affected_service}",
                    {_PAYLOAD_KEY: "signal", "data": signal.model_dump(mode="json")},
                ),
            }
        }
        return self._call("POST", "/rest/api/3/issue", body)["key"]

    def add_comment(self, jira_key: str, body: str) -> None:
        self._call("POST", f"/rest/api/3/issue/{jira_key}/comment", {"body": _adf(body)})

    def post_hypothesis(self, jira_key: str, hypothesis: Hypothesis) -> None:
        from src.services.status_updater import status_diagnosed
        # Lấy signal từ incident đã lưu để build comment format mới
        incident = self.get_incident(jira_key)
        signal = incident.signal if incident else None
        if signal:
            text = status_diagnosed(signal, hypothesis)
        else:
            text = f"🧠 CHẨN ĐOÁN NGUYÊN NHÂN\n\nNguyên nhân: {hypothesis.statement}\nĐộ tin cậy: {hypothesis.confidence:.0%}"
        self._comment_with_payload(
            jira_key,
            text,
            {_PAYLOAD_KEY: "hypothesis", "data": hypothesis.model_dump(mode="json")},
        )
        self.transition(jira_key, IncidentState.INVESTIGATING)

    def post_proposal(self, jira_key: str, proposal: RemediationProposal) -> None:
        from src.services.status_updater import status_proposed
        self._comment_with_payload(
            jira_key,
            status_proposed(proposal),
            {_PAYLOAD_KEY: "proposal", "data": proposal.model_dump(mode="json")},
        )
        self.transition(jira_key, IncidentState.AWAITING_APPROVAL)

    def _comment_with_payload(self, jira_key: str, body: str, payload: dict[str, Any]) -> None:
        """Post comment cho người đọc, kèm khối JSON cho backend đọc lại."""
        self._call(
            "POST",
            f"/rest/api/3/issue/{jira_key}/comment",
            {"body": _adf(body, payload)},
        )

    def _payloads_from_comments(self, jira_key: str) -> list[dict[str, Any]]:
        """Mọi khối JSON Agent đã nhúng vào comment của issue, theo thứ tự thời gian."""
        data = self._call(
            "GET", f"/rest/api/3/issue/{jira_key}/comment?maxResults=100&orderBy=created"
        )
        payloads: list[dict[str, Any]] = []
        for comment in data.get("comments", []):
            payloads.extend(_extract_payloads(comment.get("body")))
        return payloads

    def get_comment_bodies(self, jira_key: str) -> list[str]:
        """Trả về danh sách nội dung text (plain text) của mọi comment trên issue.

        Dùng cho idempotency check: trước khi thi hành, đọc comment tìm marker
        ``Đã thực thi khắc phục``. Nếu có thì bên kia đã chạy rồi.

        ADF (Atlassian Document Format) được duyệt đệ quy để rút text, giống
        cách ``_extract_payloads()`` duyệt tìm JSON.
        """
        data = self._call(
            "GET", f"/rest/api/3/issue/{jira_key}/comment?maxResults=100&orderBy=created"
        )
        bodies: list[str] = []
        for comment in data.get("comments", []):
            bodies.append(_adf_to_text(comment.get("body")))
        return bodies

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
                        # ⚠️ KHÔNG dùng INCIDENT_LABEL ở đây — xem ghi chú ở
                        # `ACTION_ITEM_LABEL`. Đây là việc cần làm SAU sự cố,
                        # không phải một sự cố.
                        "labels": [ACTION_ITEM_LABEL],
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

    def set_severity(self, jira_key: str, severity: Severity) -> None:
        """Đổi mức độ: sửa label `severity-*` VÀ tiền tố `[P2]` trong summary.

        Một lần `PUT /issue` cho cả hai. Sửa riêng lẻ thì có khoảng thời gian
        label và tiêu đề nói hai mức khác nhau, mà `severity_from_labels()` đọc
        label còn người đọc board đọc tiêu đề.

        Đọc lại issue trước khi ghi vì cần biết label cũ để bỏ — Jira API ghi
        `labels` là ghi đè toàn bộ danh sách, không phải thêm vào.
        """
        issue = self._call("GET", f"/rest/api/3/issue/{jira_key}?fields=summary,labels")
        fields = issue.get("fields", {})
        labels_cu = fields.get("labels", []) or []
        summary_cu = fields.get("summary", "") or ""

        self._call(
            "PUT",
            f"/rest/api/3/issue/{jira_key}",
            {
                "fields": {
                    "labels": replace_severity_label(labels_cu, severity),
                    "summary": retitle_severity(summary_cu, severity)[:250],
                }
            },
        )

    def get_transition_author(self, jira_key: str, to_state: IncidentState) -> str | None:
        """Ai đã chuyển issue sang trạng thái này, lần gần nhất.

        Nền tảng của cổng HITL ở [hitl.py](../hitl.py). Dữ liệu từ Jira changelog —
        Jira tự ghi khi có thao tác, Agent không khai báo được nên không giả mạo
        được.
        """
        return self._lan_chuyen_gan_nhat(jira_key, to_state)[0]

    def get_transition_time(self, jira_key: str, to_state: IncidentState) -> datetime | None:
        """Issue được chuyển sang trạng thái này lúc nào, lần gần nhất.

        Dùng cho node `escalate` để biết đề xuất đã treo chờ duyệt bao lâu.
        """
        return self._lan_chuyen_gan_nhat(jira_key, to_state)[1]

    def _lan_chuyen_gan_nhat(
        self, jira_key: str, to_state: IncidentState
    ) -> tuple[str | None, datetime | None]:
        """Đi changelog một lượt, trả `(accountId, thời điểm)` của lần chuyển gần nhất.

        Gộp hai câu hỏi vào một lượt đi vì cả hai đọc cùng một nguồn. Tách thành
        hai hàm mỗi hàm tự phân trang là gọi Jira API gấp đôi cho cùng dữ liệu,
        mà Jira Cloud có rate limit.

        ⚠️ Tác giả và thời điểm phải lấy từ **cùng một** entry. Bản đầu lấy tác
        giả ở hàm này và thời điểm ở hàm khác thì khi có nhiều lần chuyển sang
        cùng trạng thái, hai giá trị có thể thuộc hai lần khác nhau — cổng HITL
        sẽ nói "người X duyệt" kèm mốc thời gian của một lần chuyển khác.
        """
        target = jira_status_for(to_state)
        author: str | None = None
        at: datetime | None = None
        start = 0
        while True:
            page = self._call("GET", f"/rest/api/3/issue/{jira_key}/changelog?startAt={start}&maxResults=100")
            for entry in page.get("values", []):
                for item in entry.get("items", []):
                    if item.get("field") == "status" and item.get("toString") == target:
                        author = (entry.get("author") or {}).get("accountId") or author
                        at = _parse_jira_datetime(entry.get("created")) or at
            if page.get("isLast", True):
                break
            start += len(page.get("values", []))
            if not page.get("values"):
                break
        return author, at

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
                "?fields=summary,labels,status,created,resolutiondate,issuelinks,description",
            )
        except JiraApiError as exc:
            if exc.status_code == 404:
                return None
            raise
        incident = self._to_incident(issue)
        incident.timeline = self._timeline_from_changelog(jira_key)

        # Dựng lại dữ liệu có cấu trúc từ khối JSON trong comment. Không có
        # bước này thì `proposal` luôn None và webhook không biết thi hành hành
        # động gì — lỗi 422 gặp thật khi chạy verify end-to-end.
        # Description trước comment: `signal` nằm ở description (nhúng lúc tạo),
        # còn `hypothesis`/`proposal` nằm ở comment.
        payloads = _extract_payloads((issue.get("fields") or {}).get("description"))
        payloads.extend(self._payloads_from_comments(jira_key))

        for payload in payloads:
            kind, data = payload.get(_PAYLOAD_KEY), payload.get("data")
            if not isinstance(data, dict):
                continue
            try:
                if kind == "signal":
                    incident.signal = IncidentSignal.model_validate(data)
                elif kind == "hypothesis":
                    incident.hypotheses.append(Hypothesis.model_validate(data))
                elif kind == "proposal":
                    # Lấy đề xuất MỚI NHẤT: incident có thể được đề xuất lại sau
                    # khi hành động đầu không khắc phục được.
                    incident.proposal = RemediationProposal.model_validate(data)
            except ValidationError:
                # Payload từ phiên bản code cũ hoặc bị sửa tay — bỏ qua, không
                # để một comment lạ làm vỡ cả war room.
                continue
        return incident

    def list_incidents(self, only_open: bool = False) -> list[Incident]:
        if only_open:
            return self._search(jql_open_incidents(self._project))
        # `issuetype != Subtask` cùng lý do như trong `jql_open_incidents()`:
        # subtask là việc cần làm sau sự cố, không phải sự cố. Thiếu điều kiện
        # này thì danh sách "tất cả incident" trên war room vẫn lẫn action item
        # cũ đã mang nhãn `incident` từ trước bản vá 15/08.
        jql = (
            f"project = {self._project} AND labels = \"{INCIDENT_LABEL}\" "
            "AND issuetype != Subtask ORDER BY created DESC"
        )
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

