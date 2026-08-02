# Weekly Journal — Team Binary Brothers

> Ghi lại mỗi tuần: học được gì, khó khăn gì, quyết định gì, kế hoạch tiếp.

**Thành viên (4):** Trung · Phan Hoàng Long · Việt · Trương Công Thái Đức (2A202601581)
**Vai trò:** Đức (Lead · Kiến trúc & Tích hợp · DevOps) · Việt (AI Agent) · Trung (Backend service + QA) · Long (Frontend + Demo) — chi tiết ở [README.md](README.md#team--phân-vai)

---

## Week 1: 2026-07-26 - 2026-08-01

### Mục tiêu tuần này
- [x] Clone template, khởi tạo repo, push lên GitHub
- [x] Đọc Technical Guidebook, nắm yêu cầu 10 deliverables và 5 tiêu chí chấm điểm
- [x] Cài AI usage logging hooks
- [x] Tạo branch `develop` làm điểm tích hợp cho cả đội
- [x] Chốt đề tài: **PTNT-20 — AI Agent điều phối ứng phó sự cố**
- [x] Phân chia vai trò 4 thành viên theo năng lực thực tế
- [x] Viết README của đội (problem / solution / target user / features / phân vai) — deliverable #2
- [x] Vẽ architecture diagram thật (3 sơ đồ Mermaid) + `ARCHITECTURE.md` + 3 ADR — deliverable #3
- [x] Chốt 4 contract giữa 4 người để làm song song được từ tuần 2
- [x] Setup môi trường Python 3.11 — cả 4 người (bằng chứng: Trung, Long, Việt đều đã push code chạy được)
- [x] Cài `pre-push` hook — Đức ✅, Việt ✅, Trung ✅ (cả hai đều đã *sửa* `_pyrun.sh`, tức đã chạy hook và gặp lỗi), **Long chưa có dấu vết**

### Đã hoàn thành
- Trung khởi tạo repo từ template AI20K (`7b59cf7`); Long tạo branch `docs`, cập nhật worklog và merge PR #2 (`9c1cfd0`); Việt tạo branch `viet` và fix pre-push hook cho Git Bash trên Windows (CRLF → LF)
- Đức đọc trọn 10 chương guidebook + topic sections (code-style, anti-patterns, deliverables checklist), cài `pre-push` hook, tạo `.env`, tạo branch `develop` và gộp work của Việt

### Khó khăn & Giải pháp
| Khó khăn | Giải pháp | Kết quả |
|----------|-----------|---------|
| `scripts/setup_hooks.sh` chưa ai chạy sau khi clone → `.git/hooks/pre-push` không tồn tại. AI log vẫn ghi vào `.ai-log/session.jsonl` (qua hook của Claude Code) nhưng **không bao giờ được submit** lên grading server | Chạy `bash scripts/setup_hooks.sh`, verify hook tồn tại và executable | Log tự submit từ lần `git push` kế tiếp — cứu deliverable #4 |
| Chưa có `.env` nên `submit_log.py` không đọc được `AI_LOG_SERVER` / `AI_LOG_API_KEY` | `cp .env.example .env` | `.env` đã tạo (gitignored); còn phải điền `OPENAI_API_KEY`, `LANGCHAIN_API_KEY`, `AI_LOG_API_KEY` riêng của đội |
| 4 người làm trên 3 branch cá nhân (`docs`, `viet`) không có điểm gộp → WORKLOG.md lệch 19 dòng giữa Long và Việt chỉ sau 1 ngày. Thêm nữa CI (`.github/workflows/ci.yml`) chỉ trigger trên `[main, develop]` nên **không branch nào của đội được CI kiểm tra** | Tạo `develop` làm branch tích hợp, merge `viet` vào, gộp worklog của cả 3 người | `develop` có đủ work của cả đội và được CI chạy lint + test |
| Repo có 2 root commit khác nhau: `539c3d1` (bot của BTC, 23/07) và `7b59cf7` (Trung, 26/07) — do làm bước `rm -rf .git && git init` trên repo BTC đã tạo sẵn history | Merge chấp nhận cả 2 nhánh gốc, không rewrite history | History hơi rối nhưng không ảnh hưởng chức năng; tránh lặp lại bước này |
| `develop` tạo hôm 27/07 nhưng **chưa bao giờ được push** — `git ls-remote` chỉ có `docs`, `main`, `viet`. Hệ quả: 5 commit (gồm toàn bộ work của Việt) chỉ nằm trên 1 laptop, CI vẫn chưa chạy lần nào vì workflow chỉ trigger trên push vào `[main, develop]`, và 3 người kia không thấy branch để base từ đó | `git push -u origin develop` | `origin/develop` tồn tại, CI chạy lần đầu và **pass** (run `30346591635`, 28s), 39 AI log entry được submit (`→ 202`) |
| CI chỉ trigger `pull_request` vào `main`, nên PR `feature/*` → `develop` theo đúng workflow guidebook lại **không có lint/test gác cửa** — lỗi chỉ lộ sau khi đã merge | Thêm `develop` vào `pull_request.branches` trong `ci.yml` | PR vào `develop` được kiểm tra trước lúc merge |
| `.env` đã có `LANGCHAIN_API_KEY` nhưng trace không tới LangSmith: `pydantic-settings` chỉ nạp `.env` vào object `Settings`, **không set `os.environ`** — mà LangChain/LangGraph đọc thẳng từ `os.environ` | Thêm `configure_tracing()` export config sang `os.environ`, gọi trong `lifespan` và in rõ `tracing: on/off` lúc khởi động | Deliverable #4 không còn fail âm thầm |
| Cách chia 4 phần đều trong đề bài giả định 4 engineer tương đương, nhưng thực tế đội có 2 người mạnh (Đức, Việt) và 2 người còn ít kinh nghiệm (Long, Trung) → chia đều sẽ tắc ở người yếu, hoặc họ ngồi chờ rồi dồn việc vào tuần cuối | Chia lại theo năng lực + chọn phần việc cho Long/Trung theo 3 tiêu chí: biên rõ ràng, không chặn ai, có tài liệu tham khảo sẵn. Long dùng **Streamlit thay Next.js**. Giao Long và Trung sở hữu hẳn deliverable phi-code (video/pitch deck, eval evidence) | Phân vai chốt trong README; 4 workstream chạy song song được từ tuần 2 |

### Bài học
- Các bước setup "một lần duy nhất" (như `setup_hooks.sh`) rất dễ bị bỏ qua và **fail âm thầm** — không có thông báo nào cho biết log không được submit. Phải verify bằng artifact thật (`ls .git/hooks/pre-push`), không tin là "chắc đã làm rồi".
- Đội nhiều người mà không có branch tích hợp thì file tài liệu chung (WORKLOG) lệch nhau ngay ngày đầu. Branch `develop` không phải thủ tục hình thức — nó là chỗ duy nhất được CI kiểm tra trong config hiện tại.
- Guidebook nói rõ điểm mất nhiều nhất không phải do code kém mà do **thiếu deliverables** (đa số đội chỉ nộp ~5/10). WORKLOG / JOURNAL / CI / tests / evaluation là điểm dễ ăn nếu làm đều từ đầu thay vì dồn tuần cuối.
- Không viết agent logic trước khi xong thiết kế kiến trúc (Chương 3) — code không có thiết kế là code sẽ phải viết lại.
- **Tạo branch chưa phải là xong — phải push.** `develop` tồn tại 1 ngày trên local mà cả đội tưởng đã có. Cùng một loại lỗi với `setup_hooks.sh`: việc "làm một lần" fail âm thầm. Cách kiểm tra đúng là hỏi remote (`git ls-remote --heads origin`), không phải `git branch` local.
- **Đội lệch trình độ thì vỡ ở đường ghép, không vỡ ở từng module.** Vì vậy lead nên giữ phần contract + tích hợp thay vì nhận module khó nhất, và phải chốt interface trước để mọi người code với mock của nhau — nếu không, người làm UI sẽ ngồi chờ 3 tuần rồi làm gấp trong 1 tuần.
- **Chọn công cụ theo người dùng nó, không theo công cụ tốt nhất.** Next.js tốt hơn Streamlit về mọi mặt kỹ thuật, nhưng với người code còn yếu thì nó là 2 tuần không ra kết quả. Status page xấu vẫn tính là có; status page không tồn tại là mất một yêu cầu Cơ bản.
- **Contract là thứ mở khoá làm song song, và phải viết trước logic.** Bốn workstream của đề bài có chuỗi phụ thuộc Trung → Việt → Đức → Long; để tự nhiên thì Long ngồi chờ tới tuần 4 rồi làm gấp trong 1 tuần. Chốt 4 interface trước (kèm `FakeJiraClient` và fixture JSON) thì cả 4 người bắt đầu cùng ngày. Chi phí ~250 dòng, gần như toàn bộ là khai báo type.
- **Ràng buộc bắt buộc nên được thực thi bằng cấu trúc, không bằng thiện chí.** HITL không nằm ở chỗ "nhớ đừng cho Agent tự duyệt" mà ở chỗ `JiraClient` không có method nào duyệt, và `FakeJiraClient.transition(..., REMEDIATING)` raise `PermissionError`. Viết sai luồng thì CI đỏ ngay, không phải phát hiện lúc demo.
- **Contract dễ vỡ nhất là contract không báo lỗi.** Nếu Trung đặt tên metric khác với câu PromQL Việt viết, Prometheus trả về kết quả rỗng chứ không phải exception — Agent im lặng không phát hiện gì và không có gì để lần theo. Vì vậy tên metric và label được chốt thành văn bản trước khi ai viết code.
- **Đặc tả sai thì người làm theo đúng vẫn ra bug — và lỗi thuộc về người viết đặc tả.** TODO tôi viết trong skeleton ghi `POOL_SIZE - pool.get_idle_size()`, Trung làm theo chính xác, kết quả gauge báo pool cạn 100% vĩnh viễn sau một request. Đúng phải là `pool.get_size()` vì pool khởi động với `min_size=1`. Bài học kép: (a) khi viết TODO cho người khác thì phải **chạy thử công thức mình đưa ra**, đừng viết từ suy luận; (b) khi review thì **đo, đừng đọc** — bug này không thể phát hiện bằng cách đọc code, phải dựng Postgres lên và curl.
- **Hai người sửa cùng một file dùng chung theo hai hướng ngược nhau.** Trung và Việt đều vá `scripts/_pyrun.sh` cho vấn đề Python trên Windows. Việt thêm `--version` để loại alias giả của Windows Store, giữ nguyên fallback cho macOS/Linux. Trung thay cả chuỗi bằng đường dẫn `.venv` và bỏ fallback — làm hook chết im lặng trên máy khác. Không ai sai về ý định, nhưng thiếu một quy tắc: **file dùng chung thì phải nói trong group trước khi sửa**, vì người sửa chỉ thấy máy của mình.
- **Review là chỗ contract chứng minh giá trị lần thứ hai.** Contract ① giúp 4 người làm song song (giá trị thứ nhất), rồi chính nó cho Việt cơ sở để đo và bắt được 4 lỗi trong đặc tả trước khi ai xây lên (giá trị thứ hai). Cả hai lần đều là lỗi của tôi, và cả hai lần đều được bắt trước khi thành đắt.
- Dọn dẹp cho "gọn" (xoá branch đã merge, đổi default branch) nghe hợp lý nhưng phải cân với cái giá thật: branch biến mất dưới tay người chưa quen Git là lỗi mất cả buổi, còn đổi default sang `develop` sẽ khiến `main` stale suốt 5 tuần — trái với chương 2 (`main` luôn ổn định, deploy được). Giữ `main` làm default và merge `develop` → `main` cuối mỗi tuần.

### Kết quả tuần 1

Toàn bộ việc code/spike của cả 4 người **đã xong**. Ba trong bốn deliverable dễ mất điểm nhất đã có: README (#2), Architecture + 3 ADR (#3), Live URL (#5).

| Người | Kết quả |
|---|---|
| Đức | Contract ①–④, kiến trúc + 3 ADR, deploy Render, Jira Cloud, `RealJiraClient`, cổng HITL, `POST /webhooks/jira`, scaffolding 3 thư mục |
| Việt | Spike Prometheus/PromQL — verify được kiến trúc không phải đổi, **và tìm ra 4 lỗi trong contract ①** |
| Trung | 2 service demo có nút cổ chai thật, `seed.py`, `loadtest.py` (PR #4, đang sửa 3 điểm) |
| Long | 2 trang UI hoàn chỉnh — **đi trước lịch**, kế hoạch là tuần 2–3 |

Cổng HITL đã verify trên Jira thật, không phải mock: Agent tự chuyển sang `Remediating` → Jira cho chuyển (team-managed không chặn được) → backend đọc changelog, thấy tác giả là Agent và **từ chối thi hành**.

Còn tồn sang tuần 2: `main` thiếu 28 commit so với `develop` (chưa mở PR đóng tuần), PR #4 chờ Trung sửa, Việt chưa mở PR cho `_pyrun.sh`, và chưa xác nhận hook của Long.

### Kế hoạch tuần 2 (02/08 – 08/08)

**Đường găng: Agent.** Ba khối kia đã có, cái nối chúng lại vẫn trống.

- [ ] **Việt — `src/services/prometheus.py`**: chuyển `PrometheusQuerier` từ `spike/spike_promql.py` sang. Gần như copy, làm trước vì mọi thứ sau phụ thuộc nó
- [ ] **Việt — `src/services/rules.py`**: `detect()`, `classify_severity()`, `is_spreading()`. Rule thuần, không LLM, để đo được độ chính xác
- [ ] **Việt — 3 node đầu**: `detect` → `classify_severity` → `open_war_room`, chạy với `FakeJiraClient`
- [ ] **Trung — sửa 3 điểm PR #4** rồi merge, sau đó chạy `loadtest.py` và **ghi lại mức tải làm p95 vượt 2s** vào `demo/README.md`
- [ ] **Long — video demo + pitch deck** (deliverable #6, #7), dùng sơ đồ sequence 22 bước làm storyboard
- [ ] **Đức — nối end-to-end**: cấu hình Jira Automation rule gọi webhook, chạy thử trọn luồng duyệt → thi hành
- [ ] **Đức — `docs/use-cases.md`**: chốt dưới 3 UC theo góp ý mentor (cạn pool · OOM restart · burst xác thực)
- [ ] Hỏi mentor: `MIE`/`MIP` là viết tắt gì, và tấn công dạng metric-visible có được chấp nhận
- [x] **Chuỗi HITL end-to-end thông trên Jira thật** (02/08, `KAN-11`) — vượt mốc kiểm tra giữa tuần
- [ ] Nối Prometheus thật vào Agent: `detect` đọc PromQL → mở Jira issue, chưa qua script tay

---

## Week 2: 2026-08-02 - 2026-08-08

### Mục tiêu tuần này

**Đường găng: Agent.** Ba khối kia đã có, cái nối chúng lại vẫn trống.

- [x] **Đức — bổ sung tài liệu Gate 1**: Brief, PRD, UI Flow + bảng link ở đầu README
- [ ] **Việt — `src/services/prometheus.py`**: chuyển `PrometheusQuerier` từ `spike/spike_promql.py` sang
- [ ] **Việt — `src/services/rules.py`**: `detect()`, `classify_severity()`, `is_spreading()` — rule thuần, không LLM
- [ ] **Việt — 3 node đầu**: `detect` → `classify_severity` → `open_war_room`, chạy với `FakeJiraClient`
- [ ] **Trung — sửa 3 điểm PR #4** rồi merge, chạy `loadtest.py` và ghi lại mức tải làm p95 vượt 2s vào `demo/README.md`
- [ ] **Long — video demo + pitch deck** (deliverable #6, #7), dùng sơ đồ sequence làm storyboard
- [ ] **Đức — nối end-to-end**: cấu hình Jira Automation rule gọi webhook, chạy thử trọn luồng duyệt → thi hành
- [ ] Hỏi mentor: `MIE`/`MIP` là viết tắt gì, và tấn công dạng metric-visible có được chấp nhận
- [x] **Chuỗi HITL end-to-end thông trên Jira thật** (02/08, `KAN-11`) — vượt mốc kiểm tra giữa tuần
- [ ] Nối Prometheus thật vào Agent: `detect` đọc PromQL → mở Jira issue, chưa qua script tay

### Đã hoàn thành
- **02/08 — Ba tài liệu Gate 1** ([`docs/brief.md`](docs/brief.md), [`docs/prd.md`](docs/prd.md), [`docs/ui-flow.md`](docs/ui-flow.md)) và bảng "Tài liệu nộp" ở đầu README. Kiến trúc, README, AI log hook đã có sẵn từ tuần 1 nên chỉ thiếu đúng 3 thứ này.

### Khó khăn & Giải pháp
| Khó khăn | Giải pháp | Kết quả |
|----------|-----------|---------|
| Tài liệu nằm rải khắp repo (ADR, contracts, use-cases, architecture) nhưng mentor mở repo ra không có đường vào — README chỉ dẫn link lẻ trong từng đoạn văn | Thêm bảng "Tài liệu nộp" ngay đầu README, mỗi dòng một tài liệu kèm mô tả một câu | Mở repo là thấy toàn bộ deliverable, không phải đọc hết README để nhặt link |
| Quyết định "war room không có nút duyệt" nằm trong code từ tuần 1 nhưng **không ở đâu ghi lý do** | Viết thành mục riêng trong `ui-flow.md` kèm sequence diagram | Người review đọc được là quyết định có chủ đích, không phải quên làm |

### Bài học
- **Viết PRD sau khi đã code một phần thì phát hiện được thứ mà lúc thiết kế không thấy.** Đi ngược từ code lên tiêu chí nghiệm thu làm lộ ra những quyết định đã cài trong code nhưng chưa được viết ra ở đâu — như chuyện UI cố ý không có nút duyệt. Thứ không được viết ra thì người review đọc thành thiếu sót, và người mới vào sẽ "sửa" nó.
- **Chốt ground truth trước là điều kiện để phép đo có nghĩa.** `use-cases.md` viết ngày 30/07, trước `rules.py`. Nếu chạy Agent xong mới ghi "nguyên nhân gốc là gì" thì độ chính xác luôn 3/3 và không đo gì cả. Thứ tự chính là toàn bộ giá trị.
- **Rủi ro nguy hiểm nhất của dự án này đều thuộc họ "fail âm thầm".** Metric lệch tên → Prometheus trả rỗng chứ không lỗi. Rollback chỉ ghi log → `verify` không hồi phục → lặp vô hạn giữa buổi demo. Không cái nào ném exception, nên không cái nào chặn được bằng cách "nhớ kiểm tra lúc test" — phải viết thành tiêu chí nghiệm thu trước.

### Kế hoạch tuần sau
-

---

<!-- Tiếp tục copy block trên cho Week 3, 4, 5, 6 -->
