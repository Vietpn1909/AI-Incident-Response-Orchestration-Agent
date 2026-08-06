"""Dịch thuật ngữ kỹ thuật sang tiếng Việt cho UI — **dịch thêm, không dịch thay**.

CHỦ SỞ HỮU: Long (layout) · Đức viết phần dữ liệu dịch này ngày 06/08

## Vì sao có file này

Chạy thử UI ngày 06/08 với đúng dữ liệu Jira thật, war room hiện ra những dòng
như thế này:

    [P2] service-thanh-toan: http_request_duration_seconds p95 = 4.417 (ngưỡng 2.00)
    - db_pool_connections_in_use / db_pool_size: 1.0 (baseline None)
    - tỷ lệ lỗi 5xx: 0.0 (baseline None)
    Hành động: increase_pool → service-thanh-toan

Người không phải kỹ sư đọc không ra nghĩa gì, và `(baseline None)` thì trông
như lỗi. Nhưng đây là **trang trưng cho ban giám khảo và người ngoài xem**.

## Nguyên tắc: hai tầng trên CÙNG một dòng, không phải hai chế độ

Trang này phục vụ hai người khác nhau cùng lúc:

- **Người xem không biết tech** cần biết chuyện gì đang xảy ra với khách hàng
- **Người trực** cần **tên metric gốc và câu PromQL nguyên văn** để copy vào
  Prometheus mà đào tiếp

Nên KHÔNG được thay tên gốc bằng câu tiếng Việt. Mỗi bằng chứng trả về hai
phần: câu tiếng Việt dẫn đường, và dòng kỹ thuật giữ **nguyên văn** tên metric
cùng PromQL. Layout hiển thị dòng hai bằng chữ nhỏ ngay dưới dòng một — người
trực không phải bấm mở gì cả.

Dịch mất thông tin thì tệ hơn không dịch: người trực mất đường đào, mà đó là
người duy nhất thật sự sửa được sự cố.

## Cảnh báo cho người sửa file này

Các chuỗi trong `_METRIC` là tên `MetricEvidence` do
[`rules.py`](../src/services/rules.py) sinh ra. Đổi một chữ trong `rules.py` là
chỗ này lặng lẽ không nhận ra metric nữa và rơi về hiển thị tên thô — không sai
nhưng mất hết công dịch, và **không có gì đỏ lên**.
`tests/test_ui_labels.py::test_moi_ten_metric_deu_dich_duoc` gọi thẳng
`rules.detect*()` rồi đối chiếu, nên CI sẽ đỏ nếu lệch.
"""

from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Mức độ nghiêm trọng
# ---------------------------------------------------------------------------

#: `P2` → `("🟠", "Đáng lo", "dịch vụ suy giảm rõ rệt")`
#:
#: Kèm một câu giải thích vì "P2" tự nó không nói gì với người ngoài. Bốn mức
#: mô tả theo **ảnh hưởng tới khách hàng**, không theo con số ngưỡng.
SEVERITY: dict[str, tuple[str, str, str]] = {
    "P1": ("🔴", "Nghiêm trọng", "nhiều khách hàng bị ảnh hưởng"),
    "P2": ("🟠", "Đáng lo", "dịch vụ suy giảm rõ rệt"),
    "P3": ("🟡", "Nhẹ", "có dấu hiệu bất thường"),
    "P4": ("⚪", "Theo dõi", "lệch so với ngày thường"),
}

# ---------------------------------------------------------------------------
# Tên dịch vụ
# ---------------------------------------------------------------------------

#: Tên dịch vụ trong metric → tên người ngoài hiểu.
#:
#: `service-thanh-toan` là tên kỹ thuật, khớp label `service` trong Prometheus
#: (contract ①) nên KHÔNG được đổi ở phía backend. Chỉ đổi cách hiển thị.
SERVICE: dict[str, str] = {
    "service-thanh-toan": "Thanh toán",
    "service-dat-hang": "Đặt hàng",
}

