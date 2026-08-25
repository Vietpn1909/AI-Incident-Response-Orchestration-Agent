"""Chọn hành động khắc phục từ giả thuyết — nửa tất định của `propose_remediation`.

CHỦ SỞ HỮU: Đức

## Vì sao LLM KHÔNG chọn hành động ở đây

`docs/architecture_diagram.md` mục 2 viết *"LLM chỉ chuyển bằng chứng đó thành
lời giải thích và chọn runbook"*. Phần "chọn runbook" tôi làm khác đi, và đây là
một quyết định cố ý cần Việt biết:

`action` không phải câu văn — nó là thứ **được thi hành lên production**. Chênh
giữa `rollback` và `block_ip` là chênh giữa hạ một phiên bản và chặn truy cập
của người dùng thật. Docstring của `remediation.SUPPORTED_ACTIONS` đã ghi rõ lý
do có danh sách trắng: *"tránh việc LLM sinh ra một `action` lạ rồi backend thi
hành mù"*. Nếu LLM chọn trong danh sách trắng thì vẫn là LLM quyết định làm gì
lên production, chỉ khác là bị giới hạn phạm vi.

Nên ở đây luật chọn `action`, `params`, `runbook`, `risk` — tất tật tất định,
đọc được, test được. LLM đã làm phần của nó ở `hypothesize`: giải thích *vì sao*.
Người trực đọc câu giải thích của LLM rồi tự quyết có duyệt hành động hay không.

Ranh giới: **LLM diễn giải, luật đề xuất, người duyệt.**

## Thứ tự xét quan trọng

Đúng thứ tự ưu tiên trong `nodes/detect.py::_one_per_service`: UC-3 (bảo mật) →
UC-2 (chết) → UC-1 (chậm). Lý do cụ thể ở đây khác chỗ đó: một vụ
credential-stuffing xảy ra **đúng lúc** vừa deploy thì rollback không chặn được
cuộc tấn công, chỉ làm mất thời gian và gây thêm một lần đổi phiên bản vô ích
giữa lúc đang có sự cố.
"""

from __future__ import annotations

import logging

from src.models.incident import DeployRecord, Hypothesis, IncidentSignal, RemediationProposal
from src.services import rules

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tên bằng chứng dùng để nhận ra đây là use case nào.
#
# Đây là chuỗi literal nằm trong `rules.py` của Việt, không phải hằng có tên.
# So khớp bằng chuỗi thì Việt sửa một chữ trong `rules.py` là chỗ này lặng lẽ
# không nhận ra use case nữa, rồi mọi sự cố đều rơi vào nhánh mặc định
# `scale_up` — sai hành động mà không có gì đỏ lên.
#
# Vì vậy `tests/test_services/test_runbooks.py::test_ten_bang_chung_con_khop_voi_rules`
# gọi thẳng `rules.detect*()` rồi đối chiếu lại ba chuỗi này.
# ---------------------------------------------------------------------------

#: UC-1 — pool cạn. Bằng chứng nguyên nhân gốc, không phải triệu chứng.
EVIDENCE_POOL = "db_pool_connections_in_use / db_pool_size"

#: UC-2 — service chết rồi restart.
EVIDENCE_UP = "up (service còn sống không)"

#: UC-3 — burst đăng nhập thất bại.
EVIDENCE_AUTH = "số request /login thất bại mỗi giây"

#: Pool đề xuất tăng lên. Cố định vì Agent **không đọc được** `db_pool_size`
#: hiện tại: bằng chứng lưu tỷ lệ `in_use / size`, không lưu mẫu số. Người
#: duyệt thấy số này không hợp thì tự sửa trước khi chấp nhận — đó là việc của
#: cổng HITL, không phải việc Agent đoán.
POOL_SIZE_DE_XUAT = 20

#: Số instance đề xuất khi không có hành động nào đúng hơn.
REPLICAS_DE_XUAT = 3

#: Giới hạn tốc độ đề xuất cho UC-3, request/phút trên mỗi nguồn.
RATE_LIMIT_DE_XUAT = 60


