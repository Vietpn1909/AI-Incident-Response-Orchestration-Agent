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

**Rà toàn bộ bẫy Windows — 3/4 thành viên dùng Windows, chỉ Đức dùng macOS.**

Kiểm tra: không còn conflict marker, working tree sạch, 142 test pass, `.gitattributes` khớp với line ending thực tế trên đĩa (`git add --renormalize` không sinh thay đổi nào), `.sh` là LF, `.cmd`/`.ps1` là CRLF, mọi `open()` đều có `encoding=` hoặc dùng chế độ nhị phân.

Nhưng tìm ra **ba lỗi chỉ xảy ra trên Windows**, CI chạy Linux nên xanh hết:

1. **`scripts/run_agent.py` — điểm khởi chạy Agent — chết ngay `--help`.** `configure_logging()` được gọi *sau* `parse_args()`, mà argparse in help và thông báo lỗi tham số thẳng ra stdout ngay trong `parse_args()`. Console Windows là CP1252 nên `UnicodeEncodeError: can't encode character 'ệ'` — chết hẳn, không phải in ra chữ xấu. Tách `force_utf8_console()` khỏi `configure_logging()` và gọi trước `parse_args()`.
2. **`demo/loadtest.py` chết ngay dòng output đầu tiên** trên Windows — cùng nguyên nhân. Đây là script của Trung mà Trung cũng dùng Windows. `demo/attack.py` đã có cách vá đúng từ trước, chỉ `loadtest.py` và `seed.py` thiếu; áp cùng cách để `demo/` vẫn độc lập, không import `src`.
3. **`scripts/verify_e2e.py`** cùng lỗi, đã vá.

Cộng thêm lỗi `pip install -r demo/requirements.txt` fail trên Windows (ghi ở trên) — bốn lỗi cùng một họ: **file và luồng ra mặc định CP1252 gặp nội dung tiếng Việt**. Đội viết tài liệu và log bằng tiếng Việt nên bẫy này sẽ còn lặp lại; quy ước nên là mọi script có `print`/`argparse` tiếng Việt đều ép UTF-8 ở dòng đầu của `main()`.

**Chạy trọn chuỗi trên Windows để xác nhận:** `docker compose -f docker-compose.demo.yml up` → 2 target Prometheus UP → `seed.py` 3000 orders + 5000 payments → `loadtest.py` in tiếng Việt bình thường → `run_agent.py --fake --once` chạy sạch, báo "Vòng 1: bình thường" (đúng, vì UC-1 chưa tái hiện được như Đức đã ghi).

**Một khác biệt máy nữa:** Windows của tôi có Postgres native chiếm sẵn 5432 giống hệt máy Đức, nên `seed.py` nối nhầm vào đó và fail `InvalidPasswordError`. Đường vá `DEMO_POSTGRES_PORT` Đức thêm hôm nay **chạy đúng**, đã verify:

```bash
DEMO_POSTGRES_PORT=55432 docker compose -f docker-compose.demo.yml up -d
DATABASE_URL=postgresql://demo:demo@localhost:55432/demo python demo/seed.py
```

---

## 2026-08-04

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| Trương Công Thái Đức | Review + đo độc lập PR #13 (Việt) và PR #14 (Trung), merge cả hai | ✅ Done | `develop` = `95eb539`, CI xanh | - |
| Trương Công Thái Đức | Review PR #15 (`hypothesize`) — chạy thật với LLM thật trên stack demo | ✅ Done | Xác nhận LLM tuân ràng buộc prompt | - |
| Trương Công Thái Đức | Tìm ra `DATABASE_URL` vẫn là placeholder của template → `correlate_deploy` chết âm thầm | ✅ Done | `src/config.py`, `.env.example`, `demo/README.md` | - |
| Trương Công Thái Đức | Test gác `DATABASE_URL`, đã mutation-test | ✅ Done | `tests/test_services/test_deploys_config.py` — 205 test pass | - |
| Trương Công Thái Đức | CI bị chặn vì org hết hạn mức Actions → chuyển sang self-hosted runner của BTC | ✅ Done | `.github/workflows/ci.yml`, run `30920675914` xanh | - |
| Trương Công Thái Đức | Node `propose_remediation` + `services/runbooks.py` — nối cổng HITL vào luồng Agent | ✅ Done | 21 test mới, 226 test pass; verify trên Jira thật (KAN-6) | - |
| Trương Công Thái Đức | Node `escalate` + nới contract ③ (`get_transition_time`, `set_severity`) | ✅ Done | 8 test mới, 234 test pass | - |

**Tổng kết ngày:** Hai PR của Việt và Trung đưa dự án qua mốc lớn nhất từ đầu: **cả 3 use case đều phát hiện được, và Agent đã có LLM trong luồng chạy**. Đo lại độc lập từng cái thay vì tin số người khai.

**PR #14 (Trung) — UC-1 cuối cùng tái hiện được.** Cách sửa đúng nguyên tắc: `pg_sleep(0.2)` đặt **bên trong** `pool.acquire()` nên request giữ connection Postgres thật; đặt ngoài pool thì chỉ làm handler chậm chứ không tạo được bằng chứng pool cạn. Dựng lại stack đo trên macOS: p95 server-side **3,93s** (trước 0,048s), đỉnh pool **5/5**, một request đơn lẻ 0,225s. Trung đo trên Windows ra 4,06s — lệch do khác máy, cùng độ lớn.

**PR #15 (Việt) — `hypothesize`, và `llm.py` lần đầu được gọi sau 8 ngày nằm không.** Thiết kế hai pha: `rules.build_hypothesis()` dựng `evidence` + `confidence` + một `statement` dự phòng (tất định, không mạng), rồi LLM viết lại `statement` và thêm `reasoning`. Pha 2 hỏng thì giả thuyết vẫn giữ nguyên giá trị chấm điểm — DashScope hết quota giữa buổi demo là chuyện có thật.

Chạy thật với `qwen-plus`, LLM tuân đúng cả ba ràng buộc khó nhất trong prompt: chỉ dùng số có trong phần bằng chứng, không tự nhận độ tin cậy, và **viết "trùng thời gian với deploy v1.4.2" chứ không viết "do deploy gây ra"** — đúng luật số 4. Đây là chỗ dễ mất điểm nhất nếu buông: một Agent in ra đoạn văn nghe hay mà không truy ngược được về số liệu nào thì là chatbot, không phải công cụ vận hành.

**Lỗi tìm được, thuộc đúng họ "fail âm thầm" mà JOURNAL đã ghi ba lần: `DATABASE_URL` chưa ai sửa khỏi placeholder của template.** Biến này chỉ có `services/deploys.py` đọc, tức nó **là** DB lịch sử deploy chứ không phải database của app. Mặc định template là `sqlite:///./data/app.db` mà `asyncpg` không parse nổi, còn `.env.example` là `postgresql://user:password@localhost:5432/dbname`. Nên trên **mọi máy mới clone**, `correlate_deploy` không bao giờ chạy — `deploys.py` bắt lỗi và chỉ log một dòng warning.

Hệ quả đo được trên cùng một sự cố:

| | `DATABASE_URL` sai | `DATABASE_URL` đúng |
|---|---|---|
| Độ tin cậy | **40%** | **90%** |
| `related_deploy` | *(không có)* | **v1.4.2** |
| LLM nhắc tới deploy | không | "trùng thời gian với deploy v1.4.2" |

Mất hơn nửa độ tin cậy và mất hẳn nghi phạm `v1.4.2` — thứ mà `demo/seed.py` cắm sẵn làm linh hồn của UC-1. Không có exception nào để lần theo. Đã sửa mặc định trong `config.py`, sửa `.env.example`, ghi cảnh báo vào `demo/README.md`, và thêm test gác.

**Test gác của tôi ban đầu cũng sai, theo đúng cách tôi vừa cảnh báo Việt.** Bản đầu assert trên `Settings().database_url` — mà `pydantic-settings` đọc `.env`, nên nó đỏ trên máy có `.env` và xanh trên CI (không có `.env`). Xanh đỏ theo máy chứ không theo code, vô dụng làm cổng gác. Sửa thành đọc `Settings.model_fields[...].default`, rồi mutation-test: đặt lại placeholder → 2 test đỏ, khôi phục → xanh.

### Chiều: CI bị chặn ở tầng thanh toán, rồi chuyển sang runner của BTC

Org hết hạn mức 2.000 phút/tháng của GitHub Actions. Job bị chặn **trước khi khởi động** — không phải lỗi code. Ba dấu hiệu phân biệt, đáng ghi lại vì lần sau gặp sẽ nhận ra ngay:

1. Lần chạy đỏ chỉ **10 giây**, trong khi bình thường 31–49 giây — chưa kịp cài dependency
2. `gh run view --log-failed` trả `log not found` — không có gì được chạy để ghi log
3. Dòng ANNOTATIONS ghi thẳng `"The job was not started because recent account payments have failed or your spending limit needs to be increased"`

Mức dùng của nhóm, tách theo workflow:

| Workflow | Số lần | Tổng thời gian | Trung bình |
|---|---:|---:|---:|
| CI (lint + test) | 72 | 2.241s | 31s |
| Running Copilot Code Review | 7 | 1.349s | **192s** |

Tổng phút bị tính khoảng **100 / 2.000**, tức 5%. Cohort 3 có 35+ đề dùng chung quota nên đây là tổng của tất cả các nhóm, không phải một nhóm lạm dụng. Đáng chú ý: Copilot Code Review chỉ chạy 7 lần mà đốt gần nửa số giây của 72 lần CI — mỗi lượt tốn **6 lần** một lượt CI. Nếu phải tiết giảm thì tắt cái đó trước, không phải tắt CI.

**Cách BTC đưa ra: đổi `runs-on: ubuntu-latest` thành `runs-on: self-hosted`.** Chỉ đổi đúng một dòng, cố ý không tinh chỉnh gì thêm — lo ngại ban đầu của tôi là runner dùng chung giữa các team thì `pip install` đi vào Python hệ thống là rủi ro hai chiều, nhưng thay vì đoán trước rồi thêm venv, cứ chạy một lần rồi đọc log.

