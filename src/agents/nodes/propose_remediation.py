"""Node `propose_remediation` — đề xuất hành động và chuyển issue sang chờ duyệt.

CHỦ SỞ HỮU: Đức

Node này là chỗ Agent **dừng lại và giao quyền cho người**. Trước nó Agent nói
được *"chậm vì pool cạn, trùng thời gian với deploy v1.4.2"*; sau nó Agent nói
thêm *"đề xuất rollback về v1.4.1, đây là rủi ro, mời anh quyết"* — rồi không
làm gì nữa.

## Vì sao chuyển sang `Awaiting Approval` là bước quan trọng nhất ở đây

Cổng HITL ([`hitl.assert_human_approved()`](../../services/hitl.py)) xác minh
phê duyệt bằng cách hỏi Jira changelog: *ai* đã chuyển issue sang `Remediating`?
Nghĩa là chuỗi phê duyệt chỉ chạy được khi issue **đang ở** `Awaiting Approval`
để người trực có gì mà chuyển.

Trước node này, việc đó do [`scripts/verify_e2e.py`](../../../scripts/verify_e2e.py)
làm **bằng tay**. Nên cổng HITL đã verify chạy thật trên Jira (KAN-11 ngày
01/08) nhưng chưa bao giờ nằm trong đường đi của Agent. Node này đóng chỗ hở đó.

## Agent tuyệt đối không tự chuyển sang `Remediating`

Không phải vì Jira chặn — Jira team-managed **không chặn được** (ADR-0001, cập
nhật 29/07). Mà vì `assert_human_approved()` so `accountId` của người chuyển với
account Agent, và từ chối nếu trùng. Agent tự chuyển thì tự khoá chính mình khỏi
bước thi hành. Đó là thiết kế: cổng không dựa vào việc Agent ngoan.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from src.models.incident import Hypothesis, IncidentSignal, IncidentState, RemediationProposal
from src.services import deploys, runbooks
from src.services.jira import JiraClient

logger = logging.getLogger(__name__)


@dataclass
class ProposalResult:
    """Kết quả đề xuất cho một war room."""

    jira_key: str
    proposal: RemediationProposal
    #: Đã chuyển issue sang `Awaiting Approval` được chưa. `False` nghĩa là đề
    #: xuất đã post lên war room nhưng **chuỗi phê duyệt chưa mở** — người trực
    #: không có transition nào để bấm, nên `hitl` sẽ không có gì mà xác minh.
    awaiting_approval: bool


def propose_remediation(
    jira: JiraClient,
    jira_key: str,
    signal: IncidentSignal,
    hypothesis: Hypothesis,
) -> ProposalResult:
    """Đề xuất hành động khắc phục rồi mở cổng chờ người duyệt.

    Args:
        jira: `FakeJiraClient` khi phát triển, `RealJiraClient` khi chạy thật.
        jira_key: War room đã mở, vd. "KAN-11".
        signal: Tín hiệu từ `detect` — cho biết use case nào.
        hypothesis: Giả thuyết từ `hypothesize` — mang `related_deploy`.

    Returns:
        `ProposalResult`. Xem `awaiting_approval` để biết cổng đã mở chưa.
    """
    # Lịch sử deploy cần cho việc biết rollback **về đâu**. Đọc lại ở đây thay vì
    # nhờ `hypothesize` truyền sang: `Hypothesis` chỉ giữ đúng một `related_deploy`
    # theo contract ②, và nới contract chỉ để tiết kiệm một truy vấn thì không đáng.
    history = deploys.recent_deploys(signal.affected_service)
    proposal = runbooks.choose(signal, hypothesis, history)

    jira.post_proposal(jira_key, proposal)
    logger.info(
        "%s: đề xuất %s → %s, params=%s",
        jira_key,
        proposal.action,
        proposal.target,
        proposal.params,
    )

    awaiting = _mo_cong_cho_duyet(jira, jira_key)
    return ProposalResult(jira_key=jira_key, proposal=proposal, awaiting_approval=awaiting)


def _mo_cong_cho_duyet(jira: JiraClient, jira_key: str) -> bool:
    """Chuyển issue sang `Awaiting Approval`.

    Nuốt lỗi nhưng log ở mức **error**, không phải warning: hỏng ở đây nghĩa là
    người trực mở war room ra, đọc được đề xuất, mà **không có nút nào để duyệt**.
    Sự cố thì vẫn đang diễn ra. Đây là hỏng nghiêm trọng, chỉ không đáng làm sập
    cả vòng quét vì những war room khác trong cùng vòng vẫn cần được đề xuất.
    """
    try:
        jira.transition(jira_key, IncidentState.AWAITING_APPROVAL)
        return True
    except Exception as error:
        logger.error(
            "%s: không chuyển được sang Awaiting Approval (%s) — đề xuất đã post nhưng "
            "NGƯỜI TRỰC KHÔNG CÓ TRANSITION ĐỂ DUYỆT. Kiểm tên trạng thái trên board: "
            "src/services/jira/mapping.py phải khớp với Jira thật.",
            jira_key,
            error,
        )
        return False
