# Contracts — 4 đường ghép giữa 4 người

Đội có đúng 4 chỗ mà code của hai người gặp nhau. Mỗi contract chốt interface tại một chỗ đó, **trước khi ai viết logic**.

Mục đích không phải là hình thức: nếu không có chúng, thứ tự làm việc buộc phải là Trung → Việt → Đức → Long, tức Long ngồi chờ tới tuần 4. Có rồi thì cả 4 người bắt đầu cùng lúc, mỗi người code với bản giả của người khác.

```
Trung ──①──▶ Việt ──②──▶ Đức ──④──▶ Long
               ▲           │
               └─────③─────┘
```

| # | Contract | Đường ghép | File |
|---|---|---|---|
| ① | Metric & PromQL | Trung → Việt | [01-metrics.md](01-metrics.md) |
| ② | Model dùng chung | Việt ↔ Đức ↔ Long | [`src/models/incident.py`](../../src/models/incident.py) |
| ③ | Interface Jira | Đức → Việt | [`src/services/jira/client.py`](../../src/services/jira/client.py) |
| ④ | Endpoint + fixture | Đức → Long | [`src/api/incidents.py`](../../src/api/incidents.py) |

## Mỗi người cần đọc gì

| Người | Đọc | Để làm gì |
|---|---|---|
| **Trung** | ① | Biết phải đặt tên metric gì, thêm metric nào tay, port nào |
| **Việt** | ① ② ③ | Query PromQL nào, sinh model gì, gọi Jira qua method nào |
| **Đức** | ② ③ ④ | Implement `RealJiraClient` và đổi endpoint từ fixture sang dữ liệu thật |
| **Long** | ④ (+ ② để biết tên field) | Gọi endpoint nào, JSON hình gì |

## Làm việc với bản giả

**Việt — viết Agent không cần Jira:**

```python
from src.services.jira import FakeJiraClient

jira = FakeJiraClient()          # in ra console, không gọi mạng
key = jira.create_incident(signal)
jira.post_proposal(key, proposal)   # → Awaiting Approval, Agent phải dừng
jira.approve_as_human(key)          # chỉ có ở bản giả: mô phỏng người duyệt
```

**Long — build UI không cần Agent:**

```bash
uvicorn src.main:app --reload
curl localhost:8000/api/status
curl localhost:8000/api/incidents
curl localhost:8000/api/incidents/INC-12
```

Ba endpoint này đã trả dữ liệu thật (từ fixture) ngay bây giờ. Tuần 3 Đức đổi nguồn sang Jira — **hình dạng response không đổi**, UI không phải sửa.

## Luật sửa contract

Sửa 4 file này là sửa thoả thuận, không phải sửa code của riêng mình. Bắt buộc:

1. Mở PR riêng, không lẫn với feature
2. Người ở đầu kia của đường ghép phải review
3. Nói rõ trong PR: ai phải sửa theo

Test bảo vệ contract nằm ở [`tests/test_services/test_jira_client.py`](../../tests/test_services/test_jira_client.py) và [`tests/test_api/test_incidents.py`](../../tests/test_api/test_incidents.py). Đổi contract mà quên cập nhật phía kia thì CI đỏ — đó là chủ đích.

## Ràng buộc HITL được thực thi ở đâu

Đây là ràng buộc bắt buộc của đề bài nên nó được chốt ở tầng interface, không phải bằng thiện chí:

- `JiraClient` **không có method nào duyệt incident**. Nếu ai thêm một method như vậy, đó là dấu hiệu đang phá ràng buộc.
- **Cổng phê duyệt ở [`src/services/hitl.py`](../../src/services/hitl.py)**: trước khi thi hành remediation, `assert_human_approved()` hỏi Jira ai đã chuyển issue sang `Remediating` (qua `get_transition_author()` → changelog). Nếu là account Agent → `ApprovalError`, không thi hành.
- Mọi đường tới `execute_remediation` **phải** đi qua `assert_human_approved()`. Xoá lời gọi đó là phá ràng buộc bắt buộc của đề bài — [`test_hitl.py`](../../tests/test_services/test_hitl.py) gác ở CI.
- Cổng nằm ở backend chứ không ở phân quyền Jira, vì Jira Cloud bản mới chỉ tạo được team-managed project (không đặt được điều kiện lên transition). Đánh đổi ghi trong [ADR-0001](../adr/0001-jira-lam-lop-incident-lifecycle.md#cập-nhật-2026-07-29--hitl-chuyển-sang-kiểm-tra-changelog).
- `RemediationProposal.requires_approval` mặc định `True` cho hành động production.
