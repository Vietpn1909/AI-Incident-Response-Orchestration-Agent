# Use case sự cố — chốt 3 UC

Theo góp ý mentor *"chỉ nên chọn dưới 3 UC"* và mentor đã đồng ý thêm chiều bảo mật.

Mỗi UC ghi đủ 6 phần để dùng được cho cả ba việc: Việt viết `detect`, Trung dựng hạ tầng và đo, Long kể chuyện trong video.

| UC | Tên | Hình thái sự cố | Trạng thái |
|---|---|---|---|
| **UC-1** | Cạn connection pool do tải | Còn sống nhưng chậm dần | ✅ Hạ tầng xong, đã đo được |
| **UC-1a** | Lan truyền sang service phụ thuộc | Sự cố lây lan | ✅ Xảy ra tự nhiên trong UC-1 |
| **UC-2** | Service chết do OOM, restart loop | Chết rồi sống lại | ⬜ Chưa dựng |
| **UC-3** | Burst xác thực thất bại (tấn công) | Tác nhân xấu từ bên ngoài | ⬜ Chưa dựng · mentor đã OK |

Ba UC là **ba hình thái khác nhau**, không phải ba biến thể của một thứ. Đó là điều cần chứng minh: Agent không phải một cái rule đơn lẻ ăn may.

---

## UC-1 — Cạn connection pool do tải

### Chuỗi nhân quả

```
tải tăng dần
   → 5 chỗ trong connection pool bị chiếm hết
   → request mới phải XẾP HÀNG chờ connection
   → thời gian chờ cộng vào latency
   → p95 vượt ngưỡng 2s
   → một số request timeout → lỗi 5xx
```

Nút cổ chai là **thật**, không dàn dựng: `POOL_SIZE = 5` trong [`demo/service_thanh_toan/main.py`](../demo/service_thanh_toan/main.py), cộng truy vấn `SELECT count(*) FROM payments WHERE order_id = $1` **không có index** trên bảng 5.000 dòng. Lý do chọn cách này: [ADR-0003](adr/0003-load-test-that-thay-fault-injection.md).

### Cách dựng lại

```bash
docker compose -f docker-compose.demo.yml up --build
python demo/seed.py          # một lần
python demo/loadtest.py      # tăng tải theo bậc
```

Mức tải đã đo được trên máy demo của Trung (Windows, `LAPTOP-240I2QTN`, 30/07):

```
~285 request/giây · 200 concurrent · tỷ lệ lỗi 51%  →  p95 vượt 2s
```

Số đo từ spike của Việt (dummy service, pool 5 mô phỏng bằng `Semaphore`):

| Đại lượng | Lúc rảnh | Lúc nghẽn |
|---|---|---|
| p95 latency | 0.095 s | **1.95 s** |
| avg latency | 0.083 s | 1.56 s |
| Tỷ lệ lỗi 5xx | 0 % | 2.1 % |
| Mức dùng pool | 0.00 | **1.00** |
| Lệch baseline 30m | 1.0× | **4.0×** |

### Tín hiệu Agent quan sát

Dùng nguyên văn từ [`src/services/prometheus.py`](../src/services/prometheus.py):

| Tín hiệu | Hằng số |
|---|---|
| p95 latency vượt 2s liên tục ≥ 30s | `P95_LATENCY` |
| Tỷ lệ lỗi 5xx tăng | `ERROR_RATE` |
| **Pool đạt 100%** — bằng chứng nguyên nhân gốc | `POOL_SATURATION_PEAK_5M` |
| Lệch so baseline 30 phút | `P95_BASELINE_30M` |

⚠️ Dùng `POOL_SATURATION_PEAK_5M` chứ không phải `POOL_SATURATION` khi làm bằng chứng — gauge là giá trị tức thời, query lúc tải vừa dứt sẽ trả 0 dù ngay trước đó đã cạn.

### Severity mong đợi

**P2** — p95 > 2s nhưng chưa > 10s, tỷ lệ lỗi > 10% nhưng chưa > 50%. Leo lên **P1** khi UC-1a xảy ra (≥ 2 service bị ảnh hưởng).

### Nguyên nhân gốc — ground truth để đo

> Connection pool giới hạn 5 bị chiếm hết dưới tải, request xếp hàng chờ; truy vấn thiếu index trên `payments(order_id)` làm mỗi request giữ connection lâu hơn.

Agent tính là **chẩn đoán đúng** nếu giả thuyết số 1 nêu được **pool cạn** (hoặc truy vấn chậm giữ connection). Nêu chung chung "service chậm" thì **không tính** — đó là triệu chứng, không phải nguyên nhân.

### Hành động khắc phục mong đợi

`rollback` về `v1.4.1` — vì [`demo/seed.py`](../demo/seed.py) cố tình đặt một dòng `deploy_history` với `v1.4.2` deploy **4 phút trước**, làm "nghi phạm" cho `correlate_deploy`. Phương án hai: `increase_pool`.

Cả hai đều nằm trong `SUPPORTED_ACTIONS` của [`remediation.py`](../src/services/remediation.py) và **phải qua cổng HITL** trước khi thi hành.