Đọc log thấy lo ngại đó không có cơ sở: runner tên `eph-vmrunner-8dbd4adc`, đường dẫn `/home/gh-runner/eph/8dbd4adc/` — **`eph` là ephemeral**, mỗi job một VM mới. Không cần venv. Đây là lần thứ hai trong ngày việc đo trước khi sửa tiết kiệm được một thay đổi vô ích.

Kiểm chứng chạy thật chứ không tin dấu ✅: đếm được **205 dòng `PASSED`** trong log, đúng bằng số test local. Một CI "xanh" mà bỏ qua test thì tệ hơn CI đỏ.

Giá phải trả: **2m49s** thay vì 31s. Runner không có sẵn tool cache nên `setup-python` phải tải Python 3.11.15 về mỗi lần, cộng thời gian xếp hàng FIFO với các team khác. Chấp nhận được — chậm hơn 5 lần nhưng vẫn còn cổng gác.

### Tối: `propose_remediation` — cổng HITL cuối cùng nằm trong luồng Agent

Trước hôm nay Agent chẩn đoán được nguyên nhân rồi **dừng**. Cổng HITL đã verify chạy thật trên Jira từ 01/08 (KAN-11), nhưng việc chuyển issue sang `Awaiting Approval` do [`scripts/verify_e2e.py`](scripts/verify_e2e.py) làm **bằng tay** — nên cổng tồn tại mà chưa bao giờ nằm trên đường đi của Agent. Node này đóng chỗ hở đó.

**Quyết định đi chệch tài liệu, đã ghi lý do vào `docs/architecture_diagram.md`: LLM không chọn runbook.** Sơ đồ kiến trúc viết từ 28/07 rằng *"LLM chỉ chuyển bằng chứng thành lời giải thích và chọn runbook"*. Tôi bỏ phần chọn runbook khỏi vai của LLM, vì `action` không phải câu văn — nó là thứ **được thi hành lên production**, và chênh giữa `rollback` với `block_ip` là chênh giữa hạ một phiên bản và chặn truy cập của người dùng thật. Docstring `remediation.SUPPORTED_ACTIONS` vốn đã ghi lý do có danh sách trắng là *"tránh việc LLM sinh ra một `action` lạ rồi backend thi hành mù"* — nhưng cho LLM chọn **trong** danh sách trắng thì vẫn là LLM quyết định làm gì lên production, chỉ khác là bị giới hạn phạm vi. Ranh giới bây giờ: **LLM diễn giải, luật đề xuất, người duyệt.**

Bảng chọn hành động ở `services/runbooks.py`, thứ tự xét là **UC-3 → UC-2 → UC-1**, khớp `detect.py::_one_per_service` nhưng vì lý do khác: một vụ credential-stuffing xảy ra đúng lúc vừa deploy thì rollback không chặn được cuộc tấn công, chỉ mất thời gian và thêm một lần đổi phiên bản vô ích giữa lúc đang có sự cố.

Ba chỗ chọn cách "nói thật thay vì im lặng":

- **UC-2 không có deploy → `scale_up`, và `risk` ghi rõ đây là GIẢM NHẸ.** Service chết vì hết RAM thì cách đúng là tăng `mem_limit` hoặc sửa rò rỉ — cả hai **không** nằm trong `SUPPORTED_ACTIONS`. Đề xuất một phương án không sửa gốc mà không nói ra là để người duyệt tưởng đã xử lý xong.
- **UC-3 không chọn `block_ip` dù nó nằm trong danh sách trắng**, vì Agent chưa thu thập IP nguồn — chọn nó lúc này là chặn mù.
- **Không biết rollback về đâu thì không đề xuất rollback.** `_phien_ban_truoc()` trả `None` thì rơi sang `increase_pool`. Để `remediation._describe()` điền "phiên bản trước" là đẩy việc đoán xuống lúc thi hành.

**Test canh chuỗi tên bằng chứng, đúng bài học sáng nay.** `runbooks.py` phân nhánh theo tên `MetricEvidence`, mà tên đó là chuỗi literal trong `rules.py` của Việt. Việt sửa một chữ là chỗ này lặng lẽ không nhận ra use case nữa rồi **mọi** sự cố rơi vào nhánh mặc định `scale_up` — sai hành động lên production mà không có gì đỏ lên. Nên `test_ten_bang_chung_con_khop_voi_rules` gọi thẳng `rules.detect*()` rồi đối chiếu, không hardcode kỳ vọng ở hai nơi.

**Verify trên Jira thật, không chỉ FakeJira.** Lần chạy đầu với `RealJiraClient` đi vào nhánh "cập nhật KAN-6 đã mở" nên `propose_remediation` **không chạy** — đúng thiết kế, nhưng nghĩa là chưa kiểm được thứ đáng lo nhất: tên transition `Awaiting Approval` có tồn tại trên board thật không. Gọi thẳng vào KAN-6 thì cả ba chỗ đều đúng:

```
lịch sử deploy đọc được : ['v1.4.2', 'v1.4.1']            ← Postgres thật
đề xuất                 : rollback → to_version=v1.4.1     ← đúng bản NGAY TRƯỚC
trạng thái KAN-6        : Remediating → Awaiting Approval  ← transition có trên board
```

Chuỗi đầy đủ chạy một lần không script tay: `detect` (p95 3,481s, vượt liên tục 60s) → `open_war_room` → `hypothesize` (90%, "pool cạn kiệt") → `runbooks` (rollback v1.4.2 → v1.4.1) → `propose_remediation` → **dừng, chờ người**.

Graph kết thúc ở đây là **cố ý**, không phải chuỗi làm dở: bước tiếp theo do người khởi động, và Agent tự chuyển sang `Remediating` thì `assert_human_approved()` so `accountId` thấy trùng account Agent rồi tự khoá chính nó khỏi bước thi hành. Cổng không dựa vào việc Agent ngoan.

### `escalate` — cổng HITL là điểm chết đơn lẻ

Cổng phê duyệt là điểm mạnh của thiết kế, nhưng nó cũng có mặt kia: người trực đi ngủ, không thấy thông báo, hoặc đang xử lý việc khác thì đề xuất nằm im trong `Awaiting Approval` trong khi sự cố vẫn diễn ra. `escalate` nâng mức từng bậc (P4→P3→P2→P1, không nhảy thẳng — nhảy thẳng thì mọi thứ treo đều thành P1 và mức độ mất ý nghĩa phân loại) và ghi rõ đã treo bao lâu.

**Giới hạn phải nói ra, đã ghi trong docstring:** sơ đồ kiến trúc viết *"tăng severity, thông báo"*, nhưng phần **thông báo** hiện chưa làm được — đội không có PagerDuty, Slack webhook hay bất cứ kênh gọi người nào. Nâng mức trên Jira chỉ có tác dụng nếu có người đang xem board. Không giả vờ node này gọi được người dậy.

Phải nới contract ③ hai hàm, và cả hai đều có bẫy:

- **`get_transition_time()`** — cần biết đã treo bao lâu. Đọc từ changelog thay vì Agent tự ghi nhớ, vì **người trực có thể tự chuyển trạng thái trên UI** mà Agent không hề biết. Gộp chung một lượt đi changelog với `get_transition_author()`: tách hai hàm mỗi hàm tự phân trang là gọi Jira API gấp đôi cho cùng dữ liệu, mà quan trọng hơn là tác giả và thời điểm **phải lấy từ cùng một entry** — không thì khi có nhiều lần chuyển sang cùng trạng thái, cổng HITL sẽ nói "người X duyệt" kèm mốc của một lần chuyển khác.
- **`set_severity()`** — mức độ nằm ở **hai chỗ**: label `severity-P2` và tiền tố `[P2]` trong tiêu đề. Sửa một chỗ thì `severity_from_labels()` và mắt người đọc board nói hai điều khác nhau. Hai helper `replace_severity_label()` / `retitle_severity()` đặt trong `mapping.py` để hiểu biết về định dạng label nằm đúng một chỗ.

**Lỗi tìm được nhờ test, và nó là lỗi chỉ xuất hiện trên một trong hai bản cài đặt.** Bản đầu đọc `incident.severity` **sau** khi gọi `set_severity()`. `FakeJiraClient` sửa thẳng vào object nó đang giữ, còn `RealJiraClient` thì `get_incident()` trả object mới đọc từ API — nên cùng một dòng code cho ra mức MỚI trên bản giả và mức CŨ trên bản thật. Hệ quả thấy được: comment post lên war room ghi **"Nâng mức P2 → P2"**. Sửa bằng cách chốt `muc_cu` vào biến trước khi gọi. Đây là loại lỗi mà chỉ đọc code khó thấy, vì nó phụ thuộc vào việc bản cài đặt nào trả object dùng chung.

**Test quan trọng nhất là `test_khong_bao_gio_tu_duyet_thay_nguoi`.** `escalate` sinh ra vì cổng HITL là điểm chết đơn lẻ, nên nó chính là chỗ dễ bị "cải tiến" thành *tự duyệt sau X phút* nhất. Test đó nâng mức 5 lần liên tiếp với mốc thời gian gấp 100 lần ngưỡng, rồi chốt lại: issue vẫn ở `Awaiting Approval`, `assert_human_approved()` vẫn ném `ApprovalError`, và Agent không hề tự chuyển sang `Remediating`. Nâng mức KHÔNG kèm quyền thi hành.

---

## 2026-08-05

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| Trương Công Thái Đức | Việt phản ánh dự án sinh nhiều image Docker → truy nguyên và sửa | ✅ Done | `docker-compose.demo.yml` — 714MB → 357MB | - |
| Trương Công Thái Đức | Node `propose_remediation` + `escalate`, nối cổng HITL vào luồng Agent | ✅ Done | verify trên Jira thật (KAN-6) | - |
| Trương Công Thái Đức | Review + merge PR #16 (Long) và #17 (Trung) | ✅ Done | phát hiện 2 lỗi lúc ghép, đã vá | - |
| Trương Công Thái Đức | Gỡ 2 endpoint template khỏi URL công khai, thay bằng `/api/v1/agent/health` | ✅ Done | `src/api/routes.py` — 236 test pass | - |

