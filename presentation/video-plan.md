# Kế hoạch quay Video Demo — 3 phút

**Người quay:** Long · **Trục kịch bản:** UC-4 (deploy thiếu migration → sửa THẬT → tự xác nhận)
**Ràng buộc:** ≤ 3:00 · phải có Jira · mọi thứ trên màn hình là hệ thống thật đang chạy

> Kế hoạch này nén màn ⑥ của [docs/demo-runbook.md](../docs/demo-runbook.md) (khoảng 7 phút
> khi trình bày trực tiếp) xuống 3 phút. Mọi lệnh dưới đây **lấy nguyên văn từ runbook** —
> nếu runbook đổi thì file này phải đổi theo.

## Vì sao chọn UC-4 chứ không phải UC-1

Ba phút chỉ đủ cho một kịch bản. UC-4 là kịch bản duy nhất có đủ cả bốn thứ giám khảo sẽ tìm:

| Thứ cần chứng minh | UC-1 (pool cạn) | **UC-4 (thiếu migration)** |
|---|:---:|:---:|
| Agent tự phát hiện | ✅ | ✅ |
| Chẩn đoán được cái mà số đo **không** chỉ ra | ❌ số đo đã nói hết | ✅ p95 đẹp, phải đọc log |
| Cổng phê duyệt trên Jira | ✅ | ✅ |
| Sửa **thật** + tự đo lại xác nhận | ❌ mô phỏng | ✅ lỗi 100% → 0% |

UC-1 vẫn dùng được, nhưng để dành cho pitch deck (slide escalation P2→P1 và lan truyền)
chứ không nhét vào video.

---

## A. Chuẩn bị trước khi bấm ghi

Đây là phần dễ mất nhiều giờ nhất. Bốn cái bẫy dưới đây đều đã làm hỏng một buổi tập rồi.

### A1. Bật hệ thống — thứ tự này quan trọng

```bash
# 1) demo stack
DEMO_POSTGRES_PORT=55432 docker compose -f docker-compose.demo.yml up -d
docker ps --format '{{.Names}}' | grep p035-demo      # phải ra 4 dòng

# 2) backend — CỜ REMEDIATION_REAL PHẢI Ở ĐÂY
pkill -f "uvicorn src.main"
REMEDIATION_REAL=1 python -m uvicorn src.main:app --port 8000 &
sleep 8

# 3) war room
API_URL=http://localhost:8000 streamlit run ui/war_room.py &
curl -s -o /dev/null -w "%{http_code}\n" localhost:8501   # phải ra 200
```

> 🪤 **Bẫy 1 — `REMEDIATION_REAL=1` phải đặt trên backend, không phải trên `duyet.py`.**
> `duyet.py` chỉ gửi HTTP; phần thi hành chạy trong tiến trình backend. Đặt sai chỗ thì kết
> quả trả về `simulated=true` mà **không báo lỗi gì** — mất 15 phút mới nhận ra (17/08).
> Quay xong cả video rồi mới phát hiện chữ `simulated` trên màn hình là phải quay lại từ đầu.

> 🪤 **Bẫy 2 — sửa code Python xong phải khởi động lại backend.** Python không tự nạp lại,
> tiến trình cũ giữ code cũ.

### A2. Seed dữ liệu — trong vòng 15 phút trước khi quay cảnh 4

```bash
python demo/seed.py
```

Bảng `deploy_history` đặt bản `v1.4.3` ở mốc "3 phút trước", còn Agent chỉ soi deploy trong
vòng 15 phút quanh sự cố. Quá hạn thì Agent vẫn chẩn đoán đúng nhưng **mất dòng "trùng thời
gian với một lần deploy"** — mất luôn mạch kể của video.

### A3. Tài khoản Jira — bẫy chết người

| Việc | Tài khoản |
|---|---|
| Đăng nhập trình duyệt để **kéo phiếu duyệt** | `thaiduc200427@gmail.com` (Duc Truong — **người**) |
| Tài khoản Agent dùng — **KHÔNG được đăng nhập bằng cái này** | `thaiduc0201` |

