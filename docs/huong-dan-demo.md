# Hướng dẫn tự demo — từ máy trắng đến màn diễn

> File này dành cho **người chưa từng đụng vào dự án**. Không cần đọc code, không
> cần biết LangGraph là gì. Làm theo từ trên xuống là chạy được.
>
> Đã biết hệ thống rồi và chỉ cần lời thoại lúc diễn thì sang
> [demo-runbook.md](demo-runbook.md).

---

## Bản đồ 30 giây

Hệ thống có **9 thứ chạy cùng lúc**, chia làm hai nhóm:

| Trong Docker | Trên máy (không đóng gói) |
|---|---|
| Postgres · `5432` | Backend FastAPI · `8000` |
| service-thanh-toan · `8001` | Giao diện Streamlit · `8501` |
| service-dat-hang · `8002` | Agent (vòng quét 10 giây) |
| service-kho-hang · `8003` | |
| service-van-chuyen · `8004` | |
| Prometheus · `9090` | |

Ba thứ bên phải **cố ý không bỏ vào container**: backend gọi `docker logs` để
lấy log tươi cho war room, nằm trong container thì phải mount `docker.sock` —
trên Windows là chuyện phiền và thừa.

Chuyện xảy ra khi demo, theo đúng thứ tự:

```
bắn tải  →  Prometheus thấy p95 vọt  →  Agent quét (10s/lần) thấy vượt ngưỡng
         →  mở phiếu Jira + đọc log + chẩn đoán  →  đề xuất khắc phục
         →  DỪNG, chờ người duyệt          ← đây là cổng HITL, điểm chính của bài
         →  người kéo phiếu trên Jira  →  Jira gọi webhook  →  Agent thi hành
         →  tự kiểm tra đã khỏi chưa  →  viết postmortem  →  gửi mail
```

---

## A. Cài lần đầu — làm một lần duy nhất

### A1. Thứ phải có sẵn

- **Python 3.11+**
- **Docker Desktop** — phải mở được, không chỉ cài
- **Git**

### A2. Môi trường Python

```bash
python -m venv .venv
```

```bash
.venv/Scripts/pip install -r requirements.txt -r demo/requirements.txt
```

> Thư mục là `.venv` **có dấu chấm**. Tài liệu cũ trong repo có chỗ ghi `venv`
> không chấm — chép nhầm thì mọi lệnh báo `No such file or directory` mà không
> nói vì sao.
>
> `demo/requirements.txt` là bắt buộc, không phải tùy chọn: thiếu
> `prometheus_client` thì `tests/test_services/test_demo_services.py` không
> collect được và bộ test tụt 11 case mà không báo đỏ.

### A3. File `.env`

```bash
cp .env.example .env
```

Rồi điền. **Ba nhóm, chỉ nhóm đầu là bắt buộc:**

| Nhóm | Khóa | Thiếu thì sao |
|---|---|---|
| **Bắt buộc** | `DATABASE_URL` | Agent mù về lịch sử deploy, UC-4 mất `change_note` |
| | `JIRA_BASE_URL` `JIRA_EMAIL` `JIRA_API_TOKEN` `JIRA_PROJECT_KEY` | Không mở được phiếu — dùng `--fake` để chạy chay |
| | `JIRA_AGENT_ACCOUNT_ID` | **Cổng HITL không chạy** — xem A4 |
| | `JIRA_WEBHOOK_SECRET` | Webhook trả 401, người duyệt xong không có gì xảy ra |
| **Nên có** | `OPENAI_API_KEY` `LLM_BASE_URL` `MODEL_NAME` | Agent vẫn chạy bằng bộ luật, nhưng chẩn đoán cụt |
| | `SMTP_EMAIL` `SMTP_APP_PASSWORD` `POSTMORTEM_RECIPIENTS` | Không có mail postmortem |
| **Tùy** | `DAILY_API_KEY` | Sự cố P1/P2 không kèm link phòng họp |
| | `AUTO_REMEDIATION_ENABLED` `AUTO_REMEDIATION_TIMEOUT_MINUTES` | Không diễn được trường hợp "hết giờ chờ, Agent tự làm" |

> ⚠️ `.env` nằm trong `.gitignore`. **Đừng commit nó** — trong đó có token Jira
> và mật khẩu ứng dụng Gmail.

