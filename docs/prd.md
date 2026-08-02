# PRD — AI Agent Điều Phối Ứng Phó Sự Cố

**Đề bài:** PTNT-20 · **Team:** Binary Brothers · **Phiên bản:** 1.0 (2026-08-02)

> Bối cảnh và lý do nằm ở [brief.md](brief.md). Tài liệu này chốt **làm gì** và **thế nào là xong**. Thiết kế nằm ở [architecture_diagram.md](architecture_diagram.md), giao diện ở [ui-flow.md](ui-flow.md).

---

## 1. Phạm vi tài liệu

PRD này mô tả một hệ thống gồm hai nửa cố ý tách rời:

- **Sản phẩm** — Agent, API, hai trang UI. Đây là thứ được chấm.
- **Môi trường mẫu** — 2 service demo + Postgres + Prometheus, tồn tại chỉ để *tạo ra sự cố thật* cho Agent chẩn đoán.

Hai nửa này **không được import nhau**, chỉ nói chuyện qua HTTP và `/metrics`. Nếu backend import được `demo/`, Agent biết trước đáp án và phần chẩn đoán mất ý nghĩa.

## 2. Persona & User Story

### P1 — Kỹ sư on-call (primary)

| ID | User story | Ưu tiên |
|---|---|---|
| US-01 | Là on-call, tôi muốn được báo khi dịch vụ suy giảm **kèm mức độ nghiêm trọng**, để biết có phải dậy lúc 2h sáng không | Bắt buộc |
| US-02 | Là on-call, tôi muốn mở war room ra là đã có sẵn metric, log và lịch sử deploy, để không mất 20 phút đi gom | Bắt buộc |
| US-03 | Là on-call, tôi muốn thấy giả thuyết nguyên nhân **kèm con số dẫn chứng**, để tự kiểm chứng thay vì tin lời máy | Bắt buộc |
| US-04 | Là on-call, tôi muốn tự quyết định có chạy hành động khắc phục hay không, để chịu trách nhiệm được về thứ chạm vào production | Bắt buộc |
| US-05 | Là on-call, tôi muốn biết khi sự cố lan sang dịch vụ khác, để không xử lý nhầm triệu chứng thay vì nguyên nhân | Bắt buộc |
| US-06 | Là on-call, tôi muốn bị nhắc dữ hơn nếu tôi lỡ không phản hồi, để sự cố không treo im lặng | Nên có |
| US-07 | Là on-call, tôi muốn có sẵn bản nháp postmortem khi đóng sự cố, để không phải dựng lại timeline từ trí nhớ | Nên có |

### P2 — Người dùng dịch vụ (secondary)

| ID | User story | Ưu tiên |
|---|---|---|
| US-08 | Là người dùng, tôi muốn xem một trang biết dịch vụ nào đang có vấn đề, để không phải hỏi ai | Bắt buộc |

---

## 3. Yêu cầu chức năng

Ký hiệu: **[M]** bắt buộc cho MVP · **[S]** nên có · **[C]** tuỳ chọn.

### FR-01 [M] — Phát hiện sự cố

Agent định kỳ query Prometheus và so với baseline để phát hiện suy giảm.

- Query theo các câu PromQL đã chốt ở [contract ①](contracts/01-metrics.md)
- Tín hiệu chính: `p95 latency`, `tỷ lệ lỗi 5xx`, `mức sử dụng pool`
- Baseline: p95 trung bình 30 phút trước

**Tiêu chí nghiệm thu**
- [ ] Sinh ra `IncidentSignal` hợp lệ khi p95 vượt ngưỡng
- [ ] **Chỉ** tính là incident khi vượt ngưỡng **liên tục ≥ 30 giây** — một điểm dữ liệu đơn lẻ không kích hoạt gì
- [ ] Trước khi mở war room, kiểm tra service đó đã có incident đang mở chưa; nếu có thì **không** mở cái mới
- [ ] Không có sự cố nào thì graph kết thúc im lặng, không tạo artifact

> Hai điều kiện xác nhận và chống trùng không phải tối ưu hoá — thiếu chúng, lúc chạy load test Agent mở hàng loạt incident trùng và war room thành rác.

### FR-02 [M] — Phân loại severity

Rule thuần, không LLM, để đo được độ chính xác.

| Severity | Điều kiện |
|---|---|
| P1 | p95 > 10s **hoặc** tỷ lệ lỗi > 50% **hoặc** ≥ 2 service bị ảnh hưởng |
| P2 | p95 > 2s hoặc tỷ lệ lỗi > 10% |
| P3 | p95 > 1s hoặc tỷ lệ lỗi > 1% |
| P4 | Lệch baseline nhưng chưa vượt ngưỡng cứng |