> 🪤 **Bẫy 3.** Đăng nhập nhầm `thaiduc0201` thì cảnh 7 **bị hệ thống chặn** — đúng như thiết
> kế, nhưng hỏng mất cảnh quay. Kiểm avatar góc phải Jira trước khi bấm ghi.

Board: https://jibinarybro.atlassian.net/jira/software/projects/KAN/boards/2

### A4. Ba cửa sổ, sắp sẵn trước khi ghi

| Cửa sổ | Địa chỉ | Dùng ở cảnh |
|---|---|---|
| Terminal (phóng chữ ≥ 16pt) | — | 2, 3, 4, 6, 8 |
| War room | http://localhost:8501 | 1, 5 |
| Jira board | link ở A3 | 6, 7 |

> 🪤 **Bẫy 4 — Render ngủ.** Nếu quay cảnh nào chạm tới backend trên Render (webhook Jira
> Automation), đánh thức trước: `curl https://p-035-incident-agent.onrender.com/health`.
> Rule gọi lúc nó ngủ sẽ **fail im lặng**.

### A5. Dọn màn hình — kiểm trước khi ghi

- [ ] Đóng hết tab không liên quan, tắt thông báo Windows (Focus assist)
- [ ] Terminal **không** đang hiện nội dung `.env`, `JIRA_API_TOKEN`, `OPENAI_API_KEY`
- [ ] Lịch sử lệnh không có dòng nào chứa token (bấm `clear` trước mỗi take)
- [ ] Không mở màn hình email cảnh báo — nó chứa Gmail cá nhân của 4 thành viên
- [ ] Zoom trình duyệt 110–125% để chữ war room đọc được khi video bị nén

---

## B. Timeline — 8 cảnh

Cột **Lời thoại** là bản đọc thật, đã đếm chữ theo nhịp ~150 chữ/phút. Đừng thêm chữ:
mỗi câu thêm vào là một cảnh phải cắt bớt ở cuối.

---

### Cảnh 1 · 0:00–0:18 · Hook

**Màn hình:** War room, màn xanh *"Hệ thống đang bình thường"*. Giữ yên, không rê chuột.

> "Hai giờ sáng. Đây là bảng theo dõi sự cố của một hệ thống thanh toán. Màn hình xanh —
> không có gì bất thường. AI đang trực, nó canh ba thứ: khách phải chờ bao lâu, tỷ lệ lỗi,
> và service còn sống không."

*(45 chữ · 18 giây)*

---

### Cảnh 2 · 0:18–0:40 · Gây sự cố thật

**Màn hình:** Terminal. Gõ (hoặc dán) và để chạy:

```bash
SIMULATE_MISSING_MIGRATION=1 DEMO_POSTGRES_PORT=55432 \
  docker compose -f docker-compose.demo.yml up -d --force-recreate service-thanh-toan
sleep 10 && python eval/run_measurements.py payment-load --seconds 80 --concurrency 3 --pause 0.05
```

Kết thúc phải hiện: `{"500": 2202, "502": 735}` — **tua nhanh ×4 đoạn chờ 80 giây**.

> "Bọn em vừa deploy phiên bản một-chấm-bốn-chấm-ba, thêm tính năng chống trùng giao dịch,
> nhưng quên chạy migration. Cột `idempotency_key` chưa tồn tại trong database. Bắn tải vào:
> hai nghìn hai trăm lỗi 500, bảy trăm ba mươi lăm lỗi 502. Không một request nào thành công."

*(48 chữ · 22 giây)*

**Hậu kỳ:** khoanh đỏ dòng `{"500": 2202, "502": 735}`, giữ 2 giây.

---

### Cảnh 3 · 0:40–1:02 · Số đo MÙ — đây là lý do sản phẩm tồn tại

**Màn hình:** Terminal, chạy PromQL:

```bash
curl -s -G localhost:9090/api/v1/query --data-urlencode \
 'query=histogram_quantile(0.95, sum by (service,le) (rate(http_request_duration_seconds_bucket{handler!="/metrics"}[1m])))'
```

Kết quả: p95 ≈ **0,048s**, pool 0%.

