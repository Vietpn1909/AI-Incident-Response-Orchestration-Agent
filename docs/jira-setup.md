# Checklist cấu hình Jira Cloud

Làm một lần, khoảng 30–45 phút. Làm theo đúng thứ tự — phần sau phụ thuộc phần trước.

> ⚠️ Dùng **workspace Jira miễn phí tự tạo**, tuyệt đối không dùng Jira của công ty/tổ chức. Lý do trong [ADR-0001](adr/0001-jira-lam-lop-incident-lifecycle.md).

---

## Phần 0 — Điều quan trọng nhất: cần HAI account Jira

Đây là chỗ dễ làm sai nhất, và làm sai thì **toàn bộ cơ chế HITL vô nghĩa**.

Ràng buộc của đề bài là Agent **không được** tự chuyển incident sang `Remediating`. Nhưng nếu Agent dùng API token của bạn, nó có đúng quyền của bạn — tức là chuyển được. Lúc đó "HITL" chỉ là lời hứa trong code, không phải cơ chế được thực thi.

Nên cần:

| Account | Dùng cho | Quyền |
|---|---|---|
| **Của bạn** (`ductct@...`) | Vai on-call/IC — người duyệt | Đầy đủ, chuyển được sang `Remediating` |
| **Account riêng cho Agent** | Agent gọi REST API | Tạo issue, comment, chuyển các bước khác — **KHÔNG** chuyển được sang `Remediating` |

Tạo account thứ hai bằng một email khác (Gmail phụ, hoặc `+agent` nếu Gmail hỗ trợ: `ductct+agent@gmail.com`). Sau đó mời vào Jira site.

- [ ] Có 2 account Jira, cả hai đăng nhập được

---

## Phần 1 — Tạo site và project

- [ ] Vào https://www.atlassian.com/software/jira/free → tạo site mới (dạng `<tên>.atlassian.net`)
- [ ] Ghi lại URL site — đây là `JIRA_BASE_URL`
- [ ] Tạo project mới, **chọn loại `Company-managed`** (có nơi gọi là *Classic*)

> ⚠️ **Phải là Company-managed, không phải Team-managed.** Team-managed project có workflow đơn giản hoá, **không cho thêm condition lên transition** — tức không cấu hình được cổng phê duyệt. Nếu tạo sai loại thì phải tạo lại project từ đầu, không đổi được.

- [ ] Project key đặt là `INC` (để issue có dạng `INC-1`, khớp với `FakeJiraClient`)
- [ ] Template chọn `Bug tracking` hoặc `Kanban` — không quan trọng, sẽ tự sửa workflow sau

---

## Phần 2 — Issue type và custom field

- [ ] Project settings → **Issue types** → tạo issue type tên `Incident`
- [ ] Tạo 3 custom field, gắn vào screen của `Incident`:

| Tên field | Kiểu | Giá trị |
|---|---|---|
| `severity` | Select list (single choice) | `P1`, `P2`, `P3`, `P4` |
| `affected_service` | Short text | (để trống) |
| `root_cause_confidence` | Number | (để trống) |

- [ ] Ghi lại **field ID** của từng field: Settings → Issues → Custom fields → hover vào field, URL có dạng `...customFieldId=10050` → ID là `customfield_10050`

Cần field ID vì REST API dùng ID chứ không dùng tên. Ghi lại theo mẫu:

```
severity              = customfield_____
affected_service      = customfield_____
root_cause_confidence = customfield_____
```

---

## Phần 3 — Workflow 5 trạng thái

- [ ] Project settings → **Workflows** → edit workflow của `Incident`
- [ ] Tạo đúng 5 status, **tên viết chính xác như dưới** (khớp `IncidentState` trong [src/models/incident.py](../src/models/incident.py)):

```
Open  →  Investigating  →  Awaiting Approval  →  Remediating  →  Resolved
```

- [ ] Thêm transition giữa các bước theo đúng thứ tự trên
- [ ] Thêm transition `Resolved` ← từ bất kỳ đâu (để đóng sớm khi báo động sai)

### Chặn Agent ở cổng phê duyệt — bước then chốt

- [ ] Settings → Groups → tạo group `oncall-approvers`, thêm **account của bạn** vào (KHÔNG thêm account Agent)
- [ ] Trong workflow, click vào transition **`Awaiting Approval → Remediating`** → tab **Conditions** → **Add condition** → chọn **User Is In Group** → chọn `oncall-approvers`
- [ ] Publish workflow

