# Worklog — Team Binary Brothers

> Ghi lại tất cả công việc đã làm theo ngày. Ai làm gì, kết quả gì.

**Thành viên:** Trung · Phan Hoàng Long · Việt · Trương Công Thái Đức
**Vai trò:** Đức (Lead · Kiến trúc & Tích hợp · DevOps) · Việt (AI Agent) · Trung (Backend service + QA) · Long (Frontend + Demo) — chi tiết ở [README.md](README.md#team--phân-vai)

---

## 2026-07-26

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| Trung | Khởi tạo dự án từ template, push lên GitHub | ✅ Done | commit `7b59cf7` | - |
| Phan Hoàng Long | Tạo branch `docs`, cập nhật worklog 26/07, merge vào `main` | ✅ Done | commit `9c1cfd0`, PR #2 | - |
| Việt | Tạo và publish branch `viet` | ✅ Done | `origin/viet` | 2m |
| Việt | Fix pre-push hook (CRLF → LF line endings) | ✅ Done | Hook chạy được trên Git Bash Windows | 5m |

**Tổng kết ngày:** Repo setup xong, mỗi người tự tạo branch riêng, bắt đầu ghi worklog. Chưa có branch tích hợp chung nên worklog của Long (`docs`) và Việt (`viet`) bị lệch nội dung.

---

## 2026-07-27

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| Trương Công Thái Đức | Đọc Technical Guidebook (10 chương + topic sections) | ✅ Done | Nắm lộ trình 6 tuần, 10 deliverables, 5 tiêu chí chấm điểm | - |
| Trương Công Thái Đức | Cài AI usage logging hook (`bash scripts/setup_hooks.sh`) | ✅ Done | `.git/hooks/pre-push` — log tự submit khi `git push` | - |
| Trương Công Thái Đức | Tạo `.env` từ `.env.example` | ✅ Done | `.env` (gitignored), còn thiếu API keys thật | - |
| Trương Công Thái Đức | Tạo branch `develop` làm điểm tích hợp, gộp branch `viet` | ✅ Done | `origin/develop` | - |
| Trương Công Thái Đức | Gộp và sửa lại worklog 26/07 cho đúng từng người | ✅ Done | file này | - |
| Cả đội | Phân chia vai trò (Agent / API / Frontend / DevOps-Test) | ⏳ Todo | - | - |
| Cả đội | Chốt đề tài agent, viết PRD 1 trang | ⏳ Todo | - | - |
| Cả đội | Setup venv + dependencies, chạy được server local | ⏳ Todo | - | - |

**Tổng kết ngày:** Phát hiện `setup_hooks.sh` chưa ai chạy → AI log ghi local nhưng không submit lên grading server (rủi ro mất deliverable #4), đã fix. Tạo `develop` vì CI chỉ chạy trên `[main, develop]`, 3 branch cá nhân hiện tại không có CI bảo vệ. Chưa chốt đề tài nên `src/` vẫn là code placeholder.

---

## 2026-07-28

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| Trương Công Thái Đức | Chốt đề tài PTNT-20, đọc & tổng hợp đề bài + kiến trúc (Jira làm lớp incident lifecycle, Prometheus không Alertmanager, load test thật thay fault injection) | ✅ Done | `README.md` | - |
| Trương Công Thái Đức | Phân vai 4 thành viên theo năng lực thực tế (không chia đều 4 phần như đề bài gợi ý) | ✅ Done | `README.md`, `JOURNAL.md` | - |
| Trương Công Thái Đức | Phát hiện `develop` chưa từng được push → push lên remote | ✅ Done | `origin/develop` = `a885985` | - |
| Trương Công Thái Đức | CI chạy lần đầu trên work của đội | ✅ Done | run `30346591635` — pass, 28s | - |
| Trương Công Thái Đức | Fix CI: PR vào `develop` không có lint/test gác cửa | ✅ Done | `a885985` | - |
| Trương Công Thái Đức | Wiring LangSmith tracing (`configure_tracing()` export sang `os.environ`) | ✅ Done | `f6bc3f2` | - |
| Trương Công Thái Đức | Viết README của đội — deliverable #2 | ✅ Done | `README.md` | - |
| Trương Công Thái Đức | Vẽ 3 sơ đồ kiến trúc (container tô màu theo người, LangGraph flow, sequence demo + escalation) — deliverable #3 | ✅ Done | `docs/architecture_diagram.md` | - |
| Trương Công Thái Đức | Viết `ARCHITECTURE.md` thật thay template (thành phần, data flow, deployment, security) | ✅ Done | `ARCHITECTURE.md` | - |
| Trương Công Thái Đức | Viết 3 ADR: Jira làm incident lifecycle, bỏ Alertmanager, load test thật thay fault injection | ✅ Done | `docs/adr/0001..0003` | - |
| Trương Công Thái Đức | Contract ①: metric name, label, PromQL, ngưỡng severity (Trung → Việt) | ✅ Done | `docs/contracts/01-metrics.md` | - |
| Trương Công Thái Đức | Contract ②: Pydantic model dùng chung (Severity, IncidentSignal, Hypothesis, Incident, StatusPage…) | ✅ Done | `src/models/incident.py` | - |
| Trương Công Thái Đức | Contract ③: `JiraClient` Protocol + `FakeJiraClient` (Đức → Việt) | ✅ Done | `src/services/jira/client.py` | - |
| Trương Công Thái Đức | Contract ④: endpoint `/api/status`, `/api/incidents` + fixture JSON (Đức → Long) | ✅ Done | `src/api/incidents.py` | - |
| Trương Công Thái Đức | 17 test bảo vệ contract, gồm test HITL chặn Agent tự duyệt | ✅ Done | 22 test pass, ruff clean | - |
| Long / Trung / Việt | Cài `pre-push` hook trên clone của mình (`bash scripts/setup_hooks.sh`) | ⏳ Todo | verify `ls -l .git/hooks/pre-push` | - |
| Long / Trung / Việt | Setup venv 3.11 + chạy được `localhost:8000/docs` | ⏳ Todo | screenshot | - |
| Việt | Đọc contract ①②③, spike docker-compose Prometheus + dummy service, query PromQL từ Python | ⏳ Todo | script in ra avg latency | - |
| Trung | Đọc contract ①. Task probe: `service-thanh-toan` (FastAPI, `POST /pay`, Postgres, pool = 5, `/metrics` + `db_pool_*`) | ⏳ Todo | `curl` được + `/metrics` có `http_request_duration_seconds` và `db_pool_connections_in_use` | - |
| Long | Đọc contract ④. Streamlit status page đọc `GET /api/status` (đã có dữ liệu fixture) | ⏳ Todo | `streamlit run` mở được trang, 2 service đúng màu theo `health` | - |

**Tổng kết ngày:** Chốt đề tài và phân vai — bỏ cách chia 4 phần đều trong đề bài vì đội có 2 người mạnh và 2 người ít kinh nghiệm; phần mơ hồ dồn cho Đức/Việt, phần biên rõ và không chặn ai giao Trung/Long, kèm quyền sở hữu deliverable phi-code để 2 bạn đóng góp vào điểm số. Phát hiện `develop` tạo hôm 27/07 nhưng chưa push → cả đội tưởng đã có branch tích hợp, và CI chưa chạy lần nào. Sau khi push, CI pass lần đầu và 39 AI log entry được submit.

Buổi chiều làm xong nền kiến trúc: 3 sơ đồ + `ARCHITECTURE.md` + 3 ADR (deliverable #3), và 4 contract file mở khoá làm song song. Nhờ contract ③ và ④, Việt viết được Agent mà không cần Jira workspace (`FakeJiraClient`), Long build được UI mà không cần Agent (`/api/status` đã trả dữ liệu fixture) — cả 4 người bắt đầu cùng lúc thay vì xếp hàng chờ nhau. Cổng HITL được chốt ở tầng interface: `FakeJiraClient.transition(..., REMEDIATING)` raise `PermissionError`, nên Agent viết sai luồng sẽ fail ở CI chứ không fail lúc demo. Tổng 22 test pass, ruff clean.

Việc gấp nhất còn lại của tuần: Long, Trung, Việt vẫn chưa cài `pre-push` hook trên clone của mình — cùng loại lỗi "việc làm một lần fail âm thầm" như `setup_hooks.sh` hôm qua.

---

## 2026-07-29

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| Trương Công Thái Đức | Phát hiện `Dockerfile` của template chưa bao giờ chạy được (package ở `/root/.local`, quyền 700, non-root user không đọc được → exit 126) | ✅ Done | `8e3526e` — chuyển sang venv `/opt/venv` | - |
| Trương Công Thái Đức | Bind `$PORT` thay vì hardcode 8000 + viết `render.yaml` | ✅ Done | `8e3526e` | - |
| Trương Công Thái Đức | Test Docker local: build, PORT=10000 và mặc định, healthcheck, SIGTERM | ✅ Done | tất cả pass | - |
| Trương Công Thái Đức | Xử lý rào quyền: cả 4 thành viên chỉ có `push` trên repo org nên không cài được GitHub App của Render | ✅ Done | mirror `TruongDuke/P-035-deploy` (private, đã tắt Actions) | - |
| Trương Công Thái Đức | **Deploy Render thành công — deliverable #5** | ✅ Done | https://p-035-incident-agent.onrender.com | - |
| Trương Công Thái Đức | Điền Hồ sơ quản lý dự án (6/13 sheet: Tổng hợp, Đường link, Thành viên, 28 User Story, Lộ trình, Báo cáo tuần W1) | ✅ Done | file xlsx gửi lên Google Sheets | - |
| Long / Trung / Việt | Cài `pre-push` hook + setup môi trường | ⏳ Todo | vẫn chưa xong | - |
| Việt | Dựng spike `docker-compose`: Prometheus + service dummy có instrumentator, pool 5 mô phỏng bằng `Semaphore` | ✅ Done | `spike/` — target UP tại `localhost:9090` | - |
| Việt | Viết `spike_promql.py` query Prometheus HTTP API, verify 4 câu PromQL của contract ① | ✅ Done | `avg latency = 1.562 s` lúc nghẽn, `0.083 s` lúc rảnh | - |
| Việt | Viết `loadgen.py` sinh tải làm cạn pool để có số liệu thật hai trạng thái | ✅ Done | 150 request đồng thời → 61 req/s, p95 tăng 20 lần | - |
| Việt | **Tìm ra contract ① có 4 lỗi**, nặng nhất là bucket mặc định làm ngưỡng P1/P2 không bao giờ kích hoạt | ✅ Done | `spike/README.md` — cần PR sửa contract, Trung review | - |

**Tổng kết ngày:** Deploy xong, có public URL — deliverable #5 hoàn thành, và quan trọng hơn là bước duyệt → webhook → remediation của kịch bản demo giờ khả thi. Trên đường deploy phát hiện `Dockerfile` của template **chưa bao giờ chạy được**: package cài bằng `pip install --user` nằm ở `/root/.local` (quyền 700) nên sau `USER appuser` container exit 126 với `exec: uvicorn: Permission denied`. Đúng loại lỗi mà việc deploy sớm tồn tại để bắt — nếu để tuần 5 mới deploy thì gặp nó lúc không còn thời gian.

Rào thứ hai: cả 4 thành viên chỉ có quyền `push` trên repo org (repo do bot BTC tạo nên không ai có `admin`), mà Render cần quyền admin để cài GitHub App. Thay vì chờ BTC approve, deploy từ repo mirror trên account cá nhân — không phải xin quyền gì và có URL ngay trong ngày. Đánh đổi: sau mỗi lần merge PR trên web phải `git push origin develop` để mirror không tụt lại, đã ghi vào START-HERE.

Việc gấp nhất vẫn chưa xong: 3 thành viên còn lại chưa cài `pre-push` hook.

Việt chạy xong spike Prometheus + PromQL. **Kết luận: kiến trúc không phải đổi** — 4 câu PromQL của contract ① chạy được và phân biệt rõ lúc rảnh (p95 0.095s, pool 0%) với lúc nghẽn (p95 1.95s, pool 100%, lỗi 2.1%). Nút cổ chai là thật: pool 5 × truy vấn 80ms cho trần ~62 req/s, bắn 150 request đồng thời đo được đúng 61 req/s và phần dư xếp hàng.

Nhưng spike tìm ra **4 lỗi trong contract ①**, và lỗi nặng nhất đúng loại "không báo lỗi" mà contract ① tự cảnh báo: `prometheus-fastapi-instrumentator` mặc định chỉ có 4 bucket `(0.1, 0.5, 1, +Inf)`, nên `histogram_quantile` **kẹp p95 về 1.0** khi giá trị thật rơi vào `+Inf`. Bảng severity có P1 = p95 > 10s và P2 = p95 > 2s → **hai mức này chết cứng**, Agent sẽ phân loại mọi sự cố nặng thành P3. Query vẫn trả số, không có exception nào để lần theo. Sửa bằng cách chỉ định bucket tường minh; sau khi sửa cùng câu query trả 1.95s thay vì 1.0. Ba lỗi còn lại: câu tỷ lệ lỗi trả rỗng thay vì 0 khi service khoẻ (Agent không phân biệt được "khoẻ" với "mất metric"), request scrape `/metrics` của chính Prometheus làm nhiễu avg latency 40 lần, và label `service` của `db_pool_*` bị đổi tên thành `exported_service` do khai trùng ở hai chỗ. Chi tiết + cách sửa ở `spike/README.md`, cần PR riêng vào contract ① có Trung review vì 2 lỗi đổi code service của Trung.

---

## [YYYY-MM-DD]

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| | | | | |

**Tổng kết ngày:**

---

<!-- Format: copy block trên cho mỗi ngày làm việc -->