> "Và đây là chỗ công cụ monitor bó tay. Lỗi một trăm phần trăm, nhưng p95 chỉ bốn mươi tám
> mili giây — nhanh hơn cả lúc bình thường, vì request chết ngay ở câu lệnh đầu. Pool thì
> rảnh. Nhìn ba con số này mà đoán ra nguyên nhân là **không thể**."

*(52 chữ · 22 giây)*

**Hậu kỳ:** hiện overlay 3 ô số cạnh nhau — `Lỗi 100%` (đỏ) · `p95 0,048s` (xanh lá) ·
`Pool 0%` (xanh lá). Sự nghịch lý phải nhìn thấy được, không chỉ nghe thấy.

---

### Cảnh 4 · 1:02–1:38 · Agent vào cuộc — phần chính

**Màn hình:** Terminal:

```bash
python scripts/run_agent.py --once
```

Vài dòng WARNING đầu là Agent thử các đường phát hiện không áp dụng được — **tua nhanh qua**.
Dừng lại ở đúng hai dòng:

| Dòng log | Xử lý hình ảnh |
|---|---|
| `giả thuyết (tin cậy 30%) — Chưa đủ bằng chứng để nêu nguyên nhân gốc` | khoanh đỏ, giữ 3 giây |
| `log đổi kết luận, post lại lên war room (30% → 70%)` | khoanh đỏ, zoom vào `idempotency_key` |

> "Agent vào cuộc. Dòng đầu tiên: tin cậy ba mươi phần trăm — *chưa đủ bằng chứng để nêu
> nguyên nhân gốc*. Nó **thừa nhận nó chưa biết**, chứ không bịa ra một câu nghe cho xuôi tai.
> Rồi nó đi đọc log của service, và tìm ra: cột `idempotency_key` không tồn tại. Không con số
> nào chứa được thông tin đó. Tin cậy lên bảy mươi phần trăm — và nó tự mở một phiếu sự cố
> trên Jira."

*(78 chữ · 36 giây)*

Câu *"nó thừa nhận nó chưa biết"* là câu quan trọng nhất video. Đọc chậm lại ở đó.

---

### Cảnh 5 · 1:38–2:02 · War room — bằng chứng truy vết được

**Màn hình:** F5 http://localhost:8501 → mở phiếu vừa tạo. Thao tác đúng ba bước:

1. Lướt qua ba mục **① AI thấy gì → ② AI nghĩ vì sao → ③ AI đề nghị làm gì**
2. Bấm nút **"PromQL để kiểm chứng lại"** → Prometheus mở ra cùng con số → cắt về ngay
3. Zoom vào ô đỏ giữa màn hình

> "War room hiện ra ba mục: AI thấy gì, AI nghĩ vì sao, AI đề nghị làm gì. Bấm vào đây —
> Prometheus mở ra đúng con số đó. AI không tự chế ra số, nó chỉ dịch sang tiếng người. Và
> ô đỏ này: AI đã đề xuất cách sửa, nhưng **nó không tự thực hiện**."

*(56 chữ · 24 giây)*

---

### Cảnh 6 · 2:02–2:20 · **JIRA** — cổng chặn

**Màn hình:** hai nửa.

Nửa đầu — terminal:

```bash
python scripts/duyet.py KAN-xx      # thay xx bằng số phiếu thật
```

Phải ra: **⛔ BỊ CHẶN — chưa ai duyệt**.

Nửa sau — cắt sang **Jira board**, phiếu đang nằm ở cột `Awaiting Approval`. Rê chuột cho
thấy phiếu, không bấm gì.

> "Em thử ép hệ thống thi hành luôn. Bị chặn. Sang Jira — phiếu vẫn đang nằm ở cột *chờ phê
> duyệt*. Chưa ai bấm nút thì không có đường nào đi tiếp."

*(38 chữ · 18 giây)*

---

### Cảnh 7 · 2:20–2:44 · **JIRA** — người duyệt, hệ thống sửa thật

**Màn hình:** giữ nguyên Jira, thao tác thật trên board.

