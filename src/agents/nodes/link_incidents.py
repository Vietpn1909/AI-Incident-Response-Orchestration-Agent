"""Node `link_incidents` — nối các war room của một sự cố lan truyền.

CHỦ SỞ HỮU: Việt · dùng contract ③ (`src/services/jira/`)

`classify_severity` đã phát hiện lan truyền và nâng cả hai incident lên P1.
Nhưng nâng mức chỉ nói **"nặng hơn"**, nó không nói **"hai cái này là một vụ"**.
Thiếu bước nối, người trực mở Jira thấy hai issue P1 rời rạc và phải tự đoán
chúng có liên quan — đúng thứ Agent lẽ ra phải làm hộ.

`fixtures/incidents.json` mô tả trạng thái đích: `INC-12` và `INC-13` là hai
issue **nối với nhau**, không phải một issue hai service. War-room view của Long
đã có chỗ hiển thị `related_incidents` và cho bấm chuyển qua lại — trước node
này thì chỗ đó luôn rỗng.

**Nối một chiều là đủ.** Jira tự hiện link ở cả hai đầu, nên gọi
`link_issues(A, B)` rồi gọi thêm `link_issues(B, A)` chỉ tạo hai link trùng
nhau trên issue thật.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from itertools import combinations

from src.services.jira import JiraClient

logger = logging.getLogger(__name__)


@dataclass
class LinkResult:
    """Kết quả nối war room.

    `skipped` là các cặp đã nối từ vòng trước — đường đi **bình thường** khi
    Agent poll liên tục trong lúc sự cố còn kéo dài, không phải lỗi.
    """

    linked: list[tuple[str, str]] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)


def link_incidents(jira: JiraClient, war_rooms: dict[str, str]) -> LinkResult:
    """Nối từng cặp war room của các service cùng dính một sự cố.

    Args:
        jira: `FakeJiraClient` khi phát triển, `RealJiraClient` khi chạy thật.
        war_rooms: `{tên service: jira key}` của **mọi** war room đang mở ở vòng
            này — cả issue mới mở lẫn issue đã có từ trước. Chỉ lấy issue mới
            thì sự cố lan dần (service A hỏng trước, B hỏng sau vài phút) sẽ
            không bao giờ nối được, vì mỗi vòng chỉ có đúng một issue mới.

    Returns:
        `LinkResult`. Dưới hai war room thì không có gì để nối — trả rỗng.
    """
    keys = sorted(set(war_rooms.values()))
    if len(keys) < 2:
        return LinkResult()

    ket_qua = LinkResult()
    da_noi = _da_noi_san(jira, keys)

    for a, b in combinations(keys, 2):
        # Kiểm tra trước khi gọi: `RealJiraClient.link_issues()` POST thẳng lên
        # Jira, gọi lại là tạo link thứ hai giữa đúng hai issue đó. Agent poll
        # vài giây một lần trong khi sự cố kéo dài hàng chục phút, nên không
        # chặn thì issue đầy link trùng — cùng loại rác mà `find_open_incident()`
        # chặn ở `open_war_room`.
        if b in da_noi.get(a, set()) or a in da_noi.get(b, set()):
            ket_qua.skipped.append((a, b))
            continue

        jira.link_issues(a, b)
        ket_qua.linked.append((a, b))
        logger.warning("Nối %s ↔ %s — cùng một sự cố lan truyền", a, b)

    return ket_qua


def _da_noi_san(jira: JiraClient, keys: list[str]) -> dict[str, set[str]]:
    """Đọc lại quan hệ đã có trên Jira, `{jira key: các key đã nối}`.

    Lỗi đọc được nuốt cho **từng issue**: không đọc được quan hệ cũ của một
    issue thì coi như nó chưa nối gì. Hệ quả xấu nhất là một link trùng, còn
    hệ quả của việc ném lỗi ra ngoài là mất cả vòng quét của những incident
    khác — đánh đổi rõ ràng về phía nào.
    """
    da_noi: dict[str, set[str]] = {}
    for key in keys:
        try:
            incident = jira.get_incident(key)
        except Exception as error:
            logger.error("%s: không đọc được quan hệ đã có (%s)", key, error)
            continue
        if incident is not None:
            da_noi[key] = set(incident.related_incidents)
    return da_noi