#: Trạng thái sức khoẻ trong `ServiceStatus.health` → (icon, câu tiếng Việt).
#:
#: Bốn giá trị này là contract ④, sẽ không đổi.
HEALTH: dict[str, tuple[str, str]] = {
    "operational": ("🟢", "Hoạt động bình thường"),
    "degraded": ("🟡", "Chậm hơn bình thường"),
    "down": ("🔴", "Đang gặp sự cố"),
    "maintenance": ("🔧", "Đang bảo trì"),
}


def service(ten_goc: str) -> str:
    """`"service-thanh-toan"` → `"Thanh toán"`. Không nhận ra thì trả tên gốc."""
    return SERVICE.get(ten_goc, ten_goc)


def health(trang_thai: str) -> tuple[str, str]:
    """`"down"` → `("🔴", "Đang gặp sự cố")`."""
    return HEALTH.get(trang_thai, ("⚪", trang_thai))


# ---------------------------------------------------------------------------
# Trạng thái vòng đời incident
# ---------------------------------------------------------------------------

#: Trạng thái Jira → (icon, câu tiếng Việt).
#:
#: `Awaiting Approval` là trạng thái quan trọng nhất của cả dự án nên câu dịch
#: nói rõ **ai** đang phải làm gì, chứ không chỉ đặt tên trạng thái.
STATE: dict[str, tuple[str, str]] = {
    "Open": ("🆕", "Mới phát hiện"),
    "Investigating": ("🔍", "Đang chẩn đoán"),
    "Awaiting Approval": ("⏸", "Đang chờ người duyệt"),
    "Remediating": ("🔧", "Đang khắc phục"),
    "Resolved": ("✅", "Đã xử lý xong"),
}

# ---------------------------------------------------------------------------
# Hành động khắc phục
# ---------------------------------------------------------------------------

#: `action` trong `RemediationProposal` → câu tiếng Việt.
#:
#: Khớp `remediation.SUPPORTED_ACTIONS`, canh bằng
#: `test_moi_hanh_dong_deu_dich_duoc`. Hành động lạ hiện tên thô — thà thô còn
#: hơn dịch sai một thứ sắp được thi hành lên production.
ACTION: dict[str, str] = {
    "rollback": "Hạ về phiên bản trước",
    "restart": "Khởi động lại dịch vụ",
    "scale_up": "Tăng số máy chạy dịch vụ",
    "increase_pool": "Nâng số kết nối tới cơ sở dữ liệu",
    "rate_limit": "Giới hạn tốc độ truy cập",
    "block_ip": "Chặn nguồn truy cập",
}

# ---------------------------------------------------------------------------
# Tên metric
# ---------------------------------------------------------------------------

#: `(chuỗi con trong tên MetricEvidence, câu tiếng Việt, đơn vị hiển thị)`
#:
#: So bằng **chuỗi con** chứ không so nguyên văn: tên "đỉnh bộ nhớ 10 phút
#: (trần 128 MB)" mang trần container vào trong tên nên thay đổi theo cấu hình.
#:
#: Thứ tự có ý nghĩa — xét từ đặc trưng hẹp nhất. "đỉnh bộ nhớ" phải đứng trước
#: "bộ nhớ", không thì cả hai metric bộ nhớ dịch thành một câu.
_METRIC: tuple[tuple[str, str, str], ...] = (
    ("http_request_duration_seconds p95", "Thời gian khách phải chờ", "giây"),
    ("db_pool_connections_in_use / db_pool_size", "Chỗ kết nối cơ sở dữ liệu đã dùng", "%"),
    ("tỷ lệ lỗi 5xx", "Tỷ lệ giao dịch bị lỗi", "%"),
    ("số request /login thất bại mỗi giây", "Số lần đăng nhập sai mỗi giây", "lần/giây"),
    ("đỉnh bộ nhớ", "Bộ nhớ dùng nhiều nhất trong 10 phút", "MB"),
    ("bộ nhớ đang dùng / giới hạn container", "Bộ nhớ đang dùng so với giới hạn", "%"),
    ("số lần restart", "Số lần dịch vụ tự khởi động lại", "lần"),
    ("up (service còn sống không)", "Dịch vụ còn sống", ""),
)

