"""Thi hành khắc phục THẬT trên stack demo — mặc định TẮT.

CHỦ SỞ HỮU: Đức

`remediation.execute()` là lớp **chính sách**: kiểm hành động có hợp lệ không,
bắt buộc có `approved_by`, trả kết quả thống nhất. Module này là lớp **thi
hành**: chỗ duy nhất trong repo thật sự chạm vào hệ thống.

## Năm lớp chặn, và vì sao cần cả năm

Đây là chỗ một AI Agent chạy lệnh `docker` trên máy thật. Một lớp là không đủ.

1. **Cổng HITL** — `remediation.execute()` từ chối nếu thiếu `approved_by`, mà
   giá trị đó chỉ có sau khi `hitl.assert_human_approved()` đọc changelog Jira
   và xác nhận người chuyển trạng thái KHÁC account Agent.
2. **Tắt theo mặc định** — không đặt `REMEDIATION_REAL=1` thì module này không
   bao giờ chạy, và mọi hành động vẫn mô phỏng như trước.
3. **Danh sách trắng theo CẶP (hành động, đối tượng)** — không phải theo hành
   động. `rollback` trên `service-thanh-toan` được phép; `rollback` trên bất kỳ
   tên nào khác thì không. LLM có sinh ra `target` lạ cũng không đi tới đâu.
4. **Lệnh cố định, KHÔNG dựng chuỗi shell** — tham số truyền dạng list, không
   `shell=True`, và không có giá trị nào từ LLM hay Jira lọt vào dòng lệnh. Kể cả
   `target` cũng chỉ dùng để TRA trong bảng, không nối vào lệnh.
5. **Kiểm điều kiện THẬT của hệ thống** — chỉ thi hành khi container đang bật
   `SIMULATE_MISSING_MIGRATION`, tức đúng là sự cố UC-4.

   Bốn lớp đầu lo **an toàn**; lớp này lo **đúng việc**. Chúng khác nhau, và
   thiếu lớp 5 là bug: danh sách trắng khớp theo cặp `(hành động, đối tượng)` nên
   nó không biết đang xử sự cố nào, mà UC-1 (pool cạn do tải) CŨNG đề xuất
   `rollback → service-thanh-toan` khi có deploy trùng thời gian — đã thấy trên
   KAN-19 và KAN-25 lúc chạy live.

   Không có lớp 5 thì UC-1 bị "sửa" bằng cách tắt một cờ vốn đã tắt rồi restart,
   và báo "thành công" KHÔNG kèm "(mô phỏng)". Restart không chữa được pool cạn.
   **Báo cáo sai sự thật tệ hơn thừa nhận mô phỏng** — người trực đọc "đã sửa"
   rồi đi ngủ, trong khi sự cố vẫn đang diễn ra.

## Vì sao chỉ làm UC-4

"Rollback `v1.4.3` → `v1.4.2`" trên stack demo chính là **tắt cờ
`SIMULATE_MISSING_MIGRATION` rồi khởi động lại container** — vì bản `v1.4.3`
trong kịch bản là bản deploy thiếu migration, và cờ đó chính là thứ mô phỏng nó.

Nên đây không phải "giả vờ sửa": nó đảo đúng thay đổi đã gây ra sự cố, và hiệu
quả đo được ngay trên Prometheus — tỷ lệ lỗi 100% → 0% trong khoảng 30 giây.

Ba hành động còn lại (`scale_up`, `increase_pool`, `rate_limit`) vẫn mô phỏng:
chúng cần đổi cấu hình service hoặc dựng thêm instance, không đảo được bằng một
lệnh, và không phải chỗ đáng tiêu thời gian trước buổi demo.
"""

from __future__ import annotations

import logging
import os
import pathlib
import subprocess

logger = logging.getLogger(__name__)

#: Bật thi hành thật. Không đặt, hoặc đặt khác "1", thì mọi thứ vẫn mô phỏng.
_BIEN_BAT = "REMEDIATION_REAL"

#: Đường dẫn file compose, tính từ gốc repo — không đọc từ biến môi trường để
#: không ai trỏ nó sang một stack khác bằng cách đặt biến.
_COMPOSE = pathlib.Path(__file__).resolve().parents[2] / "docker-compose.demo.yml"

#: Danh sách trắng theo CẶP (hành động, đối tượng). Thiếu cặp nào là không thi
#: hành cặp đó, chứ không phải "thi hành đại khái".
_CHO_PHEP = {
    ("rollback", "service-thanh-toan"): "p035-demo-service-thanh-toan-1",
}

_TIMEOUT_GIAY = 90.0


def co_bat_thi_hanh_that() -> bool:
    """Có bật thi hành thật không. Tách hàm riêng để test đọc được cùng một chỗ."""
    return os.getenv(_BIEN_BAT, "").strip() == "1"


