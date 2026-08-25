# Hồ sơ nộp Demo Day — P-035

> File này để **copy-paste thẳng vào form nộp**. Mỗi mục đã viết sẵn đúng độ dài
> thường gặp của ô nhập. Hai ô còn trống là hai thứ phải deploy/quay xong mới có.

---

## 1. Tên dự án

**AI Agent Điều Phối Ứng Phó Sự Cố**

Tên tiếng Anh (nếu form hỏi): *Incident Response Orchestration Agent*
Mã đề bài: **PTNT-20** — Khối PTNT (Kiến trúc & Tích hợp) · Team **Binary Brothers**

### Tagline — 1 dòng

> AI trực sự cố hạ tầng: tự phát hiện, chẩn đoán có bằng chứng truy vết được, và **không được phép tự ý hành động**.

---

## 2. Mô tả ngắn (~60 từ — cho ô mô tả tóm tắt)

```
Khi một dịch vụ sập, phần lớn thời gian đầu của người trực không dùng để sửa mà
dùng để thu thập bối cảnh. Agent của chúng tôi làm phần đó: tự phát hiện sự cố từ
Prometheus, mở war room trên Jira, chẩn đoán kèm bằng chứng số liệu truy vết ngược
được, và đề xuất cách sửa — nhưng dừng lại chờ người phê duyệt. Agent không có
đường nào tự duyệt cho chính nó.
```

---

## 3. Mô tả đầy đủ (~250 từ — cho ô mô tả chi tiết)

```
VẤN ĐỀ

Khi một dịch vụ tích hợp sập hoặc chậm đột ngột, quy trình ứng phó vẫn hoàn toàn
thủ công: gọi người, dò log từng service, đoán nguyên nhân, cập nhật trạng thái
bằng tay. Điểm mấu chốt là phần lớn thời gian đầu của một sự cố không dành cho
việc khắc phục mà dành cho việc thu thập bối cảnh. Prometheus, Grafana, Datadog
chỉ trả lời "có gì đó sai" — chúng không tổng hợp bối cảnh xuyên service, không
nêu giả thuyết nguyên nhân, không điều phối hành động, không viết postmortem.

GIẢI PHÁP

Một AI Agent (LangGraph) điều phối trọn vòng đời sự cố: phát hiện → phân loại
severity → mở war room trên Jira → thu thập bối cảnh và đối chiếu deploy history
→ chẩn đoán kèm bằng chứng → đề xuất khắc phục → CHỜ NGƯỜI DUYỆT → thực thi →
tự đo lại xác nhận đã khỏi → sinh postmortem.

BA ĐIỂM KHÁC BIỆT

1. Chẩn đoán có bằng chứng, không phải LLM đoán. Rule engine chạy trước và sinh
   ra con số; LLM chỉ diễn giải. Mọi giả thuyết truy ngược được về một câu PromQL
   cụ thể, bấm nút là mở thẳng Prometheus ra đối chiếu. Khi số liệu phản bác câu
   LLM, hệ thống bỏ câu của LLM và giữ kết luận của luật.

2. Human-in-the-loop được thực thi bằng cấu trúc, không bằng thiện chí. Backend
   đọc changelog Jira để xác minh ai đã duyệt; nếu là account Agent thì từ chối
   thi hành. Đã verify end-to-end trên Jira thật (issue KAN-11).

3. Sự cố trong demo là sự cố thật — tải thật làm cạn connection pool thật, service
   thứ hai timeout vì nó thật sự phụ thuộc service thứ nhất. Không có dòng
   `if demo_mode`. Agent phải chẩn đoán, không đọc kịch bản.
```

---

## 4. Số liệu dùng khi bị hỏi (không bịa, mỗi số đều truy được nguồn)

