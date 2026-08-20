"""Test `src/services/meeting_room.py`.

Chạy KHÔNG gọi Daily thật — mock `httpx.post`, giống cách
`test_email_client.py` mock `smtplib`.

Không có lời gọi mạng nào ở đây là **cố ý**, và không chỉ vì tốc độ: bản free
của Daily chỉ cho 5 phòng tồn tại đồng thời, nên một test gọi thật sẽ đốt dần
hạn mức của cả đội cho tới lúc demo hết chỗ mở phòng.
"""

from __future__ import annotations

import time
from unittest.mock import patch

import httpx
import pytest

from src.services.meeting_room import (
    DAILY_ROOMS_URL,
    DailyRoomClient,
    MeetingRoom,
    _dat_ten_phong,
)

#: Body Daily trả về khi tạo phòng thành công — rút gọn còn hai field code đọc.
DAILY_OK = {
    "url": "https://ai20k.daily.co/warroom-inc-1-a7f3",
    "name": "warroom-inc-1-a7f3",
}


def _response(status: int, body: dict | None = None) -> httpx.Response:
    """Response httpx thật, có `request` để `raise_for_status()` chạy được.

    Dùng `httpx.Response` thật thay vì `MagicMock`: `raise_for_status()` khi
    thiếu `request` ném `RuntimeError` chứ không phải `HTTPStatusError`, nên
    mock lỏng tay ở đây sẽ nghiệm thu nhánh `except` sai.
    """
    return httpx.Response(
        status,
        json=body if body is not None else {},
        request=httpx.Request("POST", DAILY_ROOMS_URL),
    )


# ────────── đặt tên phòng ──────────


class TestDatTenPhong:
    def test_chua_jira_key_viet_thuong(self):
        assert _dat_ten_phong("KAN-11").startswith("warroom-kan-11-")

    def test_hai_lan_goi_ra_hai_ten_khac_nhau(self):
        """Trùng tên thì Daily trả 400.

        Sự cố tái diễn trên cùng một service mở lại war room với đúng jira key
        cũ, nên nếu tên phòng chỉ gồm jira key thì lần thứ hai không bao giờ có
        phòng — mà đó lại đúng là lúc cần nó.
        """
        assert _dat_ten_phong("KAN-11") != _dat_ten_phong("KAN-11")


# ────────── DailyRoomClient ──────────


class TestDailyRoomClient:
    def test_thieu_api_key_thi_raise(self):
        with pytest.raises(ValueError, match="DAILY_API_KEY"):
            DailyRoomClient("")

    @patch("src.services.meeting_room.httpx.post")
    def test_tao_phong_thanh_cong(self, mock_post):
        mock_post.return_value = _response(200, DAILY_OK)

        room = DailyRoomClient("fake-key").create("INC-1")

        assert isinstance(room, MeetingRoom)
        assert room.url == DAILY_OK["url"]
        assert room.name == DAILY_OK["name"]

    @patch("src.services.meeting_room.httpx.post")
    def test_gui_dung_url_va_bearer_token(self, mock_post):
        mock_post.return_value = _response(200, DAILY_OK)

        DailyRoomClient("fake-key").create("INC-1")

        assert mock_post.call_args[0][0] == DAILY_ROOMS_URL
        assert mock_post.call_args[1]["headers"]["Authorization"] == "Bearer fake-key"

    @patch("src.services.meeting_room.httpx.post")
    def test_ten_phong_chua_jira_key_viet_thuong(self, mock_post):
        mock_post.return_value = _response(200, DAILY_OK)

        DailyRoomClient("fake-key").create("KAN-11")

        assert mock_post.call_args[1]["json"]["name"].startswith("warroom-kan-11-")

    @patch("src.services.meeting_room.httpx.post")
    def test_hai_lan_cung_jira_key_ra_hai_ten_khac_nhau(self, mock_post):
        """Mở lại war room cho cùng một issue mà trùng tên thì Daily trả 400."""
        mock_post.return_value = _response(200, DAILY_OK)

        client = DailyRoomClient("fake-key")
        client.create("KAN-11")
        client.create("KAN-11")

        ten_lan_1 = mock_post.call_args_list[0][1]["json"]["name"]
        ten_lan_2 = mock_post.call_args_list[1][1]["json"]["name"]
        assert ten_lan_1 != ten_lan_2

    @patch("src.services.meeting_room.httpx.post")
    def test_exp_la_unix_seconds_trong_tuong_lai(self, mock_post):
        """Thiếu `exp` thì phòng sống mãi và bản free hết chỗ sau 5 lần demo.

        Kiểm cả đơn vị: Daily nhận **giây**, gửi nhầm mili-giây thì `exp` rơi
        vào năm 57000 và phòng thành vĩnh viễn — đúng thứ `exp` sinh ra để chặn.
        """
        mock_post.return_value = _response(200, DAILY_OK)
        truoc = int(time.time())

        DailyRoomClient("fake-key").create("INC-1")

        exp = mock_post.call_args[1]["json"]["properties"]["exp"]
        assert isinstance(exp, int)
        assert exp > truoc
        # 4 giờ = 14400s. Nới hai đầu cho thời gian chạy test, nhưng vẫn đủ chặt
        # để bắt lỗi sai đơn vị.
        assert truoc + 14_000 < exp < truoc + 15_000

    @patch("src.services.meeting_room.httpx.post")
    def test_privacy_la_public(self, mock_post):
        """`private` thì mỗi người cần một meeting token riêng mới vào được."""
        mock_post.return_value = _response(200, DAILY_OK)

        DailyRoomClient("fake-key").create("INC-1")

        assert mock_post.call_args[1]["json"]["privacy"] == "public"

    @patch("src.services.meeting_room.httpx.post")
    def test_sai_api_key_thi_tra_none_va_log_warning(self, mock_post, caplog):
        """401 → `None`, KHÔNG raise, và log phải nói rõ là sai DAILY_API_KEY."""
        mock_post.return_value = _response(401, {"error": "authentication-error"})

        with caplog.at_level("WARNING"):
            room = DailyRoomClient("wrong-key").create("INC-1")

        assert room is None
        assert "DAILY_API_KEY" in caplog.text

    @patch("src.services.meeting_room.httpx.post")
    def test_403_cung_tra_none(self, mock_post):
        mock_post.return_value = _response(403, {"error": "forbidden"})

        assert DailyRoomClient("fake-key").create("INC-1") is None

    @patch("src.services.meeting_room.httpx.post")
    def test_mat_ket_noi_thi_tra_none(self, mock_post):
        """Mạng chập không được làm chết vòng quét của Agent."""
        mock_post.side_effect = httpx.ConnectError("Connection refused")

        assert DailyRoomClient("fake-key").create("INC-1") is None

    @patch("src.services.meeting_room.httpx.post")
    def test_timeout_thi_tra_none(self, mock_post):
        mock_post.side_effect = httpx.ReadTimeout("timed out")

        assert DailyRoomClient("fake-key").create("INC-1") is None

    @patch("src.services.meeting_room.httpx.post")
    def test_body_thieu_field_thi_tra_none(self, mock_post):
        """Daily đổi định dạng response cũng không được ném ra ngoài."""
        mock_post.return_value = _response(200, {"name": "warroom-inc-1-a7f3"})

        assert DailyRoomClient("fake-key").create("INC-1") is None