### A4. `JIRA_AGENT_ACCOUNT_ID` — khóa dễ bỏ sót nhất

Cổng HITL hoạt động bằng cách đọc changelog Jira và **từ chối nếu người chuyển
trạng thái chính là Agent**. Không có `accountId` của Agent thì nó không biết đâu
là Agent, và `hitl.assert_human_approved()` ném lỗi ngay — cố ý fail to, vì cấu
hình sai ở đây nghĩa là cổng an toàn đang mở toang.

Lấy nó bằng:

```bash
curl -u "EMAIL:API_TOKEN" "https://<site>.atlassian.net/rest/api/3/myself"
```

Trường `accountId` trong kết quả, dạng `712020:xxxxxxxx-...`.

### A5. Hai rule Jira Automation

Đây là **cầu nối** từ Jira về máy — không phải cái cổng, mà là dây dẫn.

| Rule | Kích hoạt khi | Gọi |
|---|---|---|
| 1 | phiếu chuyển sang **Remediating** | `POST <api>/webhooks/jira` |
| 2 | phiếu chuyển sang **Resolved** | `POST <api>/webhooks/jira/resolved` |

Cả hai gửi header `X-Webhook-Secret` bằng đúng `JIRA_WEBHOOK_SECRET`, và body có
`issue.key`.

Chưa dựng được rule thì vẫn diễn được — kích tay bằng:

```bash
.venv/Scripts/python scripts/duyet.py KAN-123
```

Lệnh đó gọi **đúng endpoint với đúng payload** mà Jira sẽ gọi, nên **ba lớp kiểm
tra vẫn chạy nguyên**. Chưa ai duyệt trên Jira mà gõ lệnh này thì vẫn bị từ
chối. Nó thay cái *cầu*, không thay cái *cổng*.

### A6. Cho người ngoài xem được (tùy chọn)

Muốn người khác mở bằng máy của họ thì cần Cloudflare Tunnel — xem
[self-host-cloudflare.md](self-host-cloudflare.md). Ba tên miền:

| | |
|---|---|
| `035.emmetech.id.vn` | trang trạng thái + war room |
| `api-035.emmetech.id.vn` | backend (Jira gọi webhook vào đây) |
| `prom-035.emmetech.id.vn` | Prometheus |

Chỉ demo trên máy mình thì bỏ qua hẳn phần này — mọi thứ chạy ở `localhost`.

> ⚠️ **War room không có xác thực.** Trỏ tên miền thật vào nghĩa là ai biết
> đường `/war_room` cũng đọc được mã phiếu, log gốc, tên bảng database và tên
> người đã duyệt. Chưa bật Cloudflare Access thì đừng để tên miền sống quá buổi
> demo.

---

## B. Bật hệ thống — mỗi lần demo

```bash
powershell -ExecutionPolicy Bypass -File scripts/khoi_dong_demo.ps1
```

Một lệnh, khoảng 2 phút. Nó làm 7 việc và **in ra bảng kiểm ở cuối**:

1. kiểm `.venv`
2. mở Docker Desktop nếu chưa chạy, đợi tới khi daemon sẵn sàng
3. dựng stack demo, đợi **từng service trả lời thật** (không tin `docker ps`)
4. seed lại `deploy_history` nếu bảng trống
5. phóng backend + UI + Agent thành ba tiến trình độc lập
6. hâm nóng ~75 giây để biểu đồ có đường vẽ ngay
7. gọi thử 7 địa chỉ, in mã trạng thái từng cái

Tham số:

| | |
|---|---|
| `-KhongHamNong` | bỏ bước 6, nhanh hơn 75 giây (biểu đồ sẽ trống lúc đầu) |
| `-UC4` | bật sẵn cờ deploy hỏng cho kịch bản UC-4 |

Tắt:

```bash
powershell -ExecutionPolicy Bypass -File scripts/dung_demo.ps1
```

Mặc định chỉ tắt ba tiến trình trên máy, **giữ nguyên Docker** — vì container
Postgres không có volume, `docker compose down` là mất sạch dữ liệu seed. Thêm
`-CaDocker` để dừng luôn stack (vẫn giữ dữ liệu), `-Xoa` để xóa sạch làm lại.

### Muốn tự gõ tay thay vì chạy script

```bash
docker compose -f docker-compose.demo.yml up -d
```

