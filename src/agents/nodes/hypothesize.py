"""Node `hypothesize` — biến bằng chứng số thành một câu chẩn đoán đọc được.

CHỦ SỞ HỮU: Việt

Đây là chỗ duy nhất trong Agent gọi LLM, và là node quyết định sản phẩm này có
khác Alertmanager hay không: trước nó Agent nói được *"service đang chậm"*, sau
nó Agent nói được *"chậm vì cái gì, dựa trên số nào"*.

## Thứ tự không được đảo

`Hypothesis` trong contract ② ghi rõ:

    statement   ← LLM viết
    reasoning   ← LLM viết
    confidence  ← rule engine tính, KHÔNG phải LLM tự nhận
    evidence    ← số thật từ Prometheus

Nên node này chạy **hai pha**:

1. [`rules.build_hypothesis()`](../../services/rules.py) dựng `evidence`,
   `confidence` và một `statement` dự phòng — **không mạng, tất định**.
2. LLM viết lại `statement` cho gọn và thêm `reasoning`.

Pha 2 hỏng thì giả thuyết **vẫn còn nguyên giá trị chấm điểm**: bằng chứng và
độ tin cậy do pha 1 sinh. Mất câu văn hay còn hơn mất cả phần chẩn đoán, và
DashScope hết quota giữa buổi demo là chuyện có thật.

## Vì sao LLM không được đụng vào `confidence`

Không phải vì sợ nó nói sai, mà vì con số đó **sẽ không đo cái gì cả**. "Tôi
90% chắc chắn" của một mô hình ngôn ngữ không đến từ phép đo nào; lúc chấm
không giải thích được nó từ đâu ra. `_diem_tin_cay()` cộng điểm theo từng
`MetricEvidence` cụ thể, nên mỗi phần của con số truy ngược được.
"""

from __future__ import annotations

import logging

from src.models.incident import DeployRecord, Hypothesis, IncidentSignal
from src.services import deploys, rules

logger = logging.getLogger(__name__)

#: Chặn câu trả lời dài bất thường. LLM đôi khi trả về cả một bài phân tích;
#: war room cần một câu, không cần bài luận.
_MAX_STATEMENT = 400
_MAX_REASONING = 1200


# ---------------------------------------------------------------------------
# Prompt — để nguyên ở đây, đừng gom vào biến rời hay file riêng.
#
# Đây là chỗ ràng buộc LLM, tức là chỗ dễ hỏng nhất và cần review kỹ nhất.
# Giấu nó vào file khác thì người review phải mở hai chỗ mới hiểu Agent đang
# bị cấm làm gì.
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
Bạn là kỹ sư on-call đang viết chẩn đoán ban đầu cho một sự cố hạ tầng.

Bạn được cung cấp SẴN các số đo từ Prometheus. Nhiệm vụ của bạn chỉ là diễn
giải chúng thành lời cho người trực đọc.

RÀNG BUỘC BẮT BUỘC:

1. CHỈ dùng những con số có trong phần "BẰNG CHỨNG ĐO ĐƯỢC" bên dưới. Tuyệt đối
   không tự thêm số liệu, tên metric, tên service hay mốc thời gian nào khác.
   Không có số nào cho một ý thì đừng nêu ý đó.

2. KHÔNG nêu độ tin cậy, xác suất, hay mức chắc chắn dưới bất kỳ dạng nào.
   Phần đó đã được tính riêng bằng luật, không phải việc của bạn.

3. Phân biệt NGUYÊN NHÂN với TRIỆU CHỨNG. "Service chậm" là triệu chứng.
   "Connection pool cạn nên request phải xếp hàng" là nguyên nhân. Nêu được
   nguyên nhân thì nêu, không suy đoán được thì nói thẳng là chưa xác định
   được nguyên nhân.

4. Nếu có thông tin deploy, nó là TRÙNG THỜI GIAN chứ không phải bằng chứng
   nhân quả. Viết "trùng thời gian với deploy X" hoặc "nghi liên quan tới
   deploy X". KHÔNG viết "do deploy X gây ra" trừ khi bằng chứng chỉ thẳng vào
   thay đổi của lần deploy đó.

ĐỊNH DẠNG TRẢ LỜI — đúng hai phần, không thêm gì khác:

GIẢ THUYẾT: <một câu, tối đa 40 từ, nêu nguyên nhân gốc>
LÝ GIẢI: <2-4 câu, chỉ ra từng con số dẫn tới kết luận trên>

Viết bằng tiếng Việt.\
"""

_USER_TEMPLATE = """\
SỰ CỐ
- Service: {service}
- Mức độ: {severity}
- Đã bất thường liên tục: {breached:.0f} giây
- Chỉ số kích hoạt: {metric} = {value:.3f} (ngưỡng {threshold:.3f})

