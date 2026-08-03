"""Test node `hypothesize` — chỗ duy nhất Agent gọi LLM.

Dùng LLM giả nên không cần key, không cần mạng, chạy được trong CI.

Điều đáng test nhất không phải "LLM có viết hay không", mà là **ranh giới giữa
hai pha**: rule engine giữ `evidence` và `confidence`, LLM chỉ được đụng vào
`statement` và `reasoning`. Contract ② ghi "không đảo ngược thứ tự này" — test
ở đây là thứ giữ cho câu đó có hiệu lực.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.agents.nodes import hypothesize as node
from src.agents.nodes.hypothesize import _parse, hypothesize
from src.models.incident import DeployRecord, IncidentSignal, MetricEvidence, Severity

NOW = datetime(2026, 8, 3, 16, 13, 0, tzinfo=UTC)

TRA_LOI_CHUAN = """\
GIẢ THUYẾT: Connection pool cạn kiệt khiến request phải xếp hàng chờ.
LÝ GIẢI: p95 đạt 4.4s, gấp 3.7 lần mức thường ngày 1.19s. Pool dùng hết 5/5 chỗ.
Không có lỗi 5xx nên service vẫn xử lý được, chỉ là chậm vì chờ connection.\
"""


class FakeLLM:
    """LLM giả. `reply=None` nghĩa là gọi hỏng."""

    def __init__(self, reply: str | None = TRA_LOI_CHUAN) -> None:
        self._reply = reply
        self.calls: list[list] = []

    def invoke(self, messages):
        self.calls.append(messages)
        if self._reply is None:
            raise RuntimeError("hết quota")
        return type("Reply", (), {"content": self._reply})()


@pytest.fixture(autouse=True)
def _khong_doc_db(monkeypatch):
    """Mặc định không có lịch sử deploy — test nào cần thì tự ghi đè."""
    monkeypatch.setattr(node.deploys, "recent_deploys", lambda service: [])


def _signal() -> IncidentSignal:
    return IncidentSignal(
        affected_service="service-thanh-toan",
        severity=Severity.P2,
        detected_at=NOW,
        metric_name="http_request_duration_seconds p95",
        metric_value=4.4,
        threshold=2.0,
        breached_for_seconds=60.0,
        evidence=[
            MetricEvidence(
                name="http_request_duration_seconds p95", value=4.4, baseline=1.19, unit="s", promql="hq(...)"
            ),
            MetricEvidence(name="db_pool_connections_in_use / db_pool_size", value=1.0, promql="pool(...)"),
            MetricEvidence(name="tỷ lệ lỗi 5xx", value=0.0, promql="err(...)"),
        ],
    )


# ──────────────────────────────────────────── ranh giới giữa rule và LLM


def test_llm_viet_statement_va_reasoning():
    hypothesis = hypothesize(_signal(), llm=FakeLLM())

    assert hypothesis.statement == "Connection pool cạn kiệt khiến request phải xếp hàng chờ."
    assert "3.7 lần" in hypothesis.reasoning


def test_llm_khong_dung_toi_confidence_va_evidence():
    """Contract ②: rule engine điền evidence và confidence, LLM chỉ viết lời."""
    signal = _signal()

    voi_llm = hypothesize(signal, llm=FakeLLM())
    khong_llm = hypothesize(signal, llm=FakeLLM(reply=None))

    assert voi_llm.confidence == khong_llm.confidence
    assert voi_llm.evidence == khong_llm.evidence == signal.evidence


def test_llm_tra_loi_ba_lang_van_khong_doi_duoc_con_so():
    """Kể cả khi LLM tự nhận độ tin cậy, con số vẫn do rule engine giữ."""
    bia = "GIẢ THUYẾT: Tôi 99% chắc chắn là do deploy v9.9.9 gây ra.\nLÝ GIẢI: p95 lên tới 42s."

    hypothesis = hypothesize(_signal(), llm=FakeLLM(reply=bia))

    # Câu chữ đúng là bị LLM bịa — nhưng con số và bằng chứng thì không.
    # 0.70 = pool cạn (0.40) + p95 lệch 3.7× (0.30). Không có deploy nên không
    # có 0.20, dù LLM vừa khẳng định chắc nịch là "do deploy v9.9.9".
    assert hypothesis.confidence == 0.70
    assert [item.value for item in hypothesis.evidence] == [4.4, 1.0, 0.0]
    assert hypothesis.related_deploy is None


# ──────────────────────────────────────────── LLM hỏng vẫn phải chẩn đoán


def test_llm_hong_thi_van_co_giai_thuyet_dung_duoc():
    """DashScope hết quota giữa buổi demo là chuyện có thật.

    Mất câu văn hay còn hơn mất cả phần chẩn đoán.
    """
    hypothesis = hypothesize(_signal(), llm=FakeLLM(reply=None))

    assert hypothesis.confidence > 0
    assert hypothesis.evidence
    assert "pool" in hypothesis.statement.lower()
    assert hypothesis.reasoning == ""


def test_llm_tra_loi_rong_thi_giu_cau_cua_luat():
    hypothesis = hypothesize(_signal(), llm=FakeLLM(reply="   "))

    assert "pool" in hypothesis.statement.lower()


# ──────────────────────────────────────────── prompt


def test_prompt_mang_theo_bang_chung_that():
    llm = FakeLLM()
    hypothesize(_signal(), llm=llm)

    prompt = llm.calls[0][1][1]
    assert "4.4" in prompt
    assert "1.19" in prompt
    assert "service-thanh-toan" in prompt


def test_prompt_cam_bia_so_va_cam_tu_nhan_do_tin_cay():
    llm = FakeLLM()
    hypothesize(_signal(), llm=llm)

    system = llm.calls[0][0][1]
    assert "không tự thêm số liệu" in system.lower()
    assert "không nêu độ tin cậy" in system.lower()


def test_prompt_cam_suy_nhan_qua_tu_deploy(monkeypatch):
    monkeypatch.setattr(
        node.deploys,
        "recent_deploys",
        lambda service: [DeployRecord(service=service, version="v1.4.2", deployed_at=NOW)],
    )
    llm = FakeLLM()
    hypothesize(_signal(), llm=llm)

    system = llm.calls[0][0][1]
    assert "trùng thời gian" in system.lower()
    assert "không viết" in system.lower()


# ──────────────────────────────────────────── parse chịu được lệch định dạng


@pytest.mark.parametrize(
    ("reply", "mong_doi_statement"),
    [
        ("GIẢ THUYẾT: Pool cạn.\nLÝ GIẢI: vì abc.", "Pool cạn."),
        # Thiếu nhãn — lấy dòng đầu.
        ("Pool cạn kiệt do tải tăng.", "Pool cạn kiệt do tải tăng."),
        # Thừa dòng trống.
        ("\n\nGIẢ THUYẾT: Pool cạn.\n\nLÝ GIẢI: vì abc.\n", "Pool cạn."),
    ],
)
def test_parse_chiu_duoc_lech_dinh_dang(reply, mong_doi_statement):
    statement, _ = _parse(reply)
    assert statement == mong_doi_statement


def test_parse_gop_lam_nhieu_dong_cua_ly_giai():
    _, reasoning = _parse("GIẢ THUYẾT: A.\nLÝ GIẢI: câu một.\ncâu hai.\ncâu ba.")

    assert reasoning == "câu một. câu hai. câu ba."
