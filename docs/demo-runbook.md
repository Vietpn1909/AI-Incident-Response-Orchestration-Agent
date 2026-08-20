# Runbook buổi demo — mở file này ra mà làm theo

Viết ngày 12/08/2026, sau ba lượt chạy thử trọn chuỗi trên Jira thật.
Mọi con số trong đây là số đo được, không phải ước lượng.

---

## 0. Chuẩn bị — 5 phút trước giờ

### Ba cửa sổ trình duyệt

| Cửa sổ | Địa chỉ |
|---|---|
| **War room** | http://localhost:8501 |
| **Jira board** | https://jibinarybro.atlassian.net/jira/software/projects/KAN/boards/2 |
| Prometheus | http://localhost:9090 |

> ⚠️ Jira phải đăng nhập **thaiduc200427@gmail.com** (Duc Truong).
> Đăng nhập nhầm `thaiduc0201` thì bước ⑤ **bị chặn** — đó là tài khoản của Agent.

### Kiểm mọi thứ đang chạy

```bash
docker ps --format '{{.Names}}' | grep p035-demo    # phải ra 4 dòng
curl -s localhost:8000/api/incidents                 # phải ra [] hoặc danh sách
curl -s -o /dev/null -w "%{http_code}\n" localhost:8501   # phải ra 200
```

Thiếu cái nào thì bật lại:

```bash
DEMO_POSTGRES_PORT=55432 docker compose -f docker-compose.demo.yml up -d
python -m uvicorn src.main:app --port 8000                      # terminal 2
API_URL=http://localhost:8000 streamlit run ui/war_room.py      # terminal 3
```

> `API_URL` là **bắt buộc**. Thiếu nó, UI đọc backend trên Render chứ không đọc
> máy này, và màn hình sẽ hiện dữ liệu của môi trường khác.

### Tải nền cho baseline — làm SỚM, ít nhất 30 phút trước

```bash
python eval/run_measurements.py payment-load --seconds 2700 --concurrency 1 --pause 0.05 &
```

Vì sao quan trọng: bộ luật cộng 0.30 điểm tin cậy khi p95 lệch **≥ 3 lần** so với
lúc bình thường. "Lúc bình thường" tính trên cửa sổ 30 phút gần nhất.

Đo ngày 12/08 — chạy demo thử liên tục làm baseline bị ô nhiễm:

| Baseline 30 phút | p95 lúc sự cố | Lệch | Tin cậy |
|---|---|---|---|
| 0,964s (nền sạch) | 4,43s | **4,6×** | **90%** |
| 1,794s (vừa bắn tải nhiều lượt) | 4,47s | 2,5× | 60% |

Baseline bẩn thì war room mất dòng *"lệch 4,6 lần so với lúc bình thường"* —
dòng dễ hiểu nhất với người không rành kỹ thuật. **Đừng tập ngay sát giờ demo.**

### Ngay trước khi bắt đầu

```bash
python demo/seed.py
```

Bắt buộc, và phải chạy **trong vòng 15 phút** trước bước ③. Bảng `deploy_history`
đặt bản `v1.4.3` ở mốc "3 phút trước", còn Agent chỉ soi các deploy trong vòng 15
phút quanh sự cố. Quá hạn thì nó vẫn chẩn đoán đúng nhưng đề xuất `increase_pool`
thay vì `rollback`, và mất hẳn phần "trùng thời gian với một lần deploy".

---

## ① Mở đầu · 30 giây

Mở war room. Màn xanh **"Hệ thống đang bình thường"**.

> "Đây là bảng theo dõi sự cố của một hệ thống thanh toán. Hiện không có gì. AI
> đang trực, nó canh ba thứ: khách phải chờ bao lâu, tỷ lệ lỗi, và service còn
> sống không."

---

## ② Tạo sự cố · 95 giây

```bash
python demo/loadtest.py
```

> "Em sẽ tạo một sự cố **thật**, không phải dữ liệu giả. Tải tăng dần từ 5 lên 75
> người dùng đồng thời."

Nói trong lúc chờ — chỉ vào cột p95 leo dần `0,37 → 0,67 → 1,28 → 2,12 → 3,14`:

> "Service thanh toán có pool 5 kết nối, mỗi request giữ 0,2 giây, nên trần là 25
> request mỗi giây. Sắp tới bậc 75, gấp ba lần năng lực."