def phien_ban_truoc(history: list[DeployRecord], nghi_pham: DeployRecord) -> str | None:
    """Phiên bản deploy ngay TRƯỚC `nghi_pham` — tức đích để rollback về.

    Trả `None` khi không tìm được, và khi đó **không đề xuất rollback**. Đề xuất
    "rollback" mà không nói rõ về đâu thì người trực không duyệt được, còn để
    `remediation._describe()` điền "phiên bản trước" là đẩy việc đoán xuống lúc
    thi hành — sai chỗ.

    Công khai (bỏ gạch dưới) từ 18/08 vì `auto_remediation.py` cần **đúng** phép
    chọn này khi tự rollback lúc hết thời chờ. Chép sang đó một bản thứ hai là
    tạo chỗ để hai đường đi lệch nhau: người duyệt thấy một phiên bản đích, Agent
    tự thi hành một phiên bản khác — mà không có gì đỏ lên.
    """
    truoc_do = [d for d in history if d.deployed_at < nghi_pham.deployed_at]
    if not truoc_do:
        return None
    return max(truoc_do, key=lambda d: d.deployed_at).version


def _co_bang_chung(hypothesis: IncidentSignal | Hypothesis, ten: str) -> float | None:
    """Giá trị của một bằng chứng theo tên, `None` nếu không có."""
    for item in hypothesis.evidence:
        if item.name == ten:
            return item.value
    return None


def choose(
    signal: IncidentSignal,
    hypothesis: Hypothesis,
    deploy_history: list[DeployRecord] | None = None,
) -> RemediationProposal:
    """Chọn hành động khắc phục cho một sự cố đã có giả thuyết.

    Args:
        signal: Tín hiệu từ `detect`, dùng để biết service và use case nào.
        hypothesis: Giả thuyết từ `hypothesize`, mang `related_deploy`.
        deploy_history: Lịch sử deploy của service — cần để biết rollback **về
            đâu**. Thiếu thì không đề xuất rollback.

    Returns:
        `RemediationProposal` với `requires_approval=True`. Luôn trả về một đề
        xuất, không bao giờ `None`: sự cố mà Agent không biết làm gì vẫn phải
        nói ra một phương án cho người trực cân nhắc, kèm `risk` ghi rõ là
        phỏng đoán. Im lặng tệ hơn đề xuất dở.
    """
    service = signal.affected_service
    history = deploy_history or []
    nghi_pham = hypothesis.related_deploy
    ve_phien_ban = phien_ban_truoc(history, nghi_pham) if nghi_pham else None

    # ── UC-3: tấn công. Xét trước rollback, xem docstring module.
    if _co_bang_chung(signal, EVIDENCE_AUTH) is not None:
        return RemediationProposal(
            action="rate_limit",
            target=service,
            params={"limit": RATE_LIMIT_DE_XUAT, "scope": "/login"},
            runbook=(
                f"1. Bật rate limit {RATE_LIMIT_DE_XUAT} request/phút trên mỗi nguồn cho `/login` của {service}.\n"
                "2. Theo dõi `số request /login thất bại mỗi giây` — phải giảm trong 2 phút.\n"
                "3. Còn cao thì lấy danh sách IP nguồn rồi cân nhắc `block_ip`."
            ),
            risk=(
                "Chặn oan người dùng thật đang đăng nhập lại nhiều lần (quên mật khẩu, "
                "app retry). Đề xuất rate limit thay vì block_ip vì Agent CHƯA thu thập "
                "IP nguồn — chọn block_ip lúc này là chặn mù."
            ),
        )

    # ── UC-2: service chết rồi restart.
    if _co_bang_chung(signal, EVIDENCE_UP) is not None:
        if ve_phien_ban:
            return _rollback(service, nghi_pham, ve_phien_ban, ly_do="service chết ngay sau lần deploy này")
        return RemediationProposal(
            action="scale_up",
            target=service,
            params={"replicas": REPLICAS_DE_XUAT},
            runbook=(
                f"1. Tăng {service} lên {REPLICAS_DE_XUAT} instance để tải RAM chia ra, "
                "giảm khả năng chạm giới hạn bộ nhớ.\n"
                "2. Theo dõi `số lần restart trong 10 phút` — phải về 0.\n"
                "3. Còn restart thì vấn đề là bản thân giới hạn bộ nhớ, cần người tăng `mem_limit`."
            ),
            risk=(
                "⚠️ Đây là phương án GIẢM NHẸ, không phải sửa gốc. Service chết vì hết bộ "
                "nhớ thì cách đúng là tăng giới hạn bộ nhớ hoặc sửa chỗ rò rỉ — cả hai đều "
                "KHÔNG nằm trong danh sách hành động Agent được phép làm. Thêm instance chỉ "
                "mua thêm thời gian. Người duyệt nên xử lý gốc song song."
            ),
        )

    # ── UC-1: chậm. Có deploy trùng thời gian thì rollback, không thì nới pool.
    pool = _co_bang_chung(signal, EVIDENCE_POOL)
    pool_can = pool is not None and pool >= rules.POOL_EXHAUSTED_RATIO

    if ve_phien_ban:
        ly_do = "pool cạn ngay sau lần deploy này" if pool_can else "sự cố bắt đầu ngay sau lần deploy này"
        return _rollback(service, nghi_pham, ve_phien_ban, ly_do=ly_do)

    if pool_can:
        return RemediationProposal(
            action="increase_pool",
            target=service,
            params={"pool_size": POOL_SIZE_DE_XUAT},
            runbook=(
                f"1. Nâng connection pool của {service} lên {POOL_SIZE_DE_XUAT}.\n"
                "2. Theo dõi `db_pool_connections_in_use / db_pool_size` — phải tụt xuống dưới 1.0.\n"
                "3. Theo dõi p95 — phải về gần mức baseline trong 3 phút.\n"
                "4. Không đỡ thì nút thắt nằm ở Postgres chứ không ở pool, cần xem lại query."
            ),
            risk=(
                f"Mỗi connection thêm là thêm tải lên Postgres; nâng lên {POOL_SIZE_DE_XUAT} mà "
                "database đã gần giới hạn `max_connections` thì đổi một chỗ nghẽn sang chỗ khác. "
                f"Agent KHÔNG đọc được `db_pool_size` hiện tại (bằng chứng chỉ có tỷ lệ, không có "
                "mẫu số), nên con số này là mặc định — người duyệt nên đối chiếu cấu hình thật."
            ),
        )

    return RemediationProposal(
        action="scale_up",
        target=service,
        params={"replicas": REPLICAS_DE_XUAT},
        runbook=(
            f"1. Tăng {service} lên {REPLICAS_DE_XUAT} instance để chia tải.\n"
            f"2. Theo dõi `{signal.metric_name}` — phải giảm dưới ngưỡng {signal.threshold:.3g}.\n"
            "3. Không đỡ thì nguyên nhân không phải thiếu năng lực xử lý, cần chẩn đoán lại."
        ),
        risk=(
            "⚠️ Đây là phương án MẶC ĐỊNH vì bằng chứng chưa chỉ ra nguyên nhân gốc: không có "
            "deploy nào trùng thời gian, pool cũng không cạn. Thêm instance có thể chỉ che triệu "
            "chứng. Người duyệt nên đọc lại phần giả thuyết trước khi chấp nhận."
        ),
    )


