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
| Trương Công Thái Đức | Setup Jira Cloud (2 account, token, khảo sát project qua API) | ✅ Done | `jibinarybro.atlassian.net`, project `KAN` | - |
| Trương Công Thái Đức | Phát hiện Jira Cloud bản mới chỉ tạo được team-managed → **đổi cơ chế HITL** sang kiểm tra changelog | ✅ Done | `src/services/hitl.py`, ADR-0001 cập nhật | - |
| Trương Công Thái Đức | Phát hiện custom field không dùng được trên team-managed → chuyển sang label | ✅ Done | `src/services/jira/mapping.py` | - |
| Trương Công Thái Đức | `RealJiraClient` + **verify cổng HITL trên Jira thật** | ✅ Done | Agent tự duyệt → backend từ chối ✅ | - |
| Trương Công Thái Đức | `POST /webhooks/jira` — 3 lớp bảo vệ (secret → HITL → allowlist hành động) | ✅ Done | `src/api/webhooks.py`, 13 test | - |
| Trương Công Thái Đức | Gom 3 file `jira*` thành package `src/services/jira/` | ✅ Done | `96630aa` | - |
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

**Buổi tối:** setup Jira và làm trọn khối "quản lý vòng đời incident". Hai giả định trong ADR-0001 gãy khi gặp Jira thật, cả hai đều chỉ lộ ra khi chạy chứ không đọc tài liệu mà biết được:

1. Jira Cloud bản mới (mô hình Spaces) **chỉ tạo được team-managed project**, mà loại này không đặt được điều kiện phân quyền lên transition → không thể trông cậy Jira chặn Agent. Chuyển cổng HITL sang backend, kiểm tra changelog xem *ai* đã duyệt. Cách mới còn demo trực quan hơn và test được bằng CI.
2. **Custom field không dùng được** trên team-managed (tạo qua API thành công nhưng không xuất hiện trên project) → chuyển sang label, bớt hẳn một lớp phức tạp.

Đã verify cổng HITL trên Jira thật: Agent tự chuyển sang `Remediating` → Jira cho chuyển (đúng như dự đoán) → **backend từ chối thi hành**. Đây là bằng chứng cho ràng buộc bắt buộc của đề bài, chạy trên hạ tầng thật chứ không phải mock. Trên đường verify còn bắt được một bug của chính mình: Jira đặt issue mới ở status đầu tiên của board (`Idea`) mà `Idea` đang map vào `REMEDIATING`, nên incident vừa tạo đã hiện là "Remediating".

Hoàn tất `POST /webhooks/jira` với 3 lớp bảo vệ, đóng luồng bước 7→8 của kịch bản demo. Tổng 49 test pass.

---

## 2026-07-30

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| Trung | Cài đặt `service-thanh-toan` (pool = 5, ghi Postgres, truy vấn thiếu index) + `seed.py` sinh dữ liệu Faker | ✅ Done | `80e70fc` | - |
| Trung | Cài đặt `service-dat-hang` gọi chéo (timeout → 504), `loadtest.py`, unit test cho demo | ✅ Done | `60ef1e1`, `88a66eb` | - |
| Trung | Mở PR #4 vào `develop` | ✅ Done | PR #4 | - |
| Phan Hoàng Long | Cài đặt `ui/status_page.py` — trạng thái tổng theo đúng thứ tự `StatusPage.overall_health`, giờ Việt Nam, nút tải lại | ✅ Done | `642685c` | - |
| Phan Hoàng Long | Cài đặt `ui/war_room.py` — danh sách + chi tiết incident, bằng chứng kèm PromQL, timeline, postmortem, incident liên quan bấm chuyển được | ✅ Done | `0c9a508` | - |
| Phan Hoàng Long | Mở PR #6 vào `develop` | ✅ Done | PR #6 | - |

**Tổng kết ngày:** Cả Trung và Long hoàn thành phần việc của mình và mở PR — đội có PR đầu tiên đi qua quy trình review đúng chuẩn. Long làm xong **cả hai** trang UI trong tuần 1, tức đi trước lịch (kế hoạch là tuần 2–3), nên tuần 2 có thời gian dồn cho video demo và pitch deck.

---