Khi bậc 50 vượt 2 giây: *"Đó, vừa vượt ngưỡng."*

Chạy xong, **F5 war room — vẫn xanh**:

> "Hệ thống đang chậm gấp 12 lần. Chưa ai biết. Đây đúng là khoảng thời gian mà
> thực tế người ta mất — chờ khách hàng phàn nàn."

---

## ③ Agent vào cuộc · 40 giây — phần chính

```bash
python scripts/run_agent.py --once
```

> Vài dòng WARNING đầu là Agent thử các đường phát hiện không áp dụng được (không
> ai tấn công đăng nhập, chưa đủ baseline). Bình thường. Nếu bị hỏi thì nói đúng
> như vậy.

Dừng ở bốn dòng:

| Dòng log | Nói gì |
|---|---|
| `vượt liên tục 60s` | "Tự phát hiện. Và phải vượt **liên tục 60 giây** mới tính — một cú giật thì bỏ qua." |
| `Sự cố lan sang 2 service → P1` | "Lan sang service thứ hai nên tự nâng mức." |
| `BỎ câu của LLM vì bằng chứng SỐ LIỆU PHẢN BÁC` | **Dừng lâu.** "AI vừa đổ lỗi cho pool kết nối. Nhưng số đo cho thấy pool đang rảnh. Hệ thống **bỏ câu của AI**, giữ kết luận của bộ luật. AI ở đây không được nói gì nó muốn." |
| `log đổi kết luận (40% → 80%)` | "Với service đặt hàng, số đo chỉ nói 'chậm' chứ không nói vì sao. Nên nó đi đọc log, tìm ra timeout khi gọi sang service thanh toán." |

---

## ④ War room · 90 giây

F5. Bấm **KAN-lẻ trước** (service-thanh-toan — gốc), rồi cái còn lại (nạn nhân).

Ba mục: **① AI thấy gì → ② AI nghĩ vì sao → ③ AI đề nghị làm gì**

**Mở nút "PromQL để kiểm chứng lại" → bấm link:**

> "Con số này không phải AI nghĩ ra." *(Prometheus mở ra cùng số)* "Cùng một số.
> AI chỉ dịch sang tiếng người, không tự chế ra."

**Sang phiếu thứ hai, chỉ hai đề xuất khác nhau:**

> "Gốc thì đề nghị quay phiên bản. Nạn nhân thì đề nghị tăng instance. Nó phân
> biệt được đâu là nguồn, đâu là bị vạ lây — và **nối hai phiếu lại với nhau**."

**Đọc to ô đỏ giữa màn hình:**

> "AI đã chẩn đoán xong và đề xuất cách sửa, nhưng **nó không tự thực hiện**."

---

## ⑤ Cổng phê duyệt · 90 giây — chứng minh AI không tự ý hành động

Mở phiếu gốc trên Jira, cuộn tới comment **ĐỀ XUẤT KHẮC PHỤC**, đọc to phần Rủi ro:

> *"pool cạn ngay sau lần deploy này là quan hệ **trùng thời gian**, chưa phải
> bằng chứng nhân quả — nếu rollback không làm sự cố hết thì kết luận ban đầu đã sai."*

> "Đây là chỗ em muốn các thầy cô chú ý nhất. **AI đang tự nói ra giới hạn của
> chính nó.** Một hệ thống AI dễ làm là hệ thống lúc nào cũng chắc chắn — cái đó
> nguy hiểm, vì người trực sẽ tin theo cả khi nó sai."

Rồi hai lệnh:

```bash
python scripts/duyet.py KAN-26      # ⛔ BỊ CHẶN — chưa ai duyệt
```

> "Phiếu này chưa ai duyệt. Bị từ chối."

**Sang Jira, kéo phiếu gốc → Remediating.** *(nhớ đăng nhập account NGƯỜI)*

Từ 15/08 **không cần gõ lệnh nữa** — Jira Automation tự gọi webhook. Chờ ~30
giây rồi F5 issue, hai comment tự hiện:

```
✅ ĐÃ PHÊ DUYỆT — Người phê duyệt: 712020:fd2ca790…
Đã thực thi khắc phục (mô phỏng): rollback → … — thành công
```

> "Em không gõ lệnh nào. Jira tự gọi sang hệ thống, hệ thống kiểm ai đã duyệt
> rồi mới cho thi hành."

