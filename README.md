# AI Agent Điều Phối Ứng Phó Sự Cố (Incident Response)

> Sự cố hạ tầng được ứng phó thủ công nên chậm → AI Agent tự phát hiện, mở war room, chẩn đoán có bằng chứng và điều phối khắc phục **dưới sự phê duyệt của con người** → dành cho đội on-call vận hành nền tảng.

**Team Binary Brothers** · Đề bài **PTNT-20** — Khối PTNT (Kiến trúc & Tích hợp)

🌐 **Live:** https://p-035-incident-agent.onrender.com · [API docs](https://p-035-incident-agent.onrender.com/docs) · [status page (JSON)](https://p-035-incident-agent.onrender.com/api/status)

> 👋 **Thành viên đội: mở [docs/START-HERE.md](docs/START-HERE.md) trước khi code** — việc của từng người, lệnh cụ thể, và tiêu chí "xong là thế nào".

---

## Vấn đề (Problem)

Khi một dịch vụ tích hợp của nền tảng sập hoặc độ trễ tăng vọt, quy trình ứng phó hiện tại hoàn toàn thủ công: tập hợp người, dò log từng service, cập nhật trạng thái bằng tay.

- **Ai gặp vấn đề:** đội on-call / Incident Commander vận hành nền tảng
- **Tốn gì:** thời gian chết của dịch vụ kéo dài vì phần lớn thời gian đầu incident dành cho *thu thập bối cảnh*, không phải *khắc phục*
- **Vì sao giải pháp hiện tại chưa đủ:** công cụ monitor chỉ báo "có gì sai", không tổng hợp bối cảnh, không đề xuất giả thuyết nguyên nhân, không điều phối hành động và không tự sinh postmortem

## Giải pháp (Solution)

AI Agent điều phối trọn vòng đời incident, con người giữ quyền quyết định:

- **Phát hiện & phân loại severity** — query Prometheus theo PromQL, so baseline bằng rule engine trước khi đưa vào LLM
- **Tự mở war room** — tạo Jira Issue + comment thread cập nhật realtime
- **Thu thập bối cảnh** — metric, log, và đối chiếu lịch sử deploy gần đây
- **Chẩn đoán có bằng chứng** — giả thuyết nguyên nhân kèm số liệu dẫn chứng, gợi ý runbook
- **HITL bắt buộc** — mọi hành động khắc phục production phải qua bước `Awaiting Approval`; backend xác minh qua Jira changelog rằng người duyệt không phải Agent, nếu là Agent thì từ chối thi hành
- **Phát hiện lan truyền** — nhận biết sự cố lây sang dịch vụ phụ thuộc và link các incident
- **Status page công khai** — trạng thái dịch vụ tự cập nhật theo incident
- **Postmortem tự động** — sinh timeline, nguyên nhân, action item khi đóng incident

## Target User

- **Primary:** Kỹ sư on-call / Incident Commander — cần giảm thời gian từ lúc có tín hiệu đến lúc bắt đầu khắc phục
- **Secondary:** Người dùng nội bộ & khách hàng — xem status page để biết dịch vụ nào đang ảnh hưởng

## Team & Phân vai

| Member | Vai trò | Sở hữu | Student ID |
|--------|---------|--------|-----------|
| **Trương Công Thái Đức** | Team Lead · Kiến trúc & Tích hợp | Contract/schema giữa các module, `JiraClient` API layer, DevOps (Docker, CI, deploy Render, webhook), tích hợp cuối | 2A202601581 |
| **Việt** | AI Agent Engineer | LangGraph orchestration, threshold detection, rule engine so baseline, LLM diagnosis + runbook, sinh postmortem, correlation deploy | _cần bổ sung_ |
| **Trung** | Backend Engineer · QA | 2 service demo (order + payment, giới hạn connection pool), script load test k6/Locust, bảng deploy history, test suite + evaluation evidence | _cần bổ sung_ |
| **Phan Hoàng Long** | Frontend Engineer · Demo | Status page công khai (Streamlit), war-room view, video demo + pitch deck | _cần bổ sung_ |

Phân vai dựa trên năng lực thực tế của từng người, không chia đều 4 phần: phần mơ hồ nhất (chẩn đoán, orchestration, tích hợp) dồn cho Đức và Việt; phần có biên rõ ràng và không chặn ai (service demo, UI) giao cho Trung và Long. Chi tiết lý do ở [JOURNAL.md](JOURNAL.md).

## Kiến trúc — quyết định chính

Ba quyết định định hình toàn bộ dự án (ADR chi tiết trong [docs/](docs/)):

