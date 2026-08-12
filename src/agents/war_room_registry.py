"""Trí nhớ của Agent về việc nó đã làm gì cho từng war room.

CHỦ SỞ HỮU: Việt

## Vì sao cần một chỗ nhớ riêng, ngoài state của graph

`run_cycle()` **cố ý** không giữ trạng thái gì giữa các vòng — docstring của
[`detection_loop.py`](detection_loop.py) ghi rõ lý do: graph dựng lại mỗi vòng
để client thay giữa chừng lúc test không làm hỏng gì. Còn `IncidentAgentState`
thì chết theo từng lần `invoke()`.

Nhưng hai việc dưới đây **bắt buộc** phải nhớ xuyên vòng quét, nếu không sẽ sai:

1. **Phòng họp.** Bản free của Daily chỉ cho 5 phòng đồng thời, mà Agent quét 10
   giây một vòng. Không nhớ thì mỗi vòng mở lại một phòng cho cùng một sự cố và
   chưa tới một phút đã hết hạn mức.
2. **Mail cảnh báo.** Không nhớ thì người trực nhận một mail mỗi 10 giây suốt cả
   sự cố. Lần thứ ba là họ tạo filter cho vào thùng rác, và Agent mất hẳn kênh
   gọi người.

Nên trạng thái này do **người gọi sở hữu**: `run_agent.py` giữ một instance suốt
đời tiến trình rồi truyền xuống. `run_cycle()` vẫn không tự giữ gì — nó chỉ đọc
ghi lên object được đưa vào. Test muốn bắt đầu sạch thì dựng một cái mới.

## Sự cố ngày 12/08 sinh ra file này

Đo thật trên demo stack: vòng 1 chỉ `service-dat-hang` vượt ngưỡng nên nó là P3
→ không mở phòng. Vòng 2 `service-thanh-toan` vượt theo, đủ 2 service nên luật
nâng CẢ HAI lên P1 — nhưng INC-1 lúc đó không còn `created=True` nữa. Kết quả:
INC-1 không bao giờ có phòng họp, dù nó đã là P1 và đã được `link_incidents` nối
với INC-2 như cùng một sự cố.

Nó trượt vì hai lý do **khác nhau** ở hai vòng, nên đọc từng điều kiện riêng lẻ
không thấy được. Registry này chính là thứ chữa: điều kiện không còn là "vừa mở
mới" mà là "đang mở, đủ nặng, và **chưa có** phòng".
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class WarRoomRegistry:
    """Nhớ war room nào đã có phòng họp và đã báo mail, xuyên các vòng quét.

    Chỉ nằm trong bộ nhớ. Agent restart giữa lúc sự cố còn diễn ra thì nó quên
    hết và mở một phòng mới — chấp nhận được, vì phòng cũ tự hết hạn sau 4 giờ
    và một mail lặp còn hơn không có mail nào. Lưu xuống đĩa hay lên Jira để
    sống qua restart là việc khác, cần bàn riêng.
    """

    #: `{jira key: URL phòng họp}` — mọi war room đã được gán phòng.
    phong_hop: dict[str, str] = field(default_factory=dict)

    #: Jira key của những war room đã gửi mail cảnh báo rồi.
    da_bao_mail: set[str] = field(default_factory=set)

    def url_cua_cum(self, jira_keys: list[str]) -> str | None:
        """URL phòng mà **bất kỳ** war room nào trong cụm đang dùng.

        Đây là chỗ thực hiện quyết định "một sự cố một phòng": các war room của
        cùng một sự cố lan truyền đều xuất phát từ một lỗi gốc, nên người trực
        phải vào **cùng một cuộc gọi**. Mở cho mỗi issue một phòng riêng thì họ
        bị chia thành hai nhóm nói chuyện tách nhau — tệ hơn cả việc không có
        phòng nào.

        Trả `None` khi cả cụm chưa ai có phòng, tức là cần mở mới.
        """
        for key in jira_keys:
            url = self.phong_hop.get(key)
            if url:
                return url
        return None

    def gan_phong(self, jira_keys: list[str], url: str) -> list[str]:
        """Gán `url` cho cả cụm. Trả về những key **lần đầu** được gán.

        Danh sách trả về là thứ quyết định gửi mail cho ai: chỉ war room vừa
        nhận phòng lần đầu mới cần báo, còn cái đã có từ vòng trước thì thôi.
        """
        moi: list[str] = []
        for key in jira_keys:
            if key not in self.phong_hop:
                self.phong_hop[key] = url
                moi.append(key)
        return moi

    def can_bao_mail(self, jira_key: str) -> bool:
        """War room này đã báo mail chưa. Không tự đánh dấu — xem `da_bao()`.

        Tách việc hỏi khỏi việc đánh dấu là cố ý: chỉ đánh dấu **sau khi** gửi
        thành công, để một lần SMTP hỏng không làm mất luôn cảnh báo mãi mãi.
        """
        return jira_key not in self.da_bao_mail

    def da_bao(self, jira_key: str) -> None:
        """Đánh dấu đã gửi mail cho war room này."""
        self.da_bao_mail.add(jira_key)
