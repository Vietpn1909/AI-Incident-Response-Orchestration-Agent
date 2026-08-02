# Project Brief — AI Agent Điều Phối Ứng Phó Sự Cố

**Đề bài:** PTNT-20 (Khối PTNT — Kiến trúc & Tích hợp) · **Team:** Binary Brothers
**Ngày chốt:** 2026-07-28 · **Cập nhật:** 2026-08-02

> Tài liệu này trả lời *vì sao làm* và *làm cho ai*. Yêu cầu chi tiết nằm ở [prd.md](prd.md), thiết kế nằm ở [architecture_diagram.md](architecture_diagram.md).

---

## 1. Vấn đề

Khi một dịch vụ tích hợp của nền tảng sập hoặc độ trễ tăng vọt, quy trình ứng phó hiện tại **hoàn toàn thủ công**: tập hợp người vào war room, dò log từng service, đoán nguyên nhân, cập nhật trạng thái cho khách hàng bằng tay, và hôm sau ngồi viết postmortem.

Điểm mấu chốt: **phần lớn thời gian đầu của một incident không dành cho việc khắc phục, mà dành cho việc thu thập bối cảnh.** Người trực phải trả lời "chuyện gì đang xảy ra, ở đâu, từ bao giờ, có liên quan tới cái gì vừa deploy không" trước khi chạm được vào nút sửa.

Công cụ monitor hiện có (Prometheus, Grafana, Datadog) giải quyết đúng một phần nhỏ: chúng báo **"có gì đó sai"**. Chúng không:

- tổng hợp bối cảnh xuyên nhiều service
- đề xuất giả thuyết nguyên nhân kèm bằng chứng
- điều phối hành động khắc phục
- cập nhật trạng thái cho người dùng
- sinh postmortem

Bốn khoảng trống đó là toàn bộ phạm vi của dự án này.

## 2. Người dùng mục tiêu

| | Ai | Cần gì | Đo bằng |
|---|---|---|---|
| **Primary** | Kỹ sư on-call / Incident Commander vận hành nền tảng | Rút ngắn khoảng thời gian từ lúc có tín hiệu đến lúc *bắt đầu* khắc phục | Thời gian tới giả thuyết đầu tiên |
| **Secondary** | Người dùng nội bộ & khách hàng của nền tảng | Biết dịch vụ nào đang ảnh hưởng mà không phải hỏi ai | Status page tự cập nhật |

Người dùng primary **không phải là người mới**. Họ biết cách sửa; thứ họ thiếu là bối cảnh được sắp xếp sẵn lúc 2 giờ sáng. Vì vậy sản phẩm không được thiết kế theo hướng "AI thay người quyết định", mà theo hướng "AI dọn bàn trước khi người ngồi xuống".

## 3. Giải pháp

Một AI Agent điều phối **trọn vòng đời incident** — phát hiện → phân loại → mở war room → thu thập bối cảnh → chẩn đoán có bằng chứng → đề xuất khắc phục → *chờ người duyệt* → thực thi → xác minh hồi phục → postmortem.

Ba lựa chọn định hình toàn bộ dự án:

| Quyết định | Lựa chọn | Lý do ngắn | ADR |
|---|---|---|---|
| Lớp quản lý vòng đời incident | Jira Cloud | War room = Issue, HITL = workflow transition, audit trail = changelog, action item = sub-task. Không phải tự xây CRUD + phân quyền + audit | [0001](adr/0001-jira-lam-lop-incident-lifecycle.md) |
| Alerting | Prometheus, **không** Alertmanager | Logic ngưỡng nằm thẳng trong code Agent để kiểm soát được và nối trực tiếp vào LangGraph | [0002](adr/0002-khong-dung-alertmanager.md) |
| Cách tạo sự cố để demo | Load test thật, **không** fault injection giả | Pool DB giới hạn 5 → tải cao làm request xếp hàng → latency tăng do nghẽn cổ chai thật, service phụ thuộc timeout theo một cách tự nhiên | [0003](adr/0003-load-test-that-thay-fault-injection.md) |

## 4. Điểm khác biệt

