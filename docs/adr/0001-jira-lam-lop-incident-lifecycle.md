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
| HITL | Workflow `Open → Investigating → Awaiting Approval → Remediating → Resolved`, bước sang `Remediating` yêu cầu quyền mà **Agent không có** |
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

## Phần Jira không giải quyết được — vẫn phải tự xây

- Tương quan với lịch sử deploy → bảng `deploy_history` giả lập riêng
- Logic phát hiện lan truyền sự cố sang service phụ thuộc
- Status page công khai (Jira free không có)