## 2026-07-31

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| Trương Công Thái Đức | Review PR #6 (Long) → **approve và merge** | ✅ Done | `dc33e2e`, CI pass | - |
| Trương Công Thái Đức | Review PR #4 (Trung) → **request changes**, 3 điểm | ✅ Done | PR #4 `CHANGES_REQUESTED` | - |
| Trương Công Thái Đức | Dựng service của Trung từ branch, chạy Postgres thật để **đo gauge pool** → phát hiện báo cạn 100% vĩnh viễn sau 1 request | ✅ Done | đã verify bản sửa: rảnh 0.0 → tải 5.0 → hết tải 0.0 | - |
| Trương Công Thái Đức | Phát hiện Trung và Việt sửa cùng file `scripts/_pyrun.sh` theo hai hướng ngược nhau | ✅ Done | chọn bản của Việt | - |
| Trương Công Thái Đức | Đồng bộ mirror sau khi merge PR trên web | ✅ Done | hai repo cùng `dc33e2e` | - |
| Việt | Mở PR cho bản sửa `_pyrun.sh` | ✅ Done | `e2f7cf2` đã vào `develop`, hết chặn Trung | - |
| Việt | Đổi `spike_promql.py` sang bắn thẳng các hằng trong `src/services/prometheus.py`, bỏ bản sao câu query | ✅ Done | `spike/spike_promql.py` | - |
| Việt | **Tìm ra lỗi thứ 5 của contract ①**: mọi câu có phép chia trả `NaN` khi service không có request | ✅ Done | 4 câu bị: p95, tỷ lệ lỗi, avg latency, baseline | - |
| Việt | Sửa: gắn `and on(service) (_HAS_TRAFFIC)`, cập nhật contract ① + `spike/README.md` | ✅ Done | rỗng lúc rảnh, 6/6 câu trả số dưới tải | - |
| Việt | **Tìm ra lỗi thứ 6**: baseline dùng `avg_over_time` bị chính sự cố kéo lên | ✅ Done | độ lệch tụt 3.7x → 2.1x sau 2 phút | - |
| Việt | Sửa baseline sang `quantile_over_time(0.1, ...)` | ✅ Done | độ lệch đứng yên 10.9x | - |
| Trung | Sửa 3 điểm ở PR #4 | ⏳ Todo | - | - |
| Phan Hoàng Long | Xác nhận đã cài `pre-push` hook | ⏳ Todo | chưa có dấu vết nào | - |

**Tổng kết ngày:** Ngày review. Hai bài học đáng ghi.

**Thứ nhất — bug nghiêm trọng nhất trong PR của Trung là do đặc tả của tôi sai.** TODO tôi viết trong skeleton ghi `POOL_SIZE - pool.get_idle_size()`, nhưng `POOL_SIZE` là *trần* còn pool khởi động với `min_size=1`, nên phải dùng `pool.get_size()` (số connection đã tạo). Cộng thêm `finally` nằm bên trong `async with` nên đo lúc connection còn bị giữ. Kết quả đo được: sau đúng 1 request lúc hệ thống rảnh, gauge báo `5.0/5.0` và nằm mãi ở đó — tức bằng chứng "pool cạn kiệt" trở thành **luôn đúng**, phá chính ràng buộc "chẩn đoán có bằng chứng". Trung làm theo hướng dẫn hoàn toàn đúng.

**Thứ hai — hai người sửa cùng một file dùng chung theo hai hướng ngược nhau.** Cả Trung và Việt đều vá `scripts/_pyrun.sh` cho vấn đề Python trên Windows. Việt thêm `--version` để loại alias giả của Windows Store, giữ nguyên fallback `python3`/`python`. Trung thay cả chuỗi bằng đường dẫn `.venv` và bỏ hai fallback đó — làm hook chết im lặng trên macOS/Linux, tức mất deliverable #4. Lấy bản của Việt.

Long đi trước tiến độ; việc gấp duy nhất còn của 3 bạn là xác nhận hook của Long.

**Buổi tối — hai lỗi nữa trong contract ①, cùng loại "sai im lặng".** Việt gộp `spike_promql.py` về bắn thẳng các hằng đang ship trong `src/services/prometheus.py` thay vì giữ bản sao câu query. Đổi xong là lộ ngay hai lỗi mà bản sao che mất.