Ba thứ phân biệt dự án này với một con bot gắn vào Slack:

**a. Chẩn đoán có bằng chứng, không phải LLM đoán.**
Rule engine chạy **trước**, sinh ra con số (`p95 = 5.1s vs baseline 0.2s`, `pool 5/5 lúc 14:32`, `deploy v1.4.2 lúc 14:28`). LLM chỉ diễn giải bằng chứng đó thành câu và chọn runbook. Mọi giả thuyết đều truy vết ngược được về một câu PromQL cụ thể — trường `evidence[].promql` trong `Hypothesis` tồn tại chính vì lý do này.

**b. HITL được thực thi bằng cấu trúc, không bằng thiện chí.**
Agent không có đường nào tự phê duyệt. Điều này được gác ở ba tầng, không phải bằng một dòng ghi chú:
- `JiraClient` Protocol **không có method nào duyệt incident**
- `assert_human_approved()` đọc changelog Jira; nếu người chuyển trạng thái là account Agent → `ApprovalError`, không thi hành
- Mọi đường tới `execute_remediation` bắt buộc đi qua cổng đó; xoá lời gọi → CI đỏ

**c. Sự cố trong demo là sự cố thật.**
Không có `if demo_mode: raise`. Tải thật làm cạn pool thật, và service thứ hai timeout theo vì nó thật sự phụ thuộc service thứ nhất. Nghĩa là Agent phải chẩn đoán, không phải đọc kịch bản.

## 5. Chỉ số thành công

| # | Chỉ số | Ngưỡng đạt | Cách đo |
|---|---|---|---|
| M1 | Thời gian từ lúc metric vượt ngưỡng → Jira issue được tạo | < 60 giây | Timestamp Prometheus vs `Incident.detected_at` |
| M2 | Thời gian từ lúc phát hiện → giả thuyết đầu tiên có bằng chứng | < 3 phút | `TimelineEvent` của node `hypothesize` |
| M3 | Độ chính xác chẩn đoán nguyên nhân gốc | ≥ 2/3 use case đúng | So `Hypothesis.statement` với ground truth ở [use-cases.md](use-cases.md) |
| M4 | Phát hiện lan truyền | Nhận ra service thứ 2 và link issue | `Incident.related_incidents` khác rỗng |
| M5 | HITL không bị vượt qua | 100% | Test `test_hitl.py` — Agent tự duyệt phải bị từ chối |
| M6 | Status page phản ánh đúng trạng thái | Đổi trong ≤ 30s sau khi incident mở/đóng | Đối chiếu `StatusPage.updated_at` |

M3 là chỉ số khó nhất và là chỗ dự án có thể mất điểm. Nó chỉ đo được vì [use-cases.md](use-cases.md) đã chốt ground truth **trước khi** viết Agent — nếu chốt sau, con số sẽ tự khớp và vô nghĩa.

## 6. Phạm vi

**Trong phạm vi MVP:** phát hiện & phân loại severity · mở war room tự động · thu thập bối cảnh · đối chiếu deploy history · chẩn đoán + runbook · HITL bắt buộc · phát hiện lan truyền & link incident · escalation khi chờ duyệt quá lâu · status page công khai · war-room view nội bộ · postmortem tự động.

**Ngoài phạm vi (không làm, kể cả còn thời gian):**
- Sửa chữa tự động không cần người duyệt — trái ràng buộc bắt buộc của đề bài
- Tích hợp Slack / PagerDuty / email — Jira đã là kênh điều phối
- Nhận diện bất thường bằng ML (anomaly detection) — ngưỡng tĩnh + baseline là đủ, và đo được
- Multi-tenant, phân quyền người dùng, SSO
- Chạy production thật với traffic thật

**Tuỳ chọn (chỉ nếu còn thời gian):** học từ incident cũ qua JQL · Grafana dashboard.

## 7. Ràng buộc