#: Metric mà giá trị là tỷ lệ 0–1, hiển thị thành phần trăm.
_LA_TY_LE = frozenset({"%"})


def metric(ten_goc: str) -> tuple[str, str]:
    """`"tỷ lệ lỗi 5xx"` → `("Tỷ lệ giao dịch bị lỗi", "%")`.

    Không nhận ra thì trả về **nguyên tên gốc** và đơn vị rỗng. Thà hiện tên
    thô còn hơn hiện sai, và người trực vẫn đọc được.
    """
    thap = ten_goc.lower()
    for khoa, cau, don_vi in _METRIC:
        if khoa.lower() in thap:
            return cau, don_vi
    return ten_goc, ""


@dataclass(frozen=True)
class DongBangChung:
    """Một dòng bằng chứng, hai tầng.

    `plain` cho người xem, `raw` cho người trực. Layout hiện `raw` bằng chữ nhỏ
    ngay dưới `plain` — **không** gấp lại, vì người trực cần thấy ngay.
    """

    plain: str
    raw: str
    promql: str


def bang_chung(
    ten: str,
    gia_tri: float,
    *,
    baseline: float | None = None,
    unit: str = "",
    promql: str = "",
) -> DongBangChung:
    """Dựng một dòng bằng chứng hai tầng từ `MetricEvidence`.

    Bỏ hẳn `(baseline None)` — trước đây UI in nguyên chữ "None" ra trang khi
    metric không có baseline (pool và tỷ lệ lỗi đều không có), trông như lỗi.
    Không có baseline thì không nói gì về baseline.
    """
    cau, don_vi = metric(ten)

    if don_vi in _LA_TY_LE:
        hien = f"{gia_tri * 100:.0f}%"
        nen = f"{baseline * 100:.0f}%" if baseline else None
    elif don_vi:
        hien = f"{gia_tri:.3g} {don_vi}"
        nen = f"{baseline:.3g} {don_vi}" if baseline else None
    else:
        hien = f"{gia_tri:.3g}"
        nen = f"{baseline:.3g}" if baseline else None

    plain = f"{cau}: {hien}"
    if nen:
        plain += f" (thường {nen}"
        if baseline:
            plain += f" — lệch {gia_tri / baseline:.1f} lần"
        plain += ")"

    raw = f"{ten} = {gia_tri:g}{unit}"
    return DongBangChung(plain=plain, raw=raw, promql=promql)


def severity(muc: str) -> str:
    """`"P2"` → `"🟠 Đáng lo — dịch vụ suy giảm rõ rệt"`. Kèm mã gốc cho người trực."""
    icon, ten, giai_thich = SEVERITY.get(muc, ("⚪", muc, ""))
    duoi = f" — {giai_thich}" if giai_thich else ""
    return f"{icon} {ten}{duoi} ({muc})"


def state(trang_thai: str) -> str:
    """`"Awaiting Approval"` → `"⏸ Đang chờ người duyệt"`."""
    icon, ten = STATE.get(trang_thai, ("•", trang_thai))
    return f"{icon} {ten}"


def action(hanh_dong: str) -> str:
    """`"increase_pool"` → `"Nâng số kết nối tới cơ sở dữ liệu (increase_pool)"`.

    Giữ tên gốc trong ngoặc: người trực sẽ gõ đúng chữ đó khi thi hành, và nó
    cũng là chữ nằm trong `SUPPORTED_ACTIONS`.
    """
    cau = ACTION.get(hanh_dong)
    return f"{cau} ({hanh_dong})" if cau else hanh_dong


def keo_dai(giay: float) -> str:
    """`60.0` → `"1 phút liên tục — không phải nhấp nháy"`.

    Câu "không phải nhấp nháy" là phần người ngoài cần nhất: nó trả lời câu hỏi
    *"sao không phải báo động giả?"* mà không ai hỏi ra miệng.
    """
    if giay < 60:
        do_dai = f"{giay:.0f} giây"
    elif giay < 3600:
        do_dai = f"{giay / 60:.0f} phút"
    else:
        do_dai = f"{giay / 3600:.1f} giờ"
    return f"{do_dai} liên tục — không phải nhấp nháy"
