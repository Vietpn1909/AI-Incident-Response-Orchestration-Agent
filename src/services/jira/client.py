"""Contract ③ — Interface Jira.

CHỦ SỞ HỮU: Đức. Method `add_label()` do Long thêm ngày 18/08 cho nhóm nhãn `fixed-by-*`.

Đường ghép: Đức (implement) → Việt (gọi).

Việt import `JiraClient` và `FakeJiraClient`, viết trọn Agent ngay hôm nay mà
không cần Jira workspace tồn tại. Tuần 3 Đức thay bằng `RealJiraClient` —
Agent không phải đổi một dòng nào.

Lưu ý HITL: interface này KHÔNG có method nào duyệt incident. Nhưng Jira Cloud
bản mới chỉ tạo được team-managed project, mà loại này không cho đặt điều kiện
phân quyền lên từng transition — nên không thể trông cậy Jira chặn Agent.

Cổng phê duyệt vì vậy nằm ở backend: `get_transition_author()` hỏi Jira xem
*ai* đã chuyển issue sang `Remediating`, và `src/services/hitl.py` từ chối thực
thi nếu người đó chính là account Agent. Bằng chứng dựa trên changelog do Jira
ghi lại, Agent không giả mạo được. Xem ADR-0001 mục "Cập nhật 2026-07-29".
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
    LogEvidence,
    Postmortem,
    RemediationProposal,
    Severity,
    TimelineEvent,
)
from src.services.jira.mapping import labels_for, merge_label, replace_severity_label


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

    def post_logs(self, jira_key: str, body: str, logs: list[LogEvidence]) -> None:
        """Post comment "đã thu thập log" kèm chính các dòng log, để đọc lại được.

        Tách khỏi `add_comment()` vì phần log phải **lưu được dưới dạng dữ liệu**,
        không chỉ là chữ cho người đọc: log container trôi mất rất nhanh, nên đây
        là bản duy nhất còn lại khi mở phiếu sau đó vài chục phút.
        """

    def post_proposal(self, jira_key: str, proposal: RemediationProposal) -> None:
        """Post đề xuất khắc phục và chuyển issue sang `Awaiting Approval`.

        Sau lời gọi này Agent phải DỪNG. Không có đường nào để Agent tự đi tiếp.
        """
        ...

    def transition(self, jira_key: str, to_state: IncidentState) -> None:
        """Chuyển trạng thái issue.

        Agent KHÔNG được gọi hàm này với `to_state=REMEDIATING`. Jira
        team-managed không chặn được ở tầng phân quyền, nên hàng rào thật nằm ở
        `hitl.assert_human_approved()` — nó kiểm tra changelog và từ chối thực
        thi remediation nếu người transition chính là Agent.
        """
        ...

    def get_transition_author(self, jira_key: str, to_state: IncidentState) -> str | None:
        """Ai đã chuyển issue sang trạng thái này (lần gần nhất)?

        Đọc từ Jira changelog — dữ liệu do Jira ghi, không phải do Agent khai
        báo, nên dùng làm bằng chứng phê duyệt được.

        Returns:
            accountId của người thực hiện, None nếu chưa từng chuyển sang
            trạng thái đó.
        """
        ...

    def add_label(self, jira_key: str, label: str) -> None:
        """Gắn thêm một nhãn cho issue, giữ nguyên các nhãn sẵn có.

        Thêm ngày 18/08 cho nhóm nhãn `fixed-by-*`: phân biệt sự cố Agent tự
        khắc phục với sự cố khắc phục sau khi người duyệt, để **đếm được bằng
        JQL** — comment war room nói đủ chuyện nhưng không truy vấn được.

        ⚠️ "Giữ nguyên các nhãn sẵn có" là phần khó, không phải phần hiển nhiên:
        Jira API ghi `labels` là ghi đè toàn bộ danh sách. Bản cài đặt phải đọc
        nhãn cũ rồi PUT lại cả danh sách, y như `set_severity()` đang làm —
        quy tắc gộp nằm ở [`mapping.merge_label()`](mapping.py).
        """
        ...

    def set_severity(self, jira_key: str, severity: Severity) -> None:
        """Đổi mức độ của một incident đã tồn tại.

        Thêm ngày 04/08 cho node [`escalate`](../../agents/nodes/escalate.py).

        ⚠️ Mức độ nằm ở **hai chỗ**: label `severity-P2` và tiền tố `[P2]` trong
        tiêu đề (`IncidentSignal.title`). Sửa một chỗ thì
        `severity_from_labels()` và mắt người đọc board nói hai điều khác nhau —
        bản cài đặt phải sửa cả hai.
        """
        ...

    def get_transition_time(self, jira_key: str, to_state: IncidentState) -> datetime | None:
        """Issue được chuyển sang trạng thái này lúc nào (lần gần nhất)?

        Thêm ngày 04/08 cho node [`escalate`](../../agents/nodes/escalate.py):
        nó cần biết một đề xuất đã treo chờ duyệt bao lâu.

        Vì sao đọc từ changelog thay vì Agent tự ghi nhớ lúc nó transition: Agent
        restart là mất, chạy nhiều instance thì mỗi con một số, và quan trọng
        nhất là **người trực có thể tự chuyển trạng thái trên UI Jira** mà Agent
        không hề biết. Changelog là nguồn duy nhất biết hết mọi thay đổi — cùng
        lý do cổng HITL dựa vào nó.

        Returns:
            Thời điểm có timezone, None nếu chưa từng chuyển sang trạng thái đó.
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

    def get_comment_bodies(self, jira_key: str) -> list[str]:
        """Trả về danh sách nội dung text của mọi comment trên issue.

        Dùng cho kiểm tra idempotency: trước khi thi hành remediation, đọc
        comment xem có marker ``Đã thực thi khắc phục`` chưa. Nếu có thì bên
        kia (webhook hoặc poll) đã chạy rồi → bỏ qua.

        Jira là chỗ nhớ chung duy nhất mà cả webhook (Render) lẫn agent loop
        (tiến trình khác) cùng nhìn thấy.
        """
        ...

    def list_incidents(self, only_open: bool = False) -> list[Incident]:
        """Danh sách incident cho war-room view."""
        ...