| Loại | Ràng buộc | Hệ quả thiết kế |
|---|---|---|
| Đề bài | HITL bắt buộc trước mọi hành động production | Graph LangGraph *dừng hẳn* ở `await_approval`, không có edge tự động đi tiếp |
| Đề bài | Chẩn đoán phải có bằng chứng | Rule engine trước, LLM sau; mọi `Hypothesis` mang theo `MetricEvidence` |
| Thời gian | 6 tuần, 4 người làm song song | 4 contract chốt trước khi ai viết logic — nếu không, chuỗi phụ thuộc buộc Long chờ tới tuần 4 |
| Năng lực đội | 2 người giàu kinh nghiệm, 2 người ít | Chia việc theo năng lực, không chia đều; Long dùng Streamlit thay Next.js |
| Hạ tầng | Render free tier — ngủ sau 15 phút | UI phải đặt `timeout=60` và hiển thị thông báo cold-start |
| Hạ tầng | Jira Cloud bản mới chỉ tạo được team-managed project | Không đặt được điều kiện lên transition → cổng HITL chuyển sang kiểm changelog ở backend ([ADR-0001](adr/0001-jira-lam-lop-incident-lifecycle.md)) |
| Chi phí | Không ngân sách LLM | Qwen qua Alibaba Cloud Model Studio (endpoint tương thích OpenAI) |

## 8. Rủi ro chính

| Rủi ro | Ảnh hưởng | Cách giảm |
|---|---|---|
| Contract metric lệch tên → Prometheus trả rỗng, **không có exception** | Agent im lặng không phát hiện gì, không có gì để lần theo | Chốt tên metric + label thành văn bản trước khi viết code ([contract ①](contracts/01-metrics.md)); mỗi bên tự verify bằng `curl /metrics` |
| Agent mở hàng loạt incident trùng lúc load test | War room ngập rác, demo hỏng | Bắt buộc 2 quy tắc: xác nhận vượt ngưỡng liên tục ≥ 30s, và chống trùng theo service |
| Rollback chỉ ghi log mà không đổi hành vi thật | `verify` thấy metric chưa hồi phục → vòng lặp vô hạn giữa buổi demo | "Version" phải là công tắc runtime thật sự đổi hành vi DB, không chỉ một dòng trong `deploy_history` |
| Render ngủ đông đúng lúc demo | Trang trắng trước mặt giám khảo | Warm-up trước khi quay; UI hiển thị rõ trạng thái cold-start |
| Đường găng dồn vào Agent (Việt) | Ba khối kia xong mà không có gì nối chúng lại | `FakeJiraClient` + fixture JSON cho phép 3 khối kia hoàn thiện độc lập; Agent nối vào sau |

## 9. Mốc thời gian

| Tuần | Mục tiêu | Trạng thái |
|---|---|---|
| 1 (26/07–01/08) | Chốt đề tài, phân vai, kiến trúc + 3 ADR, 4 contract, deploy Live URL | ✅ Xong |
| 2 (02/08–08/08) | Agent: PromQL querier, rule engine, 3 node đầu chạy với `FakeJiraClient` | 🔄 Đang làm |
| 3 | Nối end-to-end: Jira thật, webhook, thực thi remediation | ⏳ |
| 4 | Lan truyền, escalation, postmortem; UI nối dữ liệu thật | ⏳ |
| 5 | Đo đạc theo M1–M6, evaluation evidence | ⏳ |
| 6 | Video demo, pitch deck, hoàn thiện | ⏳ |

## 10. Đội ngũ

| Thành viên | Vai trò | Sở hữu |
|---|---|---|
| Trương Công Thái Đức | Team Lead · Kiến trúc & Tích hợp | Contract/schema, `JiraClient`, cổng HITL, webhook, DevOps, tích hợp cuối |
| Việt | AI Agent Engineer | LangGraph, detection, rule engine, LLM diagnosis, correlation deploy, postmortem |
| Trung | Backend Engineer · QA | 2 service demo, load test, `deploy_history`, test suite, evaluation evidence |
| Phan Hoàng Long | Frontend Engineer · Demo | Status page, war-room view, video demo, pitch deck |

Lý do phân vai không chia đều 4 phần: [JOURNAL.md](../JOURNAL.md#week-1-2026-07-26---2026-08-01).
