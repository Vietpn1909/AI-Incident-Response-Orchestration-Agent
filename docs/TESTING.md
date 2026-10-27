# Tài liệu kiểm thử

**673 test tự động · 41 file · chạy hết trong ~5 giây · CI xanh trên mọi push.**

Trang này trả lời ba câu: kiểm thử **theo chiến lược nào**, **phủ được gì**, và —
quan trọng nhất — **chưa phủ gì**.

Mục cuối là chỗ đáng đọc nhất. Một bộ test không nói ra chỗ nó mù thì chỉ chứng
minh được rằng nó xanh.

---

## 1. Bốn tầng, mỗi tầng trả lời một câu khác nhau

| Tầng | Số test | Trả lời câu |
|---|---:|---|
**Đơn vị** — `tests/test_services/` | **435** | luật quyết định đúng chưa |
**Node & graph** — `tests/test_agents/` | **150** | các bước nối vào nhau đúng chưa |
**API & webhook** — `tests/test_api/` | **52** | cổng HITL và webhook chặn đúng chưa |
**Bộ đo & UI** — 4 file lẻ | **36** | phép đo và giao diện có gãy không |
| **Tổng** | **673** | |

Bốn file lẻ: `test_eval_case_suite` (10) · `test_eval_measurements` (7) ·
`test_ui_import` (8) · `test_ui_labels` (11).

### Vì sao tầng đơn vị chiếm 65%

Vì **quyết định nằm ở luật**, không ở LLM. `rules.py` là chỗ trả lời *"có phải sự cố
không"*, *"mức nào"*, *"nên làm gì"* — và nó thuần hàm, không gọi mạng, nên test được
đầy đủ và chạy lại ra y hệt.

LLM chỉ **diễn giải bằng chứng thành câu**. Nếu để LLM quyết định thì không tầng nào
test được, vì cùng đầu vào có thể ra khác nhau.

---

## 2. Bốn cách kiểm, không chỉ một

### a. Test tự động — 673 test

Chạy `pytest`. Không gọi mạng: `tests/conftest.py` **chặn** `OPENAI_API_KEY`,
`LLM_BASE_URL`, `DATABASE_URL`, `JIRA_*` để không test nào lỡ gọi ra ngoài.

> Đây là bản vá có thật: trước 20/08 `conftest` thiếu `OPENAI_API_KEY`, nên **mọi lần
> chạy test đều gọi LLM thật** — 146,59 giây một lượt. Sau khi chặn: 3,17 giây.

### b. Bộ đo offline — 50 case

`python -m eval.case_suite`. Ảnh chụp số đo → client Prometheus giả → **luật thật** →
`FakeJiraClient`. Không LLM, không Docker, không Jira thật.

Kết quả và cách đọc: [`eval/RESULTS-2026-08-21.md`](../eval/RESULTS-2026-08-21.md).

### c. Kiểm thủ công trên hệ thống thật — 5 case

[`eval/EVIDENCE.md`](../eval/EVIDENCE.md) — mỗi case chạy trên Prometheus + Docker +
Jira Cloud thật, **output lấy từ log và API response thật**, không viết lại.

### d. Chạy trọn vòng trong Docker

Bốn use case chạy thật: gây sự cố → Agent phát hiện → chẩn đoán → đề xuất → người
duyệt → **thi hành thật** → tự đo lại. Xem
[`docs/demo-runbook.md`](demo-runbook.md).

Đây là tầng duy nhất bắt được **lỗi dây nối** — xem §5.

---

## 3. CI — chạy trên mọi push

[`.github/workflows/ci.yml`](../.github/workflows/ci.yml):

```
pip install -r requirements.txt -r demo/requirements.txt -r ui/requirements.txt
ruff check src/ tests/ demo/ ui/
pytest tests/ -v --tb=short
```

> ⚠️ Dòng `pip install` phải có **cả ba** file. Ngày 17/08 CI chỉ cài
> `requirements.txt`, nên `plotly` — dep của `ui/` — không được cài. **War room chết
> mà CI vẫn xanh.** Chú thích cảnh báo nằm ngay trong `ci.yml`.