```bash
DATABASE_URL=postgresql://demo:demo@localhost:5432/demo .venv/Scripts/python demo/seed.py
```

```bash
CORS_ORIGINS=http://localhost:8501 .venv/Scripts/python -m uvicorn src.main:app --host 127.0.0.1 --port 8000
```

```bash
API_URL=http://localhost:8000 PROM_URL=http://localhost:9090 JIRA_BASE_URL=https://<site>.atlassian.net .venv/Scripts/python -m streamlit run ui/status_page.py
```

```bash
.venv/Scripts/python scripts/run_agent.py
```

> Streamlit **không đọc `.env`** — chỉ backend đọc, qua pydantic-settings. Nên
> mấy biến kia phải truyền tường minh. Thiếu cái nào là mất đúng chức năng đó,
> mà **trang vẫn lên bình thường**, nên lỗi này không tự lộ.
>
> Điểm khởi động là `ui/status_page.py`, **không phải** war room. Hai trang nằm
> trong một app Streamlit multi-page. Chạy thẳng `ui/pages/war_room.py` cũng
> lên, nhưng khi đó không có trang trạng thái và nút "Xem chi tiết" trỏ vào chỗ
> trống.

---

## C. Kiểm tra đã lên chưa

| Mở | Phải thấy |
|---|---|
| http://localhost:8501 | 4 dịch vụ, tất cả xanh, có biểu đồ |
| http://localhost:8501/war_room | trang war room, có thể trống phiếu |
| http://localhost:8000/docs | trang Swagger |
| http://localhost:9090 | Prometheus |

Agent còn sống hay không — nó ghi log ra **`agent.err`**, không phải `agent.log`
(module `logging` của Python đẩy cả dòng INFO ra stderr):

```bash
tail -f "$TEMP/p035-logs/agent.err"
```

Cứ 10 giây phải có một dòng `Vòng N: bình thường`.

---

## D. Bốn kịch bản sự cố

Mỗi kịch bản là một **use case** trong đề bài. Chạy độc lập được, nhưng
**đóng phiếu cũ trước khi mở phiếu mới trên cùng service** — Agent thấy phiếu
đang mở thì chỉ comment cập nhật, **không chẩn đoán lại và không đề xuất lại**
(chống mở trùng, có chủ ý).

Kiểm còn phiếu mở không:

```bash
curl -s http://localhost:8000/api/status
```

Nhìn `active_incidents` — phải là `[]`.

### UC-1 · Pool database cạn → chậm dây chuyền

```bash
.venv/Scripts/python demo/loadtest.py
```

Tải tăng dần 5 → 75 người dùng đồng thời. `service-thanh-toan` có pool 5 kết
nối, mỗi request giữ 0,2 giây → trần khoảng 25 request/giây.

**Đáng chỉ tay vào:** p95 leo `0,37 → 0,67 → 1,28 → 2,12 → 3,14`. Ở bậc 50 là
vượt ngưỡng P2. Và vì `/orders` gọi chéo sang `/pay`, **hai phiếu được nối lại
với nhau** — đó là phát hiện lan truyền.

### UC-2 · Service chết đi sống lại (OOM crash-loop)

```bash
.venv/Scripts/python demo/attack.py --mode oom-kill
```

**Đáng chỉ tay vào:** ngưỡng là **2 lần restart trong 10 phút**. Một lần thì
nhiều khả năng chỉ là deploy bình thường — báo động ở mức đó thì mỗi lần deploy
lại mở một phiếu.

> ⚠️ Số restart giữ mức ≥2 suốt **10 phút**. Trong khoảng đó, đóng phiếu xong là
> Agent lại mở phiếu mới ngay vòng quét sau. Muốn dừng hẳn thì đợi hết cửa sổ 10
> phút, hoặc tắt Agent.

### UC-3 · Dò mật khẩu hàng loạt

```bash
.venv/Scripts/python demo/attack.py --mode brute-force
```

**Đáng chỉ tay vào:** hai ngưỡng khác nhau về bản chất — số lần thất bại **mỗi
giây** (1/10/50 cho P3/P2/P1) và **số tài khoản khác nhau bị thử** (10). Cái thứ
hai không theo tốc độ, nên kẻ tấn công hạ tốc độ xuống dưới ngưỡng cũng không né
được: muốn dò nhiều tài khoản thì vẫn phải chạm đủ số tài khoản.