**Tổng kết ngày:** Việt phản ánh dự án "không thống nhất nên sinh nhiều image Docker". Đo lại thì **Việt đúng về sự thật, sai về nguyên nhân** — và cách sửa hiển nhiên lại làm hỏng thứ khác.

**Không phải do cấu hình không thống nhất.** `docker-compose.demo.yml` có `name: p035-demo` từ commit đầu tiên (`ac96ed9`, 29/07), và cả ba nhánh `trung`/`viet`/`develop` đều có dòng đó — nên compose luôn dùng đúng một project name trên mọi máy. Ba image lạ trên máy tôi (`p035pr9`, `p035rev2`, `p035review`, 357MB mỗi cái) là do **tôi tự đặt `-p`** khi review PR song song để không giết stack đang chạy, rồi không dọn. Đó là rác của riêng tôi, và image Docker là local nên không thể sang máy Việt.

**Nhưng có một chuyện thật, và nó có trên máy của cả bốn người.** `service-thanh-toan` và `service-dat-hang` cùng build từ `./demo` với cùng `Dockerfile`, khác nhau **chỉ ở `command` lúc chạy**. Compose không biết điều đó nên sinh hai tên image theo từng service và build hai lần. Đo bằng layer digest: hai image **trùng hoàn toàn** — 714MB cho thứ 357MB là đủ, cộng gấp đôi thời gian build.

**Cách sửa hiển nhiên thì sai.** Cho cả hai service cùng `image: p035-demo-service:latest` và giữ `build:` ở cả hai → hai build song song tranh nhau đặt cùng một tag, buildx báo `ERROR: image "...": already exists` và **`docker compose build` exit 1**. Image vẫn ra nhưng lệnh coi như thất bại — đủ để làm đỏ CI hoặc bất cứ script nào kiểm exit code. Nếu chỉ đọc log rồi thấy image đúng 357MB là đã kết luận xong thì đã đẩy một lệnh fail vào repo.

**Cách đúng:** chỉ `service-thanh-toan` có `build:`, `service-dat-hang` dùng lại `image:` đó kèm `pull_policy: never` (image chỉ tồn tại local, không được hỏi registry). Verify trên tình huống **máy mới clone** — xoá sạch image rồi chạy `up -d` **không kèm** `--build`:

```
up exit: 0                          image: 1 × 357MB
thanh-toan:200  dat-hang:200  prometheus:200
Prometheus targets: service-thanh-toan up · service-dat-hang up
```

Compose tự build một lần rồi service thứ hai dùng lại, không cần ai nhớ thêm cờ nào.

**Bài học lặp lại lần thứ năm trong tuần:** phản ánh của người dùng đúng về triệu chứng nhưng lệch về nguyên nhân, và nếu tin nguyên nhân họ nêu thì sẽ đi sửa cấu hình project name — thứ vốn đã đúng từ đầu. Phải đo mới ra chỗ thật.

### Việt (chiều 05/08) — sửa UC-2 sau eval M3

| Member | Task | Status | Output |
|--------|------|--------|--------|
| Việt | **Phát hiện UC-2 không được PHÁT HIỆN, không chỉ chẩn đoán kém** | ✅ Done | Docker OOM-kill 5 lần, Agent báo "bình thường" |
| Việt | Thêm bằng chứng bộ nhớ vào `detect_crashloop` (Đức chỉ ra) | ✅ Done | `MEMORY_USAGE_RATIO`, `MEMORY_PEAK_10M_MB` |
| Việt | Sửa `_diem_tin_cay()` và `_cau_giai_thuyet()` phủ cả ba UC | ✅ Done | UC-2/UC-3 từ `confidence = 0.0` lên 0.60/0.40 |
| Việt | Đường phát hiện thứ ba: restart ≥ 1 kèm bộ nhớ chạm trần | ✅ Done | cứu được lúc Prometheus đếm thiếu restart |
| Việt | Bọc lỗi Jira trong node `hypothesize` theo mẫu `_xet_nang_muc` | ✅ Done | `_chan_doan_mot_issue()` |
| Việt | 11 test hồi quy | ✅ Done | 246 test pass, ruff sạch |

Đức chỉ đúng chỗ thiếu bằng chứng bộ nhớ. Nhưng khi sửa xong và chạy thử trên OOM thật thì lộ ra **hai lỗi nặng hơn con số M3**.

**Lỗi 1 — `confidence` của UC-2 và UC-3 đang bằng 0.** `_diem_tin_cay()` tôi viết hôm 04/08 chỉ biết tên bằng chứng của UC-1 (`db_pool`, `p95`, `lỗi 5xx`), nên mọi giả thuyết UC-2/UC-3 rơi hết ra ngoài bảng điểm. `_cau_giai_thuyet()` cũng chỉ có nhánh pool, hai UC kia rơi xuống nhánh mặc định và chỉ nhắc lại con số đã có trong tiêu đề — mà `use-cases.md` chấm "nêu chung chung" là KHÔNG đạt. Tức M3 = 0 cho UC-2/UC-3 có **hai** nguyên nhân, thiếu metric chỉ là một nửa. Lỗi của tôi, và nó im lặng: 235 test vẫn xanh vì không test nào hỏi "UC-2 có confidence khác 0 không".

**Lỗi 2 — UC-2 không được phát hiện.** Nghiêm trọng hơn hẳn. Ép OOM thật: Docker báo `RestartCount = 5`, nhưng `changes(process_start_time_seconds[10m])` chỉ thấy **1** — process chết rồi sống lại nhanh hơn nhịp scrape 5s nên phần lớn mốc khởi động không ai ghi lại. Ngưỡng `CRASHLOOP_RESTARTS = 2` trượt, và **Agent báo "Vòng 1: bình thường" trong khi container vừa bị giết 5 lần**. Con số M3 = 0/8 có thể một phần đến từ đây chứ không chỉ từ chất lượng chẩn đoán.

Không hạ ngưỡng restart xuống 1 cho xong — một lần restart đơn thuần là **deploy bình thường**, hạ xuống thì mỗi lần đội deploy Agent lại mở incident. Thay bằng đường phát hiện thứ ba: **restart ≥ 1 kèm đỉnh bộ nhớ chạm trần**. Deploy không đẩy bộ nhớ tới sát giới hạn container, OOM-kill thì có.

**Ba chỗ tự bắt được khi hiệu chỉnh bằng số thật:**

- Truyền **giá trị tức thời** vào chỗ đáng lẽ là **đỉnh** — đúng cái lỗi docstring của chính tôi cảnh báo. Đo thật: tức thời 0.80 (dưới ngưỡng), đỉnh 0.89 (trên). Truyền nhầm là bỏ lọt sự cố.
- `MEMORY_NEAR_LIMIT_RATIO` đặt 0.90 theo số của Đức (127/128 = 0.99) thì máy tôi trượt (114/128 = 0.89). Cùng container, cùng cách ép — chênh do bắt trúng hay trượt nhịp scrape. Hạ xuống 0.85.
- Mượn `baseline` làm "giới hạn container" khiến war room in ra *"114 MB — lệch 0.9× baseline"*, đọc thành *thấp hơn bình thường* trong khi thật ra là **89% của trần**. Số đúng, câu sai. Ghi trần thẳng vào tên bằng chứng.

**Kết quả chạy thật**, cùng cụm OOM đã làm Agent im lặng lúc đầu:

> `service-thanh-toan` bị OOM-kill: bộ nhớ leo tới **114 MB**, chạm giới hạn **128 MB** của container, nên Docker giết process rồi khởi động lại. Bộ nhớ leo dần chứ không nhảy vọt — hình thái của rò rỉ, không phải của một request nặng bất thường.

`confidence = 60%` = đỉnh bộ nhớ chạm trần 0.40 + deploy trùng thời gian 0.20. Đã qua tiếp `propose_remediation` → `rollback` → `Awaiting Approval`.

Bọc lỗi Jira trong `hypothesize` theo mẫu `_xet_nang_muc()` — nhưng bọc **riêng phần post lên Jira**, không bọc phần chẩn đoán: giả thuyết vẫn có giá trị cho `propose_remediation` kể cả khi không post lên được.

UC-3 vẫn cần Trung bổ sung IP nguồn và số tài khoản bị thử.

**Tối: gỡ hai endpoint template khỏi URL công khai.** Gọi thử Live URL — thứ nhóm nộp làm deliverable:

```
POST /api/v1/chat  {"message":"test"}
→ {"response":"Kết quả dựa trên phân tích: Phân tích: test"}
```

Nó **lặp lại nguyên câu đầu vào**. Đây là graph mẫu 2 node của template, không gọi LLM. Cùng với `GET /api/v1/status` trả cứng `"LangGraph Agent v1.0"`. Render bật `autoDeploy` trên `develop` nên mỗi lần push là deploy lại.

Vấn đề không phải code chết mà là **nói sai về sản phẩm**: người mở URL thấy tên "Chat với AI agent", gọi thử thì nó nhại lại câu hỏi, rồi kết luận Agent của nhóm là một con echo — trong khi thứ nhóm thật sự làm nằm ở `incident_graph.py` mà endpoint đó không hề dẫn tới.

Thay bằng `GET /api/v1/agent/health` trả trạng thái **đo được**: Prometheus có trả lời không (hỏi một câu `up`), Jira đã cấu hình chưa, LLM model nào, graph có những node nào. Verify cả hai chiều — với `.env` thật thì `ready: true`, `hitl_gate: changelog`, `model: qwen-plus`; trong test thì `ready: false` vì `conftest` đã xoá cấu hình.

Cố ý **không** làm endpoint chạy Agent qua HTTP: nó sẽ thành đường thứ hai tới `open_war_room`, tức mở incident thật trên Jira chỉ vì có người tò mò gọi URL. Đã ghi lý do vào README và docstring.

Ba file template trong `src/agents/` (`graph.py`, `example_node.py`, `example_tool.py`) **để nguyên** — nằm trong phần Việt sở hữu, và hôm qua chính tôi nhắn Việt "ai định đụng file của người khác thì nhắn một câu trước, kể cả t".