| Chỉ số | Kết quả | Nguồn |
|---|---|---|
| Thời gian phát hiện (scrape đầu tiên → mở phiếu Jira) | **33,4 giây** | [eval/results/report.md](../eval/results/report.md) |
| Độ chính xác chẩn đoán nguyên nhân gốc (M3, top-1) | **80,77%** — 21/26 lượt | [eval/results/report.md](../eval/results/report.md) |
| Độ chính xác severity trên 3 lần tái hiện | **3/3 (100%)** | [eval/results/report.md](../eval/results/report.md) |
| Báo nhầm khi tải nhẹ 10 phút | **0 incident / 75 vòng poll** | [eval/results/false-alarm-warm.json](../eval/results/false-alarm-warm.json) |
| Chống mở phiếu trùng | **1 incident / 36 vòng poll** (1 mở, 35 cập nhật) | [eval/results/uc1-dedup-5m.json](../eval/results/uc1-dedup-5m.json) |
| Test case thủ công trên hệ thống thật | **5/5 PASS** | [eval/EVIDENCE.md](../eval/EVIDENCE.md) |
| Khắc phục thật UC-4 (deploy thiếu migration) | tỷ lệ lỗi **100% → 0%**, 326/326 request thành công | [docs/demo-runbook.md](../docs/demo-runbook.md) |
| Thời gian một lượt suy luận LLM | **3,088 giây** trung bình | [eval/results/report.md](../eval/results/report.md) |
| Bộ 50 case enterprise (nghiêm ngặt hơn) | recall **72%**, severity accuracy **88,89%** | [evaluation_report_v3.md](../evaluation_report_v3.md) |

> ⚠️ Đừng diễn đạt 80,77% thành "LLM đạt 80,77%". Đó là con số của **Agent**, gồm cả
> phần luật giữ lại khi LLM sai. Trong 19 câu LLM được chấp nhận, 14 câu đúng (73,68%).
> Ghi rõ như vậy nếu bị hỏi sâu — báo cáo đã ghi đúng như thế.

---

## 5. Bảng link nộp

| Hạng mục | Link | Trạng thái |
|---|---|:---:|
| **Link MVP** | `_____________` (điền sau khi deploy — xem §6) | ⏳ |
| **Video Demo** (≤ 3 phút) | `_____________` (YouTube unlisted / Drive) | ⏳ |
| **Slides thuyết trình** | `presentation/pitch-deck.html` — 12 slide, mở bằng trình duyệt | ✅ dựng xong, chưa có link chia sẻ |
| **Ảnh thumbnail** | `presentation/thumbnail.png` (1280×720) | ✅ dựng xong |
| Backend đang chạy | https://p-035-incident-agent.onrender.com | ✅ |
| API docs (Swagger) | https://p-035-incident-agent.onrender.com/docs | ✅ |
| Status API | https://p-035-incident-agent.onrender.com/api/status | ✅ |
| Source code | https://github.com/AI20K-Build-Phase-Cohort-3/P-035 | ✅ |

### Dùng slides thế nào

- **Trình chiếu:** mở `pitch-deck.html` bằng Chrome, bấm `F11` toàn màn hình, điều hướng bằng `←` `→` (hoặc `Space`, hoặc hai nút *Trước / Sau* dưới khung). Trên điện thoại thì vuốt ngang.
- **Xuất PDF để nộp:** `Ctrl+P` → Destination *Save as PDF* → Layout **Landscape** → Margins **None** → bật **Background graphics** (thiếu mục này thì nền tối mất sạch, chữ sáng trên giấy trắng sẽ không đọc được).
- **Deep link tới một slide:** thêm `#s7` vào cuối đường dẫn để mở thẳng slide 7.

---

## 6. Deploy link MVP — checklist trước khi nộp

Backend đã public sẵn, nhưng giám khảo bấm vào chỉ thấy JSON. Muốn họ thấy **sản phẩm**
thì phải đưa war room lên Streamlit Community Cloud (miễn phí, ~15 phút).

**Bước 1 — tạo app trên https://share.streamlit.io**

| Trường | Giá trị |
|---|---|
| Repository | `AI20K-Build-Phase-Cohort-3/P-035` |
| Branch | `main` |
| Main file path | `ui/war_room.py` |
| Python version | 3.11 |

