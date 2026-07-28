# Architecture Diagram — AI Agent Điều Phối Ứng Phó Sự Cố

Đề bài **PTNT-20** · Team Binary Brothers

Ba sơ đồ dưới đây phục vụ ba mục đích khác nhau: sơ đồ 1 là bản đồ hệ thống **và** bản đồ phân việc, sơ đồ 2 là đặc tả để viết Agent, sơ đồ 3 là kịch bản demo end-to-end.

---

## 1. Container diagram — hệ thống & phân việc

Màu thể hiện người sở hữu. Ai cũng nhìn được phần mình dừng ở đâu và giao tiếp với ai qua interface nào.

```mermaid
graph LR
    subgraph TRUNG["🟦 Trung — Tải & service demo"]
        K6[k6 / Locust<br/>1k → 100k request]
        ORD["service-dat-hang<br/>POST /orders"]
        PAY["service-thanh-toan<br/>POST /pay"]
        PG[("Postgres<br/>pool = 5 cố ý")]
        DEP[("deploy_history<br/>bảng giả lập")]
    end

    subgraph VIET["🟩 Việt — Phát hiện & chẩn đoán"]
        PROM[Prometheus]
        DET["Detector<br/>PromQL + ngưỡng"]
        AGENT["Incident Agent<br/>LangGraph"]
        LLM[LLM]
    end

    subgraph DUC["🟨 Đức — Tích hợp & vòng đời incident"]
        API[FastAPI]
        JC["JiraClient<br/>Protocol"]
        JIRA[["Jira Cloud<br/>Issue · Workflow · Automation"]]
    end

    subgraph LONG["🟪 Long — Giao diện"]
        SP["Status page<br/>công khai"]
        WR["War-room view<br/>nội bộ"]
    end

    ONCALL(["👤 On-call / IC"])

    K6 -->|tăng tải| ORD
    ORD -->|gọi chéo| PAY
    PAY --> PG
    ORD -. "/metrics" .-> PROM
    PAY -. "/metrics" .-> PROM

    PROM -->|"PromQL: p95 > 2s"| DET
    DET -->|"IncidentSignal ①②"| AGENT
    AGENT <-->|"giả thuyết + runbook"| LLM
    DEP -->|"đối chiếu thời gian"| AGENT

    AGENT -->|"③ JiraClient"| JC
    JC <--> JIRA

    ONCALL -->|"✋ DUYỆT (HITL)"| JIRA
    JIRA -. "webhook sau khi duyệt" .-> API
    API -->|"thực thi remediation"| AGENT
    API -->|"④ JSON"| SP
    API -->|"④ JSON"| WR
    ONCALL -->|xem| WR

    style TRUNG fill:#dbeafe,stroke:#3b82f6
    style VIET fill:#dcfce7,stroke:#22c55e
    style DUC fill:#fef9c3,stroke:#eab308
    style LONG fill:#f3e8ff,stroke:#a855f7
    style ONCALL fill:#fee2e2,stroke:#ef4444
```

Bốn số ①②③④ là **4 contract** — xem [docs/contracts/](contracts/). Nhờ có chúng, Long build xong UI mà không cần Agent tồn tại, và Việt viết xong Agent mà không cần Jira tồn tại.

### Ba tầng theo mô hình 3-tier

| Tầng | Thành phần | Ghi chú |
|---|---|---|
| Presentation | Status page, War-room view (Streamlit) | 2 vai trò: on-call/IC xem war room, người xem chỉ thấy status page |
| Application | FastAPI, Incident Agent (LangGraph), Detector, JiraClient | Toàn bộ logic điều phối |
| Data | Postgres (orders/payments/deploy_history), Prometheus TSDB, Jira Cloud | Jira đóng vai trò store cho vòng đời incident |

---

## 2. Agent flow — LangGraph state machine

Đây là đặc tả để viết node. Điểm quan trọng: graph **dừng lại** ở `await_approval` — Agent không có đường đi tiếp nếu không có tín hiệu từ bên ngoài (webhook Jira sau khi người duyệt).

```mermaid
graph TB
    START((START)) --> DETECT[detect<br/>query PromQL, so baseline]
    DETECT --> CHECK{vượt ngưỡng?}
    CHECK -->|không| END1((END))
    CHECK -->|có| SEV[classify_severity<br/>P1..P4 theo rule]

    SEV --> WAR[open_war_room<br/>tạo Jira Issue]
    WAR --> CTX[gather_context<br/>metric, log, service phụ thuộc]
    CTX --> DEPC[correlate_deploy<br/>đối chiếu deploy_history]
    DEPC --> HYPO[hypothesize<br/>rule trước → LLM diễn giải]
    HYPO --> SPREAD{lan sang<br/>service khác?}
    SPREAD -->|có| LINK[link_incidents<br/>Jira issue link]
    SPREAD -->|không| PROP
    LINK --> PROP[propose_remediation<br/>runbook + hành động đề xuất]

    PROP --> WAIT[["await_approval<br/>⏸ GRAPH DỪNG Ở ĐÂY"]]
    WAIT -.->|"webhook: on-call đã duyệt"| EXEC[execute_remediation]
    WAIT -.->|"quá X phút chưa duyệt"| ESC[escalate<br/>tăng severity, thông báo]
    ESC --> WAIT

    EXEC --> VERIFY{metric đã<br/>hồi phục?}
    VERIFY -->|chưa| PROP
    VERIFY -->|rồi| PM[generate_postmortem<br/>timeline, nguyên nhân, action item]
    PM --> END2((END))

    style WAIT fill:#fee2e2,stroke:#ef4444,stroke-width:3px
    style HYPO fill:#dcfce7
    style EXEC fill:#fef9c3
```