def _co_dang_bat_co_loi(container: str) -> bool:
    """Container có đang chạy với `SIMULATE_MISSING_MIGRATION=1` không.

    Đây là dấu hiệu duy nhất phân biệt "sự cố UC-4, rollback là cách sửa đúng"
    với "một sự cố khác cũng tình cờ đề xuất rollback".

    Đọc hỏng thì trả `False` — thà giữ mô phỏng còn hơn chạy một hành động không
    biết có đúng việc hay không.
    """
    try:
        out = subprocess.run(  # noqa: S603
            ["docker", "exec", container, "printenv", "SIMULATE_MISSING_MIGRATION"],  # noqa: S607
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except Exception:
        return False
    return out.returncode == 0 and out.stdout.strip() == "1"


def thi_hanh_that(action: str, target: str) -> tuple[bool, str] | None:
    """Thi hành thật nếu cặp `(action, target)` nằm trong danh sách trắng.

    Returns:
        `(thành công, mô tả)` nếu đã thi hành thật.
        `None` nếu **không** áp dụng — người gọi giữ nguyên đường mô phỏng.

    Không bao giờ ném ra ngoài: hỏng ở đây trả `(False, lý do)` để war room ghi
    lại được là đã thử và thất bại. Ném ra sẽ thành HTTP 500 trống rỗng trên
    webhook, và người trực chỉ biết "có gì đó sai".
    """
    if not co_bat_thi_hanh_that():
        return None

    container = _CHO_PHEP.get((action, target))
    if container is None:
        logger.info(
            "Cặp (%s, %s) không nằm trong danh sách trắng thi hành thật — giữ mô phỏng",
            action, target,
        )
        return None

    if not _COMPOSE.is_file():
        return False, f"Không tìm thấy {_COMPOSE.name} — không thi hành được."

    # Kiểm ĐIỀU KIỆN THẬT của hệ thống, không tin vào tên hành động.
    #
    # Danh sách trắng khớp theo cặp `(hành động, đối tượng)` nên nó **không biết
    # đang xử sự cố nào**. Mà UC-1 (pool cạn do tải) CŨNG đề xuất
    # `rollback → service-thanh-toan` khi có deploy trùng thời gian — đã đo ngày
    # 17/08 và trên chính KAN-19, KAN-25 lúc chạy live.
    #
    # Không có bước kiểm này thì UC-1 bị "sửa" bằng cách tắt một cờ vốn đã tắt
    # rồi restart container, và báo "thành công" KHÔNG kèm "(mô phỏng)". Restart
    # không chữa được pool cạn: tải còn thì pool lại cạn sau vài giây.
    #
    # Báo cáo sai sự thật tệ hơn thừa nhận mô phỏng — người trực đọc "đã sửa"
    # rồi đi ngủ, trong khi sự cố vẫn đang diễn ra.
    if not _co_dang_bat_co_loi(container):
        logger.info(
            "%s không đang bật SIMULATE_MISSING_MIGRATION — hành động %s KHÔNG phải "
            "cách sửa đúng cho sự cố này, giữ mô phỏng",
            container, action,
        )
        return None

    # Tắt cờ mô phỏng deploy hỏng rồi dựng lại container. Đây chính là nội dung
    # của "rollback v1.4.3 → v1.4.2" trên stack demo.
    #
    # Truyền qua `env` chứ không nhét vào dòng lệnh: đặt biến ở shell trước
    # `docker compose` chỉ tới compose chứ KHÔNG tới process bên trong container,
    # nên biến phải đi qua môi trường của chính lệnh này để compose đọc và ghi
    # vào service. Đã đo ngày 11/08 và ghi trong docker-compose.demo.yml.
    moi_truong = dict(os.environ)
    moi_truong["SIMULATE_MISSING_MIGRATION"] = "0"
    moi_truong.setdefault("DEMO_POSTGRES_PORT", "55432")

    lenh = [
        "docker", "compose",
        "-f", str(_COMPOSE),
        "up", "-d", "--force-recreate",
        "service-thanh-toan",
    ]
    logger.info("Thi hành THẬT: %s", " ".join(lenh))

    try:
        ket_qua = subprocess.run(  # noqa: S603
            lenh,
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_GIAY,
            env=moi_truong,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False, f"Lệnh docker quá {_TIMEOUT_GIAY:.0f}s không xong — đã huỷ."
    except FileNotFoundError:
        return False, "Không gọi được `docker` trên máy này."
    except Exception as loi:  # pragma: no cover - đường phòng thân
        return False, f"Lỗi khi chạy docker: {type(loi).__name__}."

    if ket_qua.returncode != 0:
        loi = (ket_qua.stderr or ket_qua.stdout or "").strip().splitlines()
        return False, f"docker compose trả mã {ket_qua.returncode}: {loi[-1] if loi else 'không rõ'}"

    return True, (
        f"Đã khởi động lại {container} với SIMULATE_MISSING_MIGRATION=0 "
        "— tương đương rollback về v1.4.2. Chờ ~30 giây rồi kiểm tỷ lệ lỗi 5xx "
        "trên Prometheus để xác nhận đã hồi phục."
    )