Rule hỏng hoặc Render đang ngủ thì vẫn kích tay được — cùng endpoint, cùng payload:

```bash
python scripts/duyet.py KAN-25      # ✅ QUA CỔNG
```

> "Em không sửa dòng code nào giữa hai lệnh. Khác duy nhất là có người bấm nút
> hay không. Nghĩa là **Agent không thể tự phê duyệt cho chính nó** — không phải
> vì bọn em dặn nó đừng làm, mà vì nó **không làm được**."

**Mở tab History của phiếu đó**, chỉ vào hai tên khác nhau:

> "Jira ghi lại ai làm gì. Agent không sửa được lịch sử này — nên đây là bằng
> chứng kiểm toán được, không phải lời hứa suông."

**Nói rõ hành động nào thật, hành động nào mô phỏng:**

> "Ở kịch bản này hành động là mô phỏng — hệ thống ghi nhận đầy đủ ai duyệt và
> duyệt cái gì, nhưng chưa đổi phiên bản thật. Bọn em không giấu chỗ đó.
>
> Nhưng với kịch bản deploy hỏng thì nó **sửa thật**, và em cho các thầy cô xem
> ngay bây giờ."

→ chuyển sang màn ⑥.

---

## ⑥ Màn mạnh nhất — UC-4: đọc log · sửa THẬT · tự xác nhận

Sự cố mà **số đo hoàn toàn mù**: 100% request lỗi, nhưng p95 chỉ 0,048s và pool
0%. Agent đọc log để chẩn đoán, sửa thật, rồi **tự đo lại** để xác nhận đã khỏi.

### Chuẩn bị — cờ phải đặt trên BACKEND

```bash
pkill -f "uvicorn src.main"
REMEDIATION_REAL=1 python -m uvicorn src.main:app --port 8000 &
sleep 8
API_URL=http://localhost:8000 streamlit run ui/war_room.py &
```

> ⚠️ Đây là chỗ dễ sai nhất. `duyet.py` chỉ gửi HTTP; `executors` chạy trong tiến
> trình **backend**. Đặt cờ cho `duyet.py` thì kết quả trả về `simulated=true` mà
> **không báo lỗi gì** — đã vấp 17/08, mất ~15 phút để hiểu. Giờ `duyet.py` tự
> cảnh báo nếu thấy đặt sai chỗ.
>
> ⚠️ Sửa code Python xong **phải khởi động lại backend**. Python không tự nạp lại,
> và tiến trình cũ giữ code cũ — đã tưởng một bản vá bị hỏng vì lý do này.

### ① Gây sự cố · 90 giây

```bash
SIMULATE_MISSING_MIGRATION=1 DEMO_POSTGRES_PORT=55432 \
  docker compose -f docker-compose.demo.yml up -d --force-recreate service-thanh-toan
sleep 10 && python eval/run_measurements.py payment-load --seconds 80 --concurrency 3 --pause 0.05
```

Kết quả: `{"500": 2202, "502": 735}` — **0 request thành công**.

> "Deploy `v1.4.3` thêm tính năng chống trùng giao dịch, nhưng **quên chạy
> migration** — cột `idempotency_key` chưa tồn tại trong database. Giờ không ai
> thanh toán được."

### ② Cho xem số đo MÙ · 30 giây

```bash
curl -s -G localhost:9090/api/v1/query --data-urlencode \
 'query=histogram_quantile(0.95, sum by (service,le) (rate(http_request_duration_seconds_bucket{handler!="/metrics"}[1m])))'
```

> "Lỗi 100%, nhưng **p95 chỉ 0,048 giây** — còn nhanh hơn bình thường, vì request
> chết ngay ở câu lệnh đầu. Pool rảnh 0%. Nhìn ba con số này mà đoán nguyên nhân
> là **không thể**."

### ③ Agent vào cuộc · 60 giây — phần chính

```bash
python scripts/run_agent.py --once
```

Dừng ở hai dòng:

| Dòng log | Nói gì |
|---|---|
| `giả thuyết (tin cậy 30%) — Chưa đủ bằng chứng để nêu nguyên nhân gốc` | "Bộ luật **thừa nhận không biết**. Nó không bịa." |
| `log đổi kết luận, post lại lên war room (30% → 70%)` | "Nó đọc log service và tìm ra **cột `idempotency_key` không tồn tại**. Không con số nào chứa thông tin đó." |

### ④ War room · 60 giây

