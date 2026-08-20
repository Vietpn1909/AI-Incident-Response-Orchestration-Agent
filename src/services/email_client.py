"""Service gửi email qua Gmail SMTP.

CHỦ SỞ HỮU: Việt

Dùng `smtplib` và `email` có sẵn trong Python — KHÔNG cần thêm dependency.

## Kiến trúc

Theo đúng pattern Protocol mà Jira client đang dùng:

    EmailClient (Protocol)
    ├── FakeEmailClient   — log ra console, dùng trong test/CI/demo
    └── GmailClient       — gửi thật qua smtp.gmail.com:587

## Bảo mật

- Dùng App Password (16 ký tự), KHÔNG dùng mật khẩu tài khoản.
- App Password yêu cầu đã bật 2FA trên tài khoản Google.
- TLS/STARTTLS bắt buộc — không bao giờ gửi plaintext.

## Tạo App Password

1. Vào https://myaccount.google.com/apppasswords
2. Chọn "Mail" → "Other" → đặt tên "AI20K Agent"
3. Copy 16 ký tự → điền vào SMTP_APP_PASSWORD trong .env
"""

from __future__ import annotations

import logging
import smtplib
from dataclasses import dataclass, field
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Gmail SMTP constants
# ---------------------------------------------------------------------------
GMAIL_SMTP_HOST = "smtp.gmail.com"
GMAIL_SMTP_PORT = 587  # STARTTLS


@dataclass(frozen=True)
class Attachment:
    """File đính kèm trong email."""

    filename: str
    content: bytes
    mime_type: str = "text/html"


@dataclass(frozen=True)
class EmailResult:
    """Kết quả gửi mail — dùng cho log và test, không phải response API."""

    success: bool
    recipients: list[str]
    subject: str
    error: str = ""

    def summary(self) -> str:
        if self.success:
            return f"✅ Đã gửi '{self.subject}' tới {', '.join(self.recipients)}"
        return f"❌ Gửi '{self.subject}' thất bại: {self.error}"


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class EmailClient(Protocol):
    """Interface gửi email — Agent chỉ dùng interface này."""

    def send(
        self,
        *,
        to: list[str],
        subject: str,
        body_html: str,
        body_text: str = "",
        attachments: list[Attachment] | None = None,
    ) -> EmailResult:
        """Gửi email tới danh sách người nhận.

        Args:
            to: Danh sách email người nhận.
            subject: Tiêu đề email.
            body_html: Nội dung HTML (ưu tiên hiển thị).
            body_text: Nội dung plaintext fallback. Nếu rỗng, tự strip từ HTML.
            attachments: File đính kèm (vd. báo cáo Postmortem chi tiết).
        """
        ...


# ---------------------------------------------------------------------------
# FakeEmailClient — test / CI / demo không cần SMTP
# ---------------------------------------------------------------------------


@dataclass
class FakeEmailClient:
    """Ghi log thay vì gửi thật — dùng trong test, CI, và demo local.

    `sent` lưu lại mọi lần gọi, test kiểm chứng Agent gửi đúng nội dung.
    """

    sent: list[EmailResult] = field(default_factory=list)

    def send(
        self,
        *,
        to: list[str],
        subject: str,
        body_html: str,
        body_text: str = "",
        attachments: list[Attachment] | None = None,
    ) -> EmailResult:
        result = EmailResult(success=True, recipients=list(to), subject=subject)
        self.sent.append(result)
        self._last_attachments = attachments or []
        logger.info("[FakeEmail] %s", result.summary())
        return result


# ---------------------------------------------------------------------------
# GmailClient — gửi thật qua smtp.gmail.com
# ---------------------------------------------------------------------------