| Quyết định | Lựa chọn | Lý do |
|---|---|---|
| Lớp quản lý vòng đời incident | **Jira Cloud** (workspace miễn phí riêng, không dùng Jira tổ chức) | War room = Issue, audit trail = changelog, action item = sub-task — không phải tự xây CRUD + phân quyền + audit từ đầu |
| Thực thi HITL | **Backend kiểm tra changelog Jira**, không dùng phân quyền workflow | Jira Cloud bản mới chỉ tạo được team-managed project, loại này không đặt được điều kiện lên transition. Backend hỏi *ai* đã duyệt, là Agent thì từ chối — đã verify trên Jira thật |
| Alerting | **Prometheus, không dùng Alertmanager** | Logic ngưỡng nằm thẳng trong code Agent để kiểm soát được và tích hợp trực tiếp với LangGraph |
| Cách tạo sự cố để demo | **Load test thật (k6/Locust), không fault injection giả** | Giới hạn connection pool ở 5 → tải cao làm request xếp hàng → latency tăng do nghẽn cổ chai thật, và service phụ thuộc timeout theo một cách tự nhiên |

Luồng end-to-end: load test → pool cạn → Prometheus ghi nhận → Agent phát hiện vượt ngưỡng & phân loại severity → tạo Jira Issue + comment bối cảnh → đối chiếu deploy history, sinh giả thuyết + runbook → phát hiện lan truyền, link issue → **on-call duyệt** → webhook → Agent thực thi remediation → status page cập nhật → sinh postmortem.

📐 Sơ đồ đầy đủ: [docs/architecture_diagram.md](docs/architecture_diagram.md) (container · agent flow · sequence) · Chi tiết thành phần: [ARCHITECTURE.md](ARCHITECTURE.md) · Interface giữa 4 người: [docs/contracts/](docs/contracts/) · **3 use case sự cố: [docs/use-cases.md](docs/use-cases.md)**

### Trong phạm vi MVP vs. tuỳ chọn

**MVP:** phát hiện & phân loại · war room · thu thập bối cảnh · chẩn đoán + runbook · HITL · status page · correlation deploy · escalation · postmortem · phát hiện lan truyền

**Tuỳ chọn (chỉ làm nếu còn thời gian):** học từ incident cũ qua JQL · Grafana dashboard

## Tech Stack

| Layer | Technology |
|-------|-----------|
| AI Agent | LangGraph + LangChain |
| LLM | Qwen (Alibaba Cloud Model Studio) qua endpoint tương thích OpenAI |
| Backend | FastAPI + Python 3.11 |
| Observability | Prometheus + `prometheus-fastapi-instrumentator` |
| Incident lifecycle | Jira Cloud REST API + Workflow + Automation |
| Frontend | Streamlit (status page + war-room view) |
| Database | PostgreSQL |
| Load testing | k6 hoặc Locust |
| DevOps | Docker + GitHub Actions + Render |

## Quick Start

```bash
# 1. Clone và vào repo
git clone https://github.com/AI20K-Build-Phase-Cohort-3/P-035.git
cd P-035

# 2. Cài AI logging hook — BẮT BUỘC, mỗi người chạy một lần trên clone của mình
bash scripts/setup_hooks.sh
ls -l .git/hooks/pre-push        # verify: file phải tồn tại và executable

# 3. Cấu hình biến môi trường
cp .env.example .env             # rồi điền OPENAI_API_KEY

# 4. Cài dependencies
# macOS / Linux
python3.11 -m venv .venv && source .venv/bin/activate
# Windows (PowerShell hoặc Git Bash)
#   py -3.11 -m venv .venv
#   .venv\Scripts\activate
pip install -r requirements.txt

# 5. Chạy server
uvicorn src.main:app --reload --port 8000
# Swagger UI: http://localhost:8000/docs
```

> ⚠️ **Bước 2 không được bỏ qua.** `.git/hooks/` không nằm trong repo nên mỗi clone phải tự cài. Thiếu hook thì AI usage log chỉ ghi local và **không bao giờ submit** lên grading server — mất deliverable #4 mà không có cảnh báo nào.

## Git Workflow

```bash
git checkout develop && git pull origin develop
git checkout -b feature/<tên-tính-năng>
# commit theo format: type(scope): mô tả
git push origin feature/<tên-tính-năng>
# tạo PR: feature/* → develop, cần 1 người review + CI pass
```

- **`main`** — luôn ổn định, deploy được. Không push trực tiếp.
- **`develop`** — branch tích hợp, mọi feature merge vào đây trước. Cuối mỗi tuần mở PR `develop` → `main`.
- **`feature/*`** — một branch cho một tính năng.

## API Endpoints

Hiện có:

| Method | Path | Description | Nguồn dữ liệu |
|--------|------|-------------|---|
| GET | `/health` | Health check | — |
| GET | `/api/status` | Dữ liệu status page công khai | fixture → Jira (tuần 3) |
| GET | `/api/incidents` | Danh sách incident (war-room view), lọc `?only_open=true` | fixture → Jira (tuần 3) |
| GET | `/api/incidents/{jira_key}` | Chi tiết incident: giả thuyết, bằng chứng, timeline, postmortem | fixture → Jira (tuần 3) |
| POST | `/webhooks/jira` | Nhận trigger từ Jira sau khi có người duyệt → thi hành khắc phục | Jira changelog |
| POST | `/api/v1/chat` | Chat với agent (placeholder từ template) | — |
| GET | `/api/v1/status` | Trạng thái agent | — |

