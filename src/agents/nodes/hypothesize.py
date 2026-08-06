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
from dataclasses import dataclass
from typing import Literal

from src.models.incident import DeployRecord, Hypothesis, IncidentSignal
from src.services import deploys, rules

logger = logging.getLogger(__name__)

#: Chặn câu trả lời dài bất thường. LLM đôi khi trả về cả một bài phân tích;
#: war room cần một câu, không cần bài luận.
_MAX_STATEMENT = 400
_MAX_REASONING = 1200


StatementOrigin = Literal["llm", "rule"]


@dataclass(frozen=True)
class HypothesisOutcome:
    """Giả thuyết và nơi câu kết luận cuối cùng được viết.

    Đây là metadata phục vụ đo M3. Không đưa vào ``Hypothesis`` hay Jira vì
    nó mô tả *lần chạy* (LLM có bị chặn hay không), không phải bản chất của sự
    cố. Nhờ vậy contract incident đang lưu vẫn tương thích với war room cũ.
    """

    hypothesis: Hypothesis
    statement_origin: StatementOrigin


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
    """Dựng giả thuyết; giữ API cũ cho luồng Agent và Jira."""
    return hypothesize_with_origin(signal, llm).hypothesis


def hypothesize_with_origin(signal: IncidentSignal, llm=None) -> HypothesisOutcome:
    """Dựng giả thuyết nguyên nhân cho một tín hiệu sự cố.

    Args:
        signal: Tín hiệu từ `detect`, đã kèm bằng chứng số.
        llm: Client LLM. `None` thì tự lấy từ `services.llm.get_llm()`. Truyền
            vào để test không cần mạng.

    Returns:
        `HypothesisOutcome` chứa `Hypothesis` và nguồn của câu kết luận cuối.
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
        return HypothesisOutcome(hypothesis, "rule")

    statement, reasoning = _parse(reply)
    if not statement:
        logger.warning("%s: không tách được giả thuyết từ câu trả lời LLM", signal.affected_service)
        return HypothesisOutcome(hypothesis, "rule")

    if _phu_dinh_ket_luan_cua_luat(statement, hypothesis.statement):
        logger.warning(
            "%s: BỎ câu của LLM vì nó PHỦ ĐỊNH một nguyên nhân mà luật đã chứng minh "
            "bằng bằng chứng. Giữ câu do luật ghép. Câu bị bỏ: %s",
            signal.affected_service,
            statement,
        )
        return HypothesisOutcome(hypothesis, "rule")

    thieu_can_cu = _nguyen_nhan_khong_co_can_cu(statement, signal, deploy)
    if thieu_can_cu:
        logger.warning(
            "%s: BỎ câu của LLM vì nêu nguyên nhân '%s' mà không có bằng chứng chống lưng. "
            "Giữ câu do luật ghép. Câu bị bỏ: %s",
            signal.affected_service,
            thieu_can_cu,
            statement,
        )
        # Giữ nguyên `statement` của luật, nhưng vẫn KHÔNG lấy `reasoning` của
        # LLM: nó diễn giải cho một kết luận vừa bị bỏ, giữ lại là tự mâu thuẫn.
        return HypothesisOutcome(hypothesis, "rule")

    return HypothesisOutcome(
        hypothesis.model_copy(update={"statement": statement, "reasoning": reasoning}),
        "llm",
    )


#: Cụm mà `rules._cau_giai_thuyet()` dùng ở nhánh cuối, tức "luật KHÔNG tìm ra
#: nguyên nhân gốc". Câu luật chứa cụm này nghĩa là luật cũng chịu, nên LLM nói
#: "chưa xác định được" là **đồng ý**, không phải mâu thuẫn.
#:
#: Chuỗi literal trong `rules.py`, canh bằng `test_cum_chua_du_bang_chung_con_khop`.
_LUAT_CUNG_CHIU = "chưa đủ bằng chứng để nêu nguyên nhân"

#: Cách LLM viết khi nó phủ định sạch nguyên nhân gốc.
#:
#: Lấy nguyên văn từ `eval/runs.csv` của Trung — 5/8 lượt UC-2 trả về đúng dạng
#: "Không có nguyên nhân gốc từ quá tải bộ nhớ hoặc crash container."
#:
#: CỐ Ý hẹp. Không bắt "không phải" trơn, vì câu ĐÚNG của luật cho UC-3 chứa
#: "không phải quá tải" — đó là loại trừ một nguyên nhân **sai**, chính là thứ
#: mình muốn giữ. Chỉ bắt việc phủ định **mọi** nguyên nhân.
_CUM_PHU_DINH = (
    "không có nguyên nhân gốc",
    "không xác định được nguyên nhân",
    "chưa xác định được nguyên nhân",
    "chưa đủ bằng chứng để nêu nguyên nhân",
)


def _phu_dinh_ket_luan_cua_luat(statement_llm: str, statement_luat: str) -> bool:
    """LLM có đang phủ định một nguyên nhân mà luật đã chứng minh không?

    ## Vì sao cần cửa này — đo được ngày 06/08 từ eval của Trung

    UC-2 sau khi Việt thêm bằng chứng bộ nhớ: luật ghép câu **đúng**
    ("OOM-kill: bộ nhớ leo tới 126 MB, chạm giới hạn 128 MB"), nhưng **5/8 lượt**
    Qwen viết lại thành:

        "Không có nguyên nhân gốc từ quá tải bộ nhớ hoặc crash container."

    kèm lý giải:

        "…đỉnh bộ nhớ 10 phút = 125.9 MB — cả hai đều nằm dưới giới hạn 128 MB,
         không cho thấy áp lực bộ nhớ."

    Nó nhìn 125,9 MB trên trần 128 MB — **98,4% trần** — rồi kết luận không có
    áp lực bộ nhớ. Đúng về số học, vô lý về vận hành. Nó còn cãi lại cả quyết
    định phát hiện: *"restart = 1, dưới ngưỡng kích hoạt là 2.000"*.

    ## Đây là mặt ngược của `_nguyen_nhan_khong_co_can_cu()`

    Cùng một khiếm khuyết thiết kế: pha 2 được phép ghi đè pha 1 **theo cả hai
    chiều**. UC-3 thì LLM *bịa thêm* nguyên nhân không có bằng chứng; UC-2 thì
    LLM *xoá đi* nguyên nhân đã có bằng chứng. Hai cửa cộng lại nói được một
    câu: **LLM chỉ được diễn đạt lại kết luận của luật, không được đổi nó.**

    Không chặn khi chính luật cũng chịu: nếu câu luật chứa
    `_LUAT_CUNG_CHIU` thì LLM nói "chưa xác định được" là **đồng ý**, giữ nguyên.
    """
    if _LUAT_CUNG_CHIU in statement_luat.lower():
        return False
    cau = statement_llm.lower()
    return any(cum in cau for cum in _CUM_PHU_DINH)


#: Nguyên nhân LLM hay nêu → bằng chứng phải có mặt để nêu được nó.
#:
#: `(từ khoá trong câu, chuỗi con trong tên MetricEvidence)`. Chuỗi con khớp
#: `MetricEvidence.name` do `rules.py` sinh, xem `test_khoa_can_cu_con_khop_voi_rules`.
#:
#: CỐ Ý không có "latency" hay "chậm": câu đúng của luật cho UC-3 có chứa
#: "latency bình thường" — một khẳng định **phủ định**, không phải nêu nguyên
#: nhân. Chặn theo từ khoá đó là bỏ đúng câu mình muốn giữ.
_CAN_CU_BAT_BUOC: tuple[tuple[tuple[str, ...], str], ...] = (
    (("pool", "connection"), "db_pool"),
    (("bộ nhớ", "memory", "oom", "ram"), "bộ nhớ"),
)

#: Từ khoá chỉ được dùng khi `correlate_deploy()` thật sự tìm ra một lần deploy.
_TU_KHOA_DEPLOY = ("deploy", "phiên bản", "rollback", "release")


def _nguyen_nhan_khong_co_can_cu(
    statement: str,
    signal: IncidentSignal,
    deploy: DeployRecord | None,
) -> str | None:
    """Câu này có nêu nguyên nhân nào mà không có bằng chứng chống lưng không?

    Trả từ khoá vi phạm đầu tiên, `None` nếu câu có căn cứ.

    ## Vì sao cần cửa này — đo được ngày 05/08 trên tấn công thật

    UC-3, 182,8 request `/login` thất bại mỗi giây, bằng chứng **duy nhất** là
    chính con số đó. Luật ghép câu đúng:

        "…183 lượt đăng nhập thất bại mỗi giây — hình thái phù hợp với
         credential-stuffing, KHÔNG PHẢI quá tải…"

    LLM viết lại thành:

        "Connection pool của service-thanh-toan cạn, gây thất bại khi xử lý
         request /login."

    Không có chữ "pool" nào trong bằng chứng. Prompt cấm thêm **số liệu** và LLM
    tuân — nhưng "pool cạn" không phải một con số, nó là **một nguyên nhân**, và
    prompt không có luật nào chặn việc lấy nguyên nhân từ kiến thức sẵn có của
    mô hình.

    Sai theo hướng tệ nhất: `docs/use-cases.md` ghi rõ kết luận "service quá
    tải" cho một vụ credential-stuffing là chẩn đoán **SAI**. Và nó còn tự tin
    hơn câu đúng (60% so với 40%), vì `confidence` do luật tính trên **bằng
    chứng** còn câu thì do LLM viết — nên một câu bịa vẫn thừa hưởng con số nghe
    đáng tin. Đó là chỗ hở trong contract ② `Hypothesis`, không phải lỗi của LLM.

    Nghịch lý đáng ghi lại: ở UC-3, **bỏ LLM đi thì chẩn đoán đúng**. Pha 2 đang
    làm chất lượng tệ hơn, không phải tốt hơn.

    Chặn ở code chứ không chỉ dặn thêm trong prompt: dặn thì phải tin mô hình
    tuân, mà chính chỗ này là bằng chứng nó không luôn tuân.
    """
    cau = statement.lower()
    ten_bang_chung = " ".join(item.name for item in signal.evidence).lower()

    for tu_khoa, chuoi_can_co in _CAN_CU_BAT_BUOC:
        if any(tu in cau for tu in tu_khoa) and chuoi_can_co.lower() not in ten_bang_chung:
            return next(tu for tu in tu_khoa if tu in cau)

    if deploy is None and any(tu in cau for tu in _TU_KHOA_DEPLOY):
        return next(tu for tu in _TU_KHOA_DEPLOY if tu in cau)

    return None


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
