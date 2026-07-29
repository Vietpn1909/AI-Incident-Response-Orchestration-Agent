# Bắt đầu từ đây — việc của từng người

> Mở file này trước khi code. Tìm mục tên mình, làm đúng phần đó.
> Đề tài đã chốt: **PTNT-20 — AI Agent điều phối ứng phó sự cố**. Xem [README.md](../README.md) để hiểu sản phẩm là gì.

---

## Phần 0 — Cả 4 người, làm trước hết ngày 29/07

### 1. Cài AI logging hook ⚠️ GẤP NHẤT

```bash
git fetch origin
git checkout develop
bash scripts/setup_hooks.sh
ls -l .git/hooks/pre-push          # phải thấy file, và có chữ x (executable)
```

**Chụp output dòng `ls -l` gửi vào group.**

Vì sao gấp: `.git/hooks/` **không nằm trong repo**, nên mỗi người phải tự cài trên máy mình. Thiếu hook thì mọi prompt AI của bạn chỉ ghi vào máy và **không bao giờ gửi lên server chấm điểm** — mất deliverable #4 mà không có cảnh báo gì. Đây là lỗi đội đã mắc một lần rồi.

### 2. Chạy được server

```bash
python3.11 -m venv .venv
source .venv/bin/activate           # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                # rồi điền OPENAI_API_KEY
uvicorn src.main:app --reload --port 8000
```

Mở http://localhost:8000/docs → **chụp màn hình gửi group**.

Thử luôn 2 endpoint này, chúng đã có dữ liệu thật:

```bash
curl localhost:8000/api/status
curl localhost:8000/api/incidents
```

### 3. Luật làm việc

```bash
git checkout develop && git pull origin develop
git checkout -b feature/<tên-việc>
# code, commit theo format: type(scope): mô tả ngắn
git push origin feature/<tên-việc>
# rồi mở PR trên GitHub: feature/* → develop
```

- **Không push trực tiếp lên `develop` hay `main`.** Luôn qua PR.
- Branch cá nhân cũ (`viet`, `docs`) **ngừng dùng**, từ giờ mọi thứ base từ `develop`.
- Commit message: `feat:` thêm tính năng · `fix:` sửa lỗi · `docs:` tài liệu · `test:` test · `chore:` việc phụ.
- Ghi việc mình làm vào [WORKLOG.md](../WORKLOG.md) mỗi ngày. Đây là deliverable được chấm, không phải thủ tục.

### 4. Backend đã deploy — dùng URL này khi cần

```
https://p-035-incident-agent.onrender.com
```

Long có thể trỏ Streamlit vào đây thay vì `localhost:8000` nếu không muốn chạy backend local:

```python
API = "https://p-035-incident-agent.onrender.com"   # hoặc "http://localhost:8000"
data = requests.get(f"{API}/api/status").json()
```

⚠️ Free tier **tự ngủ sau 15 phút** không có request, request đầu tiên sau đó mất 50 giây hoặc hơn. Gọi `/health` một lần cho service tỉnh trước khi làm việc thật.

### 5. Vì sao có repo thứ hai (`TruongDuke/P-035-deploy`)

Render deploy code từ repo `TruongDuke/P-035-deploy`, **không phải** từ repo org. Lý do: Render dùng GitHub App, mà cài GitHub App lên repo org cần quyền `admin` — cả 4 thành viên đều chỉ có `push` vì repo do bot của BTC tạo. Thay vì chờ BTC approve, deploy từ repo mirror cá nhân (Đức có admin ở đó) nên **không cần xin quyền gì**.

**Repo org vẫn là nguồn chính** — mọi người làm việc, mở PR, nộp bài ở đó. Repo mirror chỉ để Render pull code, đã tắt GitHub Actions.

⚠️ **Cạm bẫy:** khi merge PR trên web GitHub, commit đó **không đi qua máy ai cả**, nên mirror bị tụt lại và Render tiếp tục chạy code cũ — mà dashboard vẫn báo deploy thành công. Sau mỗi lần merge PR, người merge phải chạy:

```bash
git checkout develop && git pull && git push origin develop
```

Máy của Đức đã cấu hình `git push origin` đẩy tới cả hai repo trong một lệnh. Ai cần làm việc này trên máy mình thì chạy:

```bash
git remote set-url --add --push origin https://github.com/AI20K-Build-Phase-Cohort-3/P-035.git
git remote set-url --add --push origin https://github.com/TruongDuke/P-035-deploy.git
```

Nếu sau này BTC cấp quyền admin repo org thì đổi Blueprint sang repo org và bỏ mirror đi — nhưng không gấp, hiện tại đã chạy được.

### 6. Không tự sửa 4 file contract

Bốn file này là thoả thuận giữa nhiều người. Sửa một mình sẽ làm vỡ code người khác:

