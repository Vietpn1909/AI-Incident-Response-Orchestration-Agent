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
- [ ] Setup môi trường Python 3.11 (venv + dependencies), chạy được server local — **cả 4 người**
- [ ] Cài `pre-push` hook trên clone của Long, Trung, Việt

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
- Dọn dẹp cho "gọn" (xoá branch đã merge, đổi default branch) nghe hợp lý nhưng phải cân với cái giá thật: branch biến mất dưới tay người chưa quen Git là lỗi mất cả buổi, còn đổi default sang `develop` sẽ khiến `main` stale suốt 5 tuần — trái với chương 2 (`main` luôn ổn định, deploy được). Giữ `main` làm default và merge `develop` → `main` cuối mỗi tuần.

### Kế hoạch tuần sau
- [ ] Phân vai 4 người và ghi vào README (deliverable #2 yêu cầu mục team members)
- [ ] Mỗi người tạo venv Python 3.11, `pip install -r requirements.txt`, verify Swagger UI tại `/docs`
- [ ] Chốt đề tài agent + viết PRD
- [ ] Vẽ architecture diagram thật (Mermaid) thay diagram mẫu trong `docs/architecture_diagram.md`
- [ ] Viết 2-3 ADR cho quyết định quan trọng (LLM provider, vector store, streaming hay không)
- [ ] Chuyển hết về workflow `feature/*` → `develop` → `main`, ngừng push lên branch cá nhân
- [ ] Deploy sớm lên Render dù chỉ có endpoint `/health`

---

## Week 2: [Ngày bắt đầu] - [Ngày kết thúc]

### Mục tiêu tuần này
- [ ] [Mục tiêu 1]

### Đã hoàn thành
-

### Khó khăn & Giải pháp
| Khó khăn | Giải pháp | Kết quả |
|----------|-----------|---------|
| | | |

### Bài học
-

### Kế hoạch tuần sau
-

---

<!-- Tiếp tục copy block trên cho Week 3, 4, 5, 6 -->