BẰNG CHỨNG ĐO ĐƯỢC
{evidence}

{deploy}\
"""


def _format_evidence(signal: IncidentSignal) -> str:
    dong = []
    for item in signal.evidence:
        phan = f"- {item.name} = {item.value:.4g}{item.unit}"
        if item.baseline is not None:
            phan += f" (mức thường ngày {item.baseline:.4g}{item.unit}"
            ratio = item.deviation_ratio
            if ratio:
                phan += f", gấp {ratio:.1f} lần"
            phan += ")"
        dong.append(phan)
    return "\n".join(dong) or "- (không có bằng chứng số nào)"


def _format_deploy(deploy: DeployRecord | None, signal: IncidentSignal) -> str:
    if deploy is None:
        return "LỊCH SỬ DEPLOY\n- Không có lần deploy nào gần thời điểm sự cố."
    phut = deploy.minutes_before(signal.detected_at)
    return f"LỊCH SỬ DEPLOY\n- Phiên bản {deploy.version} được deploy {phut:.0f} phút TRƯỚC khi phát hiện sự cố."


def _parse(reply: str) -> tuple[str, str]:
    """Tách câu trả lời thành `(statement, reasoning)`.

    LLM hay thêm thắt dù prompt đã chốt định dạng, nên parse phải chịu được
    lệch: thiếu nhãn thì lấy dòng đầu làm giả thuyết, phần còn lại làm lý giải.
    """
    statement, reasoning = "", ""
    phan_hien_tai = None

    for dong in reply.splitlines():
        sach = dong.strip()
        if not sach:
            continue
        if sach.upper().startswith("GIẢ THUYẾT:"):
            phan_hien_tai = "statement"
            statement = sach.split(":", 1)[1].strip()
        elif sach.upper().startswith("LÝ GIẢI:"):
            phan_hien_tai = "reasoning"
            reasoning = sach.split(":", 1)[1].strip()
        elif phan_hien_tai == "reasoning":
            reasoning = f"{reasoning} {sach}".strip()
        elif phan_hien_tai is None and not statement:
            statement = sach

    return statement[:_MAX_STATEMENT], reasoning[:_MAX_REASONING]


def hypothesize(signal: IncidentSignal, llm=None) -> Hypothesis:
    """Dựng giả thuyết nguyên nhân cho một tín hiệu sự cố.

    Args:
        signal: Tín hiệu từ `detect`, đã kèm bằng chứng số.
        llm: Client LLM. `None` thì tự lấy từ `services.llm.get_llm()`. Truyền
            vào để test không cần mạng.

    Returns:
        `Hypothesis` luôn có `evidence` và `confidence` do rule engine sinh.
        `reasoning` rỗng nghĩa là LLM không viết được — giả thuyết vẫn dùng
        được, chỉ kém dễ đọc.
    """
    lich_su = deploys.recent_deploys(signal.affected_service)
    deploy = rules.correlate_deploy(lich_su, signal.detected_at)

    # Pha 1 — tất định. Chạy trước và độc lập với LLM.
    hypothesis = rules.build_hypothesis(signal, deploy)

    # Pha 2 — LLM chỉ viết lại lời.
    reply = _ask_llm(signal, deploy, llm)
    if not reply:
        logger.warning(
            "%s: LLM không trả lời — giữ câu do luật ghép, chẩn đoán vẫn có bằng chứng",
            signal.affected_service,
        )
        return hypothesis

    statement, reasoning = _parse(reply)
    if not statement:
        logger.warning("%s: không tách được giả thuyết từ câu trả lời LLM", signal.affected_service)
        return hypothesis

    return hypothesis.model_copy(update={"statement": statement, "reasoning": reasoning})


def _ask_llm(signal: IncidentSignal, deploy: DeployRecord | None, llm) -> str:
    """Gọi LLM, trả chuỗi rỗng nếu hỏng.

    Nuốt mọi lỗi ở đây là **cố ý**: hết quota, timeout, sai key, provider đổi
    định dạng — tất cả đều không được làm Agent mất phần chẩn đoán. Nhưng đều
    được log ở mức warning để không hỏng âm thầm.
    """
    try:
        if llm is None:
            from src.services.llm import get_llm

            llm = get_llm()

        prompt = _USER_TEMPLATE.format(
            service=signal.affected_service,
            severity=signal.severity.value,
            breached=signal.breached_for_seconds,
            metric=signal.metric_name,
            value=signal.metric_value,
            threshold=signal.threshold,
            evidence=_format_evidence(signal),
            deploy=_format_deploy(deploy, signal),
        )
        reply = llm.invoke([("system", _SYSTEM_PROMPT), ("human", prompt)])
        return getattr(reply, "content", str(reply)) or ""
    except Exception as error:
        logger.warning("Gọi LLM hỏng (%s) — dùng câu do luật ghép", error)
        return ""