**Tiêu chí nghiệm thu**
- [ ] Hàm phân loại là hàm thuần, có unit test cho cả 4 mức
- [ ] Không gọi LLM trong đường đi này
- [ ] Khi service thứ hai bị ảnh hưởng, severity **tự nâng lên P1**

### FR-03 [M] — Tự mở war room

Tạo Jira Issue làm không gian điều phối, kèm comment bối cảnh phát hiện.

**Tiêu chí nghiệm thu**
- [ ] Issue được tạo qua `JiraClient.create_incident()`, không gọi thẳng REST API từ node
- [ ] Title, severity, service ảnh hưởng, thời điểm phát hiện có mặt trên issue
- [ ] Comment đầu tiên chứa metric đã vượt ngưỡng và câu PromQL dùng để đo
- [ ] `Incident.jira_key` trả về đúng key thật

### FR-04 [M] — Thu thập bối cảnh

Gom metric liên quan, xác định service phụ thuộc.

**Tiêu chí nghiệm thu**
- [ ] `IncidentSignal.evidence` chứa ít nhất: p95, tỷ lệ lỗi, mức dùng pool
- [ ] Mỗi `MetricEvidence` mang theo `promql` — người khác kiểm chứng lại được
- [ ] Baseline được ghi kèm giá trị đo, không chỉ ghi giá trị hiện tại

### FR-05 [M] — Đối chiếu lịch sử deploy

So thời điểm incident với bảng `deploy_history` để tìm nghi phạm.

**Tiêu chí nghiệm thu**
- [ ] Tìm được deploy gần nhất của service bị ảnh hưởng trong cửa sổ trước thời điểm phát hiện
- [ ] `Hypothesis.related_deploy` được gắn `version`, `commit_sha`, `deployed_at`, `deployed_by`
- [ ] Không có deploy nào trong cửa sổ → trường để trống, **không bịa**

### FR-06 [M] — Chẩn đoán có bằng chứng

**Rule engine chạy trước, LLM diễn giải sau.** Đây là yêu cầu bắt buộc của đề bài, không phải lựa chọn phong cách.

**Tiêu chí nghiệm thu**
- [ ] `Hypothesis.confidence` do **rule engine** tính, không phải LLM tự nhận
- [ ] `Hypothesis.evidence` không được rỗng
- [ ] `Hypothesis.reasoning` là phần LLM sinh, và chỉ diễn giải bằng chứng đã có
- [ ] Ngắt LLM (không có API key) → vẫn ra được giả thuyết dạng rule, chỉ mất phần diễn giải
- [ ] Có gợi ý runbook tương ứng loại sự cố

> Nếu để LLM tự suy luận từ dữ liệu thô, kết quả không truy vết được về số liệu nào — và chỉ số M3 không đo được.

### FR-07 [M] — Phát hiện lan truyền & link incident

**Tiêu chí nghiệm thu**
- [ ] Nhận biết service thứ hai suy giảm trong cùng cửa sổ thời gian
- [ ] Gọi `JiraClient.link_issues()` với quan hệ `relates to`
- [ ] `Incident.related_incidents` chứa key của issue kia ở **cả hai** chiều
- [ ] Severity được nâng theo FR-02

### FR-08 [M] — HITL bắt buộc

Agent đề xuất hành động rồi **dừng hẳn**. Không có đường đi tiếp nếu không có tín hiệu từ người.

**Tiêu chí nghiệm thu**
- [ ] `RemediationProposal.requires_approval` mặc định `True` cho hành động production
- [ ] Node `await_approval` không có edge tự động sang `execute_remediation`
- [ ] `JiraClient` Protocol **không có method nào duyệt incident**
- [ ] `assert_human_approved()` đọc changelog Jira; tác giả transition là account Agent → `ApprovalError`, không thi hành
- [ ] Mọi đường tới `execute_remediation` đi qua cổng đó; hiện chỉ có một đường là `POST /webhooks/jira`
- [ ] Có test tự động chứng minh Agent tự duyệt bị từ chối (`tests/test_services/test_hitl.py`)

> Ràng buộc này được thực thi bằng cấu trúc chứ không bằng thiện chí. Xoá lời gọi cổng phê duyệt thì CI đỏ — đó là chủ đích.

### FR-09 [M] — Thực thi khắc phục sau khi được duyệt

**Tiêu chí nghiệm thu**
- [ ] Webhook Jira → xác thực shared secret → `assert_human_approved()` → danh sách hành động cho phép
- [ ] Hành động ngoài danh sách cho phép bị từ chối
- [ ] Rollback đổi hành vi thật của service, không chỉ ghi log
- [ ] Mọi bước được ghi vào `Incident.timeline` với `actor` phân biệt `agent` / tên người

