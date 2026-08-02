# ADR-0001: Dùng Jira Cloud làm lớp quản lý vòng đời incident

- **Trạng thái:** Đã chấp nhận
- **Ngày:** 2026-07-28
- **Người quyết định:** Trương Công Thái Đức (lead), thống nhất cả đội

## Bối cảnh

Đề bài PTNT-20 yêu cầu, ngoài phần AI, một loạt tính năng thuần "quản lý vòng đời":

- War room cho mỗi incident, có dòng cập nhật realtime
- HITL: bắt buộc người duyệt trước mọi hành động khắc phục production
- Phân quyền theo vai trò on-call
- Audit toàn bộ hành động
- Action item khi đóng incident
- Tự leo thang khi incident treo quá ngưỡng
- Truy vấn incident cũ để chẩn đoán nhanh hơn

Nếu tự xây, riêng phần này là một hệ CRUD + phân quyền + state machine + audit log + scheduler — nhiều tuần công việc, và **không có điểm nào trong đó là điểm AI**. Đội có 5 tuần và 2 trong 4 thành viên còn ít kinh nghiệm.

## Các phương án đã xét

| Phương án | Đánh giá |
|---|---|
| **Tự xây ticket system** (Postgres + FastAPI + RBAC + audit table + APScheduler) | Kiểm soát hoàn toàn, nhưng ngốn phần lớn thời gian còn lại cho công việc không phải AI. Rủi ro cao nhất: HITL và audit tự xây rất dễ có lỗ hổng, mà đó là ràng buộc bắt buộc bị chấm |
| **Dùng Jira Cloud qua REST API** | Có sẵn workflow với phân quyền chuyển trạng thái, changelog, sub-task, JQL, automation. Đổi lại: phụ thuộc dịch vụ ngoài, có giới hạn quota, phải cấu hình đúng |
| **GitHub Issues + Projects** | Miễn phí và có API tốt, nhưng **không có workflow transition có phân quyền** — tức không mô hình hoá được HITL đúng nghĩa, chỉ là label. Loại |
| **PagerDuty / Opsgenie** | Đúng bài toán nhất nhưng free tier hạn chế và phần lớn tính năng cần trả phí. Loại |

## Quyết định

Dùng **Jira Cloud** (workspace miễn phí đội tự tạo, **không dùng Jira của tổ chức/công ty**) làm backend cho vòng đời incident. Agent chỉ gọi Jira REST API qua một lớp trừu tượng `JiraClient`.

Mapping:

| Yêu cầu đề bài | Cơ chế Jira |
|---|---|
| War room | 1 Issue (type `Incident`) + comment thread Agent post realtime |
| HITL | Workflow `Open → Investigating → Awaiting Approval → Remediating → Resolved`. ⚠️ Cách thực thi đã đổi — xem mục "Cập nhật 2026-07-29" ở dưới |
| Audit trail | Jira changelog (có sẵn) |
| Postmortem | Comment/description cuối khi chuyển `Resolved` |
| Action item | Sub-task gắn issue chính |
| Học từ incident cũ | Search API (JQL) theo `affected_service` / label |
| Thực thi sau duyệt | Automation rule: transition → gọi webhook backend |
| Tự leo thang | Automation time-based trigger |
| Cảnh báo lan truyền | Issue Linking `relates to` |

## Hệ quả

**Tích cực**

- HITL được thực thi ở tầng phân quyền của Jira, không phải bằng `if` trong code — mạnh hơn và dễ chứng minh khi demo
- Audit trail có sẵn, không cần thiết kế bảng audit
- Đội dồn được thời gian vào phần AI (chẩn đoán, correlation, postmortem) — chỗ thực sự được chấm
- War room có UI thật ngay từ đầu, không cần Long build trước

**Tiêu cực & rủi ro**

- **Phụ thuộc dịch vụ ngoài.** Jira down hoặc rate limit là demo hỏng. Giảm thiểu: `JiraClient` là `Protocol`, có `FakeJiraClient` để test và để demo dự phòng offline.
- **Automation free plan giới hạn ~100 lần chạy/tháng** và time-based trigger không tức thời. Rủi ro cạn quota giữa lúc test escalation. Giảm thiểu: Trung verify quota thật ngay tuần 1; nếu chật, chuyển escalation logic vào Agent (scheduler nội bộ) thay vì Automation rule.
- **Webhook cần public URL.** Jira không gọi được `localhost`, nên phải deploy backend lên Render sớm — đây là lý do deploy được đặt là việc tuần 1 chứ không phải tuần cuối.
- Cấu hình Jira là bước thủ công, không nằm trong code nên không được version control. Giảm thiểu: ghi lại cấu hình thành checklist trong `docs/`.

## Cập nhật 2026-07-29 — HITL chuyển sang kiểm tra changelog

**Điều đã thay đổi so với quyết định gốc.**

Quyết định gốc dựa trên giả định: cấu hình Jira Workflow có điều kiện phân quyền trên transition `Awaiting Approval → Remediating`, để chính Jira chặn account Agent. Giả định này **không còn đúng**.

Khi thực tế cấu hình, Jira Cloud bản mới (mô hình "Spaces") **chỉ tạo được team-managed project**. Đã thử cả ba đường: luồng Create space, gallery template đầy đủ, và URL tạo project cổ điển — không đường nào cho chọn company-managed. Mà team-managed project không cho đặt điều kiện lên từng transition, nên **không thể trông cậy Jira chặn Agent**.