### UC-4 · Deploy hỏng — màn mạnh nhất

Đây là kịch bản **duy nhất mà Agent sửa THẬT**, không mô phỏng.

```bash
powershell -ExecutionPolicy Bypass -File scripts/khoi_dong_demo.ps1 -UC4
```

```bash
.venv/Scripts/python scripts/ban_mot_service.py pay 20 60
```

`/pay` trả **500** vì `INSERT` vào cột `idempotency_key` chưa tồn tại —
`UndefinedColumnError`.

**Đáng chỉ tay vào:** đây là ca mà **số đo bó tay**. p95 *thấp* (lỗi thì trả về
nhanh), pool 0%, chỉ có tỷ lệ 5xx là cao — bộ luật không nói được vì sao. Nguyên
nhân thật chỉ nằm trong **log**: `UndefinedColumnError: column "idempotency_key"`.
Agent đọc log, ghép với ghi chú deploy `v1.4.3`, rồi mới kết luận được.

Duyệt xong, rollback chạy thật: container được dựng lại với cờ tắt, và `/pay`
hết 500 — kiểm bằng:

```bash
curl -s -o /dev/null -w "%{http_code}" -X POST http://localhost:8001/pay -H "Content-Type: application/json" -d "{\"order_id\":\"kiem-tra\",\"amount\":100}"
```

> **Hai điều kiện ngầm, thiếu là màn chốt tụt xuống "(mô phỏng)" mà không báo lỗi:**
>
> 1. **Seed phải trong vòng 15 phút** trước khi gây sự cố. `seed.py` đặt `v1.4.3`
>    ở mốc "3 phút trước lúc seed", còn `DEPLOY_WINDOW_MINUTES = 15`. Seed từ
>    sáng rồi diễn buổi chiều → `correlate_deploy()` trả `None` → Agent đề xuất
>    `scale_up` thay vì `rollback` → mà chỉ `rollback` mới được thi hành thật.
> 2. **service-thanh-toan không được còn phiếu nào đang mở.**

---

## E. Ba trường hợp của cổng phê duyệt

Đây mới là phần được chấm điểm cao nhất: chứng minh **AI không tự ý hành động**.
Mỗi trường hợp cần **một phiếu riêng, không dính nhau** — nên dùng
`ban_mot_service.py` chứ đừng dùng `loadtest.py` (file kia cố ý làm hai service
cùng chậm để diễn lan truyền, nên nó nối phiếu lại).

```bash
.venv/Scripts/python scripts/ban_mot_service.py pay 30 90
```

| | Người làm gì | Kết quả | Nhãn phiếu |
|---|---|---|---|
| **TH1** | kéo `Awaiting Approval` → **Remediating** | Agent thi hành, tự kiểm tra, viết postmortem, đóng phiếu | `fixed-by-agent` |
| **TH2** | kéo thẳng → **Resolved** | Người tự sửa tay; Agent chỉ viết postmortem | `fixed-by-human` |
| **TH3** | **không làm gì** | Hết `AUTO_REMEDIATION_TIMEOUT_MINUTES` → Agent tự thi hành rồi tự đóng | `fixed-by-agent` |

TH3 cần bật trong `.env`:

```
AUTO_REMEDIATION_ENABLED=1
AUTO_REMEDIATION_TIMEOUT_MINUTES=2
```

> Trường hợp 3 **cố ý đi vòng qua cổng HITL** — đó là chủ đích, không phải lỗ
> hổng: một sự cố không ai trả lời thì để hệ thống hỏng tiếp còn tệ hơn. Nhưng
> nó mặc định **TẮT**, phải bật tường minh, và mọi phiếu tự xử lý đều có comment
> ghi rõ "Tự thi hành do hết thời chờ".

Sự cố **P1/P2** còn gửi mail cảnh báo kèm **link phòng họp** ngay khi mở phiếu
(P3/P4 thì không — `MUC_CAN_HOP = {P1, P2}`). Muốn quay cảnh đó thì phải bắn đủ
mạnh để chạm P2: `ban_mot_service.py pay 70 90`.

---

## F. Dọn giữa hai lần diễn

```bash
docker compose -f docker-compose.demo.yml restart service-thanh-toan service-dat-hang
```

