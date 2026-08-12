"""Mail cảnh báo gửi ngay lúc PHÁT HIỆN sự cố, kèm link vào phòng họp.

CHỦ SỞ HỮU: Việt

## Đây là trigger gửi mail ĐẦU TIÊN của Agent

Trước file này, không sự kiện nào làm Agent tự gửi mail. `GmailClient` và
`build_email_body()` đã có sẵn, nhưng chỗ duy nhất gọi `send()` trong cả repo là
[`scripts/send_postmortem_demo.py`](../../scripts/send_postmortem_demo.py) — một
script chạy tay. Nói cách khác mail postmortem cũng **chưa** tự động.

Nên đừng nhầm hai thứ này với nhau, chúng ngược nhau về mọi mặt:

|              | `postmortem_report` | file này |
|--------------|---------------------|----------|
| Lúc gửi      | sau khi sự cố xong  | ngay lúc phát hiện |
| Người nhận   | quản lý, đọc hôm sau| người trực, phải vào sửa ngay |
| Ngôn ngữ     | kinh doanh, tránh thuật ngữ | số liệu thô để biết nặng cỡ nào |
| Việc cần làm | đọc và lưu          | **bấm vào link, vào họp** |

## Vì sao mail chứ không phải Jira comment

Mail là kênh **đẩy**. Người trực lúc 2 giờ sáng không ngồi mở Jira chờ; họ cần
thứ tự tìm tới mình. Jira comment là kênh **kéo** — tốt để lưu vết, vô dụng để
gọi người.

## Không retry

Cùng lý do đã ghi trong docstring `GmailClient`: đây là việc phụ bám bên cạnh
việc mở war room. SMTP hỏng thì log warning rồi đi tiếp — nhưng **không** đánh
dấu đã gửi, để vòng quét sau thử lại. Xem `WarRoomRegistry.can_bao_mail()`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from src.config import get_settings
from src.models.incident import IncidentSignal
from src.services.email_client import EmailClient, GmailClient
from src.services.status_updater import _ts_full

logger = logging.getLogger(__name__)

#: Màu theo mức, dùng cho dải màu đầu mail. Người trực nhận nhiều mail một lúc
#: thì màu là thứ họ phân loại được trước cả khi đọc chữ.
_MAU_THEO_MUC = {
    "P1": "#dc2626",
    "P2": "#ea580c",
    "P3": "#ca8a04",
    "P4": "#65a30d",
}


def danh_sach_nguoi_nhan() -> list[str]:
    """Người nhận cảnh báo, đọc từ `.env`.

    Rơi về `POSTMORTEM_RECIPIENTS` khi `INCIDENT_ALERT_RECIPIENTS` trống: thà
    gửi cho nhóm rộng hơn còn hơn im lặng, vì một Agent im lặng trông y hệt một
    hệ thống không có sự cố nào.
    """
    settings = get_settings()
    raw = settings.incident_alert_recipients or settings.postmortem_recipients
    return [email.strip() for email in raw.split(",") if email.strip()]


def build_alert_email(
    signal: IncidentSignal,
    jira_key: str,
    meeting_url: str = "",
) -> tuple[str, str]:
    """Dựng `(subject, body_html)` cho mail cảnh báo.

    Hàm thuần, không gửi gì — để test kiểm nội dung mà không cần SMTP, và để
    xem trước bằng cách in ra file HTML.

    Args:
        meeting_url: Trống thì mail vẫn gửi, chỉ không có nút vào họp. Xảy ra
            khi chưa cấu hình `DAILY_API_KEY` hoặc Daily đang hỏng — mất chỗ
            họp không phải lý do để nuốt luôn cảnh báo.
    """
    muc = signal.severity.value
    mau = _MAU_THEO_MUC.get(muc, "#dc2626")
    subject = f"🔴 [{muc}] {signal.affected_service} — {jira_key}"

    # Nút vào họp đặt TRƯỚC bảng số liệu: việc cần làm ngay là vào phòng, còn
    # số liệu là thứ đọc sau khi đã vào. Người trực mở mail trên điện thoại chỉ
    # thấy phần đầu.
    nut_hop = ""
    if meeting_url:
        nut_hop = f"""
        <div style="margin:0 0 20px">
            <a href="{meeting_url}"
               style="display:inline-block;background:{mau};color:#fff;text-decoration:none;
                      font-weight:700;font-size:16px;padding:14px 28px;border-radius:8px">
                🎥 Vào phòng họp xử lý sự cố
            </a>
            <div style="color:#64748b;font-size:12px;margin-top:8px">
                Bấm vào là vào thẳng, không cần cài gì. Phòng tự đóng sau 4 giờ.
            </div>
        </div>"""
    else:
        nut_hop = """
        <div style="background:#fef3c7;border:1px solid #fcd34d;border-radius:8px;
                    padding:12px 16px;margin:0 0 20px;color:#92400e;font-size:14px">
            ⚠️ Chưa mở được phòng họp cho sự cố này — vào war room trên Jira để phối hợp.
        </div>"""

    def hang(nhan: str, gia_tri: str) -> str:
        return (
            f'<tr><td style="padding:6px 12px 6px 0;color:#64748b;font-size:14px">{nhan}</td>'
            f'<td style="padding:6px 0;color:#0f172a;font-size:14px;font-weight:600">{gia_tri}</td></tr>'
        )

    body_html = f"""
    <div style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:600px;margin:0 auto">
        <div style="background:{mau};color:#fff;padding:16px 20px;border-radius:8px 8px 0 0">
            <div style="font-size:13px;opacity:.9">AGENT ỨNG PHÓ SỰ CỐ · PHÁT HIỆN</div>
            <div style="font-size:22px;font-weight:700;margin-top:4px">
                [{muc}] {signal.affected_service}
            </div>
        </div>
        <div style="border:1px solid #e2e8f0;border-top:none;border-radius:0 0 8px 8px;padding:20px">
            {nut_hop}
            <table style="border-collapse:collapse;width:100%">
                {hang("War room", jira_key)}
                {hang("Metric", signal.metric_name)}
                {hang("Giá trị đo", f"{signal.metric_value:.3f} (ngưỡng {signal.threshold:.3f})")}
                {hang("Vượt ngưỡng liên tục", f"{signal.breached_for_seconds:.0f}s")}
                {hang("Phát hiện lúc", _ts_full(signal.detected_at))}
            </table>
            <div style="color:#94a3b8;font-size:12px;margin-top:20px;
                        border-top:1px solid #e2e8f0;padding-top:12px">
                Mail này do Agent tự gửi khi phát hiện sự cố. Agent KHÔNG tự thực thi
                khắc phục — mọi hành động đều chờ người duyệt trên Jira.
            </div>
        </div>
    </div>"""

    return subject, body_html


@dataclass
class IncidentAlerter:
    """Gửi mail cảnh báo — gom client và danh sách người nhận vào một chỗ.

    Gom lại để `build_incident_graph()` chỉ nhận **một** dependency thay vì hai
    tham số luôn phải đi cùng nhau. Client nào cũng được miễn thoả Protocol
    `EmailClient` — `FakeEmailClient` trong test, `GmailClient` khi chạy thật.
    """

    mailer: EmailClient
    recipients: list[str]

    def bao_su_co(self, jira_key: str, signal: IncidentSignal, meeting_url: str = "") -> bool:
        """Gửi cảnh báo cho một war room. Trả về có gửi được không.

        Nuốt mọi lỗi: `GmailClient.send()` đã tự bắt và trả `EmailResult` thay
        vì raise, nhưng `mailer` là tham số nên không được tin bên kia cũng làm
        vậy. Một exception lọt ra đây là giết cả vòng quét — cùng lập luận với
        `_tao_phong_hop()`.

        Trả `False` khi hỏng, và người gọi **không** đánh dấu đã gửi, để vòng
        sau thử lại.
        """
        if not self.recipients:
            logger.warning(
                "%s: chưa cấu hình INCIDENT_ALERT_RECIPIENTS lẫn POSTMORTEM_RECIPIENTS "
                "— không có ai để báo sự cố",
                jira_key,
            )
            return False

        subject, body_html = build_alert_email(signal, jira_key, meeting_url)
        try:
            result = self.mailer.send(to=list(self.recipients), subject=subject, body_html=body_html)
        except Exception as error:
            logger.warning("%s: không gửi được mail cảnh báo (%s)", jira_key, error)
            return False

        if not result.success:
            logger.warning("%s: mail cảnh báo thất bại — %s", jira_key, result.error)
            return False

        logger.info(
            "%s: đã báo sự cố tới %s%s",
            jira_key,
            ", ".join(self.recipients),
            " (kèm link phòng họp)" if meeting_url else " (chưa có phòng họp)",
        )
        return True


def build_alerter() -> IncidentAlerter | None:
    """Dựng alerter từ `.env`, hoặc `None` khi chưa cấu hình đủ.

    Trả `None` thay vì raise, cùng lý do với `build_room_client()`: thiếu SMTP
    chỉ có nghĩa là không ai được báo — Agent vẫn phát hiện, vẫn mở war room,
    vẫn chẩn đoán. Đây là lý do `run_agent.py` KHÔNG `sys.exit` cho mấy biến này
    như nó làm với cấu hình Jira.
    """
    settings = get_settings()
    if not (settings.smtp_email and settings.smtp_app_password):
        logger.warning(
            "Chưa có SMTP_EMAIL/SMTP_APP_PASSWORD — sẽ không có mail báo sự cố. "
            "Tạo App Password: https://myaccount.google.com/apppasswords"
        )
        return None

    recipients = danh_sach_nguoi_nhan()
    if not recipients:
        logger.warning(
            "Chưa có INCIDENT_ALERT_RECIPIENTS lẫn POSTMORTEM_RECIPIENTS — "
            "không có ai để báo sự cố."
        )
        return None

    return IncidentAlerter(
        mailer=GmailClient(settings.smtp_email, settings.smtp_app_password),
        recipients=recipients,
    )