**Đêm: LLM bịa nguyên nhân ở UC-3, và bỏ LLM đi thì chẩn đoán ĐÚNG.**

Việt sửa xong UC-2 rồi tự merge PR #19. Code tốt — chạy A/B trên cùng bộ dữ liệu OOM thật: `develop` cũ cho *"lỗi khởi động không ổn định"* (sai, 20%), nhánh Việt cho *"OOMKilled do bộ nhớ vượt ngưỡng 128 MB"* (đúng ground truth, 80%). Nhưng chạy tiếp UC-3 thì lộ ra một lỗi nặng hơn.

Bắn tấn công thật (12.000 request `/login`, 200 req/s). Bằng chứng **duy nhất** Agent có là `số request /login thất bại mỗi giây = 182,813`. Luật ghép câu **đúng**:

> *"…183 lượt đăng nhập thất bại mỗi giây — hình thái phù hợp với credential-stuffing, **không phải quá tải**. Hệ thống vẫn khoẻ: latency bình thường và không có lỗi 5xx."* — tin cậy 40%

LLM viết lại thành:

> *"Connection pool của service-thanh-toan cạn, gây thất bại khi xử lý request /login."* — tin cậy **60%**

Không có chữ "pool" nào trong bằng chứng. Ba điều lộ ra:

1. **LLM bịa nguyên nhân, không chỉ bịa số.** Prompt cấm thêm số liệu và nó tuân. Nhưng "pool cạn" không phải một con số — nó là một **nguyên nhân**, và prompt không có luật nào chặn việc lấy nguyên nhân từ kiến thức sẵn có của mô hình.
2. **Tin cậy 60% gắn vào một câu mà luật không hề nói.** `confidence` do luật tính trên **bằng chứng**, `statement` do LLM viết — nên câu bịa thừa hưởng con số nghe đáng tin. Đây là chỗ hở trong contract ② `Hypothesis` do tôi viết ngày 28/07, không phải lỗi của LLM.
3. **Sai theo hướng tệ nhất có thể.** `use-cases.md` ghi rõ kết luận "service quá tải" cho một vụ credential-stuffing là chẩn đoán **SAI**. LLM đi đúng vào bẫy đó, và tự tin hơn câu đúng.

Nghịch lý đáng ghi lại: **ở UC-3, bỏ LLM đi thì chẩn đoán đúng.** Pha 2 đang làm chất lượng tệ hơn, không phải tốt hơn — ngược hẳn với UC-1 và UC-2.

**Cách sửa: thêm cửa kiểm căn cứ vào pha 2.** Câu của LLM nêu nguyên nhân nào thì bằng chứng phải có mặt cho nguyên nhân đó — nói "pool" thì phải có `db_pool`, nói "bộ nhớ/OOM" thì phải có bằng chứng bộ nhớ, nói "deploy" thì `correlate_deploy()` phải thật sự tìm ra một lần deploy. Vi phạm thì **bỏ cả `statement` lẫn `reasoning`** của LLM và giữ câu của luật — giữ `reasoning` lại là diễn giải cho một kết luận vừa bị bỏ, tự mâu thuẫn.

Chặn ở code chứ không chỉ dặn thêm trong prompt: dặn thì phải tin mô hình tuân, mà chính chỗ này là bằng chứng nó không luôn tuân.

Cố ý **không** chặn theo từ khoá "latency" hay "chậm": câu đúng của luật cho UC-3 có chứa *"latency bình thường"* — một khẳng định **phủ định**, không phải nêu nguyên nhân. Chặn theo đó là bỏ đúng câu mình muốn giữ.

Verify bằng LLM thật cả hai chiều:

```
UC-3  → BỎ câu LLM ("Connection pool… cạn"), giữ câu luật (credential-stuffing) ✅
UC-1  → GIỮ câu LLM ("Connection pool cơ sở dữ liệu cạn kiệt"), 90%, có lý giải ✅
UC-2  → GIỮ câu LLM ("OOMKilled do bộ nhớ vượt ngưỡng 128 MB"), 80%, có lý giải ✅
```

**Chuyện quy trình:** Việt tự merge PR #19 không qua review. Code đúng, nhưng lỗi UC-3 này nằm ngay trong phạm vi PR đó và có review thì bắt được trước khi vào `develop`.

251 test pass, ruff sạch.

---

## 2026-08-06

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| Trương Công Thái Đức | Review + merge PR #20 (Trung) — telemetry UC-3 và đo lại UC-2 | ✅ Done | 261 test pass | - |
| Trương Công Thái Đức | Chốt chống LLM **phủ định** nguyên nhân đã có bằng chứng | ✅ Done | UC-2 từ 3/8 lên **6/6** đo bằng LLM thật | - |
| Trương Công Thái Đức | Đồng bộ `develop` và `main` sau khi PR #20 nhắm nhầm base | ✅ Done | cả hai ở `5542130` | - |
| Trương Công Thái Đức | Chạy thử trọn kịch bản demo trên Jira thật, tìm 4 chỗ sẽ vỡ | ✅ Done | KAN-12, `demo/README.md` | - |
| Trương Công Thái Đức | Nhúng `IncidentSignal` vào description để war-room view đọc lại được | ✅ Done | `src/services/jira/real.py` | - |
| Trương Công Thái Đức | Bảng dịch thuật ngữ cho UI — dịch THÊM, giữ nguyên tên metric + PromQL | ✅ Done | `ui/labels.py`, 10 test | - |
| Trương Công Thái Đức | Viết lại phần diễn đạt của `war_room.py` và `status_page.py` (Đức nhận thay Long) | ✅ Done | 275 test pass, verify trên 9/9 incident thật | - |

**Tổng kết ngày:** Hoàn tất cặp chốt bảo vệ ranh giới giữa luật và LLM. Và phát hiện ra một điều đáng suy nghĩ hơn cả con số M3.

**Trung làm hai việc đúng.** Telemetry UC-3 (số IP nguồn, số tài khoản bị thử, tỷ lệ nguồn lớn nhất, cửa sổ trượt 60s) thiết kế tốt — dùng `set_function` nên tính lúc scrape, có lock, và **không đưa IP/username thô vào label**, tránh cả nổ cardinality lẫn chuyện riêng tư. Agent chưa đọc ba metric đó, nhưng anh ấy tự ghi rõ trong báo cáo; phần nối là `prometheus.py`/`rules.py` của Việt.

**Con số 3/8 của UC-2 sửa lại hiểu biết của tôi.** Hôm qua tôi chạy **một** lượt thấy đúng nên tưởng đã xong. Trung chạy **8** lượt và chỉ 3 lượt đúng. Một lượt không đại diện — đây đúng là lý do phần eval cần nhiều lượt, và là lần thứ hai trong tuần một phép đo của người khác sửa lại kết luận của tôi.

**Kiểu hỏng lộ ra từ dữ liệu thô của Trung.** LLM nhìn *"đỉnh bộ nhớ 10 phút = 125,9 MB"* trên trần 128 MB — **98,4% trần** — rồi viết *"cả hai đều nằm dưới giới hạn 128 MB, không cho thấy áp lực bộ nhớ"*. Đúng về số học, vô lý về vận hành. Nó còn cãi lại cả quyết định phát hiện: *"restart = 1, dưới ngưỡng kích hoạt là 2.000"*.

**Đây là mặt ngược của lỗi UC-3 hôm qua**, và hai cái cộng lại mới lộ ra khiếm khuyết thật:

| | LLM làm gì | Cửa chặn |
|---|---|---|
| UC-3 | **Bịa** nguyên nhân không có trong bằng chứng | `_nguyen_nhan_khong_co_can_cu()` (05/08) |
| UC-2 | **Xoá** nguyên nhân đã có bằng chứng | `_phu_dinh_ket_luan_cua_luat()` (06/08) |

Cùng một khiếm khuyết: **pha 2 được phép ghi đè pha 1 theo cả hai chiều.** Hai cửa cộng lại nói được một câu gọn: *LLM chỉ được diễn đạt lại kết luận của luật, không được đổi nó.*

Cửa mới cố ý **hẹp**: không bắt "không phải" trơn, vì câu ĐÚNG của luật cho UC-3 chứa *"không phải quá tải"* — đó là loại trừ một nguyên nhân **sai**, chính là thứ cần giữ. Chỉ bắt việc phủ định **mọi** nguyên nhân. Và không chặn khi chính luật cũng chịu: câu luật ở nhánh mặc định có cụm "chưa đủ bằng chứng để nêu nguyên nhân" thì LLM nói "chưa xác định được" là **đồng ý**, giữ nguyên — chặn cả trường hợp đó là ép Agent khẳng định một nguyên nhân nó không có bằng chứng, đúng thứ cửa kia sinh ra để ngăn.

**Đo bằng LLM thật, 6 lượt liên tiếp trên đúng bộ số đã làm Trung ra 3/8: 6/6 đúng.**

**Nhưng con số đó nói ít hơn nó nghe, và đây mới là phần đáng báo cáo mentor.** Log cho thấy cửa chặn kích hoạt ở **5/6 lượt** — tức LLM vẫn cố phủ định gần như mọi lần, và câu đúng cuối cùng **đến từ luật, không phải từ LLM**. Cộng với UC-3 hôm qua (câu đúng cũng của luật), tình hình thật là:

| UC | Câu chẩn đoán đúng đến từ đâu |
|---|---|
| UC-1 | **LLM viết**, có bằng chứng chống lưng |
| UC-2 | **LUẬT viết** — LLM cố phủ định ở 5/6 lượt |
| UC-3 | **LUẬT viết** — LLM bịa nguyên nhân, bị bỏ |

Nếu chỉ báo cáo "M3 gần 100%" thì **nói quá về phần AI**. Sự thật là ở hai trong ba use case, LLM đang làm chất lượng chẩn đoán **tệ hơn**, và giá trị thật của nó nằm ở UC-1 cộng với việc viết câu cho người đọc. Đây là số liệu làm cho câu hỏi gửi mentor có sức nặng: *LLM chỉ diễn giải còn luật ra quyết định — có đủ coi là "AI Agent" không?*