F5 http://localhost:8501 — ba mục ①②③, đọc to ô đỏ *"nó không tự thực hiện"*.

### ⑤ Người duyệt + sửa THẬT · 60 giây

Kéo phiếu sang **Remediating** *(tài khoản `thaiduc200427`)*, rồi:

```bash
python scripts/duyet.py KAN-xx
```

Phải thấy — và **không** có dòng `simulated`:

```
✅ QUA CỔNG — người duyệt: 712020:fd2ca790…
   hành động : rollback → service-thanh-toan
   kết quả   : thành công=True
```

> Thứ tự kéo/gõ **không quan trọng** từ 17/08: nếu Jira Automation bắn trước và
> Render ghi một bản *mô phỏng*, lệnh local vẫn ghi đè được, vì bản mô phỏng chưa
> sửa gì nên không được coi là "đã xong".

### ⑥ Agent TỰ XÁC NHẬN đã khỏi · 60 giây

```bash
python eval/run_measurements.py payment-load --seconds 45 --concurrency 2 --pause 0.05
sleep 12
python scripts/run_agent.py --once
```

Agent tự in, và tự comment lên Jira:

```
verify service-thanh-toan: không còn tín hiệu sự cố — đã hồi phục
KAN-xx: verify → ĐÃ HỒI PHỤC
```

> "Nó tự đo lại bằng **đúng những truy vấn đã phát hiện sự cố** — nên 'đã hồi
> phục' cùng một định nghĩa với 'phát hiện'. Trước: 0 request thành công. Sau:
> 326/326."

> ⚠️ Bước này **phải có tải** mới đo được. Không request nào thì PromQL trả rỗng
> và Agent không kết luận gì — cố ý, vì "không đo được" khác "đã hồi phục".

### Dọn sau demo

```bash
SIMULATE_MISSING_MIGRATION=0 DEMO_POSTGRES_PORT=55432 \
  docker compose -f docker-compose.demo.yml up -d --force-recreate service-thanh-toan
```

### Nếu `verify` báo CHƯA ĐỠ hoặc TỆ HƠN

Không phải hỏng — đó là hai nhánh có thật:

| Agent nói | Nghĩa |
|---|---|
| ⚠️ **CHƯA ĐỠ** | *"chẩn đoán ban đầu có thể sai, đừng thi hành lại cùng hành động"* — đúng bước 4 runbook nó tự viết |
| 🔴 **TỆ HƠN** | mức nặng hơn lúc mở phiếu → *"cần người vào ngay, đừng thi hành thêm"* |

Gặp thì cứ đọc to ra. Một hệ thống dám nói "tôi có thể đã sai" đáng tin hơn một
hệ thống lúc nào cũng báo thành công.

---

## Câu hỏi chắc chắn bị hỏi

**"Sau khi duyệt thì có sửa thật không?"**

> "Có, với kịch bản deploy hỏng. Em bấm duyệt, hệ thống kiểm đúng người rồi thi
> hành — **tỷ lệ lỗi từ 100% về 0%**, số lấy từ Prometheus chứ không phải em nói.
>
> Ba hành động còn lại vẫn mô phỏng vì chúng cần đổi cấu hình hoặc dựng thêm
> instance, không đảo được bằng một lệnh. Bọn em ưu tiên làm đúng phần khó trước:
> chẩn đoán chính xác, và cái khoá không cho AI tự ý hành động.
>
> Và hệ thống **tự biết** cái nào nó sửa thật được: trước khi hành động nó kiểm
> điều kiện thật của hạ tầng, chứ không tin vào tên hành động. Không đúng việc thì
> nó thà không làm và ghi rõ là mô phỏng."

**"Làm sao biết nó sửa đúng?"**

> "Nó tự đo lại. Vòng quét sau, nó chạy **đúng những truy vấn đã phát hiện sự cố**
> rồi ghi kết luận lên phiếu — nên 'đã hồi phục' cùng một định nghĩa với 'phát hiện'.
>
> Và nếu chưa đỡ thì nó nói thẳng: *'chẩn đoán ban đầu có thể sai, đừng thi hành
> lại cùng hành động'*. Đó chính là bước 4 trong runbook nó tự viết.
>
> Nếu Prometheus lỗi thì nó **không kết luận gì** — 'không đo được' khác 'đã hồi
> phục', và ghi nhầm là người trực đọc thấy đã khỏi rồi đi ngủ."

