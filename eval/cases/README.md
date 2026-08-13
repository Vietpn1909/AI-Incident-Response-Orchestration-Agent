# Bộ 30 test case incident

Bộ dữ liệu này phục vụ **error analysis** cho baseline phát hiện incident:

- 10 case `normal`;
- 15 case `incident`;
- 5 case `noisy`/mơ hồ.

Ground truth được ghi trong
[`incident_cases.json`](incident_cases.json) **trước khi chạy** Agent. Các case
là snapshot tổng hợp do nhóm thiết kế từ pattern của nguồn tham khảo, không
phải dữ liệu thô sao chép từ các nguồn đó.

## Nguồn và cách sử dụng

- [Cloudflare incident 21/03/2025](https://blog.cloudflare.com/cloudflare-incident-march-21-2025/):
  cấu trúc impact → timeline → root cause; pattern deploy credential sai môi
  trường, cache che khuất một phần impact, cần nối metric với log và deploy.
- [AWS Fault Injection Service](https://docs.aws.amazon.com/fis/latest/userguide/what-is.html):
  mỗi experiment có `target`, `action`, thời lượng và `stop_condition`. Bộ này
  chỉ mô phỏng trên demo/pre-production, không tác động tài nguyên production.
- [OpenTelemetry Demo feature flags](https://opentelemetry.io/docs/demo/feature-flags/):
  pattern payment failure/unreachable, memory leak, traffic flood và delay.
- [`docs/use-cases.md`](../../docs/use-cases.md): ground truth nội bộ của
  UC-1 đến UC-4.

## Metric chất lượng

| Metric | Công thức | Ý nghĩa |
|---|---|---|
| Incident recall | `TP / (TP + FN)` | Trong tất cả incident thật, Agent bắt được bao nhiêu |
| Incident precision | `TP / (TP + FP)` | Trong các cảnh báo Agent mở, bao nhiêu là incident thật |
| Tỷ lệ báo nhầm | `FP / (FP + TN)` | Trong các case âm, bao nhiêu case bị mở nhầm |
| Severity accuracy | severity đúng / incident đã bắt được | Xếp P1–P4 đúng hay không |
| Top-1 root-cause accuracy (rule baseline) | nguyên nhân đúng / incident thật | Câu dự phòng tất định có đúng nguyên nhân gốc không; chưa phải kết quả LLM |
| Evidence coverage | đủ evidence / incident thật | Tín hiệu có mang đủ bằng chứng bắt buộc không |
| Noisy rejection rate | noisy bị từ chối / 5 | Khả năng không phản ứng quá mức với nhiễu |

Recall không được đọc một mình: Agent có thể đạt recall cao bằng cách báo động
mọi thứ. Vì vậy báo cáo luôn đặt recall cạnh precision và tỷ lệ báo nhầm.

## Cách chạy

Từ thư mục gốc repo:

```bash
python -m eval.case_suite
```

Kết quả được ghi vào:

```text
eval/results/case-suite/summary.json
eval/results/case-suite/report.md
```

Runner có hai đường để phát hiện lỗi wiring:

1. gọi rule public trực tiếp;
2. chạy snapshot qua Prometheus client giả → `detect_incidents()` thật →
   `open_war_room()` thật → `FakeJiraClient`.

Hai đường phải cho cùng confusion matrix. Runner không gọi Docker, Prometheus
server, Jira Cloud hay LLM, nên 30 case không làm lẫn cửa sổ metric 1–30 phút
của nhau và không có tác dụng phụ bên ngoài. Đây là baseline tái lập; vẫn cần
chọn một số case đại diện để chạy live end-to-end và đo MTTD/LLM riêng.

## Cách đọc lỗi hiện tại

- `FN`: incident thật bị bỏ lọt → làm giảm recall.
- `FP`: case bình thường/nhiễu bị mở incident → làm giảm precision.
- `TP` nhưng root cause sai: Agent thấy hệ thống hỏng nhưng chưa chẩn đoán được
  vì sao; không được tính là M3 đúng.

Không sửa `rules.py` hay prompt chỉ để làm đẹp số trong cùng PR với dataset.
Hãy giữ kết quả baseline, ghi top error rồi xử lý bằng một thay đổi độc lập để
có thể so sánh trước/sau.