Streamlit tự đọc `ui/requirements.txt` và `.streamlit/config.toml` (theme tối) ở gốc repo.

**Bước 2 — Advanced settings → Secrets, dán đúng dòng này:**

```toml
API_URL = "https://p-035-incident-agent.onrender.com"
```

> ⚠️ **Không được bỏ qua.** Thiếu `API_URL`, UI rơi về mặc định và hiển thị dữ liệu của
> môi trường khác — đúng lỗi đã ghi ở [docs/demo-runbook.md](../docs/demo-runbook.md).
> Triệu chứng: trang trắng hoặc dữ liệu lạ, và **không có thông báo lỗi nào**.

**Bước 3 — deploy trang thứ hai (status page công khai)**

Lặp lại bước 1–2 với main file `ui/status_page.py`. Đây là trang cho người dùng cuối,
không cần đăng nhập — hợp làm link MVP nếu form chỉ nhận một link và bạn muốn giám khảo
thấy ngay giá trị mà không cần giải thích. War room thì cho thấy chiều sâu kỹ thuật hơn.

**Khuyến nghị:** để **war room** làm link MVP chính (nó thể hiện phần lõi: bằng chứng,
giả thuyết, cổng phê duyệt), và dán status page + Swagger vào phần mô tả làm link phụ.

**Bước 4 — đánh thức Render trước khi giám khảo chấm**

```bash
curl https://p-035-incident-agent.onrender.com/health
```

Render free tier ngủ sau 15 phút không có request, tỉnh lại mất 30–60 giây. Giám khảo mở
trúng lúc nó ngủ sẽ thấy trang chờ rất lâu. Gọi `/health` vài phút trước giờ chấm, hoặc
đặt một cron ping bên ngoài (cron-job.org, mỗi 10 phút) trong tuần chấm bài.

**Bước 5 — nghiệm thu link MVP**

- [ ] Mở link ở **cửa sổ ẩn danh** (không có cache, không có session) — vẫn lên
- [ ] Mở trên **điện thoại** — không vỡ layout
- [ ] Có ít nhất 1 incident hiển thị (chạy `run_agent.py` một lượt trước khi nộp để có dữ liệu thật, đừng để trang rỗng)
- [ ] Không có dòng lỗi đỏ nào của Streamlit trên màn hình

---

## 7. Đội ngũ

| Thành viên | Vai trò | Sở hữu |
|---|---|---|
| Trương Công Thái Đức | Team Lead · Kiến trúc & Tích hợp | Contract/schema, `JiraClient`, cổng HITL, webhook, DevOps, tích hợp cuối |
| Việt | AI Agent Engineer | LangGraph, detection, rule engine, LLM diagnosis, correlation deploy, postmortem |
| Trung | Backend Engineer · QA | 2 service demo, load test, `deploy_history`, test suite, evaluation evidence |
| Phan Hoàng Long | Frontend Engineer · Demo | Status page, war-room view, video demo, pitch deck |

---

## 8. Còn thiếu gì — nói thẳng nếu bị hỏi

Ba câu trả lời này đã được chuẩn bị sẵn trong [docs/demo-runbook.md](../docs/demo-runbook.md),
mục *"Câu hỏi chắc chắn bị hỏi"*. Đọc lại trước khi thuyết trình.

- **Thi hành thật**: `rollback` trên `service-thanh-toan` đã chạy thật (bật bằng `REMEDIATION_REAL=1`).
  Ba hành động còn lại vẫn mô phỏng vì cần đổi cấu hình hạ tầng, không đảo được bằng một lệnh.
  Hệ thống **tự biết** cái nào nó sửa thật được và ghi rõ là mô phỏng khi không làm được.
- **Recall 72%** trên bộ 50 case enterprise: rule baseline bỏ lọt các dạng silent failure.
  Đây là hạn chế đã đo và ghi lại, không giấu.
- **`awaiting_keys` chỉ nhớ trong tiến trình**: khởi động lại Agent thì nó quên phiếu đang
  chờ duyệt. Cần seed từ Jira lúc khởi động — đang là việc tiếp theo.
