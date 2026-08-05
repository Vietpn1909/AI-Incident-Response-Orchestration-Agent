import pytest

from eval.run_measurements import diagnosis_correct


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Burst phù hợp credential-stuffing, không phải quá tải.", True),
        ("Đây là vấn đề bảo mật, không phải là quá tải.", True),
        ("Service quá tải nên login thất bại.", False),
        ("Connection pool cạn.", False),
        ("Chưa xác định được nguyên nhân gốc.", False),
    ],
)
def test_cham_uc3_hieu_phu_dinh(text: str, expected: bool):
    assert diagnosis_correct("UC-3", text) is expected


def test_cham_uc2_khong_nhan_cau_phu_dinh_oom():
    text = (
        "Không có nguyên nhân gốc từ quá tải bộ nhớ hoặc crash container. "
        "Số liệu không cho thấy áp lực bộ nhớ."
    )

    assert not diagnosis_correct("UC-2", text)
