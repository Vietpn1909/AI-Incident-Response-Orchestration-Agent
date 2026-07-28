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
| Long / Trung / Việt | Cài `pre-push` hook trên clone của mình (`bash scripts/setup_hooks.sh`) | ⏳ Todo | verify `ls -l .git/hooks/pre-push` | - |
| Long / Trung / Việt | Setup venv 3.11 + chạy được `localhost:8000/docs` | ⏳ Todo | screenshot | - |
| Việt | Spike: docker-compose Prometheus + dummy service, query PromQL từ Python | ⏳ Todo | script in ra avg latency | - |
| Trung | Task probe: `service-thanh-toan` (FastAPI, `POST /pay`, Postgres, pool = 5, `/metrics`) | ⏳ Todo | `curl` được + `/metrics` có `http_request_duration_seconds` | - |
| Long | Streamlit status page hardcode 2 service (xanh/đỏ) | ⏳ Todo | `streamlit run` mở được trang | - |

**Tổng kết ngày:** Chốt đề tài và phân vai — bỏ cách chia 4 phần đều trong đề bài vì đội có 2 người mạnh và 2 người ít kinh nghiệm; phần mơ hồ dồn cho Đức/Việt, phần biên rõ và không chặn ai giao Trung/Long, kèm quyền sở hữu deliverable phi-code để 2 bạn đóng góp vào điểm số. Phát hiện `develop` tạo hôm 27/07 nhưng chưa push → cả đội tưởng đã có branch tích hợp, và CI chưa chạy lần nào. Sau khi push, CI pass lần đầu và 39 AI log entry được submit. Cùng loại lỗi "việc làm một lần fail âm thầm" như `setup_hooks.sh` hôm qua — lần này 3 người còn lại vẫn chưa cài hook, là việc gấp nhất còn lại của tuần.

---

## [YYYY-MM-DD]

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| | | | | |

**Tổng kết ngày:**

---

<!-- Format: copy block trên cho mỗi ngày làm việc -->