class FakeJiraClient:
    """Bản giả trong bộ nhớ — không gọi mạng.

    Dùng cho: Việt phát triển Agent trước khi có Jira, pytest, và làm đường lùi
    nếu Jira gặp sự cố đúng hôm demo.

    Mô phỏng đúng thực tế Jira team-managed: `transition` sang REMEDIATING
    **không** bị chặn, ai gọi cũng chuyển được. Nhưng client ghi lại *ai* đã
    chuyển, để `hitl.assert_human_approved()` kiểm tra và từ chối — giống hệt
    cách backend hoạt động với Jira thật.
    """

    AGENT_ACCOUNT_ID = "agent-account"
    HUMAN_ACCOUNT_ID = "oncall-account"

    def __init__(self, *, verbose: bool = True) -> None:
        self._incidents: dict[str, Incident] = {}
        self._counter = 0
        self._verbose = verbose
        #: Lưu text comment riêng cho `get_comment_bodies()`. Timeline cũng ghi
        #: nhưng kiểm tra bằng cách duyệt timeline dễ lẫn với các entry khác.
        self._comments: dict[str, list[str]] = {}
        # (jira_key, to_state) -> accountId của người transition gần nhất
        self._transition_authors: dict[tuple[str, IncidentState], str] = {}
        # (jira_key, to_state) -> thời điểm transition gần nhất. Bản thật đọc từ
        # changelog; ở đây ghi lúc `transition()` được gọi.
        self._transition_times: dict[tuple[str, IncidentState], datetime] = {}
        #: jira_key -> danh sách nhãn, mô phỏng đúng field `labels` của Jira.
        #:
        #: Giữ riêng chứ không nhét vào `Incident`: model đó là contract ② dùng
        #: chung ba người, còn nhãn là chi tiết cài đặt của riêng Jira — bản thật
        #: cũng không giữ nhãn trong `Incident` mà đọc thẳng từ API.
        self._labels: dict[str, list[str]] = {}

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
        # Nhãn khởi tạo giống hệt `RealJiraClient.create_incident()`. Bắt đầu từ
        # danh sách rỗng thì bản giả không bao giờ lộ được lỗi nguy hiểm nhất của
        # nhóm nhãn mới: gắn `fixed-by-*` mà làm bay mất `incident`/`severity-*`.
        self._labels[jira_key] = labels_for(signal.severity, signal.affected_service)
        self._append_timeline(jira_key, "agent", "mở war room", signal.title)
        self._log(f"tạo {jira_key}: {signal.title}")
        return jira_key

    def add_comment(self, jira_key: str, body: str) -> None:
        self._append_timeline(jira_key, "agent", "comment", body)
        # Lưu comment text riêng để `get_comment_bodies()` đọc lại được.
        self._comments.setdefault(jira_key, []).append(body)
        self._log(f"{jira_key} comment: {body}")

    def post_hypothesis(self, jira_key: str, hypothesis: Hypothesis) -> None:
        incident = self._incidents.get(jira_key)
        if incident is not None:
            incident.hypotheses.append(hypothesis)
            incident.state = IncidentState.INVESTIGATING
        self._append_timeline(jira_key, "agent", "giả thuyết", hypothesis.statement)
        self._log(f"{jira_key} giả thuyết ({hypothesis.confidence:.0%}): {hypothesis.statement}")

    def post_logs(self, jira_key: str, body: str, logs: list[LogEvidence]) -> None:
        incident = self._incidents.get(jira_key)
        if incident is not None:
            incident.log_evidence = list(logs)
        self._append_timeline(jira_key, "agent", "thu thập log", f"{len(logs)} dòng")
        self._log(f"{jira_key} thu thập {len(logs)} dòng log")

    def post_proposal(self, jira_key: str, proposal: RemediationProposal) -> None:
        incident = self._incidents.get(jira_key)
        if incident is not None:
            incident.proposal = proposal
            incident.state = IncidentState.AWAITING_APPROVAL
        self._append_timeline(jira_key, "agent", "đề xuất khắc phục", proposal.action)
        self._log(f"{jira_key} đề xuất {proposal.action} → CHỜ NGƯỜI DUYỆT")

    def transition(self, jira_key: str, to_state: IncidentState, *, actor: str | None = None) -> None:
        """Chuyển trạng thái. `actor` mặc định là Agent — đúng với thực tế là
        Agent gọi hàm này, còn người duyệt thì bấm trên UI Jira."""
        self._transition_authors[(jira_key, to_state)] = actor or self.AGENT_ACCOUNT_ID
        self._transition_times[(jira_key, to_state)] = self._now()
        incident = self._incidents.get(jira_key)
        if incident is not None:
            incident.state = to_state
            if to_state == IncidentState.RESOLVED:
                incident.resolved_at = self._now()
        self._append_timeline(jira_key, "agent", "chuyển trạng thái", to_state.value)
        self._log(f"{jira_key} → {to_state.value}")

    def approve_as_human(self, jira_key: str) -> None:
        """Chỉ có ở bản giả: mô phỏng người duyệt bấm nút trên Jira.

        Dùng trong pytest và khi Việt chạy thử luồng end-to-end local. Trên Jira
        thật, việc này do người bấm nút, và backend biết được qua webhook rồi
        xác minh bằng changelog.
        """
        self.transition(jira_key, IncidentState.REMEDIATING, actor=self.HUMAN_ACCOUNT_ID)
        self._append_timeline(jira_key, "on-call", "DUYỆT", "Awaiting Approval → Remediating")
        self._log(f"{jira_key} ✋ người duyệt → Remediating")

    def get_transition_author(self, jira_key: str, to_state: IncidentState) -> str | None:
        return self._transition_authors.get((jira_key, to_state))

    def get_transition_time(self, jira_key: str, to_state: IncidentState) -> datetime | None:
        return self._transition_times.get((jira_key, to_state))

    def add_label(self, jira_key: str, label: str) -> None:
        """Gắn nhãn, giữ nguyên nhãn cũ — qua `merge_label()` như bản thật.

        Dùng chung đúng một hàm gộp với `RealJiraClient` là cách duy nhất để test
        chạy trên bản giả còn nói được điều gì đó về bản thật.
        """
        self._labels[jira_key] = merge_label(self._labels.get(jira_key, []), label)
        self._log(f"{jira_key} nhãn += {label}")

    def get_labels(self, jira_key: str) -> list[str]:
        """Chỉ có ở bản giả: đọc lại nhãn để test kiểm chứng.

        Không đưa vào Protocol vì Agent không cần đọc nhãn để chạy — thêm vào
        contract ③ là bắt bản thật gánh một method chỉ test dùng.
        """
        return list(self._labels.get(jira_key, []))

    def set_severity(self, jira_key: str, severity: Severity) -> None:
        incident = self._incidents.get(jira_key)
        if incident is None:
            return
        cu = incident.severity
        incident.severity = severity
        # Nhãn `severity-*` phải đi theo, đúng như bản thật làm trong cùng một
        # lần PUT. Bản giả để nhãn cũ lại thì nó tự mâu thuẫn: `escalate` nâng
        # P3 → P1 mà nhãn vẫn `severity-P3`.
        self._labels[jira_key] = replace_severity_label(
            self._labels.get(jira_key, []), severity
        )
        # Tiêu đề mang tiền tố `[P2]`, đổi luôn cho khớp — xem cảnh báo ở
        # Protocol. Bản thật cũng phải làm y hệt trên summary của Jira.
        incident.title = incident.title.replace(f"[{cu.value}]", f"[{severity.value}]", 1)
        self._append_timeline(jira_key, "agent", "nâng mức", f"{cu.value} → {severity.value}")
        self._log(f"{jira_key} mức {cu.value} → {severity.value}")

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

    def get_comment_bodies(self, jira_key: str) -> list[str]:
        return list(self._comments.get(jira_key, []))

    def list_incidents(self, only_open: bool = False) -> list[Incident]:
        incidents = list(self._incidents.values())
        if only_open:
            incidents = [incident for incident in incidents if incident.is_open]
        return sorted(incidents, key=lambda incident: incident.detected_at, reverse=True)