---

## UC-1a — Lan truyền sang service phụ thuộc

Không phải UC riêng, mà là **tình huống con** của UC-1. Điểm hay: nó xảy ra **miễn phí**, không cần code gì để mô phỏng.

```
service-thanh-toan chậm (UC-1)
   → service-dat-hang gọi chéo sang nó, timeout 3s
   → service-dat-hang trả 504
   → Agent thấy service THỨ HAI suy giảm
   → link 2 incident bằng Jira issue link
```

**Độ trễ lan truyền đo được: khoảng 30 giây** sau UC-1. Vì vậy `is_spreading()` trong [`rules.py`](../src/services/rules.py) dùng ngưỡng 60s làm biên an toàn.

Ground truth: Agent phải nhận ra `service-dat-hang` suy giảm **do phụ thuộc**, không phải một sự cố độc lập — và link 2 incident lại. Severity tổng lên **P1** vì ≥ 2 service bị ảnh hưởng.

---

## UC-2 — Service chết do OOM, restart loop

**Chưa dựng.** Đây là bản server của "xanh màn hình" mà mentor nói — trên hệ container thì tương đương là bị OOM-kill rồi restart liên tục.

### Vì sao đáng thêm

Không phải để cho nhiều UC, mà vì nó có **loại tín hiệu khác hẳn UC-1**:

| | UC-1 | UC-2 |
|---|---|---|
| Tín hiệu | latency, tỷ lệ lỗi, pool | **`up == 0`**, số lần restart |
| Hình thái | service còn sống nhưng chậm | **service chết rồi sống lại** |
| Khắc phục | rollback / tăng pool | `restart` + tăng memory limit |

Có 2 UC khác loại chứng minh Agent không phải một cái rule đơn lẻ ăn may. Một UC thì người chấm có lý do nghi ngờ điều đó.

### Cách dựng — việc của Trung, độ nửa ngày

1. Thêm `mem_limit: 128m` cho `service-thanh-toan` trong [`docker-compose.demo.yml`](../docker-compose.demo.yml)
2. Thêm endpoint `POST /pay/batch` giữ kết quả truy vấn trong một list toàn cục (rò rỉ có chủ đích, ghi rõ comment là cố ý)
3. Bắn tải vào endpoint đó → RAM tăng dần → Docker OOM-kill → container restart

### Tín hiệu Agent quan sát

```promql
up{service="service-thanh-toan"} == 0
changes(process_start_time_seconds{service="service-thanh-toan"}[10m]) > 1
```

Câu thứ hai đếm số lần process khởi động lại — đó là dấu hiệu restart loop, phân biệt được với "service tắt hẳn".

### Severity mong đợi

**P1** — service không phục vụ được, không chỉ chậm.

### Ground truth

> Container bị OOM-kill vì vượt memory limit 128MB do rò rỉ bộ nhớ ở endpoint xử lý theo lô.

### Hành động khắc phục mong đợi

`restart` (tạm) hoặc `rollback`. Ghi vào postmortem action item: sửa chỗ rò rỉ + tăng memory limit.

---

## UC-3 — Burst xác thực thất bại (dấu hiệu tấn công)

**Chưa dựng.** Mentor đã đồng ý thêm chiều bảo mật.

### Phạm vi — chốt rõ để không trôi

Làm dạng **hiện ra trên metric**: burst credential-stuffing khiến tỷ lệ `401` tăng vọt. Phát hiện bằng cùng loại counter đã có, cùng rule engine, cùng dạng PromQL.

**KHÔNG** làm dạng phân tích payload (SQL injection, path traversal). Cái đó cần pipeline thu thập và phân tích **log** — một nhánh kiến trúc thứ hai, không khả thi trong thời gian còn lại.

> ⚠️ Nếu mentor thực ra muốn dạng phân tích payload thì phải bàn lại phạm vi — đó là việc khác hẳn, không phải mở rộng nhỏ.

### Chuỗi nhân quả

```
kẻ tấn công bắn hàng loạt request đăng nhập với mật khẩu sai
   → service trả 401 liên tục
   → tỷ lệ request 4xx trên /login tăng vọt
   → Agent phát hiện bất thường về HÌNH THÁI truy cập, không phải hiệu năng
```

Khác UC-1 và UC-2 ở chỗ: **hệ thống vẫn hoàn toàn khoẻ**. Latency bình thường, không lỗi 5xx, pool không cạn. Chỉ có hình thái truy cập là bất thường. Vì vậy nó kiểm được một nhánh khác của Agent.

### Cách dựng — việc của Trung, độ nửa ngày

1. Thêm endpoint `POST /login` vào [`demo/service_thanh_toan/main.py`](../demo/service_thanh_toan/main.py): nhận `{username, password}`, so với một cặp hardcode, sai thì `raise HTTPException(401)`.

   Dùng endpoint **riêng**, không gắn xác thực vào `/pay` — để UC-3 không làm ảnh hưởng UC-1 và `loadtest.py` không phải sửa.

2. Thêm `demo/attack.py`: bắn ~200 request/giây vào `/login` với mật khẩu sai ngẫu nhiên, trong 60 giây.