1. **Kéo phiếu từ `Awaiting Approval` sang `Remediating`** — quay trọn cú kéo, đừng cắt
2. Chờ ~30 giây (Jira Automation gọi webhook) — **tua nhanh ×4**
3. F5 phiếu → hai comment tự hiện:
   ```
   ✅ ĐÃ PHÊ DUYỆT — Người phê duyệt: 712020:fd2ca790…
   Đã thực thi khắc phục: rollback → service-thanh-toan — thành công
   ```
4. Mở tab **History** của phiếu → **khoanh đỏ hai cái tên khác nhau** (người mở phiếu = Agent,
   người duyệt = người)

> "Giờ em kéo phiếu sang *Remediating*, bằng tài khoản người thật. Em không gõ thêm lệnh nào
> — Jira tự gọi sang hệ thống, hệ thống kiểm ai đã duyệt rồi mới cho thi hành. Hai comment tự
> hiện. Và mở lịch sử phiếu ra: **hai cái tên khác nhau**. Agent không sửa được lịch sử này —
> nên đây là bằng chứng kiểm toán được, không phải lời hứa suông."

*(60 chữ · 24 giây)*

> ⚠️ Trên màn hình **không được** xuất hiện chữ `simulated`. Thấy chữ đó nghĩa là quên
> `REMEDIATION_REAL=1` trên backend (bẫy 1) — dừng, sửa, quay lại cảnh này.

---

### Cảnh 8 · 2:44–3:00 · Agent tự xác nhận + kết

**Màn hình:** terminal:

```bash
python eval/run_measurements.py payment-load --seconds 45 --concurrency 2 --pause 0.05
sleep 12
python scripts/run_agent.py --once
```

Dừng ở: `verify service-thanh-toan: không còn tín hiệu sự cố — đã hồi phục`

> "Agent tự đo lại, bằng **đúng những truy vấn đã phát hiện ra sự cố**. Trước: không một
> request nào thành công. Sau: ba trăm hai mươi sáu trên ba trăm hai mươi sáu. Đã hồi phục."

*(35 chữ · 16 giây)*

**Hậu kỳ — card kết, giữ 4 giây cuối:**

```
AI Agent Điều Phối Ứng Phó Sự Cố
Team Binary Brothers · PTNT-20

Tự phát hiện · Chẩn đoán có bằng chứng · Người quyết định

<link MVP>
```

---

## C. Cách quay

**Tách 3 take, đừng quay một mạch.** Quay liền 3 phút nghĩa là sai ở giây thứ 160 phải làm lại
từ đầu, mà cảnh 2 và 8 đều phải chờ loadtest.

| Take | Cảnh | Ghi chú |
|---|---|---|
| Take A — terminal | 2, 3, 4, 8 | Quay một lượt liền mạch của cả chuỗi lệnh, cắt sau |
| Take B — war room | 1, 5 | Cảnh 1 quay **sau cùng** (lúc hệ thống đã dọn sạch, màn mới xanh lại) |
| Take C — Jira | 6, 7 | Đây là take quan trọng nhất — quay 2–3 lần lấy bản mượt nhất |

**Thông số:**

- Độ phân giải **1920×1080**, 30fps
- Terminal: font ≥ 16pt, nền tối (khớp tông war room)
- Trình duyệt zoom 110–125%, ẩn bookmark bar
- Công cụ: OBS Studio (miễn phí) hoặc Xbox Game Bar (`Win+G`, có sẵn Windows 11)
- Thu tiếng riêng nếu được — thu cùng lúc thì tiếng quạt laptop lúc loadtest lọt vào rất rõ

**Hậu kỳ (CapCut / DaVinci Resolve, đều miễn phí):**

- Tua nhanh ×4 mọi đoạn chờ (loadtest 80s, webhook 30s) — có nhãn `×4` góc màn hình
- Khoanh đỏ: 4 chỗ đã ghi trong timeline, không khoanh thêm chỗ nào nữa
- Phụ đề **burn-in** cho 3 câu chốt: *"nó thừa nhận nó chưa biết"* · *"AI không tự thực hiện"* ·
  *"hai cái tên khác nhau"*