**Chuyện quy trình:** PR #20 của Trung nhắm base `main` thay vì `develop`, và tôi merge mà không kiểm base. Không gây hậu quả vì nhánh anh ấy đã chứa toàn bộ `develop` nên `main` nhận đủ, nhưng `develop` bị bỏ lại 4 commit — đã fast-forward lại. Lần sau phải xem `base=` trước khi merge.

**Chiều: chạy thử trọn kịch bản demo trên Jira thật.** Bốn chỗ sẽ vỡ nếu không chạy thử trước, không chỗ nào đọc code mà thấy được.

**1. `Incident.signal` không bao giờ dựng lại được từ Jira.** `create_incident()` gọi `_adf(text)` **không kèm payload**, nên `IncidentSignal` chỉ tồn tại dưới dạng văn bản cho người đọc. Hệ quả: war-room view của Long luôn hiện *"Chưa có tín hiệu gốc"* — mất đúng mục trưng bằng chứng kèm **PromQL kiểm chứng được**, tức thứ chứng minh "chẩn đoán có bằng chứng". Kiểm cả 6 incident trên board: `signal=None` hết.

Sửa: nhúng payload `signal` vào description lúc tạo, và `get_incident()` đọc thêm field `description` rồi gộp payload từ đó với payload từ comment. Đặt ở description chứ không thêm comment nữa — mỗi war room đã có comment bối cảnh của `open_war_room`, thêm nữa chỉ làm ồn.

Verify bằng cách tạo KAN-12 qua chuỗi đầy đủ: `signal` ✅ 3 bằng chứng có PromQL · `hypotheses` 1 · `proposal` · `timeline` 3 mốc. Bốn mục của UI giờ có dữ liệu.

**2. Tín hiệu tan trong khoảng 60–90 giây sau khi tải dứt.** Lần chạy đầu tôi bắn tải xong rồi mới chạy Agent, và nó báo **"bình thường"** — `rate(...[1m])` không còn mẫu mới nên p95 thành `nan`. Lúc demo phải chạy Agent **trong lúc** tải còn chạy, và nên dùng `run_agent.py` không có `--once` để nó tự poll mỗi 10 giây.

**3. Dòng deploy trong seed HẾT HẠN sau ~11 phút.** `seed.py` cắm `v1.4.2` ở mốc "4 phút trước lúc seed", còn `correlate_deploy()` có cửa sổ `DEPLOY_WINDOW_MINUTES = 15`. Nên phải phát hiện sự cố **trước `seed_time + 11 phút`**. Tôi seed lúc 17:35, chạy lúc 17:49 — deploy đã 22,2 phút tuổi, ngoài cửa sổ. Kết quả: đề xuất tụt từ `rollback v1.4.1` xuống `increase_pool`, tin cậy từ 90% xuống **70%**, và mất luôn nghi phạm — tức mất phần hay nhất của UC-1.

**Phải seed lại ngay trước khi demo.** Đây là loại lỗi không có exception nào, chỉ là một đề xuất kém hơn mà không ai biết vì sao.

**4. Incident đang mở làm Agent KHÔNG mở issue mới.** Luật chống mở trùng chạy đúng, nhưng nó giết mất khoảnh khắc chính của buổi demo. Board có KAN-4 (P2, Open) và KAN-6 (P1, Awaiting Approval) → Agent đi nhánh cập nhật. Phải đóng hết incident đang mở trước khi demo.

**Được thêm một xác nhận ngoài dự tính:** `escalate` chạy thật trên Jira lần đầu — KAN-6 treo chờ duyệt **2610 phút** nên Agent nâng **P2 → P1**, và `set_severity()` sửa đúng **cả hai chỗ** như contract đòi (label `severity-P1` và tiền tố `[P1]` trong tiêu đề). Trước đó tôi chỉ test cái này bằng `FakeJiraClient`.

**Tối: bảng dịch thuật ngữ cho UI.** Đức mở war room ra và không hiểu — mà Đức là người biết dự án rõ nhất. Ban giám khảo chỉ có 10 phút và không có bối cảnh gì, nên đó là vấn đề của UI chứ không của người xem.

Ba lỗi cụ thể tìm ra khi đối chiếu với dữ liệu Jira thật:

1. Trang danh sách là bức tường **9 dòng gần như giống hệt nhau**, 8 cái là rác test từ mấy ngày trước và 7 cái mở ra hiện "Chưa có tín hiệu gốc".
2. **`(baseline None)` in ra thẳng trang**, hai lần — pool và tỷ lệ lỗi đều không có baseline. Trông như lỗi.
3. Tiêu đề là tên metric thô: `http_request_duration_seconds p95 = 4.417 (ngưỡng 2.00)`.

**Nguyên tắc chốt được sau khi Đức nhắc: dịch THÊM, không dịch THAY.** Trang này phục vụ **hai** người cùng lúc — người xem không biết tech cần biết chuyện gì đang xảy ra với khách hàng, còn **người trực cần tên metric gốc và câu PromQL nguyên văn** để copy vào Prometheus mà đào tiếp. Dịch mất thông tin thì tệ hơn không dịch: người trực mất đường đào, mà đó là người duy nhất thật sự sửa được sự cố.

Nên mỗi bằng chứng trả về **hai tầng trên cùng một dòng**, không phải hai chế độ:

```
Thời gian khách phải chờ: 4.42 giây (thường 0.58 giây — lệch 7.6 lần)
  ↳ http_request_duration_seconds p95 = 4.417s
```

`ui/labels.py` là **dữ liệu thuần, không đụng layout** — Long giữ phần thiết kế. Vì sao chia thế: `ui/` là của Long, và hôm 02/08 tôi đã đụng vào phần của Việt rồi tự nhắc "ai định đụng file của người khác thì nhắn một câu trước, kể cả t". Long không phải tự nghĩ ra 14 câu dịch, nhưng layout vẫn là quyết định của anh ấy.

Hai test canh chuỗi, cùng họ với `test_runbooks.py`: bảng dịch so khớp theo chuỗi con của tên `MetricEvidence`, nên `rules.py` đổi một chữ là bảng lặng lẽ rơi về tên thô — không sai, nhưng mất hết công dịch và không có gì đỏ lên. `test_moi_ten_metric_deu_dich_duoc` gọi thẳng `rules.detect*()` cả ba UC rồi đối chiếu.

Một chi tiết thứ tự có ý nghĩa: `"đỉnh bộ nhớ"` phải đứng **trước** `"bộ nhớ đang dùng"` trong bảng, không thì hai metric bộ nhớ của Việt dịch thành cùng một câu. Có test riêng cho chỗ đó.

**Làm luôn phần layout UI thay Long, theo yêu cầu của Đức.** Ghi rõ ở đây vì `ui/` là của Long và hôm 02/08 tôi đã tự đặt luật "ai định đụng file của người khác thì nhắn một câu trước, kể cả t". Lần này Đức quyết, nhưng vẫn phải nói cho Long biết phần nào bị sửa và vì sao.

Bốn thay đổi trong `war_room.py`:

1. **Câu mở đầu trang** — ba câu nói AI làm gì và **không** tự sửa. Trước đó trang không nói nó là cái gì.
2. **Tách danh sách thành "đang xảy ra" / "đã xử lý xong"**, gấp phần đã xong lại. Trước đó 9 incident đổ chung một chỗ mà 8 cái là sự cố cũ.
3. **Đánh số ①②③** — người xem thấy đây là ba bước suy nghĩ, không phải ba khối rời.
4. **Bằng chứng hai tầng**: câu tiếng Việt + dòng `↳` giữ nguyên văn tên metric, PromQL trong `st.code()` bấm copy được.

`status_page.py`: tên dịch vụ thành "Thanh toán"/"Đặt hàng" nhưng vẫn giữ `↳ service-thanh-toan` bên dưới, và đổi tên khối JSON debug từ *"để tham khảo khi code"* thành *"Dữ liệu thô (dành cho người trực)"* — đây là trang công khai, câu cũ đọc ra như trang chưa làm xong.

