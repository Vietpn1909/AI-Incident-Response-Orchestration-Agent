"""Chạy Agent: poll Prometheus, tự mở Jira issue khi phát hiện sự cố.

    # Dùng FakeJiraClient — không cần token Jira, in ra console
    python scripts/run_agent.py --fake

    # Dùng Jira thật, đọc cấu hình từ .env
    python scripts/run_agent.py

    # Đang chỉnh sửa và chạy đi chạy lại — đừng làm phiền hộp thư người trực
    python scripts/run_agent.py --fake --no-mail

Phòng họp và mail cảnh báo KHÔNG phụ thuộc `--fake`: có `DAILY_API_KEY` là phòng
tạo thật, có `SMTP_EMAIL` là mail gửi thật. Thiếu biến nào thì phần đó tự tắt
kèm một dòng warning, Agent vẫn chạy bình thường.

Dừng bằng Ctrl+C.

Cần Prometheus đang chạy:
    docker compose -f docker-compose.demo.yml up -d
    python demo/seed.py
    python demo/loadtest.py        # terminal khác, để tạo sự cố
"""

from __future__ import annotations

import argparse
import logging
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from src.agents.detection_loop import run_cycle  # noqa: E402
from src.agents.war_room_registry import WarRoomRegistry  # noqa: E402
from src.config import configure_logging, force_utf8_console, get_settings  # noqa: E402
from src.services.incident_alert import IncidentAlerter, build_alerter  # noqa: E402
from src.services.jira import FakeJiraClient, JiraClient, RealJiraClient  # noqa: E402
from src.services.meeting_room import DailyRoomClient, build_room_client  # noqa: E402
from src.services.prometheus import PrometheusClient  # noqa: E402

logger = logging.getLogger("agent")

DEFAULT_PROMETHEUS = "http://localhost:9090"
DEFAULT_INTERVAL = 10.0


def build_jira(use_fake: bool) -> JiraClient:
    if use_fake:
        logger.info("Dùng FakeJiraClient — không gọi Jira thật")
        return FakeJiraClient()

    settings = get_settings()
    missing = [
        name
        for name, value in (
            ("JIRA_BASE_URL", settings.jira_base_url),
            ("JIRA_EMAIL", settings.jira_email),
            ("JIRA_API_TOKEN", settings.jira_api_token),
            ("JIRA_PROJECT_KEY", settings.jira_project_key),
        )
        if not value
    ]
    if missing:
        sys.exit(f"❌ Thiếu {', '.join(missing)} trong .env. Chạy với --fake nếu chưa có token Jira.")

    logger.info("Dùng RealJiraClient — %s project %s", settings.jira_base_url, settings.jira_project_key)
    return RealJiraClient(
        base_url=settings.jira_base_url,
        email=settings.jira_email,
        api_token=settings.jira_api_token,
        project_key=settings.jira_project_key,
    )


def build_room() -> DailyRoomClient | None:
    """Dựng client mở phòng họp, hoặc `None` khi chưa có `DAILY_API_KEY`.

    Thiếu key thì **không** `sys.exit` như `build_jira()` làm: phòng họp là tính
    năng phụ bám bên cạnh war room. Thiếu Jira thì Agent không có chỗ nào để ghi
    sự cố nên chạy tiếp là vô nghĩa; thiếu Daily thì nó chỉ mất cái link họp.

    ⚠️ KHÔNG xét `--fake`. Cờ đó chỉ thay `FakeJiraClient`, và đây là đường chạy
    end-to-end **duy nhất** khi đội chưa được cấp Jira API — tắt luôn phòng họp
    theo `--fake` thì tính năng này không nghiệm thu được cho tới tận Mức C.
    """
    return build_room_client()