**Lỗi 5 — `NaN`.** Không có request nào trong cửa sổ `[1m]` thì `rate` = 0, mọi phép chia thành 0/0 = `NaN`. Bốn câu bị: p95, tỷ lệ lỗi, avg latency, baseline. Nguy hiểm hơn kết quả rỗng vì `NaN > x` **và** `NaN < x` đều là `False` — mọi so sánh ngưỡng rơi tọt qua, Agent bỏ lọt sự cố mà không có dấu hiệu gì; mức P4 chết hẳn vì nó dựa trọn vào độ lệch baseline; Pydantic serialize `NaN` thành `null` nên bằng chứng số biến mất khỏi war-room view của Long. Sửa bằng `and on(service) (_HAS_TRAFFIC)` để câu trả **rỗng** thay vì `NaN`, nhờ đó `PrometheusClient.query()` chỉ phải xử lý một trạng thái "không có dữ liệu" thay vì hai.

**Lỗi 6 — baseline tự nhiễm.** Cửa sổ 30 phút bao gồm cả khoảng đang có sự cố, nên `avg_over_time` bị chính sự cố kéo lên: sự cố càng lâu càng trông bình thường. Đo thật với p95 giữ nguyên 1.95s — trung bình cho độ lệch 3.7x ở phút thứ nhất rồi tụt còn 2.1x ở phút thứ ba, trong khi `quantile_over_time(0.1, ...)` đứng yên ở 10.9x. Chọn phân vị 0.1 thay vì trung vị 0.5 vì trung vị bị nhiễm khi sự cố chiếm quá nửa cửa sổ (~15 phút), còn 0.1 chịu được tới ~27 phút — kịch bản demo có bước chờ người duyệt trên Jira, thời gian chờ không đoán trước được.

Sau hai lỗi này, spike chạy đủ 6/6 câu trả số và độ lệch đạt **10.8x** — đủ mạnh để làm bằng chứng cho `Hypothesis`.

**Bài học lặp lại lần thứ hai trong ba ngày: hai bản sao của cùng một thứ thì bản được kiểm tra không phải bản đang chạy.** Lỗi bucket hôm 29/07 lọt lưới cũng vì spike verify bản sao của chính nó, và may chạy đúng lúc có traffic liên tục nên câu baseline vẫn trả ra số.

Việc phát sinh cho Trung: `PROFILE_DEMO` trong `demo/loadtest.py` đã có bậc đầu `(5, 20)` làm warm-up, chỉ cần **kéo dài bậc đó lên vài phút** để cửa sổ 30 phút có đủ dữ liệu bình thường. Đổi sang phân vị vẫn không tạo baseline từ hư không.

---

## 2026-08-01

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| Việt | Review và merge PR #10 (`fix/promql-baseline-nan`) vào `develop` | ✅ Done | `9bfaa80`, CI pass | - |
| Trung | Kéo dài bậc warm-up trong `PROFILE_DEMO` | ⏳ Todo | cần cho baseline có nghĩa | - |
| Việt | **Cài `PrometheusClient.query()` + `query_range()`** — đường găng tuần 2 | ✅ Done | `query(P95_LATENCY)` → `[MetricSample(service='service-thanh-toan', value=1.93)]` | - |
| Việt | Thêm `PrometheusError` — phân biệt "không có dữ liệu" với "không biết tình hình" | ✅ Done | Prometheus chết thì raise, không trả rỗng | - |
| Việt | 9 test cho `PrometheusClient` bằng `httpx.MockTransport`, chạy được trong CI | ✅ Done | 68 test pass, ruff clean | - |
| Việt | Fix log tiếng Việt vỡ trên console Windows — `configure_logging()` ép UTF-8 cho cả stdout lẫn stderr | ✅ Done | `src/config.py`, gọi trong `lifespan` | - |
| Việt | **Cài 4 hàm trong `src/services/rules.py`** (`classify_severity`, `detect`, `classify_auth_burst`, `is_spreading`) | ✅ Done | 39 test, 107 test toàn repo pass | - |
| Việt | **Phát hiện mức P3 và P4 không đạt tới được** với ngưỡng ghi trong stub | ✅ Done | sửa cửa `detect` xuống ngưỡng P3 + thêm `BASELINE_DEVIATION_RATIO` | - |
| Việt | Node `detect` + `BreachTracker` — quy tắc "liên tục ≥ 30s" bắc qua nhiều vòng poll | ✅ Done | `src/agents/nodes/detect.py` | - |
| Việt | Node `classify_severity` — nâng P1 khi sự cố lan sang ≥ 2 service | ✅ Done | `src/agents/nodes/classify_severity.py` | - |
| Việt | Node `open_war_room` — `find_open_incident()` TRƯỚC `create_incident()` | ✅ Done | `src/agents/nodes/open_war_room.py` | - |
| Việt | Nối 3 node thành `incident_graph.py`, chạy thật trên Prometheus + load test | ✅ Done | 3 vòng đầu không mở incident, vòng 4 mở `INC-1`, vòng 5–7 dùng lại | - |
| Việt | 28 test cho node và graph, dùng client giả nên chạy được trong CI | ✅ Done | 135 test toàn repo pass, ruff clean | - |

