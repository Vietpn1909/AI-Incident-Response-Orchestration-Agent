"""Tạo phòng họp online cho war room — Daily.co.

CHỦ SỞ HỮU: Việt

Dùng `httpx` — đã có sẵn trong `requirements.txt` cho Prometheus và Jira, KHÔNG
thêm dependency mới. Giữ đúng tinh thần `email_client.py`: một tính năng phụ
không được kéo theo một thư viện nữa.

## Vì sao Daily.co, KHÔNG phải Google Meet

Đã điều tra và chốt — đừng đề xuất lại:

1. Meet REST API **chỉ nhận OAuth 2.0 user authentication**. Tài liệu Google ghi
   nguyên văn *"For Meet REST API, you can only authenticate using user
   authentication"* — API key bị từ chối thẳng, không có đường service account.
2. Đi đường OAuth thì phải dựng consent screen trên Google Cloud, và refresh
   token ở chế độ Testing **hết hạn sau 7 ngày**. Tức nó sẽ hỏng đúng vào lúc
   demo, mà lại hỏng im lặng cho tới khi ai đó bấm thử link.
3. Daily.co: một API key Bearer duy nhất, không hết hạn, chạy headless được trên
   Render, free 10.000 phút/tháng — đủ xa so với mức dùng của cả đợt demo.

## Không retry

Cùng lý do đã ghi trong docstring `GmailClient`: mở phòng họp là việc **phụ**
bám bên cạnh việc mở war room. Hỏng thì log warning rồi đi tiếp — retry ở đây
chỉ block luồng Agent, mà Agent đang poll Prometheus vài giây một lần.

## Lấy API key

daily.co → Dashboard → Developers → copy vào `DAILY_API_KEY` trong `.env`.
"""

from __future__ import annotations

import logging
import secrets
import time
from dataclasses import dataclass

import httpx

from src.config import get_settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Daily.co REST API
# ---------------------------------------------------------------------------
DAILY_ROOMS_URL = "https://api.daily.co/v1/rooms"

#: Phòng tự hết hạn sau 4 giờ. Đây là ràng buộc BẮT BUỘC, không phải tuỳ chọn:
#: bản free chỉ cho **5 phòng tồn tại đồng thời**. Không đặt `exp` thì phòng
#: sống mãi, và tới lần chạy demo thứ sáu Daily trả lỗi hết quota — đúng lúc
#: đang trình bày. Có hạn 4 giờ thì phòng tự dọn, chạy lại bao nhiêu lần cũng
#: không đụng trần, mà vẫn thừa thời gian cho một buổi ứng phó sự cố thật.
ROOM_TTL_SECONDS = 4 * 60 * 60


@dataclass(frozen=True)
class MeetingRoom:
    """Phòng họp vừa mở — chỉ giữ thứ người trực cần: link để bấm vào."""

    url: str
    name: str


def _dat_ten_phong(jira_key: str) -> str:
    """Sinh tên phòng cho một war room, vd. `warroom-kan-11-a7f3`.

    Phần ngẫu nhiên 4 ký tự là **bắt buộc**, không phải để cho đẹp: Daily trả
    400 khi tên phòng đã tồn tại. Sự cố tái diễn trên cùng một service sẽ mở lại
    war room với đúng jira key cũ (xem `test_incident_da_dong_thi_mo_lai_issue_moi`),
    và nếu tên trùng thì lần thứ hai không bao giờ có phòng.
    """
    return f"warroom-{jira_key.lower()}-{secrets.token_hex(2)}"


class DailyRoomClient:
    """Mở phòng họp qua Daily.co REST API.

    Mọi lỗi đều nuốt và trả `None` — xem mục "Không retry" ở đầu file. Người gọi
    chỉ cần phân biệt "có link" và "không có link", không cần biết vì sao.
    """

    def __init__(self, api_key: str, *, timeout: float = 15.0) -> None:
        if not api_key:
            raise ValueError(
                "Thiếu DAILY_API_KEY trong cấu hình. "
                "Lấy key: daily.co → Dashboard → Developers"
            )
        self._api_key = api_key
        self._timeout = timeout

    def create(self, jira_key: str) -> MeetingRoom | None:
        """Mở một phòng họp cho war room `jira_key`.

        Returns:
            `MeetingRoom` khi Daily nhận, `None` khi bất kỳ lỗi nào — sai key,
            mạng chập, hay Daily trả body không như mong đợi. Người gọi coi
            `None` là "war room này không có phòng họp", không phải lỗi cần dừng.
        """
        ten = _dat_ten_phong(jira_key)
        body = {
            "name": ten,
            # `public` để người nhận link bấm vào là vào thẳng. `private` thì
            # mỗi người cần một meeting token riêng — thêm một lời gọi API nữa
            # cho mỗi người trực, giữa lúc đang có sự cố.
            "privacy": "public",
            "properties": {"exp": int(time.time()) + ROOM_TTL_SECONDS},
        }

        try:
            response = httpx.post(
                DAILY_ROOMS_URL,
                headers={"Authorization": f"Bearer {self._api_key}"},
                json=body,
                timeout=self._timeout,
            )
            response.raise_for_status()
            data = response.json()
            return MeetingRoom(url=data["url"], name=data["name"])

        except httpx.HTTPStatusError as error:
            # Phải bắt TRƯỚC `httpx.HTTPError` — nó là lớp con.
            status = error.response.status_code
            if status in (401, 403):
                logger.warning(
                    "%s: Daily từ chối xác thực (%d) — kiểm DAILY_API_KEY trong .env. "
                    "Lấy lại key: daily.co → Dashboard → Developers",
                    jira_key,
                    status,
                )
            else:
                logger.warning(
                    "%s: Daily trả %d khi mở phòng %s (%s)", jira_key, status, ten, error
                )
            return None

        except httpx.HTTPError as error:
            logger.warning(
                "%s: không gọi được Daily để mở phòng họp (%s: %s)",
                jira_key,
                type(error).__name__,
                error,
            )
            return None

        except Exception as error:
            # Body không có `url`/`name`, JSON hỏng… Daily đổi định dạng response
            # cũng không được làm chết vòng quét của Agent.
            logger.warning(
                "%s: Daily trả về thứ không đọc được (%s: %s)",
                jira_key,
                type(error).__name__,
                error,
            )
            return None


def build_room_client() -> DailyRoomClient | None:
    """Dựng client từ `.env`, hoặc `None` khi chưa cấu hình.

    Trả `None` thay vì raise: thiếu `DAILY_API_KEY` chỉ có nghĩa là war room mở
    ra không kèm link họp — Agent vẫn phát hiện, vẫn mở issue, vẫn chẩn đoán.
    Đây là lý do `run_agent.py` KHÔNG `sys.exit` cho biến này như nó làm với
    cấu hình Jira.
    """
    settings = get_settings()
    if not settings.daily_api_key:
        logger.warning(
            "Chưa có DAILY_API_KEY — war room sẽ mở không kèm phòng họp. "
            "Lấy key: daily.co → Dashboard → Developers"
        )
        return None
    return DailyRoomClient(settings.daily_api_key)