class GmailClient:
    """Gửi email qua Gmail SMTP với App Password.

    ## Không retry

    Gửi mail là bước cuối sau khi sự cố đã resolved — nếu hỏng thì log warning
    và Agent vẫn hoạt động bình thường. Retry ở đây sẽ block luồng Agent vô ích.

    ## Vì sao không dùng aiosmtplib

    Agent flow hiện tại chạy sync (LangGraph nodes đều sync). Thêm async cho
    riêng email sẽ tạo ra dependency mới + phải chạy event loop riêng. Không
    đáng cho một lời gọi SMTP mất < 2 giây.
    """

    def __init__(self, sender_email: str, app_password: str) -> None:
        if not sender_email or not app_password:
            raise ValueError(
                "Thiếu SMTP_EMAIL hoặc SMTP_APP_PASSWORD trong cấu hình. "
                "Xem hướng dẫn: https://myaccount.google.com/apppasswords"
            )
        self._sender = sender_email
        self._password = app_password

    def send(
        self,
        *,
        to: list[str],
        subject: str,
        body_html: str,
        body_text: str = "",
        attachments: list[Attachment] | None = None,
    ) -> EmailResult:
        """Gửi email qua Gmail SMTP/TLS."""
        if not to:
            return EmailResult(
                success=False, recipients=[], subject=subject, error="Danh sách người nhận rỗng"
            )

        msg = self._build_message(to, subject, body_html, body_text, attachments)

        try:
            with smtplib.SMTP(GMAIL_SMTP_HOST, GMAIL_SMTP_PORT, timeout=15) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(self._sender, self._password)
                server.sendmail(self._sender, to, msg.as_string())

            result = EmailResult(success=True, recipients=list(to), subject=subject)
            logger.info("[Gmail] %s", result.summary())
            return result

        except smtplib.SMTPAuthenticationError as exc:
            error = (
                f"Gmail từ chối xác thực — kiểm SMTP_EMAIL và SMTP_APP_PASSWORD. "
                f"Đảm bảo dùng App Password, không phải mật khẩu tài khoản. ({exc})"
            )
            logger.warning("[Gmail] %s", error)
            return EmailResult(success=False, recipients=list(to), subject=subject, error=error)

        except smtplib.SMTPRecipientsRefused as exc:
            error = f"Gmail từ chối người nhận: {exc}"
            logger.warning("[Gmail] %s", error)
            return EmailResult(success=False, recipients=list(to), subject=subject, error=error)

        except Exception as exc:
            error = f"Lỗi gửi email: {type(exc).__name__}: {exc}"
            logger.warning("[Gmail] %s", error)
            return EmailResult(success=False, recipients=list(to), subject=subject, error=error)

    def _build_message(
        self,
        to: list[str],
        subject: str,
        body_html: str,
        body_text: str,
        attachments: list[Attachment] | None = None,
    ) -> MIMEMultipart:
        # Có attachment → mixed (body + files). Không → alternative (text + html).
        if attachments:
            msg = MIMEMultipart("mixed")
            msg["From"] = self._sender
            msg["To"] = ", ".join(to)
            msg["Subject"] = subject

            # Body là sub-part alternative bên trong mixed
            body_part = MIMEMultipart("alternative")
            self._attach_body(body_part, body_html, body_text)
            msg.attach(body_part)

            # Đính kèm từng file
            for att in attachments:
                part = MIMEBase(*att.mime_type.split("/", 1))
                part.set_payload(att.content)
                from email import encoders
                encoders.encode_base64(part)
                part.add_header(
                    "Content-Disposition", "attachment", filename=att.filename
                )
                msg.attach(part)
        else:
            msg = MIMEMultipart("alternative")
            msg["From"] = self._sender
            msg["To"] = ", ".join(to)
            msg["Subject"] = subject
            self._attach_body(msg, body_html, body_text)

        return msg

    @staticmethod
    def _attach_body(part: MIMEMultipart, body_html: str, body_text: str) -> None:
        """Gắn nội dung text/plain và text/html vào một MIMEMultipart."""
        if not body_text:
            import re
            body_text = re.sub(r"<[^>]+>", "", body_html)
            body_text = re.sub(r"\s+", " ", body_text).strip()
        part.attach(MIMEText(body_text, "plain", "utf-8"))
        part.attach(MIMEText(body_html, "html", "utf-8"))