**Tổng kết ngày:** PR #10 merge — hai lỗi làm bằng chứng số sai im lặng đã vào `develop`, cả đội pull về là có. Đây cũng là PR đầu tiên của Việt đi đúng quy trình `feature/*` → `develop` thay vì merge thẳng như lần trước.

Xong **đường găng tuần 2**: `PrometheusClient` hết `NotImplementedError`, `rules.py` và node `detect` hết bị chặn. Phần gọi API gần như chép từ `PrometheusQuerier` đã chạy trong spike, nhưng có thêm một quyết định thiết kế đáng ghi.

**Ranh giới giữa "không có dữ liệu" và "không biết tình hình".** `query()` trả **danh sách rỗng** khi Prometheus chạy tốt nhưng không có series nào — service chưa nhận request, đó là trạng thái bình thường. Còn khi Prometheus chết, sai địa chỉ, hoặc câu PromQL sai cú pháp thì **raise `PrometheusError`**. Nuốt lỗi và trả rỗng ở nhóm thứ hai là nguy hiểm nhất: Agent sẽ hiểu "mọi thứ bình thường" đúng lúc nó mù hoàn toàn. Có 3 test riêng gác ranh giới này.

Client cũng **loại bỏ mẫu `NaN`** kèm warning, dù các câu trong `prometheus.py` đã chặn NaN bằng `_HAS_TRAFFIC`. Đây là lớp phòng thủ thứ hai: hôm 31/07 đã có 4 câu lọt NaN, nếu sau này ai thêm câu mới mà quên bộ lọc thì client vẫn không để NaN chạm tới rule engine.

9 test dùng `httpx.MockTransport` nên **chạy được trong CI mà không cần Prometheus** — phần verify với Prometheus thật vẫn nằm ở `spike/spike_promql.py`, chạy tay khi có docker. Verify thật: cả 7 hằng đều trả đúng qua client (p95 1.93s, lỗi 2.4%, pool 1.00), riêng `AUTH_FAILURE_RATE` trả rỗng kèm warning vì service dummy không có endpoint `/login` — đúng như thiết kế.

**Log tiếng Việt vỡ trên Windows.** Console Windows mặc định cp1252, mà `logging` ghi vào **stderr** chứ không phải stdout, nên cảnh báo của `prometheus.py` in ra thành `Kh�ng gọi được...`. Thêm `configure_logging()` vào `src/config.py`, ép UTF-8 cho cả hai luồng và gắn handler cho root logger — trước đó chưa ai gọi `basicConfig`, nên Python dùng handler "cứu hộ" chỉ in từ WARNING trở lên và `logger.info` biến mất không dấu vết. Nhân tiện hạ `httpx` xuống WARNING: nó log một dòng INFO mỗi request, mà Agent poll Prometheus vài giây một lần.

