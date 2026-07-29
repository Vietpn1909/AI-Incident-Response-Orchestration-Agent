# Checklist cấu hình Jira Cloud

Làm một lần, khoảng 20–30 phút.

> ⚠️ Dùng **workspace Jira miễn phí tự tạo**, tuyệt đối không dùng Jira của công ty/tổ chức. Lý do trong [ADR-0001](adr/0001-jira-lam-lop-incident-lifecycle.md).

> 📌 **Bản trước của file này yêu cầu tạo project `Company-managed` để cấu hình điều kiện phân quyền trên workflow. Yêu cầu đó đã bỏ** — Jira Cloud bản mới chỉ tạo được team-managed project. Cổng phê duyệt HITL giờ nằm ở backend, kiểm tra qua changelog. Chi tiết: [ADR-0001, mục "Cập nhật 2026-07-29"](adr/0001-jira-lam-lop-incident-lifecycle.md#cập-nhật-2026-07-29--hitl-chuyển-sang-kiểm-tra-changelog).

---

## Phần 0 — Vẫn cần HAI account Jira

Đây vẫn là điều quan trọng nhất, chỉ khác lý do.

Cổng HITL hoạt động bằng cách so **accountId** của người đã chuyển issue sang `Remediating` với accountId của Agent. Nếu Agent và người duyệt dùng **cùng một account**, backend không phân biệt được ai làm gì và cổng phê duyệt vô nghĩa.

| Account | Dùng cho |
|---|---|
| **Của bạn** | Vai on-call/IC — người bấm duyệt trên Jira |
| **Account riêng cho Agent** | Agent gọi REST API (tạo issue, comment, transition các bước khác) |

- [ ] Chuẩn bị một email thứ hai (Gmail phụ, hoặc `ductct+agent@gmail.com` nếu Gmail hỗ trợ)
- [ ] Jira → ⚙️ → **User management** → **Invite user** → mời email đó vào site
- [ ] Cả hai account đăng nhập được

---

## Phần 1 — Project

Dùng luôn project có sẵn, không cần tạo mới.

- [ ] Ghi lại URL site → đây là `JIRA_BASE_URL`, dạng `https://<tên>.atlassian.net`
- [ ] Ghi lại project key đang dùng (vd. `KAN`) → `JIRA_PROJECT_KEY`
- [ ] Xoá các space mẫu không dùng cho gọn (tuỳ, không bắt buộc)

Loại team-managed hay company-managed **không còn quan trọng**.

---

## Phần 2 — Trạng thái workflow (tuỳ chọn)

**Không bắt buộc.** Project đã có sẵn 5 status `Idea · To Do · In Progress · In Review · Done`, và [`JIRA_STATUS`](../src/services/jira/mapping.py) map thẳng vào 5 trạng thái incident nên code chạy được ngay.

Nhưng đổi tên 5 cột trên board thành đúng tên dưới đây sẽ làm **demo dễ hiểu hơn nhiều** — nhất là `Awaiting Approval`, vì đó là cổng HITL người chấm cần nhìn thấy:

```
Open  ·  Investigating  ·  Awaiting Approval  ·  Remediating  ·  Resolved
```

- [ ] Board của project → bấm vào tên cột → đổi tên (team-managed cho đổi trực tiếp)
- [ ] Sau khi đổi, sửa dict `JIRA_STATUS` trong `src/services/jira/mapping.py` cho khớp — chỉ một chỗ đó

Không cần cấu hình transition. Team-managed cho chuyển tự do giữa mọi trạng thái, và điều đó **không sao** vì hàng rào phê duyệt nằm ở backend.

---

## Phần 3 — Custom field: KHÔNG CẦN LÀM

Đã thử và **không dùng được**: global custom field tạo qua API thành công nhưng không xuất hiện trên team-managed project, vì loại này quản field riêng.

Thay bằng **label**, đã verify chạy đủ trên site thật:

| Dữ liệu | Label |
|---|---|
| Severity | `severity-P2` |
| Service ảnh hưởng | `service-service-thanh-toan` |
| Đánh dấu issue của Agent | `incident` |

`root_cause_confidence` nằm trong comment cùng bằng chứng số, không cần lên Jira.

Quy ước ở [`src/services/jira/mapping.py`](../src/services/jira/mapping.py), chi tiết đánh đổi trong [ADR-0001](adr/0001-jira-lam-lop-incident-lifecycle.md#cập-nhật-2026-07-29-2--dùng-label-thay-custom-field).

---

## Phần 4 — API token và accountId của Agent

- [ ] Đăng nhập bằng **account Agent** (không phải account bạn)
- [ ] https://id.atlassian.com/manage-profile/security/api-tokens → **Create API token** → copy ngay (chỉ hiện một lần)
- [ ] Lấy **accountId** của account Agent — đây là giá trị cổng HITL dựa vào. Cách dễ nhất, chạy sau khi đã có token:

```bash
curl -sS -u "<email-agent>:<token>" \
  "https://<site>.atlassian.net/rest/api/3/myself" | python3 -m json.tool | grep accountId
```

- [ ] Điền vào `.env` local **và** Render → service → Environment:

```
JIRA_BASE_URL           = https://______.atlassian.net
JIRA_EMAIL              = <email account Agent>
JIRA_API_TOKEN          = <token>
JIRA_PROJECT_KEY        = KAN
JIRA_AGENT_ACCOUNT_ID   = <accountId vừa lấy>
```

⚠️ `JIRA_AGENT_ACCOUNT_ID` **bắt buộc phải có**. Thiếu nó thì [`assert_human_approved()`](../src/services/hitl.py) raise `ValueError` và từ chối chạy — cố ý làm vậy, vì thiếu giá trị này đồng nghĩa không có cổng phê duyệt nào cả.

⚠️ Token không được commit. Lỡ đẩy lên GitHub thì revoke ngay ở link trên rồi tạo token mới.

---

## Phần 5 — Automation (tuỳ chọn, làm sau)

Không còn là bắt buộc. Nếu quota gói Free đủ thì làm, không thì Agent tự poll Jira.

- [ ] Project settings → **Automation** → tab **Usage**: xem giới hạn thực tế (khoảng 100 lần chạy/tháng)
- [ ] Kiểm tra action **Send web request** có dùng được trên gói Free không

### Rule 1: webhook khi được duyệt

- [ ] Trigger: **Issue transitioned** → To status = `Remediating`
- [ ] Action: **Send web request**
  - URL: `https://p-035-incident-agent.onrender.com/webhooks/jira`
  - Method: `POST`, Header `X-Webhook-Secret` = giá trị `JIRA_WEBHOOK_SECRET` trên Render
  - Body: `Issue data`

> Nếu `Send web request` bị chặn hoặc quota quá chật: cho Agent poll Jira bằng JQL tìm issue vừa sang `Remediating`, chậm hơn vài giây và luồng HITL giữ nguyên **vì cổng phê duyệt không nằm ở webhook**. Ghi kết quả kiểm tra vào JOURNAL.

---

## Phần 6 — Gửi lại cho người làm tích hợp

Token và accountId gửi riêng, không đăng group chat:

Đã xác định xong ngày 2026-07-29:

```
JIRA_BASE_URL         = https://jibinarybro.atlassian.net
JIRA_PROJECT_KEY      = KAN
account người duyệt   = thaiduc200427@gmail.com
                        712020:fd2ca790-fbc0-4c1a-9def-2538883643a8
account Agent         = thaiduc0201@gmail.com
                        712020:1bf02a7a-3621-4611-b358-7e905dd2dcf7
```

Còn thiếu: **API token của account Agent** (`thaiduc0201@gmail.com`). Đăng nhập bằng account đó → https://id.atlassian.com/manage-profile/security/api-tokens → tạo token → điền vào `.env`:

```
JIRA_EMAIL=thaiduc0201@gmail.com
JIRA_API_TOKEN=<token của account Agent>
JIRA_AGENT_ACCOUNT_ID=712020:1bf02a7a-3621-4611-b358-7e905dd2dcf7
```

⚠️ Phải là token của **account Agent**, không phải account chính. Nếu Agent dùng token của người duyệt thì cổng HITL không phân biệt được ai với ai và mất hiệu lực.

---

## Phần 7 — Verify bằng Jira thật

Sau khi có thông tin trên, `RealJiraClient` được implement theo [contract ③](../src/services/jira/client.py) và chạy 4 test với Jira thật:

| Test | Kỳ vọng |
|---|---|
| Agent tạo issue, comment, set custom field | Thành công |
| Agent chuyển `Open → Investigating → Awaiting Approval` | Thành công |
| Agent tự chuyển sang `Remediating`, rồi gọi remediation | **`ApprovalError`** — changelog cho thấy tác giả là Agent |
| Bạn bấm duyệt trên Jira, rồi gọi remediation | Thành công, trả về accountId của bạn |

Hai test cuối là bằng chứng cho ràng buộc bắt buộc của đề bài. Bản mock của chúng đã chạy trong CI: [`tests/test_services/test_hitl.py`](../tests/test_services/test_hitl.py).
