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
    """State của Agent ứng phó sự cố — xem sơ đồ ở docs/architecture_diagram.md mục 2.

    ⚠️ **Chưa có chỗ nào dùng.** Vòng quét hiện tại là `detection_loop.run_cycle()`
    — một vòng lặp tuần tự truyền tham số trực tiếp, không đi qua state dict.
    Schema này là chỗ dựa cho bước dựng LangGraph state machine, chưa tới.
    Nếu tới cuối tuần 2 vẫn chưa dùng thì nên xoá thay vì để làm nhiễu.

    `total=False` nên mọi field đều tuỳ chọn: graph chạy được với vài node đầu,
    không cần có đủ node mới khởi động.

    Lưu ý về `signals` và `signal`: `detect` có thể phát hiện nhiều service cùng
    lúc hỏng, nên nó ghi vào **`signals`**. `classify_severity` mới chọn ra
    **`signal`** chính để mở war room, sau khi đã cân nhắc chuyện lan truyền —
    một service hỏng là P2, hai service hỏng cùng lúc là P1, mà chỉ nhìn từng
    tín hiệu riêng lẻ thì không thấy điều đó.
    """

    #: Mọi service đang vượt ngưỡng ở vòng poll này. Output của `detect`.
    signals: list[IncidentSignal]

    #: Tín hiệu được chọn để mở war room. Output của `classify_severity`.
    signal: IncidentSignal | None

    #: Có dấu hiệu sự cố lan sang service khác không.
    spreading: bool

    #: Key Jira của war room. Output của `open_war_room`.
    jira_key: str

    #: Giả thuyết nguyên nhân kèm bằng chứng. Output của `hypothesize`.
    hypotheses: list[Hypothesis]

    #: Đề xuất khắc phục. Sau node này Agent DỪNG, chờ người duyệt.
    proposal: RemediationProposal | None

    #: Lỗi khiến vòng chạy này dừng sớm. Có giá trị nghĩa là chưa kết luận được
    #: gì — KHÁC với "đã kiểm tra và mọi thứ bình thường".
    error: str