**Cài `rules.py` — và phát hiện thêm một mức severity chết.** Stub bảo `detect()` chặn ở `P95_THRESHOLD_SECONDS = 2.0`. Nhưng 2.0 là ngưỡng của **P2**, nên mọi tín hiệu lọt qua cửa đó đều đã từ P2 trở lên, và **P3 với P4 trong bảng contract ① vĩnh viễn không đạt tới được**. Cùng loại lỗi với bucket mặc định hôm 29/07 — bảng có 4 mức, thực tế dùng được 2 — chỉ khác là lần này nằm trong Python thay vì PromQL. Sửa: cửa `detect` hạ xuống ngưỡng P3 (thấp nhất), và thêm `BASELINE_DEVIATION_RATIO = 2.0` làm đường vào cho P4 ("lệch baseline nhưng chưa vượt ngưỡng cứng") — không có nó thì P4 nằm trong bảng mà không có cách nào chạm tới. Có test `test_moi_muc_severity_deu_dat_toi_duoc` gác lại, để lần sau ai đổi ngưỡng mà làm chết một mức thì CI đỏ.

Rule engine cũng **từ chối NaN bằng `ValueError`** thay vì cho qua. Đây là lớp thứ hai sau `PrometheusClient`: NaN không làm chương trình chết, nó làm `classify_severity` tụt xuống P4 vì `NaN > x` luôn False — một sự cố P1 bị xếp thành nhẹ nhất mà không có dấu hiệu gì.

`classify_auth_burst` (UC-3) đi nhánh riêng, không dùng chung bảng với UC-1: burst credential-stuffing xảy ra khi hệ thống **hoàn toàn khoẻ**, nên severity dựa trên số tuyệt đối request/giây. Có test chứng minh cùng bộ số liệu đó `detect()` trả `None` còn `classify_auth_burst()` trả P1 — nếu hai nhánh dùng chung ngưỡng thì Agent sẽ kết luận "service quá tải" thay vì "vấn đề bảo mật", và theo use-cases.md thì đó là chẩn đoán SAI.

**Ba node đầu của graph, và Agent đã chạy thật.** `detect` → `classify_severity` → `open_war_room`, nối trong `src/agents/incident_graph.py` (tách khỏi `graph.py` của template).

Mảnh thiết kế phải giải trước khi viết `detect`: quy tắc "vượt ngưỡng liên tục ≥ 30s" bắc qua **nhiều vòng poll**, mà state của LangGraph chỉ sống trong một lần chạy graph. Nếu không có chỗ nhớ riêng thì `breached_for_seconds` luôn bằng 0 và quy tắc chống nhiễu quan trọng nhất trở thành vô hiệu. Giải bằng `BreachTracker` — một object sống ở module, nhớ mốc bắt đầu vượt ngưỡng của từng service, và **xoá mốc khi service hồi phục** để hai sự cố cách nhau một tiếng không bị cộng dồn thành một.

`detect` **không hardcode danh sách service**: Prometheus trả mỗi service một series nên service nào có traffic thì tự xuất hiện. Thêm service mới chỉ cần sửa `prometheus.yml`, không đụng code Agent.

`classify_severity` thoạt nhìn thừa vì `rules.detect()` đã gán severity rồi. Nhưng nó gán dựa trên **một** service, mà contract ① có vế "≥ 2 service bị ảnh hưởng → P1" — vế đó chỉ nhìn thấy khi đã có đủ tín hiệu cả vòng poll. Hai service mỗi cái p95 = 3s, xét riêng đều là P2; xét cùng nhau là P1.

Chạy thật trên Prometheus + `loadgen` xác nhận **cả hai quy tắc chống nhiễu**: ba vòng poll đầu đã thấy vượt ngưỡng nhưng chưa đủ 30s nên không mở incident; vòng thứ tư (32s liên tục) mở `INC-1`; ba vòng sau dùng lại `INC-1` thay vì tạo trùng. Severity P3 đúng theo số đo, vì p95 = 1.90s còn dưới ngưỡng P2.

---

