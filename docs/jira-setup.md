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

### ⚠️ Đo ngày 11/08/2026 — việc này CHƯA làm, và nó chặn màn demo phê duyệt

Không phải cảnh báo lý thuyết. `.env` lúc đó khai cùng một account cho cả hai vai:

```
JIRA_EMAIL             = thaiduc0201@gmail.com
accountId của email đó = 712020:1bf02a7a-3621-4611-b358-7e905dd2dcf7
JIRA_AGENT_ACCOUNT_ID  = 712020:1bf02a7a-3621-4611-b358-7e905dd2dcf7   ← TRÙNG
```

Chuyển KAN-17 sang `Remediating` bằng chính account đó — tức mô phỏng đúng việc
người trực bấm nút trên Jira — rồi gọi cổng HITL:

```
TỪ CHỐI — KAN-17 được chuyển sang Remediating bởi chính account Agent
(712020:1bf02a7a-…). Hành động production phải do người phê duyệt.
Từ chối thực thi.
```

Cổng chạy **đúng thiết kế**, nhưng vì hai vai dùng một account nên nó từ chối cả
người thật. Hệ quả: không demo được bước "người duyệt → hành động thi hành" —
đúng cái bước làm nên ý nghĩa của HITL.

Hai cách đi:

| Cách | Chi phí | Đánh đổi |
|---|---|---|
| Mời account thứ hai cho Agent (đúng như Phần 0) | ~10 phút, phải bấm trên Jira | Cách đúng. Còn dọn luôn việc mail thông báo Jira dội về hộp thư của người trực, vì Agent tự thành watcher |
| Để một thành viên khác bấm duyệt lúc demo | 0 phút | Phụ thuộc người đó online đúng lúc; và `.env` vẫn sai cho lần sau |

Kể cả chưa kịp làm, vẫn demo được **nửa mạnh hơn** của cổng: Agent tự chuyển
trạng thái thì bị từ chối, có log kèm accountId. Chứng minh Agent không tự duyệt
cho mình được — chỉ là chưa chứng minh được chiều còn lại.

---

## Phần 1 — Project

Dùng luôn project có sẵn, không cần tạo mới.

- [ ] Ghi lại URL site → đây là `JIRA_BASE_URL`, dạng `https://<tên>.atlassian.net`
- [ ] Ghi lại project key đang dùng (vd. `KAN`) → `JIRA_PROJECT_KEY`
- [ ] Xoá các space mẫu không dùng cho gọn (tuỳ, không bắt buộc)

Loại team-managed hay company-managed **không còn quan trọng**.

---

## Phần 2 — Đổi tên 5 cột board (nên làm sớm)

**Code chạy được cả khi chưa đổi** — `RealJiraClient` thử tên mong muốn trước, không có thì dùng tên mặc định. Nên không có khoảng thời gian hỏng, đổi lúc nào cũng được.

**Nhưng nên đổi sớm**, vì tên mặc định đã gây nhầm lẫn hai lần khi test thật:

1. Bug `Idea → Remediating`: issue vừa tạo đã hiện là "Remediating"
2. Comment Agent ghi *"chuyển sang trạng thái **To Do** để phê duyệt"* — đọc lên vô nghĩa, và người xem demo sẽ hiểu sai trạng thái

Cách đổi: mở board của project → bấm vào **tên cột** → sửa. Team-managed cho đổi trực tiếp, không cần quyền admin.

| Cột hiện tại | Đổi thành |
|---|---|
| `Idea` | **Open** |
| `In Progress` | **Investigating** |
| `In Review` | **Awaiting Approval** |
| `To Do` | **Remediating** |
| `Done` | **Resolved** |

Đổi xong **không cần sửa code** — `JIRA_STATUS` trong [`jira/mapping.py`](../src/services/jira/mapping.py) đã dùng đúng bộ tên này.

<details>
<summary>Bản cũ của mục này (giữ để tham khảo)</summary>

**Không bắt buộc.** Project đã có sẵn 5 status `Idea · To Do · In Progress · In Review · Done`, và [`JIRA_STATUS`](../src/services/jira/mapping.py) map thẳng vào 5 trạng thái incident nên code chạy được ngay.

Nhưng đổi tên 5 cột trên board thành đúng tên dưới đây sẽ làm **demo dễ hiểu hơn nhiều** — nhất là `Awaiting Approval`, vì đó là cổng HITL người chấm cần nhìn thấy:

