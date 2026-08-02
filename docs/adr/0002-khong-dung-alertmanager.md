# ADR-0002: Dùng Prometheus nhưng không dùng Alertmanager

- **Trạng thái:** Đã chấp nhận
- **Ngày:** 2026-07-28
- **Người quyết định:** Trương Công Thái Đức (lead) + Việt (AI Agent)

## Bối cảnh

Agent cần biết khi nào có sự cố. Stack monitoring tiêu chuẩn là Prometheus (thu thập metric) + Alertmanager (đánh giá alert rule, định tuyến, dedup, silence) + Grafana (dashboard).

Nhưng trong kiến trúc PTNT-20, **quyết định "có phải incident không" là bước đầu tiên của Agent**, không phải một hệ thống riêng đứng ngoài. Bước này gắn liền với `classify_severity` và `gather_context` phía sau nó.

## Các phương án đã xét

| Phương án | Đánh giá |
|---|---|
| **Prometheus + Alertmanager → webhook → Agent** | Đúng chuẩn production. Nhưng thêm một service, một file cấu hình YAML (`alert.rules` + routing tree), và một lớp bất đồng bộ nữa giữa "vượt ngưỡng" và "Agent biết". Debug khó hơn: khi Agent không phản ứng, phải kiểm tra 3 chỗ thay vì 1 |
| **Prometheus, Agent tự query PromQL và tự đánh giá ngưỡng** | Bớt một service. Logic ngưỡng nằm trong Python cùng chỗ với `classify_severity`, test được bằng pytest. Đổi lại: không có dedup/silence/grouping có sẵn, phải tự xử nếu cần |
| **Bỏ Prometheus, Agent gọi thẳng endpoint đo của service** | Đơn giản nhất nhưng mất time-series, tức mất khả năng **so baseline** — mà so baseline là nền tảng của "chẩn đoán có bằng chứng". Loại |

## Quyết định

Dùng **Prometheus** để thu thập metric, nhưng **không triển khai Alertmanager**. Logic kiểm tra ngưỡng nằm thẳng trong code Agent:

- 2 service demo dùng `prometheus-fastapi-instrumentator` để tự expose `/metrics`, không đo tay
- Agent định kỳ query Prometheus HTTP API bằng PromQL, ví dụ `histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[1m])) by (le, service)) > 2`
- Ngưỡng và quy tắc severity là Python, sống cùng LangGraph node `detect` / `classify_severity`
- **Grafana là tuỳ chọn** — chỉ dựng nếu còn thời gian, và chỉ để có ảnh đẹp cho pitch deck

## Hệ quả

**Tích cực**

- Bớt một service trong `docker-compose`, bớt một file YAML phải học cú pháp
- Logic ngưỡng test được bằng pytest thông thường — thuộc phần việc test của Trung, không cần dựng Alertmanager để test
- Không có độ trễ và lớp gián tiếp giữa "vượt ngưỡng" và "Agent hành động"; khi Agent không phản ứng, chỉ có một chỗ để kiểm tra
- Ngưỡng nằm trong code nên được version control và review qua PR, khác với cấu hình Alertmanager

**Tiêu cực**

- Tự cài lại vài thứ Alertmanager có sẵn: chống báo trùng (Agent phải nhớ đã mở incident cho service nào), và `for:` duration (chỉ báo khi vượt ngưỡng liên tục X giây, tránh nhiễu do một spike). Cả hai phải làm, chỉ là làm trong Python
- Không phải kiến trúc production thật. Cần nói rõ điều này khi trình bày, kèm lý do — đây là đánh đổi có ý thức để đổi lấy thời gian, không phải thiếu hiểu biết
- Nếu sau này muốn nhiều kênh thông báo (Slack, email, SMS) thì phải tự viết routing

## Ghi chú khi làm

Việt cần xử hai thứ ngay từ đầu, vì thiếu chúng thì Agent sẽ mở hàng loạt incident trùng lúc load test:

1. **Chống trùng** — trước khi `open_war_room`, kiểm tra đã có incident đang mở cho `affected_service` đó chưa
2. **Xác nhận kéo dài** — chỉ coi là incident khi vượt ngưỡng liên tục ≥ 30s, không phản ứng với một điểm dữ liệu đơn lẻ