def _rollback(service: str, deploy: DeployRecord, ve_phien_ban: str, *, ly_do: str) -> RemediationProposal:
    """Đề xuất rollback, có nói rõ về phiên bản nào."""
    logger.info("Đề xuất rollback %s: %s → %s (%s)", service, deploy.version, ve_phien_ban, ly_do)
    return RemediationProposal(
        action="rollback",
        target=service,
        params={"to_version": ve_phien_ban, "from_version": deploy.version},
        runbook=(
            f"1. Rollback {service} từ `{deploy.version}` về `{ve_phien_ban}`.\n"
            f"2. Theo dõi `{'p95 và ' if ly_do.startswith('pool') else ''}"
            "chỉ số đã kích hoạt sự cố` — phải về gần baseline trong 3 phút.\n"
            f"3. Hồi phục thì mở issue riêng điều tra thay đổi trong `{deploy.version}`.\n"
            "4. KHÔNG hồi phục thì deploy chỉ là trùng thời gian, không phải nguyên nhân — "
            "chẩn đoán lại thay vì rollback tiếp."
        ),
        risk=(
            f"`{deploy.version}` có thể chứa thay đổi khác đang cần thiết (sửa lỗi, vá bảo mật); "
            f"rollback là bỏ luôn cả những thay đổi đó. Ngoài ra {ly_do} là quan hệ **trùng thời "
            "gian**, chưa phải bằng chứng nhân quả — nếu rollback không làm sự cố hết thì kết luận "
            "ban đầu đã sai."
        ),
    )