## 2026-08-02

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| Trương Công Thái Đức | Rà yêu cầu nộp Gate 1 của BTC, đối chiếu với repo → thiếu 3 tài liệu | ✅ Done | Brief, PRD, UI Flow chưa có; kiến trúc/README/AI log hook đã đủ | - |
| Trương Công Thái Đức | Viết Project Brief — vấn đề, người dùng, phạm vi, 6 chỉ số thành công, ràng buộc, rủi ro | ✅ Done | `docs/brief.md` | - |
| Trương Công Thái Đức | Viết PRD — 8 user story, 16 yêu cầu chức năng kèm tiêu chí nghiệm thu, 12 NFR, kế hoạch phát hành R0–R5 | ✅ Done | `docs/prd.md` | - |
| Trương Công Thái Đức | Viết UI Flow + wireframe 2 trang Streamlit, ghi rõ lý do war room không có nút duyệt | ✅ Done | `docs/ui-flow.md` | - |
| Trương Công Thái Đức | Thêm bảng "Tài liệu nộp" đầu README — mentor mở repo là thấy link, không phải đi tìm | ✅ Done | `README.md` | - |
| Trương Công Thái Đức *(viết hộ Việt, Việt vắng)* | Node `detect` — đọc Prometheus, đo thời lượng bất thường không cần giữ state, gọi `rules.detect()` | ✅ Done | `src/agents/nodes/detect.py` | - |
| Trương Công Thái Đức *(viết hộ Việt)* | Node `open_war_room` + vòng lặp quét + CLI chạy Agent | ✅ Done | `src/agents/nodes/open_war_room.py`, `src/agents/detection_loop.py`, `scripts/run_agent.py` | - |
| Trương Công Thái Đức | 15 test cho chuỗi detect, gồm test canh chính bộ nhận diện PromQL của fake | ✅ Done | `tests/test_agents/test_detection.py` — 133/133 pass | - |
| Trương Công Thái Đức | Đo thật trên stack demo: load test **không** tạo được sự cố latency, OOM **không** sinh 5xx nào | ⚠️ Blocker cho Việt | Số liệu ở dưới | - |

**Tổng kết ngày:** Bổ sung 3 tài liệu Gate 1 còn thiếu. Ba chỗ đáng ghi lại vì chúng lộ ra khi viết chứ không phải khi code:

**Chỉ số M3 (độ chính xác chẩn đoán) chỉ đo được nhờ ground truth đã chốt trước.** `use-cases.md` viết xong ngày 30/07, trước khi Việt viết `rules.py`. Nếu làm ngược lại — chạy Agent rồi mới ghi "nguyên nhân gốc là gì" — thì con số sẽ tự khớp 3/3 và không đo gì cả. Thứ tự ở đây là toàn bộ giá trị của phép đo.

**Ba rủi ro trong brief đều là rủi ro "fail âm thầm".** Metric lệch tên → Prometheus trả rỗng chứ không lỗi. Rollback chỉ ghi log → `verify` không hồi phục → vòng lặp vô hạn giữa buổi demo. Agent mở incident trùng khi load test → war room thành rác. Cùng một họ với `setup_hooks.sh` tuần trước: không có exception nào để lần theo, nên phải chặn bằng tiêu chí nghiệm thu viết sẵn chứ không bằng việc nhớ ra lúc test.

**Viết UI flow mới thấy phải nói rõ vì sao war room không có nút duyệt.** Người đọc mặc định coi đó là thiếu sót. Thật ra một nút duyệt trong Streamlit sẽ tạo đường thứ hai tới `execute_remediation` — mà FR-08 đòi mọi đường phải qua `assert_human_approved()`, và cổng đó xác minh danh tính bằng changelog Jira, cần một transition có tác giả thật. Streamlit không có đăng nhập nên nút đó là đường vòng qua cổng. Quyết định này đã nằm trong code từ đầu, nhưng chưa ở đâu ghi lý do — người review sẽ đọc là quên làm.

### Chiều: viết hộ Việt phần `detect`

Việt vắng, mà `src/agents/nodes/` mới chỉ có `example_node.py` của template — tức là `prometheus.py` và `rules.py` Việt viết xong tuần này vẫn chưa có ai gọi. Viết ba mảnh nối chúng lại: `detect` (đọc → quyết định), `open_war_room` (mở Jira, chống mở trùng), và một vòng lặp tuần tự tối thiểu. **Chưa phải LangGraph** — cố ý, để Việt về dựng state machine mà không phải gỡ thứ tôi làm dở.

**Đo thời lượng bất thường không giữ state.** `rules.detect()` cần `breached_for_seconds`, mà Agent thì poll theo chu kỳ. Giữ mốc bắt đầu trong RAM là cách dễ nghĩ nhất nhưng sai ba chỗ: restart là mất, chạy nhiều instance thì mỗi con một số, và test phải giả lập thời gian. Thay vào đó hỏi thẳng Prometheus — `min_over_time(p95[30s])` mà vẫn trên ngưỡng nghĩa là suốt 30 giây đó chưa lúc nào tụt xuống. Thử 4 cửa sổ (30/60/120/300s) rồi lấy cửa sổ lớn nhất còn thoả.

