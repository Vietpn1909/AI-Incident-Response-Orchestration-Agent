"""Contract ③ — Interface Jira.

Đường ghép: Đức (implement) → Việt (gọi).

Việt import `JiraClient` và `FakeJiraClient`, viết trọn Agent ngay hôm nay mà
không cần Jira workspace tồn tại. Tuần 3 Đức thay bằng `RealJiraClient` —
Agent không phải đổi một dòng nào.

Lưu ý HITL: interface này KHÔNG có method nào duyệt incident. Việc chuyển
`Awaiting Approval -> Remediating` chỉ người mới làm được, trên Jira, qua
workflow có phân quyền (xem ADR-0001). Nếu có ai định thêm một method như vậy
vào đây thì đó là dấu hiệu đang phá ràng buộc bắt buộc của đề bài.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol, runtime_checkable

from src.models.incident import (
    ActionItem,
    Hypothesis,
    Incident,
    IncidentSignal,
    IncidentState,
    Postmortem,
    RemediationProposal,
    TimelineEvent,
)


@runtime_checkable
class JiraClient(Protocol):
    """Các thao tác Agent cần trên Jira.

    Mọi method dùng `jira_key` dạng "INC-12" để định danh issue.
    """

    def create_incident(self, signal: IncidentSignal) -> str:
        """Mở war room: tạo Jira Issue type `Incident`.

        Returns:
            jira_key của issue vừa tạo, vd. "INC-12".
        """
        ...

    def add_comment(self, jira_key: str, body: str) -> None:
        """Post comment vào issue — đây là dòng cập nhật realtime của war room."""
        ...

    def post_hypothesis(self, jira_key: str, hypothesis: Hypothesis) -> None:
        """Post giả thuyết nguyên nhân kèm bằng chứng số."""
        ...

    def post_proposal(self, jira_key: str, proposal: RemediationProposal) -> None:
        """Post đề xuất khắc phục và chuyển issue sang `Awaiting Approval`.

        Sau lời gọi này Agent phải DỪNG. Không có đường nào để Agent tự đi tiếp.
        """
        ...

    def transition(self, jira_key: str, to_state: IncidentState) -> None:
        """Chuyển trạng thái issue.

        Raises:
            PermissionError: khi cố chuyển sang REMEDIATING — bước đó chỉ người
                duyệt được, Agent không có quyền.
        """
        ...

    def link_issues(self, from_key: str, to_key: str, link_type: str = "relates to") -> None:
        """Liên kết 2 incident — dùng khi phát hiện sự cố lan sang service khác."""
        ...

    def create_subtasks(self, jira_key: str, items: list[ActionItem]) -> list[str]:
        """Tạo sub-task cho action item của postmortem.

        Returns:
            Danh sách jira_key của các sub-task đã tạo.
        """
        ...

    def attach_postmortem(self, jira_key: str, postmortem: Postmortem) -> None:
        """Ghi postmortem vào issue khi chuyển Resolved."""
        ...

    def find_open_incident(self, affected_service: str) -> str | None:
        """Tìm incident đang mở của một service.

        Agent PHẢI gọi hàm này trước `create_incident` để chống mở trùng — lúc
        load test, không có bước này thì Agent tạo hàng loạt issue giống nhau.

        Returns:
            jira_key nếu đang có incident mở, None nếu không.
        """
        ...

    def search_similar(self, affected_service: str, limit: int = 5) -> list[Incident]:
        """Tìm incident cũ cùng service qua JQL — dùng để chẩn đoán nhanh hơn.

        Ngoài phạm vi MVP, chỉ làm nếu còn thời gian.
        """
        ...

    def get_incident(self, jira_key: str) -> Incident | None:
        """Đọc lại incident từ Jira — API và status page dùng hàm này."""
        ...

    def list_incidents(self, only_open: bool = False) -> list[Incident]:
        """Danh sách incident cho war-room view."""
        ...


class FakeJiraClient:
    """Bản giả trong bộ nhớ — không gọi mạng.

    Dùng cho: Việt phát triển Agent trước khi có Jira, pytest, và làm đường lùi
    nếu Jira gặp sự cố đúng hôm demo.

    Hành vi mô phỏng đúng ràng buộc quan trọng nhất: `transition` sang
    REMEDIATING sẽ raise PermissionError, giống hệt Jira thật khi Agent không có
    quyền — nhờ vậy Agent viết sai luồng HITL sẽ fail ngay ở test, không phải
    lúc demo.
    """

    def __init__(self, *, verbose: bool = True) -> None:
        self._incidents: dict[str, Incident] = {}
        self._counter = 0
        self._verbose = verbose

    def _log(self, message: str) -> None:
        if self._verbose:
            print(f"[FakeJira] {message}")

    def _now(self) -> datetime:
        return datetime.now(UTC)

    def _append_timeline(self, jira_key: str, actor: str, action: str, detail: str = "") -> None:
        incident = self._incidents.get(jira_key)
        if incident is not None:
            incident.timeline.append(
                TimelineEvent(at=self._now(), actor=actor, action=action, detail=detail)
            )

    def create_incident(self, signal: IncidentSignal) -> str:
        self._counter += 1
        jira_key = f"INC-{self._counter}"
        self._incidents[jira_key] = Incident(
            jira_key=jira_key,
            title=signal.title,
            severity=signal.severity,
            state=IncidentState.OPEN,
            affected_services=[signal.affected_service],
            detected_at=signal.detected_at,
            signal=signal,
        )
        self._append_timeline(jira_key, "agent", "mở war room", signal.title)
        self._log(f"tạo {jira_key}: {signal.title}")
        return jira_key

    def add_comment(self, jira_key: str, body: str) -> None:
        self._append_timeline(jira_key, "agent", "comment", body)
        self._log(f"{jira_key} comment: {body}")

    def post_hypothesis(self, jira_key: str, hypothesis: Hypothesis) -> None:
        incident = self._incidents.get(jira_key)
        if incident is not None:
            incident.hypotheses.append(hypothesis)
            incident.state = IncidentState.INVESTIGATING
        self._append_timeline(jira_key, "agent", "giả thuyết", hypothesis.statement)
        self._log(f"{jira_key} giả thuyết ({hypothesis.confidence:.0%}): {hypothesis.statement}")

    def post_proposal(self, jira_key: str, proposal: RemediationProposal) -> None:
        incident = self._incidents.get(jira_key)
        if incident is not None:
            incident.proposal = proposal
            incident.state = IncidentState.AWAITING_APPROVAL
        self._append_timeline(jira_key, "agent", "đề xuất khắc phục", proposal.action)
        self._log(f"{jira_key} đề xuất {proposal.action} → CHỜ NGƯỜI DUYỆT")

    def transition(self, jira_key: str, to_state: IncidentState) -> None:
        if to_state == IncidentState.REMEDIATING:
            raise PermissionError(
                f"Agent không có quyền chuyển {jira_key} sang Remediating. "
                "Bước này phải do người duyệt thực hiện trên Jira (HITL)."
            )
        incident = self._incidents.get(jira_key)
        if incident is not None:
            incident.state = to_state
            if to_state == IncidentState.RESOLVED:
                incident.resolved_at = self._now()
        self._append_timeline(jira_key, "agent", "chuyển trạng thái", to_state.value)
        self._log(f"{jira_key} → {to_state.value}")

    def approve_as_human(self, jira_key: str) -> None:
        """Chỉ có ở bản giả: mô phỏng người duyệt trên Jira.

        Dùng trong pytest và khi Việt chạy thử luồng end-to-end local. Trên Jira
        thật, việc này do người bấm nút, và backend biết được qua webhook.
        """
        incident = self._incidents.get(jira_key)
        if incident is not None:
            incident.state = IncidentState.REMEDIATING
        self._append_timeline(jira_key, "on-call", "DUYỆT", "Awaiting Approval → Remediating")
        self._log(f"{jira_key} ✋ người duyệt → Remediating")

    def link_issues(self, from_key: str, to_key: str, link_type: str = "relates to") -> None:
        for a, b in ((from_key, to_key), (to_key, from_key)):
            incident = self._incidents.get(a)
            if incident is not None and b not in incident.related_incidents:
                incident.related_incidents.append(b)
        self._append_timeline(from_key, "agent", "link incident", f"{link_type} {to_key}")
        self._log(f"link {from_key} {link_type} {to_key}")

    def create_subtasks(self, jira_key: str, items: list[ActionItem]) -> list[str]:
        keys: list[str] = []
        for index, item in enumerate(items, start=1):
            subtask_key = f"{jira_key}-{index}"
            item.jira_key = subtask_key
            keys.append(subtask_key)
            self._log(f"sub-task {subtask_key}: {item.title}")
        return keys

    def attach_postmortem(self, jira_key: str, postmortem: Postmortem) -> None:
        incident = self._incidents.get(jira_key)
        if incident is not None:
            incident.postmortem = postmortem
        self._append_timeline(jira_key, "agent", "postmortem", postmortem.summary)
        self._log(f"{jira_key} postmortem: {postmortem.summary}")

    def find_open_incident(self, affected_service: str) -> str | None:
        for key, incident in self._incidents.items():
            if incident.is_open and affected_service in incident.affected_services:
                return key
        return None

    def search_similar(self, affected_service: str, limit: int = 5) -> list[Incident]:
        matches = [
            incident
            for incident in self._incidents.values()
            if affected_service in incident.affected_services
            and incident.state == IncidentState.RESOLVED
        ]
        return matches[:limit]

    def get_incident(self, jira_key: str) -> Incident | None:
        return self._incidents.get(jira_key)

    def list_incidents(self, only_open: bool = False) -> list[Incident]:
        incidents = list(self._incidents.values())
        if only_open:
            incidents = [incident for incident in incidents if incident.is_open]
        return sorted(incidents, key=lambda incident: incident.detected_at, reverse=True)