### Phương án thay: cổng phê duyệt ở backend, bằng chứng từ changelog

Khi issue chuyển sang `Remediating`, backend hỏi Jira: *ai* đã thực hiện transition này? Nếu là account Agent → **từ chối thực thi remediation**.

```python
author = client.get_transition_author(jira_key, IncidentState.REMEDIATING)
if author == agent_account_id:
    raise ApprovalError("Agent không được tự duyệt hành động production")
```

Thực thi ở [`src/services/hitl.py`](../../src/services/hitl.py). Mọi đường tới `execute_remediation` phải đi qua `assert_human_approved()`.

Vẫn cần **hai account Jira** như quyết định gốc — một cho Agent, một cho người duyệt — vì cơ chế này so accountId để phân biệt.

### Đánh đổi

**Được thêm**

- Không phụ thuộc loại project hay gói Jira. Đổi Jira sang công cụ khác cũng chỉ cần một hàm đọc "ai đã thay đổi trạng thái"
- **Demo trực quan hơn:** cho Agent thử tự transition rồi gọi remediation → backend từ chối, in log rõ ràng. Thuyết phục hơn "Jira ẩn nút nên Agent không bấm được"
- Kiểm được bằng pytest nên CI gác được. `tests/test_services/test_hitl.py::test_agent_tu_duyet_bi_tu_choi` là test quan trọng nhất repo
- Bằng chứng là changelog do Jira tự ghi, Agent không giả mạo được

**Mất đi**

- Hàng rào nằm trong code của mình, không ở tầng phân quyền của hệ thống ngoài. Nếu ai xoá lời gọi `assert_human_approved()` thì cổng mất — chống bằng test trong CI, nhưng vẫn yếu hơn phân quyền hạ tầng
- Agent vẫn *chuyển được* trạng thái issue sang `Remediating` trên Jira, chỉ là hành động khắc phục không được thi hành. Trạng thái trên Jira có thể gây nhầm lẫn khi xem bằng mắt → cần comment cảnh báo khi phát hiện trường hợp này
- Phụ thuộc `jira_agent_account_id` được cấu hình đúng. Thiếu giá trị này thì `assert_human_approved()` raise `ValueError` chứ không cho qua — cấu hình sai phải fail to

## Cập nhật 2026-07-29 (2) — dùng label thay custom field

Đã kiểm chứng trên site Jira thật, không phải suy đoán:

| Thử | Kết quả |
|---|---|
| `POST /rest/api/3/field` tạo global custom field `severity` | ✅ Tạo được (`customfield_10042`) |
| Field đó xuất hiện trên `createmeta` của team-managed project? | ❌ **KHÔNG** |
| Tạo issue với `labels: [incident, severity-P2, service-service-thanh-toan]` | ✅ Được |
| Đọc lại label | ✅ `['incident', 'service-service-thanh-toan', 'severity-P2']` |
| JQL `labels = "severity-P2"` | ✅ Tìm thấy đúng issue |
| `GET /rest/api/3/issue/{key}/changelog` | ✅ OK — nền tảng của cổng HITL |

Team-managed project quản lý field riêng và **không nhận global custom field**. Nên bỏ hẳn custom field, chuyển sang label:

| Dữ liệu | Trước | Sau |
|---|---|---|
| `severity` | custom field | label `severity-P2` |
| `affected_service` | custom field | label `service-<tên>` |
| `root_cause_confidence` | custom field | nằm trong comment cùng bằng chứng số — không cần lên Jira |
| Đánh dấu issue của Agent | — | label `incident` |

Quy ước và hàm chuyển đổi ở [`src/services/jira/mapping.py`](../../src/services/jira/mapping.py).

**Được:** bớt hẳn một lớp phức tạp — không phải quản field ID, context, option, screen configuration. Label truy vấn được bằng JQL nên vẫn đủ cho chống mở trùng và tìm incident cũ. Không phụ thuộc loại project.

**Mất:** label là chuỗi phẳng, không có validation kiểu dữ liệu như custom field. Nhập sai `severity-P9` thì Jira vẫn nhận, chỉ phía code phát hiện được — đã có [`severity_from_labels()`](../../src/services/jira/mapping.py) trả `None` và test cho trường hợp này. Trên UI Jira, severity hiện dưới dạng label chứ không phải một trường riêng, nhìn kém gọn hơn.

### Trạng thái workflow

Project team-managed có sẵn 5 status: `Idea`, `To Do`, `In Progress`, `In Review`, `Done`. Map trong `JIRA_STATUS` dùng đúng tên đang có nên **code chạy được ngay không cần đổi gì trên Jira**.

Đổi tên 5 cột trên board thành đúng tên `IncidentState` sẽ làm demo dễ hiểu hơn — nhất là `Awaiting Approval`, vì đó là cổng HITL người chấm cần thấy. Đổi rồi thì chỉ sửa `JIRA_STATUS`, không phải sửa chỗ khác. Đây là việc tuỳ chọn, không chặn.

## Phần Jira không giải quyết được — vẫn phải tự xây

- Tương quan với lịch sử deploy → bảng `deploy_history` giả lập riêng
- Logic phát hiện lan truyền sự cố sang service phụ thuộc
- Status page công khai (Jira free không có)