**Lỗi của chính tôi, tìm ra bằng cách đọc lại `rules.detect()` chứ không phải bằng test.** Bản đầu chỉ đo thời lượng theo p95. Nhưng cửa 1 của `detect()` (`breached_for_seconds >= 30`) chặn **trước** cả ba đường của cửa 2. Hệ quả: sự cố nào không làm chậm latency thì `breached_for_seconds` luôn bằng 0, và **đường error-rate cùng đường lệch baseline vĩnh viễn không với tới được** — tức là toàn bộ UC-2. Đúng cùng một họ lỗi mà Việt đã ghi trong docstring `rules.detect()` và tôi mắc trong bucket hôm 29/07: bảng có nhiều nhánh, thực tế chạy được một. **Cửa lọc "đủ lâu" phải đo đúng cái điều kiện mà nó đang lọc.** Sửa: đo cả ba đường, lấy cửa sổ lớn nhất trong ba.

**Fake trong test sai hai lần liên tiếp, mà test vẫn xanh cả hai lần.** Bộ nhận diện câu PromQL của fake phân loại theo chuỗi đặc trưng. Lần một: xét `http_requests_total` trước → nhận nhầm mọi câu p95 thành câu error, vì `P95_LATENCY` có chứa `http_requests_total` — đó là bộ lọc `_HAS_TRAFFIC` chống NaN của Việt. Lần hai: xét "có chứa `histogram_quantile`" → nhận nhầm baseline thành câu đo lệch, vì `P95_BASELINE_30M` bọc một `histogram_quantile` bên trong. Cả hai lần test vẫn pass, chỉ là **pass vì lý do khác** — `NGHEN` có error 12% nên vẫn ra P2, đúng con số tôi assert. Đã thêm `test_fake_phan_loai_dung_tung_cau_promql` canh chính cái fake. Test giả mà sai thì cả file test thành vô nghĩa, và nó không đỏ để báo.

### Đo thật trên stack demo — hai chỗ demo không tái hiện được sự cố

Chạy `docker compose -f docker-compose.demo.yml up` + `demo/seed.py` + `demo/loadtest.py` để xem Agent có tự mở issue không. **Không mở.** Đào ra hai chuyện, cả hai đều là chuyện thật của demo chứ không phải của detect:

**1. Load test không tạo được sự cố latency.** `loadtest.py` in ra `p95: 0.585s` ở bậc 200 concurrent, nhưng đó là **p95 đo phía client**. Server-side Prometheus đọc **0,048s** suốt cả 5 bậc, và histogram cho thấy 35.202/35.650 request xong dưới 50ms — service không hề chậm. Đã loại trừ từng nghi vấn:

| Thử | rps đạt được | p95 server-side |
|-----|--------------|-----------------|
| `demo/loadtest.py` (200 concurrent, từ host) | 294 | 0,048s |
| Bỏ hàng rào `gather`+`sleep`, nâng `max_connections` (từ host) | 294 | 0,050s |
| 150 worker liên tục, chạy **trong** mạng compose | 421 | 0,048s |

Trần ~294 rps từ host là port-forward của Docker Desktop trên macOS; vào trong mạng thì lên 421 rps và trần mới là uvicorn một worker. Nhưng p95 server-side **không nhúc nhích ở cả ba lần**, và `db_pool_connections_in_use` chỉ bằng 1 — pool 5 connection chưa bao giờ là nút thắt vì mỗi query xong trong ~3ms. Xếp hàng xảy ra ở socket backlog, **trước khi** ASGI app nhìn thấy request, nên histogram không đo được. Kết luận: câu TODO trong `loadtest.py` — "ghi lại mức tải làm p95 vượt 2s" — trên máy này **không có mức tải nào làm được**. Muốn UC-1 tái hiện thì phải làm việc trong `/pay` nặng lên, không phải bắn thêm tải.

