# `src/agents/nodes/` — Node của LangGraph Agent

**Chủ sở hữu: Việt**

Sơ đồ state machine: [docs/architecture_diagram.md](../../../docs/architecture_diagram.md) mục 2.

Mỗi node là một file, một hàm nhận state và trả state đã cập nhật. Bắt đầu từ `detect` rồi đi dần — không cần viết hết cùng lúc, graph chạy được với vài node đầu.

## Danh sách node

| File | Việc | Dùng gì |
|---|---|---|
| `detect.py` | Query PromQL, so baseline, quyết định có phải incident | `services/prometheus.py`, `services/rules.py` |
| `classify_severity.py` | Gán P1–P4 | `rules.classify_severity()` |
| `open_war_room.py` | **Gọi `find_open_incident()` TRƯỚC** rồi mới `create_incident()` | `services/jira` |
| `gather_context.py` | Gom metric liên quan, tỷ lệ lỗi, pool, service phụ thuộc | `prometheus.py` |
| `correlate_deploy.py` | So thời điểm incident với bảng `deploy_history` | Postgres |
| `hypothesize.py` | **Rule tìm bằng chứng trước**, LLM chỉ diễn giải | `rules.py` + `services/llm.py` |
| `link_incidents.py` | Nối incident khi phát hiện lan truyền | `rules.is_spreading()`, `jira.link_issues()` |
| `propose_remediation.py` | Chọn runbook, `jira.post_proposal()` → **Agent DỪNG** | `services/jira` |
| `escalate.py` | Treo quá lâu chưa duyệt → tăng severity, comment cảnh báo | `services/jira` |
| `generate_postmortem.py` | Timeline, nguyên nhân, action item → sub-task | `jira.attach_postmortem()` |

Node `await_approval` và `execute_remediation` **không cần viết** — Đức đã làm ở [`src/api/webhooks.py`](../../api/webhooks.py). Graph chỉ cần dừng sau `propose_remediation`.

## Ba luật không được phá

**1. Rule trước, LLM sau.** LLM không được tự suy luận từ dữ liệu thô. Rule engine sinh ra `MetricEvidence` (có số, có câu PromQL), LLM chỉ viết `statement` và `reasoning` dựa trên bằng chứng đó. Đề bài yêu cầu chẩn đoán *có bằng chứng*.

**2. Agent không bao giờ gọi `transition(..., REMEDIATING)`.** Sau `propose_remediation` là hết phần của Agent. Việc thực thi do webhook làm, sau khi [`hitl.assert_human_approved()`](../../services/hitl.py) xác minh có người thật duyệt.

**3. Chống trùng và chống nhiễu.** `open_war_room` phải gọi `find_open_incident()` trước. `detect` phải kiểm `SUSTAINED_SECONDS`. Thiếu hai cái này thì lúc load test Agent mở hàng loạt issue giống nhau và war room thành rác.

## Việt code được ngay, không cần Jira hay Prometheus

```python
from src.services.jira import FakeJiraClient

jira = FakeJiraClient()              # in ra console, không gọi mạng
key = jira.create_incident(signal)
jira.post_proposal(key, proposal)    # → Awaiting Approval
jira.approve_as_human(key)           # mô phỏng người duyệt (chỉ bản giả có)
```

Tuần sau đổi sang `RealJiraClient` — **code Agent không phải sửa một dòng**, đó là mục đích của Protocol.

Với Prometheus thì dựng local bằng `docker compose -f docker-compose.demo.yml up` (Đức đã dựng sẵn cấu hình), hoặc hardcode số giả để test `rules.py` trước.