**Một lỗi bắt được nhờ không tin HTTP 200.** Cả hai trang trả 200 và log sạch, nhưng Streamlit chỉ chạy script khi có websocket — 200 chỉ là vỏ trang. Mô phỏng lại `sys.path` mà `streamlit run ui/war_room.py` thật sự dựng thì ra `ModuleNotFoundError: No module named 'ui'`: streamlit đặt **thư mục ui/** vào path, không đặt thư mục gốc repo. Pytest import được vì nó tự thêm rootdir.

Tức là test xanh, trang trả 200, mà Long chạy thật sẽ vỡ ngay dòng import. Vá bằng `sys.path.insert` như `scripts/run_agent.py` đang làm. Cùng họ với vụ `.env` làm test đỏ theo máy hôm qua: **môi trường lúc test khác môi trường lúc chạy.**

**Verify trên dữ liệu thật thay vì chỉ mở trang xem.** Chạy lại đúng các phép truy cập field của UI trên **cả 9 incident** trên board — kể cả 8 cái cũ thiếu `signal` và `hypotheses`, vì đó mới là chỗ dễ vỡ bằng `KeyError`. Kết quả 9/9 render được, 0 lỗi.


---

## 2026-08-06 — Việt

| Member | Task | Status | Output |
|--------|------|--------|--------|
| Việt | Nối 3 metric hình dạng nguồn UC-3 của Trung vào `IncidentSignal` | ✅ Done | 1 → 4 bằng chứng |
| Việt | Câu giả thuyết UC-3 chỉ nói "credential-stuffing" khi CÓ số chống lưng | ✅ Done | có số thì nêu, không có thì chỉ "vấn đề bảo mật" |
| Việt | Baseline phải **đủ điểm** mới tin, không chỉ khác 0 | ✅ Done | `BASELINE_SAMPLE_COUNT_30M`, ngưỡng 20/30 điểm |
| Việt | 7 test hồi quy + dạy fake Prometheus câu `count_over_time` | ✅ Done | 271 test pass, ruff sạch |

**UC-3 — bằng chứng từ 1 lên 4.** Trước đó tín hiệu chỉ có tỷ lệ thất bại, mà con số đó **không phân biệt được tấn công với quá tải** — cả hai đều làm nhiều lượt đăng nhập hỏng. Đó là lý do LLM viết "connection pool cạn" cho một vụ credential-stuffing hôm 05/08: nó không có gì để phân biệt. Ba metric của Trung cho đúng thứ thiếu — hình **dạng** nguồn:

| | nguồn | tài khoản | nguồn lớn nhất |
|---|---|---|---|
| Credential-stuffing | ít | **nhiều** | gần 1.0 |
| Người dùng gõ nhầm | nhiều | ít | thấp |
| Service lỗi | nhiều | nhiều | thấp |

Đo trên tấn công thật: 118 lượt/giây, **1 IP nguồn, 100 tài khoản, tỷ lệ 1.0**.

Một quyết định đi kèm: câu luật **chỉ nói "credential-stuffing" khi có hai con số chống lưng** (số tài khoản ≥ 10 và một nguồn chiếm > 50%). Không có số thì chỉ nói "vấn đề bảo mật, không phải quá tải". Khẳng định hình thái tấn công mà không có hình dạng nguồn là đoán — đúng cái mình đang cấm LLM làm, nên luật cũng không được phép. Có sửa một assert trong test của Đức theo hướng này, mốc nhận diện đổi từ "credential-stuffing" sang "vấn đề bảo mật".

**Baseline — "có" phải nghĩa là "đủ điểm để tin".** `p95_baseline > 0` chỉ nói *có số*, không nói *số đó tính trên đủ dữ liệu*. Prometheus không có volume nên `docker compose down` là mất sạch lịch sử, mà `quantile_over_time(...[30m:1m])` **vẫn trả về một con số** dù chỉ có vài điểm. Thêm `BASELINE_SAMPLE_COUNT_30M` đếm điểm thật, ngưỡng 20/30. Verify ngay trong lần chạy hôm nay: sau khi dựng lại stack, số điểm là **1** — đúng tình huống Trung gặp báo nhầm.

Chặn theo cấu trúc chứ không theo quy trình: không phụ thuộc ai nhớ chạy warm-up. Và **không làm Agent mù** — ngưỡng cứng vẫn xét bình thường, chỉ đường lệch baseline bị tạm ngưng. Có test riêng cho điều đó.

Phải kèm cùng điều kiện vào `breached_seconds_by_service()` nữa, nếu không hai chỗ nói khác nhau về cùng một sự việc: `rules.detect()` im lặng còn log lại báo "đã bất thường 300s".

**Fake Prometheus dính bẫy cũ lần thứ tư.** `count_over_time(...)` bọc ngoài câu p95 nên chứa `histogram_quantile`, rơi xuống nhánh p95 và số điểm baseline nhận giá trị p95 (0.4) — dưới ngưỡng 20, mọi test đi qua đường lệch baseline hỏng im lặng. Đã thêm nhánh và assert canh. Bốn lần cùng một chỗ: nếu thêm hằng PromQL nữa thì nên đổi hẳn sang so nguyên văn.

**Chạy thật, cả chuỗi:** 118 lượt/giây → `INC-1` → giả thuyết 60% nêu đủ hình dạng nguồn → đề xuất `rate_limit` → `Awaiting Approval`.

### Việt (chiều 06/08) — nối war room khi sự cố lan truyền

| Member | Task | Status | Output |
|--------|------|--------|--------|
| Việt | Node `link_incidents` — gọi `jira.link_issues()` khi phát hiện lan truyền | ✅ Done | `INC-1 ↔ INC-2` trên sự cố thật |
| Việt | Chống nối trùng: đọc lại `related_incidents` trước khi gọi | ✅ Done | vòng 2 trở đi không nối lại |
| Việt | Thêm `all_war_rooms` vào state — sự cố lan **dần** vẫn nối được | ✅ Done | `state.py` |
| Việt | 11 test mới | ✅ Done | 282 test pass, ruff sạch |

`is_spreading()` phát hiện lan truyền và `classify_severity` nâng cả hai lên P1 từ hôm 03/08. Nhưng nâng mức chỉ nói **"nặng hơn"**, không nói **"hai cái này là một vụ"** — `jira.link_issues()` chưa từng được gọi. Người trực mở Jira thấy hai issue P1 rời rạc và phải tự đoán chúng có liên quan, đúng thứ Agent lẽ ra làm hộ. War-room view của Long đã có sẵn chỗ hiển thị `related_incidents` và cho bấm chuyển qua lại — trước node này chỗ đó luôn rỗng.

**Hai quyết định đáng ghi:**

`all_war_rooms` tách riêng khỏi `war_rooms`. `war_rooms` chỉ chứa issue **mới mở** (dùng cho `hypothesize`, để không chẩn đoán lại mỗi vòng). Nhưng sự cố lan **dần** — A hỏng trước, B hỏng sau vài phút — nên mỗi vòng chỉ có đúng một issue mới, và hai war room không bao giờ gặp nhau để nối. Có test riêng cho kịch bản đó.

Chống nối trùng bằng cách đọc lại `related_incidents` trước khi gọi. `RealJiraClient.link_issues()` POST thẳng lên Jira, gọi lại là tạo link thứ hai giữa đúng hai issue — mà Agent poll vài giây một lần trong lúc sự cố kéo dài hàng chục phút. Cùng loại rác mà `find_open_incident()` chặn ở `open_war_room`.

**Chạy thật trên sự cố lan truyền** (bắn tải cả hai service, p95 9.69s và 4.85s):

```
Sự cố lan sang 2 service — tính lại severity theo contract ①
Mở war room INC-1 cho service-thanh-toan (P1)
Mở war room INC-2 cho service-dat-hang (P1)
Nối INC-1 ↔ INC-2 — cùng một sự cố lan truyền
```

**Còn thiếu một phần của ground truth.** `use-cases.md` yêu cầu ba thứ cho lan truyền: nhận ra `service-dat-hang` suy giảm **do phụ thuộc**, link hai incident, và nâng P1. Giờ có (2) và (3); (1) chưa. Giả thuyết cho `INC-2` ra `confidence 10%` và câu *"Chưa đủ bằng chứng để nêu nguyên nhân gốc"* — trung thực, nhưng chưa phải điều `use-cases.md` chấm là đúng. Cần bàn với Đức vì nó là một khẳng định gần với nhân quả.
---

## 2026-08-07

| Member | Task | Status | Output |
|--------|------|--------|--------|
| Trương Công Thái Đức | Review + merge PR #24 (Trung) — đo lại M3 kèm cột nguồn câu kết luận | ✅ Done | 296 test pass |
| Trương Công Thái Đức | Cửa chặn thứ ba: LLM không được khẳng định thứ luật vừa loại trừ | ✅ Done | UC-3 từ 3/8 lên **8/8** đo bằng LLM thật |

**Trung đo lại M3 kèm cột "câu cuối do LLM hay luật viết"** — đúng thứ tôi nhờ, và anh ấy **giữ nguyên 3/8 của UC-3 thay vì làm đẹp số liệu**, ghi thẳng trong PR *"kết quả này được giữ nguyên trong báo cáo, không làm đẹp số liệu"*.

| Use case | M3 | Câu cuối do ai viết |
|---|---:|---|
| UC-1 | 10/10 | LLM 10 · luật 0 |
| UC-2 | 8/8 | LLM 1 · **luật 7** |
| UC-3 | 3/8 | LLM 8 · luật 0 |
| **Tổng** | **21/26 (80,8%)** | LLM 19 · luật 7 |

Thiết kế của anh ấy đúng chỗ: `hypothesize_with_origin()` trả kèm nguồn, `hypothesize()` giữ làm vỏ mỏng nên không phá API luồng Agent, và `origin` **không** nhét vào `Hypothesis`/Jira vì nó mô tả *lần chạy* chứ không phải bản chất sự cố.

**Số liệu của Trung chỉ ra chỗ hở trong cửa chặn của tôi, và code review không tìm ra được.** 5 lượt sai của UC-3 chỉ khác 3 lượt đúng **đúng một mệnh đề đuôi**:

```
ĐÚNG: "…100 lần thử đăng nhập khác nhau mỗi phút vào endpoint /login."
SAI:  "…100 lần thử đăng nhập khác nhau mỗi phút, GÂY QUÁ TẢI request thất bại."
```

LLM mô tả **đúng** hình dạng nguồn rồi gắn thêm "gây quá tải" — đúng cái `use-cases.md` gọi là chẩn đoán SAI, vì nó dẫn người trực đi sửa nhầm hướng.

Cửa của tôi không bắt được vì `"quá tải"` **cố ý** không nằm trong danh sách cần bằng chứng — câu ĐÚNG của luật cho UC-3 có chứa "không phải quá tải", chặn theo từ khoá là bỏ đúng câu muốn giữ. Tôi thấy nửa đó, nhưng bỏ sót nửa còn lại: câu luật **phủ định thẳng** "quá tải", còn LLM thì **khẳng định** nó.

**Cửa thứ ba đọc phủ định ra từ chính câu luật**, không liệt kê từ khoá: tìm cụm `"không phải X"` trong câu luật rồi cấm LLM khẳng định `X`. Luật đổi cách diễn đạt thì cửa tự theo, không cần ai nhớ cập nhật hai chỗ. Có xử lý trường hợp LLM **nhắc lại** chính phủ định đó ("đây là tấn công, không phải quá tải") — đó là đồng ý, không phải ngược.

**Lần thứ ba cùng một họ, và giờ mới thấy đủ hình:**

| Ngày | LLM làm gì | Cửa |
|---|---|---|
| 05/08 | **bịa** nguyên nhân không có bằng chứng | `_nguyen_nhan_khong_co_can_cu()` |
| 06/08 | **xoá** nguyên nhân đã có bằng chứng | `_phu_dinh_ket_luan_cua_luat()` |
| 07/08 | **khẳng định** thứ luật vừa phủ định | `_khang_dinh_thu_luat_da_loai_tru()` |

Ba mặt của cùng một chuyện: pha 2 ghi đè pha 1. Ba cửa cộng lại giữ đúng một ranh giới — **LLM diễn đạt lại kết luận của luật, không đổi nó.**

**Đo bằng LLM thật, 8 lượt trên đúng bộ số Trung ra 3/8:**

```
→ 8/8 đúng · câu do LLM viết: 3/8 · do luật viết: 5/8
   (trước: 3/8 đúng, LLM viết 8/8)
```

**Con số đẹp hơn nhưng phần LLM nhỏ đi — phải báo cáo đúng như thế.** M3 tổng dự kiến lên khoảng 96%, nhưng trong 26 lượt thì luật viết 12 câu. Ba lượt LLM viết được ở UC-3 lần này lại hay hơn câu luật (*"tấn công brute-force vào endpoint /login"*), nên giá trị của LLM là **có thật ở chỗ diễn đạt**, chỉ không đáng tin ở chỗ **kết luận**.

Đó chính là câu trả lời cho câu hỏi gửi mentor, và giờ có số liệu chống lưng.

---

## 2026-08-10

| Member | Task | Status | Output |
|--------|------|--------|--------|
| Việt | Pull code mới nhất từ `develop` về branch `viet`, scan và resolve conflicts | ✅ Done | Branch `viet` đồng bộ |
| Việt | Implement `MeetingRoomClient` + `DailyMeetingRoom` — tạo phòng họp khẩn trên Daily.co khi sự cố ≥ P2 | ✅ Done | `src/services/meeting_room.py`, 20 test |
| Việt | Implement `IncidentAlertService` — gửi email cảnh báo kèm link phòng họp khi phát hiện sự cố | ✅ Done | `src/services/incident_alert.py`, 15 test |
| Việt | Tích hợp phòng họp + email cảnh báo vào `open_war_room` — Agent tự tạo phòng họp + gửi email khi mở incident P1/P2 | ✅ Done | `src/agents/nodes/open_war_room.py` |
| Việt | Điểm thông minh: nếu 2 dịch vụ cùng bị lỗi → tạo **1 phòng họp dùng chung** thay vì 2 | ✅ Done | Logic `_get_or_create_shared_room()` |

**Tổng kết ngày:** Tích hợp Daily.co meeting room + email cảnh báo vào pipeline. Agent giờ tự tạo phòng họp và gửi email cảnh báo khi phát hiện sự cố nghiêm trọng (P1/P2). Key Daily.co: `ec878...` đã cấu hình trong `.env`.

---

## 2026-08-11

| Member | Task | Status | Output |
|--------|------|--------|--------|
| Việt | Implement `LogSearchTool` — Agent đọc log thật từ các dịch vụ | ✅ Done | `f6b58d2`, PR #25 merged |
| Việt | Fix `_bang_chung_phan_bac()` — sửa logic phản bác bằng chứng trong chẩn đoán | ✅ Done | `0f893b7`, PR #27 merged |
| Việt | Cấu hình Gmail SMTP (`vietpn04@gmail.com`) + App Password | ✅ Done | `8243cbf` |
| Trương Công Thái Đức | Dọn 31 lỗi lint làm CI đỏ trên develop từ PR #25 | ✅ Done | `02ac999` |
| Trương Công Thái Đức | Fix Jira IPv6 NAT64 — ép IPv4 vì IPv6 treo 30 giây | ✅ Done | `74e6e7a` |
| Trương Công Thái Đức | UC-4: log là nguồn duy nhất — bỏ nhãn chẩn đoán khỏi log demo | ✅ Done | `b88c775` |
| Trương Công Thái Đức | Vá 6 lỗi chỉ lộ ra khi chạy live trọn chuỗi | ✅ Done | `e7c4b33` |

**Tổng kết ngày:** Hai PR của Việt merge vào develop (PR #25: log observability, PR #27: fix chẩn đoán). Đức fix hàng loạt lỗi phát hiện khi chạy live trọn chuỗi trước demo. Gmail SMTP đã cấu hình xong.

---

## 2026-08-12

| Member | Task | Status | Output |
|--------|------|--------|--------|
| Việt | Implement `StatusUpdater` — Agent tự comment tiến trình lên Jira theo từng bước | ✅ Done | `src/services/status_updater.py` |
| Việt | Implement `PostmortemGenerator` — Agent tự sinh báo cáo postmortem từ dữ liệu Jira thật | ✅ Done | `src/services/postmortem_generator.py` |
| Việt | Implement `PostmortemReport` — render postmortem thành HTML (email body + report đính kèm) | ✅ Done | `src/services/postmortem_report.py` |
| Việt | Implement `GmailClient` — gửi email postmortem qua Gmail SMTP với HTML body + attachment | ✅ Done | `src/services/email_client.py` |
| Việt | Tích hợp postmortem + email vào webhook — sau execute thành công → tự sinh + gửi postmortem | ✅ Done | `src/api/webhooks.py` hàm `_try_send_postmortem()` |
| Việt | Fix pipeline gap #1: Auto-transition ticket sang Resolved sau execute thành công | ✅ Done | `webhooks.py` bước 7, 2 test mới |
| Việt | Fix pipeline gap #2: Guard chống postmortem gửi 2 lần khi cả Rule #1 + Rule #2 fire | ✅ Done | `/webhooks/jira/resolved` guard, 1 test mới |
| Việt | Implement `POST /webhooks/jira/resolved` — xử lý manual resolution khi con người tự sửa | ✅ Done | `webhooks.py`, 9 test mới |
| Việt | Setup Jira credentials trong `.env` — kết nối thành công tới `jibinarybro.atlassian.net` | ✅ Done | 25 incident đọc được từ Jira Cloud |
| Việt | Viết `docs/pipeline.md` — tài liệu pipeline chi tiết cho toàn team | ✅ Done | 568 dòng, có sơ đồ Mermaid |
| Trương Công Thái Đức | Review + vá 6 chỗ trong nhánh `viet` trước merge | ✅ Done | `751edf4` |
| Trương Công Thái Đức | Thêm `scripts/duyet.py` — kích webhook phê duyệt cho issue có sẵn | ✅ Done | `0247edc` |
| Trương Công Thái Đức | Fix UI: vá 3 lỗi lộ ra khi tập demo trên màn hình thật | ✅ Done | `06f7845` |
| Trương Công Thái Đức | Viết runbook buổi demo | ✅ Done | `docs/demo-runbook.md` |

**Tổng kết ngày:** Pipeline hoàn chỉnh tự động end-to-end. Toàn bộ 501 test pass. Hai khoảng trống pipeline cuối cùng được fix: (1) ticket không auto-resolve sau execute, (2) postmortem gửi 2 lần khi cả 2 rule fire. Jira Cloud kết nối thành công, 25 incident đã tồn tại. Tài liệu pipeline chi tiết viết xong cho team.

**Test toàn bộ:** 501 test pass (tăng 3 test từ 498 → 501 nhờ thêm test cho 2 fix + guard).

---

## 2026-08-13

| Member | Task | Status | Output |
|--------|------|--------|--------|
| Trương Công Thái Đức | Chặn `OPENAI_API_KEY` và `LLM_BASE_URL` trong conftest — test đang gọi DashScope thật, tốn quota và chậm 46× | ✅ Done | `327ca18`, test 146s → 3s |
| Trương Công Thái Đức | Fix CI: cài `ui/requirements.txt` + thêm test khói import 3 trang UI — `plotly` thiếu làm war room chết | ✅ Done | `869086a`, 505 test |
| Trương Công Thái Đức | Tách THIẾT KẾ khỏi HIỆN TRẠNG trong `docs/pipeline.md` — 3 chỗ mô tả thiết kế như thể đã có | ✅ Done | `c459e8d` |
| Trương Công Thái Đức | Sửa test khói UI: test gọi mạng thật ra Render, mock trả sai kiểu → dựng mock từ model thật | ✅ Done | `c152e03`, 505 test, 4s ổn định |
| Trung | Implement bộ đánh giá recall sự cố — `eval/case_suite.py` + 30 test case + 107 test | ✅ Done | `c284453`, 7 file, 2639 dòng |

**Tổng kết ngày:** Đức dọn nợ kỹ thuật: chặn LLM thật trong test (nhanh 46×), fix lỗ hổng CI khiến war room chết mà không ai biết, sửa tài liệu pipeline đang mô tả cái chưa có. Trung hoàn thành bộ đánh giá recall — framework eval đầu tiên của đội.

**Test toàn bộ:** 505 test pass.

---

## 2026-08-15

| Member | Task | Status | Output |
|--------|------|--------|--------|
| Trương Công Thái Đức | Fix Jira: subtask postmortem bị đếm là sự cố — board báo 5 đang mở thay vì 2 | ✅ Done | `3c56c17`, 508 test |
| Trương Công Thái Đức | Fix endpoint sức khoẻ: thiếu 2 node (`analyze_logs`, `link_incidents`) + `ready=false` trên Render vì đòi Prometheus | ✅ Done | `bf7ca92`, 510 test |
| Trương Công Thái Đức | Rollback UC-4 thi hành THẬT — `SIMULATE_MISSING_MIGRATION` off → restart container → lỗi 100% → 0% | ✅ Done | `330be75`, 530 test (+20), 4 lớp chặn an toàn |
| Trương Công Thái Đức | Cập nhật `docs/pipeline.md` + `docs/demo-runbook.md` — Automation Rule #1 đã chạy, thêm màn ⑥ demo rollback thật | ✅ Done | Nằm trong `bf7ca92` và `330be75` |
| Việt | Đo recall trên bộ case mở rộng — tăng từ 30 → 50 test case enterprise-grade | ✅ Done | `796c602`, `bf3dfb3` |
| Việt | Commit Gate02 — cập nhật README, architecture diagram, viết `eval/EVIDENCE.md`, thêm `scripts/run_agent.py` | ✅ Done | `b73fbd9`, 518 dòng mới |
| Việt | Implement idempotency guard — `is_already_remediated()` chống thi hành trùng qua marker trong Jira comment | ✅ Done | `94dd6fd` |
| Việt | Thêm `get_comment_bodies()` với ADF-to-text parser cho Jira client | ✅ Done | `94dd6fd` |
| Việt | Viết evaluation report v3.0 — Recall 72%, Precision 72%, 50 case, confusion matrix đầy đủ | ✅ Done | `evaluation_report_v3.md`, 433 dòng |

**Tổng kết ngày:** Hai bước nhảy lớn. (1) UC-4 rollback chạy thật — đo được lỗi 100% → 0%, với 4 lớp chặn an toàn (HITL, default off, whitelist cặp, lệnh cố định). (2) Evaluation report v3 hoàn chỉnh: 50 case enterprise-grade, Recall 72%, Precision 72%, Severity Accuracy 89%. Jira board dọn sạch subtask bị đếm nhầm (5 → 2 đang mở). Endpoint sức khoẻ fix đúng.

**Test toàn bộ:** 530 test pass (tăng 29 test từ 501 → 530).

---

## 2026-08-17

| Member | Task | Status | Output |
|--------|------|--------|--------|
| Việt | Dựng lại war room theo đúng `scratch_warroom_ref.html` — cả trang thành MỘT khối HTML/CSS/JS nhúng qua `st.iframe`, bỏ hẳn widget Streamlit | ✅ Done | `ui/war_room.py` — header 52px, sidebar 340px cuộn riêng, content 920px, đo trên DOM thật |
| Việt | Fix lỗi biểu đồ **chưa bao giờ** vẽ được dữ liệu — `khoi_bieu_do_svg()` đọc khoá `values`, trong khi `truy_van_range()` trả khoá `diem`, nên luôn rơi vào nhánh "Prometheus không khả dụng" mà không báo gì | ✅ Done | `ui/war_room.py::bang_bieu_do()` |
| Việt | Xoá `bieu_do_realtime()` + `dung_bieu_do()` (~350 dòng plotly chết từ lần redesign 16/08, không còn chỗ nào gọi) và bỏ `plotly` khỏi `ui/requirements.txt` | ✅ Done | `ui/requirements.txt` còn 2 dep |
| Việt | Thêm light theme đầy đủ + nút toggle sun/moon; tab, ô tìm kiếm (`⌘K`), chọn sự cố, nút sao chép PromQL đều chạy client-side không reload | ✅ Done | Trạng thái đang xem ghi vào URL `?key=&theme=` nên "Làm mới" quay lại đúng chỗ |
| Việt | Ô "Ảnh hưởng" đo thật thay vì con số trang trí của file mẫu — sự cố lỗi lấy tỷ lệ 5xx, sự cố latency tính `1 − bucket[le=ngưỡng]/bucket[le=+Inf]` | ✅ Done | `ui/war_room.py::ty_le_anh_huong()` |
| Việt | Ô "Agent" trên header lấy `/api/v1/agent/health` thay vì "% uptime" — không có nguồn dữ liệu cho con số đó (Prometheus không scrape Agent, endpoint chỉ trả boolean) | ✅ Done | Cố ý **không** đọc khoá `prometheus` của endpoint đó — bản Render trỏ `localhost:9090` theo thiết kế, dùng nó là báo động giả (đúng bẫy đã ghi ở `src/api/routes.py`) |
| Việt | Chuyển `st.components.v1.html` → `st.iframe` (deprecated, hạn gỡ 2026-06-01), giữ đường lùi cho Streamlit cũ vì `ui/requirements.txt` cố ý không ghim version | ✅ Done | `ui/war_room.py` |

| Việt | Sửa 3 lỗi lộ ra khi test giao diện với dữ liệu Jira thật (34 phiếu KAN) | ✅ Done | xem 3 dòng ngay dưới |
| Việt | **Tìm kiếm không lọc được gì** — JS đặt `hidden` đúng, nhưng `.incident { display: block }` của trang đè luôn `[hidden] {display:none}` mặc định của trình duyệt | ✅ Done | Vá lần đầu bằng `.incident[hidden]`, xem dòng dưới |
| Việt | **Màn chờ che kín trang ngay khi mở** — cùng đúng loại lỗi trên, lặp lại ở `.dang-tai { display: grid }`, và lọt qua bản kiểm cũng vì cùng một lý do: bản kiểm đọc `el.hidden` chứ không đọc `getComputedStyle(el).display` | ✅ Done | Chặn cả loại lỗi bằng `[hidden] { display: none !important; }` trong `theme.RESET_CSS`, bỏ bản vá lẻ |
| Việt | **Bấm chọn sự cố không ăn** — iframe của Streamlit chạy sandbox **không có** `allow-top-navigation`, nên gán `window.parent.location.href` ném `SecurityError`. Đổi sang `history.replaceState()` rồi `location.reload()` — hai thứ sandbox vẫn cho | ✅ Done | `ui/war_room.py::_JS` |
| Việt | **Tải sẵn chi tiết mọi phiếu không dùng được**: 34 phiếu mất 18,3 giây, tăng luồng không nhanh hơn (Render 1 worker, request xếp hàng ở server). Chuyển sang chỉ tải chi tiết phiếu đang xem | ✅ Done | `tai_danh_sach()` + `tai_chi_tiet()`, mỗi lần mở trang còn ~2 lời gọi |
| Việt | Hai nút Runbooks/Postmortems `disabled` kèm lý do khi phiếu đang xem không có mục đó, thay vì bấm không phản hồi | ✅ Done | `ui/war_room.py::header_html()` |
| Việt | Dò Prometheus **4,02s → 0,52s**: `localhost` phân giải cả `::1` lẫn `127.0.0.1` nên mọi timeout bị nhân đôi. Đổi sang bắt tay TCP (cổng có người nghe trả lời trong 0,001s) rồi mới hỏi `/-/healthy` | ✅ Done | Tách luôn `agent/health` sang cache TTL 60s |
| Việt | Đo và ghi lại thời gian phản hồi từng chặng — mở trang 3,09s, chuyển phiếu 1,42s, trong đó 0,39s là độ trễ mạng thuần tới Render (đo bằng endpoint `/health` rỗng) | ✅ Done | Số liệu trong tổng kết ngày |
| Việt | Tách `ui/theme.py` — token hai theme, reset, icon, nút, pill dùng chung; `labels.MAU/SEVERITY_MAU/HEALTH_MAU/LOG_MAU` lấy màu từ `theme.PALETTE` thay vì gõ lại hex | ✅ Done | `ui/theme.py` mới, hết trùng bảng màu ở 3 chỗ |
| Việt | Dựng lại `status_page.py` theo cùng hệ thiết kế — cùng token, cùng font, cùng dòng `↳`, có light theme; bố cục vẫn một cột kiểu tờ thông báo, không bắt chước bàn làm việc của war room | ✅ Done | `ui/status_page.py` |

**Tổng kết ngày:** War room dựng lại từ đầu theo file thiết kế mẫu. Lý do phải đổi kiến trúc chứ không chỉ sửa CSS: Streamlit đặt mỗi widget trong một `stElementContainer` riêng nên không có cách nào cho hai vùng cuộn độc lập cạnh nhau — mà đó là khung của thiết kế (header cố định, sidebar cuộn riêng, content cuộn riêng). Đổi lại: mỗi lần tải trang phải lấy chi tiết của **tất cả** sự cố (gọi song song, cache 15s) vì mọi sự cố đều được render sẵn thành một `.view` để JS bật/tắt. Nhân tiện lộ ra biểu đồ đã hỏng im lặng từ trước: sai tên khoá nên không lần nào vẽ được dữ liệu Prometheus, mà nhánh lỗi lại nói "Prometheus không khả dụng" nên trông hệt như đường bình thường của bản deploy. Ba ràng buộc cũ giữ nguyên: dòng `↳` hai tầng cho người trực, không bịa số khi thiếu nguồn (hiện `—` kèm lý do), và trang không thi hành hành động nào — duyệt/từ chối vẫn ở Jira.

Buổi chiều test lại với **dữ liệu Jira thật** (34 phiếu KAN thay vì 3 fixture) thì lộ ra ba lỗi mà bản fixture không thể lộ: tìm kiếm không lọc được thẻ nào, bấm chọn sự cố không ăn, và tải sẵn chi tiết mọi phiếu mất 18 giây. Cả ba đều thuộc loại "chạy đúng trong lý thuyết": JS đặt `hidden` đúng nhưng CSS của chính trang đè lên; điều hướng đúng cú pháp nhưng sandbox của iframe chặn; tải song song đúng cách nhưng server chỉ có một worker nên chẳng song song được gì. Bài học ghi lại để khỏi lặp: **kiểm CSS bằng `getComputedStyle`, không bằng thuộc tính DOM** — bản kiểm đầu tiên của tìm kiếm "xanh" chỉ vì nó đọc `el.hidden` thay vì nhìn xem thẻ có biến mất thật không. Bài học này phải trả giá hai lần trong cùng một ngày: vá xong ô tìm kiếm thì đúng cái bẫy đó cắn lại ở màn chờ, và cũng lọt kiểm y hệt. Lần thứ hai mới sửa đúng chỗ — một dòng `[hidden] { display: none !important; }` trong reset dùng chung, chặn cả loại lỗi thay vì vá từng phần tử.

Cuối ngày dọn nốt chỗ lệch tông giữa hai trang: tách `ui/theme.py` làm nguồn duy nhất của token rồi dựng lại status page theo đó.

**Thời gian phản hồi, đo ngày 17/08 từ máy ở Việt Nam:** mở trang lần đầu **3,09s** (danh sách 0,95 + sức khoẻ 0,56 + chi tiết một phiếu 1,05 + dò Prometheus 0,53), chuyển sang phiếu khác **1,42s** (chỉ còn chi tiết phiếu 1,23 + trình duyệt dựng lại trang 0,19). Sàn cứng là **0,39s mỗi lượt gọi** — đo bằng `/health`, một endpoint không làm gì cả — nên đó thuần là độ trễ mạng tới Render, không tối ưu được từ phía UI. Phần còn lại của mỗi lượt gọi chi tiết là 3 lượt Jira REST (issue + changelog + comment) mà API phải đi thay ta. Muốn nhanh hơn nữa thì phải sửa backend, không phải sửa giao diện — xem gợi ý trong docstring `tai_chi_tiet()`.

**Test toàn bộ:** 536 test pass, ruff clean.

---

<!-- Format: copy block trên cho mỗi ngày làm việc -->