---

## 4. Số đo chất lượng — trên 50 tình huống dựng từ số đo thật

```
TP=21   FN=4   FP=5   TN=20
```

| Chỉ số | Kết quả | KTC 95% |
|---|---:|:---:|
Recall *(không bỏ lọt)* | **84,00%** | 70–98% |
Precision | 80,77% | 66–96% |
Báo nhầm | **20,00%** | 4–36% |
F2 *(nghiêng recall)* | 83,33% | — |
MCC | **+0,6405** | — |
Xếp mức độ P1–P4 | 80,95% | — |
Nguyên nhân gốc *(luật, LLM tắt)* | 28,00% | — |

> ⚠️ **Đừng so hai phần trăm giữa hai lần đo.** Ở n = 25 case sự cố thì khoảng tin cậy
> rộng vài chục điểm — recall 72% (15/08) có khoảng 54–90%, trùm gần hết lên 84%. Cái
> chứng minh được là **cơ chế đã bịt**, không phải con số.

Chi tiết, kèm cách đọc từng dòng: [`eval/RESULTS-2026-08-21.md`](../eval/RESULTS-2026-08-21.md).

### Con số 28% "nguyên nhân gốc" bị đọc sai

Chia 25 case sự cố ra thì nó **không phải "sai 72%"**:

| | Số |
|---|---:|
✅ Đúng nguyên nhân | **7** |
🤷 **Tự nhận "chưa đủ bằng chứng"** | **11** |
❌ Nói sai | **2** |
⬜ Bỏ lọt, không chẩn đoán gì | 4 |

**Chỉ 2 trên 25 là nói sai**, và cả hai đều *gần đúng* — không case nào bịa. 11 case
kia Agent **từ chối đoán**, đó là hành vi đúng.

Và 28% là điểm của **luật khi LLM bị tắt**. Chạy thật với log tham gia: tin cậy đi từ
30% *"chưa đủ bằng chứng"* lên 70% *"thiếu cột `idempotency_key`"*.

---

## 5. Bộ test này **KHÔNG** bắt được gì

Đây là mục quan trọng nhất trang này.

### a. Lỗi dây nối — code đúng nhưng không được gọi

Bảy lỗi nghiêm trọng trong tuần, **cả bảy đều lọt qua test**:

| Lỗi | Test lúc đó |
|---|---|
`planned_events.py` viết xong nhưng **chưa nối vào Agent** | xanh, và **báo sai theo hướng đẹp hơn** |
UI đọc `os.getenv` không đọc `.env` → mất nút sang Jira | xanh |
Một lần duyệt thi hành **2 lần** | xanh |
Thiếu `plotly` → war room chết | xanh |
Postmortem **không bao giờ tới war room** | xanh |
Agent đề xuất `scale_up` thay `rollback` | xanh |
Deploy gần đó **bịt miệng UC-2** | xanh |

Nguyên nhân chung: test dùng **client giả**, mà client giả cư xử khác client thật.
Ví dụ `FakeJiraClient.attach_postmortem()` có gán `incident.postmortem`, còn
`RealJiraClient` chỉ post một comment — nên chỉ **đường thật** hỏng.

**Cách chặn từ 21/08:** mỗi bản vá loại này thêm một test đi **đúng đường thật**
*(nhặt body đã POST lên Jira, dựng lại object từ khối JSON)*, và **kiểm ngược**: bỏ
bản vá đi thì test phải đỏ. Không đỏ thì test đó vô nghĩa.

### b. Khâu Agent CHỌN HÀNH ĐỘNG

Bộ đo chấm **3 khâu trên 11**: phát hiện · xếp mức độ · nêu nguyên nhân.

**Không chấm** `propose_remediation`. Ngày 21/08 Agent đề xuất `scale_up` cho ca phải
`rollback` — mà `executors` chỉ cho thi hành thật `rollback`, nên màn khắc phục sẽ ra
`(mô phỏng)`. **Mọi chỉ số vẫn xanh.**