### FR-10 [M] — Xác minh hồi phục

**Tiêu chí nghiệm thu**
- [ ] Sau khi thực thi, query lại Prometheus và so ngưỡng
- [ ] Chưa hồi phục → quay lại `propose_remediation` đề xuất phương án khác
- [ ] Hồi phục → chuyển Jira sang `Resolved`

### FR-11 [M] — Status page công khai

**Tiêu chí nghiệm thu**
- [ ] Hiển thị từng dịch vụ với 1 trong 4 trạng thái: `operational` / `degraded` / `down` / `maintenance`
- [ ] Trạng thái tổng theo thứ tự ưu tiên `down > degraded > maintenance > operational`
- [ ] Dịch vụ đang có sự cố hiện kèm Jira key
- [ ] Cập nhật trong ≤ 30 giây sau khi incident mở hoặc đóng
- [ ] **Không** lộ chi tiết nội bộ: giả thuyết, bằng chứng, runbook, đề xuất

### FR-12 [M] — War-room view nội bộ

**Tiêu chí nghiệm thu**
- [ ] Danh sách incident sắp theo thời gian phát hiện, mới nhất trước
- [ ] Lọc được "chỉ hiện đang mở"
- [ ] Incident ở trạng thái `Awaiting Approval` được đánh dấu nổi bật
- [ ] Trang chi tiết có đủ 6 khối: tín hiệu · giả thuyết · đề xuất · timeline · postmortem · incident liên quan
- [ ] Bấm được sang incident liên quan
- [ ] **Không có nút duyệt** — duyệt xảy ra trên Jira (xem [ui-flow.md](ui-flow.md#4-vì-sao-war-room-không-có-nút-duyệt))

### FR-13 [S] — Escalation khi chờ duyệt quá lâu

**Tiêu chí nghiệm thu**
- [ ] Treo quá ngưỡng thời gian → tăng severity + comment cảnh báo
- [ ] Escalate xong **quay lại** `await_approval`, không đi tiếp
- [ ] Không có đường nào cho phép Agent tự duyệt sau khi escalate

### FR-14 [S] — Postmortem tự động

**Tiêu chí nghiệm thu**
- [ ] Sinh `summary`, `root_cause`, `impact`, `timeline`, `actions_taken`
- [ ] Mỗi action item được tạo thành Jira sub-task và mang `jira_key` thật
- [ ] Văn phong blameless — mô tả hệ thống, không quy trách nhiệm cá nhân

### FR-15 [C] — Học từ incident cũ · FR-16 [C] — Grafana dashboard

Chỉ làm nếu FR-01…FR-14 đã xong và còn thời gian.

---

## 4. Yêu cầu phi chức năng

| ID | Yêu cầu | Ngưỡng | Kiểm chứng |
|---|---|---|---|
| NFR-01 | Độ trễ phát hiện | Metric vượt ngưỡng → Jira issue < 60s | Chỉ số M1 |
| NFR-02 | Độ trễ chẩn đoán | Phát hiện → giả thuyết đầu tiên < 3 phút | Chỉ số M2 |
| NFR-03 | Truy vết | Mọi giả thuyết truy về được một câu PromQL cụ thể | Trường `evidence[].promql` |
| NFR-04 | Chịu lỗi phụ thuộc | Jira lỗi → hệ thống báo rõ mã lỗi, không nuốt thành HTTP 500 chung | `JiraApiError.status_code` |
| NFR-05 | Chịu lỗi LLM | Không có LLM → vẫn chẩn đoán được dạng rule | FR-06 |
| NFR-06 | An ninh webhook | 3 lớp: shared secret → kiểm changelog → allowlist hành động | `src/api/webhooks.py` |
| NFR-07 | Bí mật | Không có credential nào trong repo; đọc từ `.env` | `.gitignore`, `.env.example` |
| NFR-08 | Quan sát được | LLM interaction được trace lên LangSmith | Deliverable #4 |
| NFR-09 | Chất lượng code | `ruff` sạch, type hints, không `except` trần | CI |
| NFR-10 | Kiểm thử | Test bảo vệ cả 4 contract; đổi contract mà quên phía kia → CI đỏ | `tests/` |
| NFR-11 | UI cold start | Render free tier ngủ sau 15 phút → UI đặt `timeout=60`, báo rõ cho người dùng | `ui/*.py` |
| NFR-12 | Múi giờ | Mọi thời điểm hiển thị theo giờ Việt Nam (UTC+7); lưu trữ theo UTC | `fmt_time_vn()` |

---

## 5. Mô hình dữ liệu

Contract ② — Pydantic model dùng chung giữa cả 4 người, định nghĩa ở [`src/models/incident.py`](../src/models/incident.py).

```
StatusPage ──┬── ServiceStatus (name, health, message, active_incident)
             └── Incident ──┬── IncidentSignal ── MetricEvidence[]
                            ├── Hypothesis[] ──┬── MetricEvidence[]
                            │                  └── DeployRecord
                            ├── RemediationProposal
                            ├── TimelineEvent[]
                            ├── Postmortem ── ActionItem[]
                            └── related_incidents: str[]
```

Enum chốt cứng: `Severity` (P1–P4) · `IncidentState` · `ServiceHealth` (`operational`/`degraded`/`down`/`maintenance`).

Đổi model này là đổi thoả thuận giữa 4 người → bắt buộc PR riêng, người ở đầu kia review. Xem [luật sửa contract](contracts/README.md#luật-sửa-contract).

---

## 6. Giao diện lập trình

| Method | Path | Mô tả | Người dùng |
|---|---|---|---|
| GET | `/health` | Health check | Hạ tầng |
| GET | `/api/status` | Dữ liệu status page công khai | Status page |
| GET | `/api/incidents` | Danh sách incident, lọc `?only_open=true` | War room |
| GET | `/api/incidents/{jira_key}` | Chi tiết: giả thuyết, bằng chứng, timeline, postmortem | War room |
| POST | `/webhooks/jira` | Trigger sau khi có người duyệt → thi hành khắc phục | Jira Automation |

Ba endpoint incident **đã trả dữ liệu thật từ fixture ngay bây giờ**, nên UI hoàn thiện được trước khi Agent và Jira tồn tại. Tuần 3 đổi nguồn dữ liệu, **hình dạng response không đổi** — đó là toàn bộ mục đích của contract ④.

---

## 7. Ngoài phạm vi

Ghi rõ để không trôi phạm vi giữa chừng:

- Tự sửa chữa không cần người duyệt — **trái ràng buộc bắt buộc**, không phải chuyện thiếu thời gian
- Tích hợp Slack / PagerDuty / email
- Anomaly detection bằng ML
- Multi-tenant, phân quyền người dùng, SSO
- Chạy production thật với traffic thật
- Nút duyệt trên UI (xem [ui-flow.md](ui-flow.md#4-vì-sao-war-room-không-có-nút-duyệt))

---

## 8. Kế hoạch phát hành

| Mốc | Nội dung | Yêu cầu | Tuần |
|---|---|---|---|
| R0 | Contract + fixture + Live URL | — | 1 ✅ |
| R1 | Agent phát hiện và mở được Jira issue thật từ tín hiệu Prometheus thật | FR-01…FR-03 | 2 |
| R2 | Chẩn đoán có bằng chứng + luồng duyệt end-to-end | FR-04…FR-06, FR-08, FR-09 | 3 |
| R3 | Lan truyền, escalation, postmortem, UI nối dữ liệu thật | FR-07, FR-10…FR-14 | 4 |
| R4 | Đo M1–M6, evaluation evidence | Toàn bộ | 5 |
| R5 | Video demo, pitch deck | — | 6 |

Đường găng là Agent. Ba khối còn lại (service demo, API/Jira, UI) đã chạy độc lập được nhờ `FakeJiraClient` và fixture.

---

## 9. Kịch bản kiểm chứng

Ba use case đã chốt ground truth **trước khi** viết Agent, chi tiết ở [use-cases.md](use-cases.md):

| UC | Sự cố | Nguyên nhân gốc (ground truth) | Severity mong đợi |
|---|---|---|---|
| UC-1 | Cạn connection pool do tải | Pool = 5, request xếp hàng | P2 |
| UC-1a | Lan truyền sang service phụ thuộc | Vẫn là pool của service gốc; service thứ 2 là nạn nhân | P1 |
| UC-2 | Service chết do OOM, restart loop | Rò rỉ bộ nhớ | P1 |
| UC-3 | Burst xác thực thất bại | Dấu hiệu tấn công dò mật khẩu | P2 |

Chốt ground truth trước là điều kiện để M3 có ý nghĩa. Chốt sau thì con số sẽ tự khớp và không đo gì cả.

---

## 10. Câu hỏi còn mở

| # | Câu hỏi | Chặn cái gì | Người theo |
|---|---|---|---|
| Q1 | `MIE` / `MIP` trong đề bài là viết tắt của gì | Cách diễn đạt trong pitch | Đức — hỏi mentor |
| Q2 | Tấn công dạng metric-visible (UC-3) có được chấp nhận là "sự cố" không | Có làm UC-3 hay bỏ | Đức — hỏi mentor |
| Q3 | Ngưỡng thời gian escalation là bao nhiêu phút | FR-13 | Việt — chốt sau khi đo thời gian thật |