Sau bước này, Agent gọi API để chuyển sang `Remediating` sẽ nhận lỗi HTTP 400/403 — giống hệt `PermissionError` mà `FakeJiraClient` đã mô phỏng.

---

## Phần 4 — Automation

- [ ] Project settings → **Automation**

### Rule 1: webhook khi được duyệt

- [ ] Trigger: **Issue transitioned** → To status = `Remediating`
- [ ] Action: **Send web request**
  - URL: `https://p-035-incident-agent.onrender.com/webhooks/jira`
  - Method: `POST`
  - Header: `X-Webhook-Secret` = giá trị lấy từ Render (Dashboard → service → Environment → `JIRA_WEBHOOK_SECRET`)
  - Body: `Issue data` (hoặc custom JSON có `{{issue.key}}`)
- [ ] Đặt tên rule: `Approved → notify agent`, bật rule

### Rule 2: leo thang khi treo quá lâu

- [ ] Trigger: **Scheduled** → mỗi 5 phút, kèm JQL:
  ```
  project = INC AND status = "Awaiting Approval" AND updated <= -10m
  ```
- [ ] Action: **Add comment** — nội dung cảnh báo leo thang
- [ ] Đặt tên: `Escalate stale approval`, **tạm thời để TẮT** (bật lúc test để không tốn quota)

### Kiểm tra quota — làm ngay, đừng bỏ qua

- [ ] Project settings → Automation → tab **Usage**: xem giới hạn thực tế của gói Free (khoảng 100 lần chạy/tháng)
- [ ] Kiểm tra action **Send web request** có dùng được trên gói Free không

> Nếu `Send web request` bị chặn (yêu cầu gói trả phí), **không cần đổi kiến trúc**: chuyển sang cho Agent tự poll Jira định kỳ (query JQL tìm issue vừa sang `Remediating`) thay vì chờ webhook. Chậm hơn vài giây, nhưng luồng HITL giữ nguyên và không cần public URL nữa. Ghi lại kết quả kiểm tra này vào JOURNAL vì nó ảnh hưởng thiết kế.

---

## Phần 5 — API token cho Agent

- [ ] Đăng nhập bằng **account Agent** (không phải account bạn)
- [ ] Vào https://id.atlassian.com/manage-profile/security/api-tokens → **Create API token**
- [ ] Copy token ngay (chỉ hiện một lần)
- [ ] Điền vào Render → service → Environment:

```
JIRA_BASE_URL  = https://<tên-site>.atlassian.net
JIRA_EMAIL     = <email của account Agent>
JIRA_API_TOKEN = <token vừa tạo>
```

- [ ] Đồng thời thêm 3 biến này vào `.env` local (file đã gitignore, không lo lộ)

⚠️ Token này **không được commit**. Nếu vô tình đẩy lên GitHub thì vào lại trang trên revoke ngay rồi tạo token mới.

---

## Phần 6 — Cần gửi lại cho ai làm tích hợp

Sau khi xong, gửi 5 thông tin sau (token gửi riêng, không đăng group chat):

```
JIRA_BASE_URL         = https://______.atlassian.net
Project key           = INC
severity              = customfield_____
affected_service      = customfield_____
root_cause_confidence = customfield_____
Send web request có dùng được trên Free?   có / không
Quota automation còn lại:                  ___/100
```

---

## Phần 7 — Sẽ verify bằng test thật

Sau khi có thông tin trên, `RealJiraClient` được implement theo [contract ③](../src/services/jira_client.py) và chạy 3 test này với Jira thật — không phải giả định:

| Test | Kỳ vọng |
|---|---|
| Agent tạo issue, comment, chuyển `Open → Investigating → Awaiting Approval` | Thành công |
| **Agent chuyển `Awaiting Approval → Remediating`** | **Bị từ chối** (403/400) — nếu thành công thì cấu hình Phần 3 sai, HITL không được thực thi |
| Account của bạn chuyển `Awaiting Approval → Remediating` | Thành công |

Test thứ hai là quan trọng nhất. Nó là bằng chứng cho thấy ràng buộc bắt buộc của đề bài được thực thi ở tầng hạ tầng, không phải bằng thiện chí trong code.