- Nhạc nền: có cũng được, nhưng để rất nhỏ (−28 dB). Video kỹ thuật không cần nhạc kịch tính

---

## D. Phương án B — khi Jira Automation không bắn

Rule Jira hỏng, hoặc Render đang ngủ và fail im lặng. **Quay sẵn take dự phòng này** để khỏi
phải dựng lại cả buổi:

```bash
python scripts/duyet.py KAN-xx      # ✅ QUA CỔNG
```

Cùng endpoint, cùng payload, kết quả giống hệt — chỉ khác là kích tay thay vì Jira tự gọi.
Lời thoại cảnh 7 đổi thành:

> "Em kéo phiếu sang *Remediating* bằng tài khoản người thật, rồi kích cho hệ thống chạy.
> Cùng một lệnh với lúc nãy — lúc nãy bị chặn, giờ qua. Em không sửa dòng code nào giữa hai
> lần; khác duy nhất là **có người bấm nút hay không**."

Thực ra câu này còn mạnh hơn bản chính, vì nó nêu bật đúng biến số duy nhất đã thay đổi.
Nếu bí thời gian, dùng thẳng phương án B.

**Các trục trặc khác:**

| Triệu chứng | Xử lý |
|---|---|
| War room trắng / dữ liệu lạ | Thiếu `API_URL`. Bật lại kèm `API_URL=http://localhost:8000` |
| Agent báo không có sự cố | Để nguội quá lâu sau loadtest. Chạy lại loadtest rồi chạy Agent **ngay** |
| Đề xuất `increase_pool` thay vì `rollback` | Quên `seed.py`, hoặc seed quá 15 phút |
| Duyệt xong vẫn bị chặn | Jira đang đăng nhập `thaiduc0201` (tài khoản Agent) |
| `verify` báo ⚠️ CHƯA ĐỠ | Không phải hỏng — đó là nhánh có thật. Nhưng với video thì quay lại, vì mạch kể cần nhánh "đã hồi phục" |
| `docker compose` chết ở port 5432 | Máy có Postgres khác. Dùng `DEMO_POSTGRES_PORT=55432` |

---

## E. Dọn sau khi quay

```bash
SIMULATE_MISSING_MIGRATION=0 DEMO_POSTGRES_PORT=55432 \
  docker compose -f docker-compose.demo.yml up -d --force-recreate service-thanh-toan
```

Quên bước này thì service demo giữ nguyên trạng thái hỏng, và lần tập sau sẽ tưởng là bug mới.

---

## F. Checklist trước khi nộp video

**Nội dung**
- [ ] Thời lượng **≤ 3:00** (bấm giờ bản final, không ước lượng)
- [ ] Có Jira xuất hiện rõ ràng ở **hai** cảnh: bị chặn (cảnh 6) và được duyệt (cảnh 7)
- [ ] Tab History của Jira với hai tên khác nhau có lên hình
- [ ] Không có chữ `simulated` ở cảnh 7
- [ ] Số cuối là **326/326**, khớp với con số trong pitch deck và `SUBMISSION.md`

**An toàn**
- [ ] Không lộ `JIRA_API_TOKEN`, `OPENAI_API_KEY`, nội dung `.env` ở bất kỳ frame nào
- [ ] Không lộ Gmail cá nhân của thành viên khác (màn hình email cảnh báo — đừng quay)
- [ ] Tua từng frame ở đoạn terminal cuộn nhanh để chắc chắn không có dòng nào lọt

**Kỹ thuật**
- [ ] Xem lại trên **điện thoại** — chữ terminal còn đọc được không
- [ ] Tiếng nói to đều, không bị tiếng quạt át
- [ ] Upload YouTube ở chế độ **unlisted** (không phải private — giám khảo mở không được)
- [ ] Tiêu đề video: `P-035 — AI Agent Điều Phối Ứng Phó Sự Cố | Team Binary Brothers`
- [ ] Ảnh thumbnail YouTube: dùng `presentation/thumbnail.png`
- [ ] Dán link vào bảng ở [SUBMISSION.md §5](SUBMISSION.md)