- `docs/contracts/01-metrics.md`
- `src/models/incident.py`
- `src/services/jira/client.py`
- `src/api/incidents.py`

Cần đổi thì nói trong group, mở PR riêng, người ở đầu kia review. Chi tiết: [docs/contracts/](contracts/).

---

## Trung — Service demo & tải

**Vai trò:** Backend Engineer · QA
**Sở hữu:** 2 service demo, script load test, bảng deploy history, test suite, evaluation evidence (deliverable #10)

### Đọc

[docs/contracts/01-metrics.md](contracts/01-metrics.md) — bắt buộc. File này quy định tên metric bạn phải expose. Nếu đặt tên khác, Agent của Việt sẽ **không phát hiện được gì mà cũng không báo lỗi**, rất khó tìm ra.

### Việc tuần này (28–31/07)

Viết `service-thanh-toan`:

- FastAPI, endpoint `POST /pay`, ghi vào Postgres thật
- **Connection pool giới hạn đúng 5** — đây là nút cổ chai cố ý, không phải nhầm
- Expose `/metrics` bằng `prometheus-fastapi-instrumentator`
- Thêm tay 2 metric: `db_pool_connections_in_use` và `db_pool_size` (instrumentator không có sẵn 2 cái này, mà Agent cần chúng để chứng minh nguyên nhân)
- Port `8001`

### Xong là thế nào

```bash
curl -X POST localhost:8001/pay -H "Content-Type: application/json" -d '{"order_id":"1","amount":100}'
curl -s localhost:8001/metrics | grep -E "http_request_duration_seconds_bucket|db_pool"
```

Cả hai lệnh phải ra kết quả. Báo Đức khi xong.

### Tuần 2–3 sẽ làm

`service-dat-hang` (gọi chéo sang service thanh toán), seed dữ liệu Faker, script k6/Locust tăng tải 1k → 100k, bảng `deploy_history`, pytest cho service của mình.

**Vì sao pool = 5:** khi tải cao, request phải xếp hàng chờ connection → latency tăng **thật** do nghẽn cổ chai. Nhờ vậy Agent có nguyên nhân thật để chẩn đoán, thay vì mình tự gán một con số giả. Lý do đầy đủ: [ADR-0003](adr/0003-load-test-that-thay-fault-injection.md).

---

## Việt — Agent phát hiện & chẩn đoán

**Vai trò:** AI Agent Engineer
**Sở hữu:** LangGraph, threshold detection, rule engine, LLM diagnosis, postmortem, correlation deploy

### Đọc

- [docs/contracts/01-metrics.md](contracts/01-metrics.md) — câu PromQL và ngưỡng severity
- [src/models/incident.py](../src/models/incident.py) — model bạn sinh ra
- [src/services/jira/client.py](../src/services/jira/client.py) — cách gọi Jira
- [docs/architecture_diagram.md](architecture_diagram.md) mục 2 — sơ đồ node bạn phải viết

### Việc tuần này (28–31/07)

**Chưa code Agent.** Việc quan trọng nhất là verify giả định kỹ thuật cốt lõi — nếu nó sai thì kiến trúc phải đổi, biết bây giờ tốt hơn biết tuần 3:

1. `docker-compose` local: Prometheus + 1 FastAPI dummy có `prometheus-fastapi-instrumentator`
2. Vào `localhost:9090` xác nhận target **UP**
3. Viết script Python query Prometheus HTTP API bằng PromQL

**Xong là thế nào:** chạy `python spike_promql.py` in ra được `avg latency = 0.0xx s` của dummy service.

Không cần chờ service của Trung — gán label `service` tuỳ ý cho dummy là được, vì tên metric đã chốt ở contract ① nên query sau này không phải sửa.

### Bạn viết Agent được ngay, không cần Jira

```python
from src.services.jira import FakeJiraClient

jira = FakeJiraClient()              # in ra console, không gọi mạng
key = jira.create_incident(signal)
jira.post_proposal(key, proposal)    # → Awaiting Approval, Agent phải DỪNG
jira.approve_as_human(key)           # mô phỏng người duyệt (chỉ có ở bản giả)
```

Tuần 3 Đức thay bằng `RealJiraClient` — **code Agent của bạn không phải sửa một dòng**.

### Hai điều quan trọng nhất

**1. Rule trước, LLM sau.** Rule engine tìm bằng chứng số (p95 tăng 25 lần, pool cạn lúc 14:32, deploy v1.4.2 lúc 14:28); LLM **chỉ** diễn giải bằng chứng đó thành câu và chọn runbook. Đừng để LLM tự suy luận từ dữ liệu thô — đề bài yêu cầu "chẩn đoán **có bằng chứng**", kết luận không truy vết được về số liệu cụ thể thì không được tính.

**2. Agent không được tự duyệt.** `jira.transition(key, REMEDIATING)` sẽ **raise `PermissionError`** — đó là chủ đích, không phải bug. Chỉ người duyệt trên Jira mới chuyển được bước đó. Đây là ràng buộc bắt buộc của đề bài.

Thêm 2 quy tắc chống nhiễu, thiếu là lúc load test Agent mở hàng loạt incident trùng: chỉ tính incident khi vượt ngưỡng **liên tục ≥ 30s**, và gọi `find_open_incident()` trước khi `create_incident()`.

---

## Long — Giao diện & demo

**Vai trò:** Frontend Engineer · Demo
**Sở hữu:** Status page công khai, war-room view, video demo (deliverable #6), pitch deck (deliverable #7)

### Đọc

[src/api/incidents.py](../src/api/incidents.py) — chỉ cần biết gọi endpoint nào, nhận JSON hình gì. **Không cần hiểu Agent hay Jira.**

### Việc tuần này (28–31/07)

Làm status page bằng **Streamlit** (Python thuần, không phải React — dễ hơn nhiều):

```bash
pip install streamlit requests
```

Tạo `ui/status_page.py`, đọc dữ liệu từ API:

```python
import requests, streamlit as st

data = requests.get("http://localhost:8000/api/status").json()

st.title("Trạng thái dịch vụ")
for svc in data["services"]:
    color = {"operational": "🟢", "degraded": "🟡", "down": "🔴"}[svc["health"]]
    st.write(f"{color} **{svc['name']}** — {svc['message']}")
```

Chạy: `streamlit run ui/status_page.py` (nhớ bật `uvicorn src.main:app --reload` ở terminal khác).

**Xong là thế nào:** mở được trang, thấy 2 service với màu đúng theo `health`.

### Dữ liệu đã có sẵn ngay bây giờ

Bạn không phải chờ ai. Ba endpoint này đã trả dữ liệu thật:

| Endpoint | Trả về |
|---|---|
| `GET /api/status` | 2 service + trạng thái, dùng cho status page |
| `GET /api/incidents` | Danh sách 3 incident, dùng cho war-room view |
| `GET /api/incidents/INC-12` | Chi tiết 1 incident: giả thuyết, bằng chứng, timeline |

Hiện là dữ liệu mẫu, tuần 3 Đức đổi sang dữ liệu thật — **hình dạng JSON không đổi nên UI của bạn không phải sửa**.

Xem trước JSON: `curl localhost:8000/api/status` hoặc mở http://localhost:8000/docs bấm "Try it out".

### Tuần 2–3 sẽ làm

War-room view (danh sách incident + timeline chi tiết). Gợi ý: incident có `state == "Awaiting Approval"` nên làm nổi bật, vì đó là lúc đang chờ người xử lý.

### Việc riêng của bạn: video + pitch deck

Bắt đầu nghĩ từ giờ, đừng để tuần cuối. Kịch bản demo đã có sẵn dạng sơ đồ ở [docs/architecture_diagram.md](architecture_diagram.md) mục 3 — 22 bước theo thứ tự, dùng luôn làm storyboard.

Xuất hình sơ đồ ra PNG cho slide:

```bash
npx -y -p @mermaid-js/mermaid-cli mmdc -i docs/architecture_diagram.md -o out.md -e png -w 2200
```

---

## Đức — Lead, tích hợp & DevOps

**Sở hữu:** Contract, `JiraClient`, DevOps (Docker/CI/Render/webhook), tích hợp cuối

### Việc tuần này

- [x] Deploy `/health` lên Render → https://p-035-incident-agent.onrender.com
- [x] `RealJiraClient` + cổng HITL — đã verify trên Jira thật
- [x] `POST /webhooks/jira` — nhận trigger sau khi duyệt, 3 lớp bảo vệ
- [ ] Tạo Jira Cloud workspace + workflow — làm theo [docs/jira-setup.md](jira-setup.md)
- [ ] Cấu hình Jira Automation rule gọi webhook (xem [jira-setup.md](jira-setup.md) Phần 5) + **verify quota free plan (~100 lần/tháng)**
- [ ] Pair với Trung phần cấu hình Jira (đừng giao khoán — chỗ này encode HITL, sai là sai ràng buộc cứng)
- [ ] Cuối 30/07 xem kết quả task probe của Trung để quyết phần việc tuần 2
- [ ] Cuối tuần mở PR `develop` → `main`

---

## Bị tắc thì làm gì

1. Đọc lại phần contract của mình — phần lớn câu hỏi "cái này trả về gì" đã có câu trả lời ở đó
2. Nhắn group kèm **lệnh đã chạy + lỗi đầy đủ**, đừng chỉ nói "không chạy được"
3. Tắc quá 30 phút thì nhắn luôn, đừng ngồi một mình cả buổi

Xem thêm: [docs/guide/troubleshooting.md](guide/troubleshooting.md)