**"Vậy có phải AI Agent thật không?"**

> "Nó tự quan sát, tự quyết định có sự cố không, tự chẩn đoán, tự chọn hành động.
> Phần duy nhất nó **cố ý** không tự làm là bấm nút cuối — vì đề bài yêu cầu có
> người phê duyệt."

**"Sự cố này có thật hay các em bịa?"**

> "Dàn dựng đúng một dòng: `SELECT pg_sleep(0.2)` làm mỗi truy vấn chậm lại.
> Ngoài đời độ chậm đó đến từ bảng vài triệu dòng thiếu index — bọn em thu nhỏ để
> chạy được trên laptop.
>
> Còn lại là thật: pool 5 kết nối là thật, việc xếp hàng là hành vi thật của
> driver database, số đo do Prometheus lấy từ service thật, timeout lan sang
> service thứ hai là thật."

**"Sao không dùng sự cố thật ngoài production?"**

> "Vì cần tái hiện được. Muốn đo Agent chẩn đoán đúng bao nhiêu phần trăm thì phải
> chạy được cùng một sự cố nhiều lần và biết trước đáp án đúng. Bốn kịch bản của
> bọn em đều có đáp án ghi sẵn trong `docs/use-cases.md`, viết **trước** khi chạy."

**"AI có bịa số không?"**

> "Không tạo ra số nào cả. Nó đọc số có sẵn rồi diễn đạt lại. Mỗi con số trong
> trang này đều bấm ra được nguồn gốc." *(bấm nút PromQL cho xem)*

---

## Hỏng giữa chừng thì làm gì

| Triệu chứng | Xử lý |
|---|---|
| War room trắng / dữ liệu lạ | UI thiếu `API_URL`. Bật lại kèm `API_URL=http://localhost:8000` |
| Agent báo không có sự cố | Để nguội quá lâu sau `loadtest.py`. Chạy lại loadtest, rồi chạy Agent **ngay** |
| Đề xuất `increase_pool` thay vì `rollback` | Quên `seed.py`, hoặc seed quá 15 phút. Seed lại rồi chạy lại Agent |
| Duyệt xong vẫn bị chặn | Jira đang đăng nhập `thaiduc0201` (tài khoản Agent). Đổi sang `thaiduc200427@gmail.com` |
| Jira treo ~30 giây | Mạng IPv6 hỏng. Kiểm `curl -6 -m 5 https://api.github.com` — treo là đúng bệnh, đổi mạng |
| Tin cậy thấp hơn mong đợi | Baseline bị ô nhiễm do tập nhiều. Không sửa kịp giữa buổi, cứ chạy tiếp |
| `docker compose up` chết ở port 5432 | Máy đã có Postgres khác. Dùng `DEMO_POSTGRES_PORT=55432` và sửa `DATABASE_URL` trong `.env` |

---

## Việc còn tồn — nói ra nếu được hỏi "còn thiếu gì"

- **Thi hành thật**: `rollback` trên `service-thanh-toan` **đã chạy thật** từ
  15/08 — bật bằng `REMEDIATION_REAL=1`, mặc định tắt. Đo trọn vòng: lỗi 100% →
  0%, 120/120 request thành công. Ba hành động còn lại vẫn mô phỏng.
- **Jira Automation Rule #1 đã chạy** từ 15/08 — bấm `Remediating` là chuỗi tự
  đi tới cùng. Rule #2 (postmortem khi `Resolved`) chưa cấu hình.
- ⚠️ **Render free tier ngủ sau 15 phút**, tỉnh lại mất 30–60s, và rule gọi lúc
  nó ngủ sẽ **fail im lặng**. Trước demo phải đánh thức:
  `curl https://p-035-incident-agent.onrender.com/health`
- **Node `verify`** ✅ **đã có** từ 17/08 — Agent tự đo lại và tự comment kết luận.
- ⚠️ `awaiting_keys` chỉ nhớ phiếu mở TRONG tiến trình đó, nên khởi động lại Agent
  là nó quên phiếu đang chờ duyệt — cả `poll_jira_approvals` lẫn `verify` đều
  không chạm tới. Đo được 17/08: KAN-48 duyệt trước khi Agent khởi động thì không
  ai xử, và Agent còn mở KAN-50 mới cho cùng service. Cần seed từ Jira lúc bắt đầu.