### Node và người phụ trách

| Node | Việc | Người |
|---|---|---|
| `detect` | Query PromQL, so với baseline | Việt |
| `classify_severity` | Rule thuần: mức vượt ngưỡng + số service ảnh hưởng → P1..P4 | Việt |
| `open_war_room` | Gọi `JiraClient.create_incident()` | Việt (qua contract ③) |
| `gather_context` | Gom metric liên quan, xác định service phụ thuộc | Việt |
| `correlate_deploy` | So thời điểm incident với `deploy_history` | Việt |
| `hypothesize` | **Rule engine tìm bằng chứng trước**, LLM chỉ diễn giải thành câu | Việt |
| `link_incidents` | `JiraClient.link_issues()` khi phát hiện lan truyền | Việt |
| `propose_remediation` | Chọn runbook, post comment đề xuất | Việt |
| `await_approval` | Không làm gì — chờ webhook | Đức (webhook + transition) |
| `escalate` | Tăng severity khi treo quá ngưỡng | Việt |
| `execute_remediation` | Thực thi hành động đã duyệt (rollback giả lập) | Đức |
| `generate_postmortem` | Sinh báo cáo, tạo sub-task action item | Việt |

> **Vì sao `hypothesize` chạy rule trước rồi mới tới LLM:** ràng buộc đề bài yêu cầu *chẩn đoán có bằng chứng*. Rule engine tạo ra bằng chứng số (p95 tăng 25×, pool cạn lúc 14:32, deploy v1.4.2 lúc 14:28); LLM chỉ chuyển bằng chứng đó thành lời giải thích và chọn runbook. Nếu để LLM tự suy luận từ dữ liệu thô, kết quả không truy vết được về số liệu nào.

---

## 3. Sequence diagram — kịch bản demo end-to-end

Sơ đồ này kiêm luôn kịch bản demo và storyboard video. Chú ý khối đỏ: đó là chỗ Agent **không thể tự đi qua**.

```mermaid
sequenceDiagram
    autonumber
    actor OC as 👤 On-call
    participant K6 as k6/Locust
    participant SVC as 2 service demo
    participant PROM as Prometheus
    participant AG as Incident Agent
    participant JIRA as Jira Cloud
    participant SP as Status page

    K6->>SVC: tăng tải 1k → 100k request
    SVC->>SVC: pool DB (5) cạn → request xếp hàng
    Note over SVC: latency p95: 0.2s → ~5s<br/>lỗi 500 tăng — nghẽn thật, không dàn dựng
    SVC-->>PROM: /metrics

    AG->>PROM: PromQL (định kỳ)
    PROM-->>AG: p95 = 5.1s
    AG->>AG: vượt ngưỡng 2s → severity P2

    AG->>JIRA: tạo Issue "war room"
    AG->>JIRA: comment bối cảnh phát hiện
    JIRA-->>SP: status → "Đang gặp sự cố"

    AG->>AG: đối chiếu deploy_history → v1.4.2 deploy 4 phút trước
    AG->>JIRA: comment giả thuyết + runbook (đề xuất rollback)

    Note over SVC: service-dat-hang timeout theo<br/>vì phụ thuộc service-thanh-toan
    AG->>PROM: phát hiện service thứ 2 suy giảm
    AG->>JIRA: link 2 issue ("relates to")

    rect rgb(254, 226, 226)
        Note over OC,JIRA: ✋ HITL — Agent dừng tại đây
        OC->>JIRA: xem war room, duyệt<br/>Awaiting Approval → Remediating
    end

    JIRA->>AG: webhook (Jira Automation)
    AG->>SVC: thực thi remediation (rollback v1.4.1)
    SVC-->>PROM: latency về ~0.2s
    AG->>PROM: verify đã hồi phục
    AG->>JIRA: transition → Resolved
    JIRA-->>SP: status → "Đã khắc phục"
    AG->>JIRA: postmortem + sub-task action item
    OC->>JIRA: đọc postmortem
```

### Nhánh escalation

Nếu on-call không duyệt trong ngưỡng thời gian, Agent không được tự vượt cổng HITL — nó chỉ leo thang:

```mermaid
sequenceDiagram
    autonumber
    participant AG as Incident Agent
    participant JIRA as Jira Cloud
    actor OC as 👤 On-call

    AG->>JIRA: đề xuất remediation, chờ duyệt
    loop mỗi X phút chưa được duyệt
        AG->>AG: kiểm tra thời gian treo
        AG->>JIRA: tăng severity + comment cảnh báo
        AG->>OC: thông báo leo thang
    end
    Note over AG,OC: Agent KHÔNG bao giờ tự duyệt —<br/>chỉ làm ồn hơn cho tới khi có người xử lý
```

---

## Quyết định kiến trúc

Lý do đằng sau các lựa chọn ở trên được ghi trong ADR:

| ADR | Quyết định |
|---|---|
| [0001](adr/0001-jira-lam-lop-incident-lifecycle.md) | Dùng Jira Cloud làm lớp quản lý vòng đời incident |
| [0002](adr/0002-khong-dung-alertmanager.md) | Prometheus nhưng không dùng Alertmanager |
| [0003](adr/0003-load-test-that-thay-fault-injection.md) | Tạo sự cố bằng load test thật, không fault injection giả |
