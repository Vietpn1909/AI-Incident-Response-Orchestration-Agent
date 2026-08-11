"""Contract ② — Model dùng chung cho toàn hệ thống.

Đường ghép: Việt (sinh IncidentSignal, Hypothesis) ↔ Đức (chuyển thành Jira
issue) ↔ Long (hiển thị Incident, ServiceStatus).

Đây là ngôn ngữ chung của cả ba người. Sửa file này là sửa contract — phải
qua PR có review, không sửa một mình.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class Severity(StrEnum):
    """Mức độ nghiêm trọng. Quy tắc phân loại ở docs/contracts/01-metrics.md."""

    P1 = "P1"  # p95 > 10s, hoặc lỗi > 50%, hoặc >= 2 service bị ảnh hưởng
    P2 = "P2"  # p95 > 2s hoặc lỗi > 10%
    P3 = "P3"  # p95 > 1s hoặc lỗi > 1%
    P4 = "P4"  # lệch baseline nhưng chưa vượt ngưỡng cứng


class IncidentState(StrEnum):
    """Trạng thái incident — khớp 1:1 với Jira Workflow.

    Agent KHÔNG có quyền tự chuyển AWAITING_APPROVAL -> REMEDIATING. Bước đó
    do người duyệt thực hiện trên Jira, đây chính là cơ chế HITL (xem ADR-0001).
    """

    OPEN = "Open"
    INVESTIGATING = "Investigating"
    AWAITING_APPROVAL = "Awaiting Approval"
    REMEDIATING = "Remediating"
    RESOLVED = "Resolved"


class ServiceHealth(StrEnum):
    """Trạng thái dịch vụ hiển thị trên status page công khai."""

    OPERATIONAL = "operational"  # Hoạt động bình thường
    DEGRADED = "degraded"  # Suy giảm hiệu năng
    DOWN = "down"  # Đang gặp sự cố
    MAINTENANCE = "maintenance"  # Đang bảo trì


class MetricEvidence(BaseModel):
    """Một số liệu cụ thể làm bằng chứng.

    Ràng buộc đề bài yêu cầu chẩn đoán *có bằng chứng*, nên mọi giả thuyết đều
    phải kèm danh sách các bản ghi này — không được chỉ có câu chữ từ LLM.
    """

    name: str = Field(..., description="Tên metric, vd. http_request_duration_seconds p95")
    value: float = Field(..., description="Giá trị đo được")
    baseline: float | None = Field(default=None, description="Giá trị baseline để so sánh")
    unit: str = Field(default="", description="Đơn vị, vd. s hoặc %")
    promql: str = Field(default="", description="Câu PromQL đã dùng — để người khác kiểm chứng lại")

    @property
    def deviation_ratio(self) -> float | None:
        """Số lần lệch so với baseline. None nếu không có baseline."""
        if self.baseline is None or self.baseline == 0:
            return None
        return self.value / self.baseline


class LogEvidence(BaseModel):
    """Một đoạn log làm bằng chứng bổ sung cho chẩn đoán.

    Khác với MetricEvidence (số liệu truy vết được qua PromQL), LogEvidence
    cung cấp ngữ cảnh **định tính** từ log thực tế của service — stack trace,
    error message, warning pattern.

    Agent chỉ thu thập log **khi Rule Engine đã phát hiện có incident** (Event-
    Driven), không đọc log stream 24/7 → tối ưu token.
    """

    source: str = Field(..., description="Tên container hoặc service sinh ra log")
    timestamp: str = Field(default="", description="Thời điểm dòng log, ISO format")
    level: str = Field(default="ERROR", description="Log level: ERROR, WARNING, INFO")
    message: str = Field(..., description="Nội dung dòng log")
    pattern: str = Field(
        default="",
        description="Pattern đã match, vd. POOL_EXHAUSTED, UPSTREAM_TIMEOUT",
    )


class IncidentSignal(BaseModel):
    """Tín hiệu phát hiện sự cố — output của node `detect`.

    Việt sinh ra, Đức dùng để tạo Jira issue.
    """

    affected_service: str = Field(..., description="Tên service, khớp label `service` trong Prometheus")
    severity: Severity
    detected_at: datetime
    metric_name: str = Field(..., description="Metric đã vượt ngưỡng")
    metric_value: float
    threshold: float
    breached_for_seconds: float = Field(
        default=0.0, description="Đã vượt ngưỡng liên tục bao lâu — phải >= 30s mới tính là incident"
    )
    evidence: list[MetricEvidence] = Field(default_factory=list)

    @property
    def title(self) -> str:
        """Tiêu đề Jira issue."""
        return f"[{self.severity.value}] {self.affected_service}: {self.metric_name} = {self.metric_value:.2f} (ngưỡng {self.threshold:.2f})"


class DeployRecord(BaseModel):
    """Một lần deploy — dùng cho correlate_deploy.

    Đọc từ bảng deploy_history giả lập do Trung seed.
    """

    service: str
    version: str
    deployed_at: datetime
    deployed_by: str = ""
    commit_sha: str = ""
    #: Ghi chú thay đổi, kiểu release note — dữ liệu **phi cấu trúc** duy nhất
    #: Agent có. Luật không đọc được đoạn văn; chỉ LLM đọc được rồi nối với số.
    #:
    #: Đo ngày 11/08: cùng một sự cố UC-4, LLM chỉ nêu đúng nguyên nhân khi có
    #: CẢ ghi chú này VÀ log. Có ghi chú mà không log thì nó chỉ đoán được
    #: "logic idempotency thất bại, có thể do một trong ba thứ".
    change_note: str = ""

    def minutes_before(self, moment: datetime) -> float:
        """Deploy này xảy ra trước `moment` bao nhiêu phút. Âm nghĩa là sau."""
        return (moment - self.deployed_at).total_seconds() / 60


class Hypothesis(BaseModel):
    """Giả thuyết nguyên nhân — output của node `hypothesize`.

    Rule engine điền `evidence` và `confidence`; LLM chỉ viết `statement` và
    `reasoning` dựa trên bằng chứng đã có. Không đảo ngược thứ tự này.
    """

    statement: str = Field(..., description="Giả thuyết một câu, vd. 'Pool DB cạn do tải tăng'")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Do rule engine tính, không phải LLM tự nhận")
    evidence: list[MetricEvidence] = Field(default_factory=list)
    related_deploy: DeployRecord | None = None
    reasoning: str = Field(default="", description="Diễn giải của LLM từ bằng chứng trên")
    log_evidence: list[LogEvidence] = Field(
        default_factory=list,
        description="Bằng chứng từ log thực tế — bổ sung cho MetricEvidence",
    )


class RemediationProposal(BaseModel):
    """Hành động khắc phục đề xuất — luôn phải qua HITL trước khi thực thi."""

    action: str = Field(..., description="Hành động, vd. rollback, restart, scale_up")
    target: str = Field(..., description="Đối tượng tác động, vd. service-thanh-toan")
    params: dict = Field(default_factory=dict, description="Vd. {'to_version': 'v1.4.1'}")
    runbook: str = Field(default="", description="Các bước trong runbook liên quan")
    risk: str = Field(default="", description="Rủi ro để người duyệt cân nhắc")
    requires_approval: bool = Field(
        default=True, description="Luôn True cho hành động production — ràng buộc bắt buộc của đề bài"
    )


class TimelineEvent(BaseModel):
    """Một mốc trong dòng thời gian incident — dùng cho war-room view và postmortem."""

    at: datetime
    actor: str = Field(..., description="'agent' hoặc tên người")
    action: str
    detail: str = ""


class ActionItem(BaseModel):
    """Việc cần làm sau incident — trở thành Jira sub-task."""

    title: str
    owner: str = ""
    jira_key: str = Field(default="", description="Key của sub-task sau khi tạo trên Jira")


class Postmortem(BaseModel):
    """Báo cáo sau sự cố, sinh khi incident chuyển Resolved.

    Theo văn hoá blameless — mô tả hệ thống và quy trình, không chỉ trích cá nhân.
    """

    summary: str
    root_cause: str
    impact: str
    timeline: list[TimelineEvent] = Field(default_factory=list)
    actions_taken: list[str] = Field(default_factory=list)
    action_items: list[ActionItem] = Field(default_factory=list)


class Incident(BaseModel):
    """Incident đầy đủ — Long hiển thị model này trong war-room view."""

    jira_key: str = Field(..., description="Vd. INC-12")
    title: str
    severity: Severity
    state: IncidentState
    affected_services: list[str] = Field(default_factory=list)
    detected_at: datetime
    resolved_at: datetime | None = None
    signal: IncidentSignal | None = None
    hypotheses: list[Hypothesis] = Field(default_factory=list)
    proposal: RemediationProposal | None = None
    timeline: list[TimelineEvent] = Field(default_factory=list)
    postmortem: Postmortem | None = None
    related_incidents: list[str] = Field(
        default_factory=list, description="Jira key của incident liên quan — dấu hiệu lan truyền"
    )

    @property
    def is_open(self) -> bool:
        return self.state != IncidentState.RESOLVED

    @property
    def awaiting_human(self) -> bool:
        """True khi đang chờ người duyệt — war-room view nên làm nổi bật trạng thái này."""
        return self.state == IncidentState.AWAITING_APPROVAL


class ServiceStatus(BaseModel):
    """Trạng thái một dịch vụ trên status page công khai."""

    name: str
    health: ServiceHealth
    message: str = Field(default="", description="Câu hiển thị cho người xem")
    active_incident: str | None = Field(default=None, description="Jira key của incident đang mở")


class StatusPage(BaseModel):
    """Toàn bộ dữ liệu status page — response của GET /api/status."""

    updated_at: datetime
    services: list[ServiceStatus] = Field(default_factory=list)
    active_incidents: list[Incident] = Field(default_factory=list)

    @property
    def overall_health(self) -> ServiceHealth:
        """Trạng thái tổng: lấy mức xấu nhất trong các service."""
        if any(s.health == ServiceHealth.DOWN for s in self.services):
            return ServiceHealth.DOWN
        if any(s.health == ServiceHealth.DEGRADED for s in self.services):
            return ServiceHealth.DEGRADED
        if any(s.health == ServiceHealth.MAINTENANCE for s in self.services):
            return ServiceHealth.MAINTENANCE
        return ServiceHealth.OPERATIONAL