**2. OOM không sinh ra 5xx nào cả.** Gọi `/pay/batch` liên tục: `RestartCount` lên **7**, container chết và restart thật. Nhưng `http_requests_total{status=~"5.."}` **bằng 0 tuyệt đối** — process chết giữa request nên không kịp ghi metric, và counter trong process reset sạch sau restart. Tức là UC-2 hiện **không thể phát hiện được** bằng error-rate, dù `rules.detect()` có đường cho nó.

Prometheus vẫn thấy sự cố, chỉ là bằng metric khác: `min_over_time(up[5m])` = **0**, và `changes(process_start_time_seconds[10m])` = **3**. Hai tín hiệu này có sẵn miễn phí, không cần service làm gì thêm. Nhưng nhận chúng thì phải thêm tham số vào `rules.detect()` — đó là chữ ký hàm của Việt, nên để Việt quyết chứ tôi không tự đổi. Đây là việc đầu tiên Việt cần xem khi về.

**Chuyện nhỏ dọc đường:** máy tôi có Postgres native chiếm sẵn cổng 5432 nên compose không lên được. Đổi thành `${DEMO_POSTGRES_PORT:-5432}` — mặc định giữ nguyên nên cả nhóm không bị ảnh hưởng, ai trùng cổng thì set biến môi trường.

---

**Việt (tối 02/08) — gỡ conflict và nối lại phần lan truyền.**

Sáng 02/08 tôi cũng viết `detect` + `open_war_room` + graph LangGraph (`e4488ee`) nhưng **không push**, nên Đức không thấy và viết bản của mình lúc tối. Lỗi ở tôi: hôm 01/08 đã tự xếp "3 commit chưa push" là mục số 1 trong danh sách rà lỗi rồi vẫn để đó. Hai bản viết song song, và lúc merge `develop` vào `viet` thì branch vỡ — `detect.py` thành bản Đức trong khi `incident_graph.py` và 2 file test của tôi vẫn gọi `BreachTracker`, `detect_node`.

Giữ bản Đức, bỏ bản mình. Cách đo `breached_for_seconds` bằng `min_over_time` **đúng hơn** `BreachTracker` của tôi ở cả ba điểm Đức nêu: restart mất state, nhiều instance mỗi con một số, test phải giả lập thời gian. Xoá `incident_graph.py`, `test_detect.py`, `test_incident_graph.py` — khôi phục được từ `e4488ee` khi dựng state machine.

Port sang phần bản Đức chưa có: **`escalate_spreading()`**. `rules.detect()` gán severity dựa trên *một* service, còn vế "≥ 2 service bị ảnh hưởng → P1" của contract ① chỉ thấy được khi nhìn cả vòng quét — hai service mỗi cái p95 = 3s, xét riêng đều P2, xét cùng nhau là P1. Trước đó `is_spreading()` viết xong từ 01/08 nhưng **chưa chỗ nào gọi**, tức luật lan truyền đang là code chết.

Gọi trong `run_cycle()` **trước** `open_war_room` — severity đi vào tiêu đề issue lúc tạo, nâng sau khi tạo thì tiêu đề mang mức sai. Vẫn mở **một war room cho mỗi service** như thiết kế của Đức, không gộp: đúng mẫu INC-12/INC-13 trong fixture, việc nối là của `link_incidents`.

⚠️ **Mâu thuẫn contract cần Đức chốt:** contract ① ghi "≥ 2 service bị ảnh hưởng → P1", nhưng `fixtures/incidents.json` lại có INC-12 (P2) và INC-13 (P3) nối với nhau — hai service dính mà không cái nào P1. Tôi làm theo chữ trong contract ①. Nếu Đức muốn theo fixture (hiểu "≥ 2 service" là `affected_services` của **một** incident có 2 phần tử) thì sửa một dòng.

**Bug mới, ảnh hưởng cả Trung:** `pip install -r demo/requirements.txt` **fail trên Windows** — pip đọc file bằng cp1252 mà file có comment tiếng Việt, `UnicodeDecodeError: 'charmap' codec can't decode byte 0x8d`. CI chạy Linux nên xanh. Vá tạm bằng `PYTHONUTF8=1 pip install -r demo/requirements.txt`; nên bỏ dấu khỏi file hoặc ghi cách này vào README.

142 test pass, ruff sạch.

---

<!-- Format: copy block trên cho mỗi ngày làm việc -->