Ba endpoint incident **đã trả dữ liệu thật ngay bây giờ** (từ fixture JSON), nên UI build được trước khi Agent và Jira tồn tại. Tuần 3 chỉ đổi nguồn dữ liệu, hình dạng response không đổi — xem [contract ④](src/api/incidents.py).

`POST /webhooks/jira` có **3 lớp bảo vệ**: shared secret → `assert_human_approved()` kiểm changelog Jira → danh sách hành động cho phép. Chi tiết: [src/api/webhooks.py](src/api/webhooks.py).

## Project Structure

Ba khối chạy độc lập nên 4 người sửa cùng lúc không đụng nhau. Mỗi thư mục có `README.md` riêng ghi việc của người sở hữu.

```
├── src/                      # Backend chính — Agent + API        (Đức + Việt)
│   ├── agents/nodes/         #   node LangGraph              → VIỆT
│   ├── api/                  #   routes, webhooks, fixtures  → ĐỨC  ✅
│   ├── models/incident.py    #   schema dùng chung           → ĐỨC  ✅
│   ├── services/
│   │   ├── jira/             #     tích hợp Jira            → ĐỨC  ✅
│   │   ├── hitl.py           #     cổng phê duyệt           → ĐỨC  ✅
│   │   ├── remediation.py    #     thực thi khắc phục       → ĐỨC  ✅
│   │   ├── prometheus.py     #     query PromQL             → VIỆT
│   │   └── rules.py          #     ngưỡng + phân loại       → VIỆT
│   ├── config.py
│   └── main.py
│
├── demo/                     # Hệ thống BỊ sự cố (chỉ chạy local)      → TRUNG
│   ├── service_thanh_toan/   #   POST /pay, pool = 5 cố ý
│   ├── service_dat_hang/     #   POST /orders → gọi chéo
│   ├── seed.py               #   Faker + bảng deploy_history
│   ├── loadtest.py           #   bắn tải tăng dần
│   └── prometheus.yml        #   cấu hình scrape (contract ①)
│
├── ui/                       # 2 trang Streamlit                       → LONG
│   ├── status_page.py        #   trang công khai
│   └── war_room.py           #   trang nội bộ
│
├── eval/                     # Số liệu đo đạc — deliverable #10        → TRUNG
├── tests/                    # 49 test, chạy trong CI
├── docs/                     # Architecture, ADR, contracts, guidebook
├── presentation/             # Video demo + pitch deck                 → LONG
├── docker-compose.demo.yml   # bật demo stack + Prometheus
└── render.yaml               # deploy backend lên Render
```

⚠️ **`src/` và `demo/` không được import nhau** — chỉ nói chuyện qua HTTP và `/metrics`. Backend phải coi 2 service demo như hệ thống bên ngoài, y như production thật. Import nhau thì Agent biết trước đáp án và phần "chẩn đoán" mất ý nghĩa.

## Chạy demo stack (tạo sự cố thật)

```bash
docker compose -f docker-compose.demo.yml up --build
python demo/seed.py            # sinh dữ liệu mẫu, chạy một lần
python demo/loadtest.py         # bắn tải tăng dần
```

Rồi mở http://localhost:9090 và query p95 — xem [demo/README.md](demo/README.md).

## Deliverables Checklist

| # | Deliverable | Vị trí | Phụ trách | Trạng thái |
|---|---|---|---|:---:|
| 1 | Source Code | `src/` | Cả đội | 🔄 |
| 2 | README.md | file này | Đức | ✅ |
| 3 | Architecture Diagram | `docs/architecture_diagram.md` + `ARCHITECTURE.md` + 3 ADR | Đức | ✅ |
| 4 | AI Logs | LangSmith + `.ai-log/` | Đức | 🔄 |
| 5 | Live URL | [p-035-incident-agent.onrender.com](https://p-035-incident-agent.onrender.com) | Đức | ✅ |
| 6 | Video Demo | `presentation/` | Long | ⏳ |
| 7 | Pitch Deck | `presentation/` | Long | ⏳ |
| 8 | Weekly Journal | `JOURNAL.md` | Đức | 🔄 |
| 9 | Worklog | `WORKLOG.md` | Cả đội | 🔄 |
| 10 | Evaluation Evidence | `eval/results/` | Trung | ⏳ |

## Giải thích thuật ngữ

- **War room** — không gian tập trung tạm thời để đội phối hợp xử lý sự cố; ở đây mô phỏng bằng 1 Jira issue + comment thread cập nhật realtime.
- **Postmortem** — báo cáo tổng kết sau sự cố (timeline, nguyên nhân gốc rễ, tác động, action item), theo văn hoá *blameless*.
- **HITL (Human-in-the-loop)** — bắt buộc con người phê duyệt trước khi AI thực hiện hành động có ảnh hưởng thật, ví dụ rollback production.

## Liên kết

- 📖 [Technical Guidebook](https://phoenix.note.transformerlabs.ai/technical-book) — cũng có offline trong `docs/guide/`
- 👨‍🏫 Mentor: Trần Thanh Trung

## License

MIT
