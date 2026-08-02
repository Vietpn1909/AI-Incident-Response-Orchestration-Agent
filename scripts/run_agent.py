"""Chạy Agent: poll Prometheus, tự mở Jira issue khi phát hiện sự cố.

    # Dùng FakeJiraClient — không cần token Jira, in ra console
    python scripts/run_agent.py --fake

    # Dùng Jira thật, đọc cấu hình từ .env
    python scripts/run_agent.py

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
from src.config import configure_logging, get_settings  # noqa: E402
from src.services.jira import FakeJiraClient, JiraClient, RealJiraClient  # noqa: E402
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Agent phát hiện sự cố")
    parser.add_argument("--fake", action="store_true", help="dùng FakeJiraClient, không gọi Jira thật")
    parser.add_argument("--prometheus", default=DEFAULT_PROMETHEUS)
    parser.add_argument("--interval", type=float, default=DEFAULT_INTERVAL, help="giây giữa hai vòng quét")
    parser.add_argument("--once", action="store_true", help="chạy đúng một vòng rồi thoát")
    args = parser.parse_args()

    configure_logging()
    jira = build_jira(args.fake)
    prometheus_client = PrometheusClient(args.prometheus)

    logger.info("Bắt đầu quét %s mỗi %.0fs. Ctrl+C để dừng.", args.prometheus, args.interval)
    cycles = 0
    try:
        while True:
            cycles += 1
            result = run_cycle(prometheus_client, jira)

            if result.error:
                pass  # đã log ở run_cycle
            elif result.quiet:
                logger.info("Vòng %d: bình thường", cycles)
            else:
                if result.opened:
                    logger.info("Vòng %d: MỞ war room %s", cycles, ", ".join(result.opened))
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