def build_alert(no_mail: bool) -> IncidentAlerter | None:
    """Dựng client gửi mail cảnh báo, hoặc `None` khi tắt / chưa cấu hình SMTP.

    ⚠️ KHÔNG xét `--fake`, cùng lý do với `build_room()`: cờ đó chỉ thay
    `FakeJiraClient`, và `--fake` là đường chạy end-to-end **duy nhất** khi đội
    chưa được cấp Jira API. Tắt mail theo `--fake` thì tính năng này không
    nghiệm thu được cho tới tận Mức C.

    Cờ tắt riêng là `--no-mail`, vì việc cần tắt là **gửi mail**, không phải
    "đang dùng Jira giả" — trộn hai thứ đó vào một cờ là cách để về sau không ai
    đoán được `--fake` thật ra tắt những gì.

    Không cần `--no-mail` mà vẫn im: chưa đặt `SMTP_EMAIL`/`SMTP_APP_PASSWORD`
    thì `build_alerter()` tự trả `None`. Và `WarRoomRegistry` chặn gửi lặp, nên
    một lần ép tải chỉ ra đúng một mail cho mỗi war room, không phải một mail
    mỗi 10 giây.
    """
    if no_mail:
        logger.info("--no-mail: KHÔNG gửi mail cảnh báo")
        return None
    return build_alerter()


def main() -> int:
    # PHẢI đứng trước parse_args(): argparse in `--help` và thông báo lỗi tham
    # số thẳng ra stdout ngay trong parse_args(), tức trước cả configure_logging().
    # Trên Windows (3/4 thành viên) chưa ép UTF-8 thì `--help` chết bằng
    # UnicodeEncodeError chứ không phải in ra chữ xấu.
    force_utf8_console()

    parser = argparse.ArgumentParser(description="Agent phát hiện sự cố")
    parser.add_argument("--fake", action="store_true", help="dùng FakeJiraClient, không gọi Jira thật")
    parser.add_argument("--prometheus", default=DEFAULT_PROMETHEUS)
    parser.add_argument("--interval", type=float, default=DEFAULT_INTERVAL, help="giây giữa hai vòng quét")
    parser.add_argument("--once", action="store_true", help="chạy đúng một vòng rồi thoát")
    parser.add_argument("--no-mail", action="store_true", help="không gửi mail cảnh báo")
    args = parser.parse_args()

    configure_logging()
    jira = build_jira(args.fake)
    room = build_room()
    alerter = build_alert(args.no_mail)
    prometheus_client = PrometheusClient(args.prometheus)

    # Dựng MỘT lần cho cả đời tiến trình, không phải mỗi vòng. Đây chính là chỗ
    # duy nhất giữ trí nhớ giữa các vòng quét: thiếu nó thì mỗi 10 giây Agent
    # lại mở một phòng họp mới và gửi lại một mail cho cùng một sự cố.
    registry = WarRoomRegistry()

    logger.info("Bắt đầu quét %s mỗi %.0fs. Ctrl+C để dừng.", args.prometheus, args.interval)
    cycles = 0
    try:
        while True:
            cycles += 1
            result = run_cycle(
                prometheus_client, jira, room=room, alerter=alerter, registry=registry
            )

            if result.error:
                pass  # đã log ở run_cycle
            elif result.quiet:
                logger.info("Vòng %d: bình thường", cycles)
            else:
                if result.opened:
                    logger.info("Vòng %d: MỞ war room %s", cycles, ", ".join(result.opened))
                # In lại URL ở đây dù `_tao_phong_hop()` đã log lúc tạo: dòng kia
                # nằm lẫn giữa log của LangGraph và Jira, còn dòng này đứng ngay
                # cạnh "MỞ war room" — chỗ người trực thật sự nhìn vào.
                for jira_key, url in result.meeting_rooms.items():
                    logger.info("%s: phòng họp %s", jira_key, url)
                if result.updated:
                    logger.info("Vòng %d: cập nhật %s (đã có incident mở)", cycles, ", ".join(result.updated))

            if args.once:
                break
            time.sleep(args.interval)
    except KeyboardInterrupt:
        logger.info("Dừng sau %d vòng.", cycles)
    finally:
        prometheus_client.close()
        close = getattr(jira, "close", None)
        if callable(close):
            close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