```bash
DATABASE_URL=postgresql://demo:demo@localhost:5432/demo .venv/Scripts/python demo/seed.py
```

Rồi **đóng hết phiếu đang mở trên Jira** — nếu không, lần diễn sau Agent chỉ
comment vào phiếu cũ.

Đang ở kịch bản UC-4 thì trả service về lành:

```bash
docker compose -f docker-compose.demo.yml up -d --force-recreate service-thanh-toan
```

---

## G. Hỏng thì làm gì

Bảng này chỉ ghi những lỗi **đã vấp thật**. Điểm chung của gần hết: chúng
**không báo lỗi** — chỉ cho ra màn hình trống hoặc con số sai, nên nguy hiểm hơn
crash.

| Triệu chứng | Nguyên nhân | Sửa |
|---|---|---|
| `/pay` trả **503 "Pool chưa khởi tạo"** | Postgres restart sau khi service đã lên. Pool asyncpg khởi tạo **một lần** trong `lifespan`, không thử lại | `docker compose -f docker-compose.demo.yml restart service-thanh-toan service-dat-hang` |
| **Biểu đồ trắng trơn** | Prometheus chưa có series — chưa có traffic | `.venv/Scripts/python scripts/ham_nong.py 75` |
| Agent log đầy `PromQL không trả series nào` | Cùng nguyên nhân trên | như trên |
| **Agent không đề xuất `rollback`** mà đề xuất `scale_up` | Seed quá cũ, deploy nằm ngoài cửa sổ 15 phút | seed lại rồi gây sự cố **ngay** |
| Duyệt xong ra **"(mô phỏng)"** | Hành động không nằm trong danh sách cho thi hành thật, hoặc container không bật cờ lỗi | chỉ `rollback` + `service-thanh-toan` + `SIMULATE_MISSING_MIGRATION=1` mới chạy thật |
| **Agent chỉ comment, không chẩn đoán lại** | Service đó còn phiếu đang mở | đóng phiếu cũ trên Jira |
| Người duyệt xong **không có gì xảy ra** | Rule Jira chưa gọi tới, hoặc sai `JIRA_WEBHOOK_SECRET` | thử tay: `scripts/duyet.py KAN-x`. Trả 401 là sai secret |
| Webhook trả **403** | Người chuyển trạng thái chính là account Agent — **cổng HITL đang làm đúng việc** | kéo phiếu bằng tài khoản người thật |
| **Mất nút sang Jira**, thành ô xám | Thiếu `JIRA_BASE_URL` khi bật Streamlit | truyền tường minh, xem mục B |
| **Không có log** trong war room | `docker logs` trên Docker Desktop trả lát cắt sai; hoặc log đã trôi | log sự cố cũ hơn ~20 phút có thể mất hẳn — đó là bản chất log container |
| **LLM không chẩn đoán** nhưng không báo lỗi | Hết credit (402). Agent **vẫn chạy tiếp** bằng bộ luật nên nhìn qua tưởng bình thường | xem `agent.err`, tìm dòng 402 |
| `deploy_history` trống sau khi bật lại | `docker compose up` recreate Postgres, mà container đó **không có volume** | seed lại (script khởi động tự làm) |
| **Port 8501 đang bị dùng** | Streamlit cũ còn tiến trình con sót lại | `scripts/dung_demo.ps1` |
| Máy khác **không mở được trang** | Thiếu `API_PUBLIC_URL`/`PROM_PUBLIC_URL` — trình duyệt gọi `localhost` của **máy người xem** | truyền hai biến đó khi bật UI |

---

## H. Đọc tiếp

| File | Nội dung |
|---|---|
| [demo-runbook.md](demo-runbook.md) | Lời thoại từng giây khi diễn, và các câu chắc chắn bị hỏi |
| [demo-video-script.md](demo-video-script.md) | Kịch bản quay video |
| [use-cases.md](use-cases.md) | Bốn use case, ngưỡng và bằng chứng |
| [self-host-cloudflare.md](self-host-cloudflare.md) | Dựng tunnel để người ngoài xem được |
| [contracts/01-metrics.md](contracts/01-metrics.md) | Tên metric, câu PromQL, bảng ngưỡng severity |
| [../ARCHITECTURE.md](../ARCHITECTURE.md) | Thành phần và luồng dữ liệu |