### Tín hiệu Agent quan sát — CẦN THÊM MỚI

⚠️ **`ERROR_RATE` hiện tại không bắt được UC này** — nó chỉ khớp `status=~"5.."`, còn 401 là `4xx`. Phải thêm hằng số mới vào [`src/services/prometheus.py`](../src/services/prometheus.py):

```promql
# Số request xác thực thất bại mỗi giây, theo service
sum by (service) (rate(http_requests_total{handler="/login", status=~"4.."}[1m]))
```

Và **một nhánh rule riêng** trong [`rules.py`](../src/services/rules.py): severity của UC-3 dựa trên **số lượng tuyệt đối** request thất bại mỗi giây, không dựa trên p95 hay tỷ lệ lỗi 5xx như bảng severity chung.

| Điều kiện | Severity |
|---|---|
| > 50 lần thất bại/giây, liên tục ≥ 30s | **P1** — nghi đang bị tấn công chủ động |
| > 10 lần thất bại/giây | **P2** |
| Lệch baseline nhưng dưới 10/giây | **P3** |

Ngưỡng theo số tuyệt đối vì tỷ lệ không có ý nghĩa ở đây: nếu kẻ tấn công là nguồn traffic duy nhất thì tỷ lệ lỗi là 100% ngay từ request đầu, chưa nói được gì về mức nghiêm trọng.

### Nguyên nhân gốc — ground truth

> Burst request đăng nhập thất bại từ một nguồn, hình thái phù hợp với credential-stuffing. Hệ thống không có lỗi kỹ thuật.

Agent tính là **chẩn đoán đúng** nếu nêu được đây là **vấn đề bảo mật / truy cập bất thường**, không phải sự cố hiệu năng. Nếu Agent kết luận "service quá tải" hay "pool cạn" thì **sai** — và đây là phép thử tốt, vì nó kiểm xem rule engine có phân biệt được hai loại nguyên nhân hay chỉ khớp mẫu bừa.

### Hành động khắc phục mong đợi

`rate_limit` — cần **thêm vào `SUPPORTED_ACTIONS`** trong [`remediation.py`](../src/services/remediation.py), hiện chỉ có `rollback`, `restart`, `scale_up`, `increase_pool`.

Đây là hành động ảnh hưởng người dùng thật (chặn truy cập), nên **vẫn phải qua cổng HITL** — đúng tinh thần đề bài, và là ví dụ tốt trong video: một hành động bảo mật cũng không được để AI tự quyết.

### Việc phát sinh cho từng người

| Người | Việc |
|---|---|
| Trung | Endpoint `/login` + `demo/attack.py` |
| Đức | Thêm `AUTH_FAILURE_RATE` vào `prometheus.py`, thêm `rate_limit` vào `SUPPORTED_ACTIONS` |
| Việt | Nhánh rule riêng cho UC-3 trong `classify_severity()` |

---

## Chi phí đo đạc — điều bạn cần biết khi chốt 3 UC

[`eval/README.md`](../eval/README.md) yêu cầu **≥ 10 lần chạy mỗi UC** để tỷ lệ phần trăm có nghĩa. Với 3 UC là **30 lần chạy**, và đó là thời gian của Trung — người còn phải làm test suite.

Hai cách đi:

| Cách | Tổng số lần chạy | Đánh đổi |
|---|---|---|
| 10 lần × 3 UC | 30 | Số liệu chắc, nhưng nặng cho Trung |
| **10 lần UC-1 · 8 lần UC-2 và UC-3** | **26** | Ưu tiên UC chính vì nó xuất hiện trong demo; ghi rõ `n` trong báo cáo |

Đề nghị cách hai. Điều quan trọng không phải `n` bằng bao nhiêu mà là **ghi rõ `n` trong báo cáo** — số liệu có `n=8` và nói thẳng vẫn đáng tin hơn số liệu không ghi `n`.

## Vì sao 3 UC này, không phải 3 UC khác

Ba UC được chọn vì **ba hình thái khác nhau**, mỗi cái kiểm một nhánh khác của Agent:

| UC | Hệ thống lúc đó | Nhánh Agent được kiểm |
|---|---|---|
| UC-1 | Còn sống, chậm dần | Ngưỡng latency + so baseline + tìm nguyên nhân gốc |
| UC-2 | Chết rồi sống lại | Phát hiện qua `up == 0`, không qua latency |
| UC-3 | **Hoàn toàn khoẻ** | Phân biệt bất thường truy cập với sự cố hiệu năng |

UC-3 là phép thử khó nhất trong ba: hệ thống khoẻ mạnh về mọi chỉ số hiệu năng, nên Agent phải **không** kết luận "quá tải". Nếu nó kết luận sai thì lộ ra rule engine chỉ khớp mẫu chứ không thực sự chẩn đoán.

**Đã cân nhắc và bỏ:** *mất dữ liệu* — không demo an toàn được, và Agent chẳng có hành động khắc phục tự động nào ngoài leo thang, nên giá trị chẩn đoán gần bằng 0.
