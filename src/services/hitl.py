"""Cổng phê duyệt Human-in-the-loop.

Đây là **chỗ duy nhất** thực thi ràng buộc bắt buộc của đề bài: không hành động
production nào được thi hành nếu chưa có người phê duyệt.

Vì sao hàng rào nằm ở đây chứ không ở Jira: Jira Cloud bản mới chỉ tạo được
team-managed project, mà loại này không cho đặt điều kiện phân quyền lên từng
transition. Nghĩa là không thể trông cậy Jira chặn account Agent chuyển issue
sang `Remediating` (xem ADR-0001, mục "Cập nhật 2026-07-29").

Thay vào đó backend hỏi Jira: *ai* đã chuyển issue sang `Remediating`? Câu trả
lời đến từ Jira changelog — dữ liệu Jira tự ghi khi có thao tác, không phải do
Agent khai báo. Agent không giả mạo được, nên dùng làm bằng chứng phê duyệt.

Mọi đường dẫn tới `execute_remediation` PHẢI đi qua `assert_human_approved()`.
"""

from __future__ import annotations

from src.models.incident import IncidentState
from src.services.jira_client import JiraClient


class ApprovalError(PermissionError):
    """Hành động khắc phục bị từ chối vì chưa được người phê duyệt hợp lệ."""


def assert_human_approved(
    client: JiraClient,
    jira_key: str,
    *,
    agent_account_id: str,
) -> str:
    """Xác minh việc chuyển sang `Remediating` do người thực hiện, không phải Agent.

    Args:
        client: JiraClient để đọc changelog.
        jira_key: Issue cần kiểm tra, vd. "INC-12".
        agent_account_id: accountId của account Agent dùng để gọi Jira API.
            Lấy từ cấu hình `jira_agent_account_id`.

    Returns:
        accountId của người đã phê duyệt — ghi vào timeline và postmortem để
        biết ai chịu trách nhiệm cho hành động này.

    Raises:
        ApprovalError: khi chưa ai chuyển sang `Remediating`, hoặc khi người
            chuyển chính là Agent (tức Agent đang cố tự duyệt).
        ValueError: khi `agent_account_id` rỗng — cấu hình sai thì phải fail to,
            không được im lặng cho qua. Thiếu giá trị này mà vẫn chạy đồng nghĩa
            với việc không có cổng phê duyệt nào cả.
    """
    if not agent_account_id:
        raise ValueError(
            "Thiếu jira_agent_account_id — không xác định được đâu là Agent nên "
            "không thể kiểm tra phê duyệt. Điền biến môi trường trước khi chạy."
        )

    author = client.get_transition_author(jira_key, IncidentState.REMEDIATING)

    if author is None:
        raise ApprovalError(
            f"{jira_key} chưa được chuyển sang Remediating — không có phê duyệt nào "
            "để thực thi hành động khắc phục."
        )

    if author == agent_account_id:
        raise ApprovalError(
            f"{jira_key} được chuyển sang Remediating bởi chính account Agent "
            f"({author}). Hành động production phải do người phê duyệt. "
            "Từ chối thực thi."
        )

    return author