Đây là lỗ lớn nhất còn lại, và đã biết cách bịt: chấm `runbooks.choose()` theo
`expected_action`. Hàm đó **thuần luật, không có LLM** nên chạy lại ra y hệt — sẽ là
chỉ số đáng tin nhất trong bộ đo.

### c. Bốn loại sự cố Agent bỏ lọt — **kể tên**

| Case | Nội dung | Số đo lúc đó |
|---|---|---|
`I15` | lỗi xác thực bị metric tổng hợp che | p95 0,08 / thường 0,07 |
`I16` | trả `200 OK` nhưng **ghi sai DB** | p95 0,19 / thường 0,20 |
`I22` | dependency **gửi dữ liệu ra ngoài** | p95 0,21 / thường 0,20 |
`I25` | race condition **thu tiền 2 lần** | không có lỗi 5xx nào |

**Ba trên bốn có số đo hoàn toàn bình thường** — không phải luật nắn sai, mà trong
Prometheus **không có tín hiệu nào để bắt**. Cần kiểm tính đúng dữ liệu, theo dõi
traffic đi ra, đối soát giao dịch trùng.

Chỉ `I15` sửa được bằng metric *(tách p95 theo từng endpoint)*, và bản vá đó sửa luôn
một case báo nhầm.

> Bộ case **cố ý** chứa những sự cố mà metric không thấy được. Nếu chỉ nhét vào đúng
> mấy loại đã viết luật thì sẽ ra ~100%, và con số đó vô nghĩa.

### d. Chính bộ đo cũng từng đo sai

Ngày 21/08 phát hiện `planned_events.py` **chỉ được gọi từ `eval/`**, chưa nối vào
Agent. Nên *"báo nhầm 16%"* từng công bố là tính chất của **bộ đo**; sản phẩm thật
vẫn 28%.

Nặng hơn: bộ đo lọc bằng `context["maintenance_event"]` — nguồn Agent **không** có lúc
chạy — và bỏ qua `context["deploy"]` — nguồn Agent **có**.

**Vá:** `detect_incidents()` nhận nguồn qua tham số, bộ đo truyền thẳng bối cảnh của
case. Nhờ vậy hai đường *(qua node / gọi luật trực tiếp)* **không thể lệch nhau nữa** —
`test_pipeline_prometheus_detect_jira_khop_voi_rule_truc_tiep` đỏ ngay khi chúng lệch.

---

## 6. Bốn nguyên tắc rút ra

**① Test phải kiểm ngược được.** Mỗi bản vá lỗi thêm test, rồi **bỏ bản vá đi xem test
có đỏ không**. Không đỏ thì test đó không canh gì cả.

**② Đừng cắm cứng con số vào test.** Bốn test từng viết `assert TP == 18`,
`recall == 0.72` — mỗi lần vá một lỗ hổng là chúng đỏ vì lý do không liên quan. Đã
viết lại thành khẳng định **tính chất** *(recall không được giảm, FP không được tăng)*.

**③ Client giả phải cư xử như client thật, hoặc phải có test đi đường thật.**
Bảy lỗi ở §5a đều sinh ra từ khoảng cách này.

**④ Test xanh không thay được chạy thật.** Ngày 21/08 chạy trọn 4 UC trong Docker tìm
ra **4 lỗi** mà 596 test không thấy — trong đó có việc `_prometheus` giả trong
`test_detection.py` **không mô hình hoá bộ nhớ**, nên chưa test nào từng chạm tới
nhánh đó.

---

## 7. Chạy lại

```bash
# 673 test — khoảng 5 giây, không gọi mạng
pytest -q

# lint
ruff check src/ tests/ eval/ demo/ ui/

# bộ đo 50 case — offline, không LLM
python -m eval.case_suite

# bộ đo CÓ LLM, đo độ bao quát chẩn đoán
python -m eval.case_suite --with-llm

# chạy trọn vòng trong Docker — xem docs/demo-runbook.md
```
