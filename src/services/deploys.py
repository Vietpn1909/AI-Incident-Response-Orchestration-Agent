"""Đọc lịch sử deploy — nguồn "nghi phạm" cho `correlate_deploy`.

CHỦ SỞ HỮU: Việt

Bảng `deploy_history` do [`demo/seed.py`](../../demo/seed.py) tạo và seed. Đây
là **chỗ duy nhất** `src/` chạm vào cơ sở dữ liệu của `demo/`, và nó có lý do:

    src/  ──── HTTP ────▶  demo/       ✅
    src/  ──── import ──▶  demo/       ❌   (luật ở demo/README.md)

Đọc bảng bằng SQL không phải `import`, nên không phạm luật đó. Nhưng nó vẫn
buộc `src/` biết schema của `demo/`, nên chốt cho rõ: contract ② đã cho phép —
`DeployRecord` ghi thẳng *"Đọc từ bảng deploy_history giả lập do Trung seed"*.

Trong hệ thật, lịch sử deploy đến từ CI/CD chứ không phải database của service.
Khi đó chỉ cần thay thân `recent_deploys()`; `correlate_deploy()` trong
`rules.py` không phải đổi vì nó chỉ nhận `list[DeployRecord]`.
"""

from __future__ import annotations

import asyncio
import logging

import asyncpg

from src.config import get_settings
from src.models.incident import DeployRecord

logger = logging.getLogger(__name__)

#: Lấy tối đa bấy nhiêu bản ghi. `correlate_deploy` chỉ quan tâm vài lần deploy
#: gần nhất, kéo cả bảng về là phí.
_LIMIT = 20

_QUERY = """
SELECT service, version, deployed_at, deployed_by, commit_sha, change_note
FROM deploy_history
WHERE service = $1
ORDER BY deployed_at DESC
LIMIT $2
"""


async def _fetch(service: str, limit: int) -> list[DeployRecord]:
    """Phần async thật sự — `asyncpg` không có API đồng bộ."""
    conn = await asyncpg.connect(get_settings().database_url)
    try:
        rows = await conn.fetch(_QUERY, service, limit)
    finally:
        await conn.close()

    return [
        DeployRecord(
            service=row["service"],
            version=row["version"],
            deployed_at=row["deployed_at"],
            deployed_by=row["deployed_by"] or "",
            commit_sha=row["commit_sha"] or "",
            change_note=row["change_note"] or "",
        )
        for row in rows
    ]


def recent_deploys(service: str, limit: int = _LIMIT) -> list[DeployRecord]:
    """Các lần deploy gần nhất của một service, mới nhất trước.

    Đồng bộ, dù `asyncpg` là async: cả graph và `run_cycle()` đều đồng bộ, nên
    gói `asyncio.run()` vào đây để chỗ gọi không phải biết. Đổi lại là **không
    gọi được hàm này từ trong event loop đang chạy** — nếu sau này có route
    FastAPI cần lịch sử deploy thì gọi thẳng `_fetch()` bằng `await`.

    Returns:
        Danh sách rỗng khi **không đọc được bảng** cũng như khi **service chưa
        deploy lần nào**. Hai tình huống này cố ý gộp làm một, ngược với cách
        `PrometheusClient` phân biệt rỗng với lỗi.

        Lý do khác nhau: thiếu metric thì Agent mù, không kết luận được gì.
        Thiếu lịch sử deploy thì Agent vẫn chẩn đoán được — chỉ là thiếu một
        bằng chứng phụ, và `confidence` tự thấp xuống đúng phần đóng góp của
        bằng chứng đó. Làm Agent im lặng vì không đọc nổi một bảng phụ là đánh
        đổi sai.
    """
    try:
        return asyncio.run(_fetch(service, limit))
    except RuntimeError as error:
        # `asyncio.run` bên trong event loop đang chạy. Đây là lỗi lập trình,
        # không phải sự cố hạ tầng — nói rõ thay vì để nó lẫn vào nhóm dưới.
        logger.error("recent_deploys() gọi từ trong event loop — dùng `await _fetch()`: %s", error)
        return []
    except Exception as error:
        # Bắt rộng: asyncpg ném đủ loại (sai mật khẩu, sai host, DB chưa lên,
        # bảng chưa seed). Với chỗ gọi thì chúng như nhau — không có lịch sử
        # deploy để đối chiếu.
        logger.warning("Không đọc được deploy_history (%s) — chẩn đoán sẽ thiếu bằng chứng deploy", error)
        return []