```
Open  ·  Investigating  ·  Awaiting Approval  ·  Remediating  ·  Resolved
```

- [ ] Board của project → bấm vào tên cột → đổi tên (team-managed cho đổi trực tiếp)
- [ ] Sau khi đổi, sửa dict `JIRA_STATUS` trong `src/services/jira/mapping.py` cho khớp — chỉ một chỗ đó

Không cần cấu hình transition. Team-managed cho chuyển tự do giữa mọi trạng thái, và điều đó **không sao** vì hàng rào phê duyệt nằm ở backend.

</details>

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
  "https://<site>.atlassian.net/rest/api/3/myself" | python -m json.tool | grep accountId
```

> Trên Windows chạy trong **Git Bash** (PowerShell không có `grep`). Hoặc bỏ phần `| grep accountId` rồi tự tìm bằng mắt.

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

### ⚠️ Trước khi làm rule: điền biến Jira lên Render

Webhook chạy **trên Render**, không phải trên máy bạn. Nên nếu Render chưa có cấu hình Jira thì webhook sẽ lỗi ngay ở bước tạo client — và thông báo lỗi không chỉ về nguyên nhân này.

`render.yaml` đã khai sẵn 4 giá trị không bí mật (`JIRA_BASE_URL`, `JIRA_PROJECT_KEY`, `JIRA_EMAIL`, `JIRA_AGENT_ACCOUNT_ID`) nên chúng tự áp khi deploy. Còn lại điền tay:

- [ ] Render → service → **Environment** → điền `JIRA_API_TOKEN` (token của account Agent)
- [ ] Cùng trang, **copy giá trị `JIRA_WEBHOOK_SECRET`** mà Render tự sinh — cần cho cả rule Jira và script verify
- [ ] Dán secret đó vào `.env` local: `JIRA_WEBHOOK_SECRET=<giá trị>`

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

## Phần 6.5 — Verify cả chuỗi bằng một lệnh

Có script chạy trọn chuỗi và in rõ tắc ở mảnh nào:

```bash
# Bước 1 — chỉ kiểm logic, KHÔNG cần Jira Automation rule.
# Làm cái này TRƯỚC để loại trừ lỗi phía code.
uvicorn src.main:app --reload          # terminal khác
python scripts/verify_e2e.py --local

# Bước 2 — kiểm cả hop Jira Automation → Render.
python scripts/verify_e2e.py --live
```

Script làm 7 bước: Agent mở war room → đề xuất → **kiểm chưa duyệt thì bị từ chối** → **kiểm Agent tự duyệt thì bị từ chối** → dừng chờ bạn bấm duyệt trên Jira → gọi webhook → kiểm kết quả ghi lên war room.

Nó tạo issue **thật** rồi chuyển sang `Resolved` khi xong. Không xoá được vì account Agent không có quyền xoá — đúng như mong muốn.

Ý nghĩa mã lỗi nếu bước 6 fail:

| Mã | Nguyên nhân |
|---|---|
| `401` | `JIRA_WEBHOOK_SECRET` trong `.env` không khớp giá trị trên Render |
| `403` | Bạn chưa chuyển trạng thái, hoặc `JIRA_AGENT_ACCOUNT_ID` trên Render sai |
| `503` | Render chưa có `JIRA_WEBHOOK_SECRET` |

## Phần 7 — Verify bằng Jira thật

Sau khi có thông tin trên, `RealJiraClient` được implement theo [contract ③](../src/services/jira/client.py) và chạy 4 test với Jira thật:

| Test | Kỳ vọng |
|---|---|
| Agent tạo issue, comment, set custom field | Thành công |
| Agent chuyển `Open → Investigating → Awaiting Approval` | Thành công |
| Agent tự chuyển sang `Remediating`, rồi gọi remediation | **`ApprovalError`** — changelog cho thấy tác giả là Agent |
| Bạn bấm duyệt trên Jira, rồi gọi remediation | Thành công, trả về accountId của bạn |

Hai test cuối là bằng chứng cho ràng buộc bắt buộc của đề bài. Bản mock của chúng đã chạy trong CI: [`tests/test_services/test_hitl.py`](../tests/test_services/test_hitl.py).
