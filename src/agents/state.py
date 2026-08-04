from __future__ import annotations

from typing import TypedDict

from src.models.incident import Hypothesis, IncidentSignal, RemediationProposal


class AgentState(TypedDict, total=False):
    """State schema cho LangGraph agent mẫu (endpoint `/api/v1/chat`).

    Giữ lại từ template. Agent ứng phó sự cố dùng `IncidentAgentState` bên dưới.
    """

    query: str
    context: str
    analysis: str
    response: str
    error: str
    metadata: dict


class IncidentAgentState(TypedDict, total=False):
    """State của Agent ứng phó sự cố — sơ đồ ở docs/architecture_diagram.md mục 2.

    `total=False` nên mọi field đều tuỳ chọn: graph chạy được với vài node đầu,
    không cần có đủ node mới khởi động.

    Chỉ khai những field các node **hiện có** thực sự đọc/ghi. Thêm field cho
    node chưa viết (`hypotheses`, `proposal`…) nghe như chuẩn bị trước, nhưng
    thực tế là mô tả một thứ chưa tồn tại — người đọc sẽ tưởng graph đã làm được
    những bước đó. Viết node nào thì thêm field ấy.
    """

    #: Mọi service đang có sự cố ở vòng quét này. Output của `detect`.
    #:
    #: Rỗng nghĩa là **đã kiểm tra và mọi thứ bình thường** — khác hẳn với
    #: `error` có giá trị, nghĩa là không biết tình hình ra sao.
    signals: list[IncidentSignal]

    #: Sự cố có lan sang service khác không. Output của `classify_severity`.
    spreading: bool

    #: Jira key của các war room vừa **mở mới** ở vòng này.
    opened: list[str]

    #: `{tên service: jira key}` của các war room **vừa mở mới**.
    #:
    #: Chỉ chứa issue mới, không chứa issue đang cập nhật — `hypothesize` dùng
    #: nó để biết cần chẩn đoán cho ai. Sự cố kéo dài thì Agent poll liên tục,
    #: chẩn đoán lại mỗi vòng sẽ vừa spam war room vừa đốt quota LLM.
    war_rooms: dict[str, str]

    #: Jira key của các war room **đã có sẵn**, chỉ được cập nhật thêm bối cảnh.
    #: Đây là đường đi bình thường khi Agent poll liên tục lúc sự cố còn kéo dài.
    updated: list[str]

    #: `{jira key: giả thuyết}` của các war room vừa chẩn đoán. Output của
    #: `hypothesize`, input của `propose_remediation` — đề xuất hành động cần
    #: `related_deploy` để biết rollback về đâu.
    hypotheses: dict[str, Hypothesis]

    #: `{jira key: đề xuất}` đã post lên war room. Output của `propose_remediation`.
    proposals: dict[str, RemediationProposal]

    #: War room đã chuyển sang `Awaiting Approval` thành công, tức người trực có
    #: transition để bấm và cổng HITL sẽ có changelog mà xác minh.
    #:
    #: Key nào có trong `proposals` mà KHÔNG có ở đây là hỏng nghiêm trọng: đề
    #: xuất hiện trên war room nhưng không ai duyệt được.
    awaiting_approval: list[str]

    #: Lỗi khiến vòng quét dừng sớm. Có giá trị nghĩa là Agent **đang mù**.
    error: str
