"""Test `src/services/email_client.py`.

Chạy KHÔNG cần SMTP thật — FakeEmailClient và mock smtplib.
"""

from __future__ import annotations

import smtplib
from unittest.mock import MagicMock, patch

import pytest

from src.services.email_client import (
    EmailClient,
    EmailResult,
    FakeEmailClient,
    GmailClient,
)


# ────────── FakeEmailClient ──────────


class TestFakeEmailClient:
    def test_la_email_client(self):
        """FakeEmailClient phải thoả mãn Protocol EmailClient."""
        assert isinstance(FakeEmailClient(), EmailClient)

    def test_gui_thanh_cong_va_ghi_lai(self):
        client = FakeEmailClient()
        result = client.send(
            to=["a@x.com", "b@x.com"],
            subject="Test",
            body_html="<p>Hello</p>",
        )
        assert result.success
        assert result.recipients == ["a@x.com", "b@x.com"]
        assert result.subject == "Test"
        assert len(client.sent) == 1

    def test_gui_nhieu_lan_deu_ghi_het(self):
        client = FakeEmailClient()
        client.send(to=["a@x.com"], subject="1", body_html="<p>1</p>")
        client.send(to=["b@x.com"], subject="2", body_html="<p>2</p>")
        assert len(client.sent) == 2
        assert client.sent[0].subject == "1"
        assert client.sent[1].subject == "2"


# ────────── EmailResult ──────────


class TestEmailResult:
    def test_summary_thanh_cong(self):
        r = EmailResult(success=True, recipients=["a@x.com"], subject="Postmortem INC-1")
        assert "✅" in r.summary()
        assert "Postmortem INC-1" in r.summary()

    def test_summary_that_bai(self):
        r = EmailResult(
            success=False, recipients=["a@x.com"], subject="Test", error="SMTP lỗi"
        )
        assert "❌" in r.summary()
        assert "SMTP lỗi" in r.summary()


# ────────── GmailClient ──────────


class TestGmailClient:
    def test_la_email_client(self):
        """GmailClient phải thoả mãn Protocol EmailClient."""
        client = GmailClient("test@gmail.com", "fake-password")
        assert isinstance(client, EmailClient)

    def test_thieu_cau_hinh_thi_raise(self):
        with pytest.raises(ValueError, match="SMTP_EMAIL"):
            GmailClient("", "password")
        with pytest.raises(ValueError, match="SMTP_APP_PASSWORD"):
            GmailClient("test@gmail.com", "")

    def test_danh_sach_nguoi_nhan_rong(self):
        client = GmailClient("test@gmail.com", "fake-password")
        result = client.send(to=[], subject="Test", body_html="<p>Hi</p>")
        assert not result.success
        assert "rỗng" in result.error

    @patch("src.services.email_client.smtplib.SMTP")
    def test_gui_thanh_cong_qua_smtp(self, mock_smtp_cls):
        """Mock SMTP để kiểm luồng gửi không cần mạng."""
        mock_server = MagicMock()
        mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_server)
        mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

        client = GmailClient("agent@gmail.com", "xxxx-xxxx-xxxx-xxxx")
        result = client.send(
            to=["leader@gmail.com"],
            subject="Postmortem INC-42",
            body_html="<h1>Postmortem</h1><p>Root cause: OOM</p>",
        )

        assert result.success
        assert result.recipients == ["leader@gmail.com"]
        # Kiểm tra SMTP flow: ehlo → starttls → ehlo → login → sendmail
        mock_server.ehlo.assert_called()
        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once_with("agent@gmail.com", "xxxx-xxxx-xxxx-xxxx")
        mock_server.sendmail.assert_called_once()

    @patch("src.services.email_client.smtplib.SMTP")
    def test_smtp_auth_error_khong_crash(self, mock_smtp_cls):
        """Sai App Password → trả result.success=False, KHÔNG raise."""
        mock_server = MagicMock()
        mock_server.login.side_effect = smtplib.SMTPAuthenticationError(
            535, b"Authentication failed"
        )
        mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_server)
        mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

        client = GmailClient("agent@gmail.com", "wrong-password")
        result = client.send(
            to=["leader@gmail.com"],
            subject="Test",
            body_html="<p>Hi</p>",
        )

        assert not result.success
        assert "App Password" in result.error

    @patch("src.services.email_client.smtplib.SMTP")
    def test_smtp_connection_error_khong_crash(self, mock_smtp_cls):
        """Mất kết nối → trả result.success=False, KHÔNG raise."""
        mock_smtp_cls.side_effect = ConnectionError("Connection refused")

        client = GmailClient("agent@gmail.com", "xxxx")
        result = client.send(
            to=["leader@gmail.com"],
            subject="Test",
            body_html="<p>Hi</p>",
        )

        assert not result.success
        assert "ConnectionError" in result.error

    @patch("src.services.email_client.smtplib.SMTP")
    def test_gui_nhieu_nguoi_nhan(self, mock_smtp_cls):
        """Gửi tới nhiều người — sendmail nhận list."""
        mock_server = MagicMock()
        mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_server)
        mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

        client = GmailClient("agent@gmail.com", "xxxx")
        recipients = ["a@gmail.com", "b@gmail.com", "c@gmail.com"]
        result = client.send(
            to=recipients,
            subject="Postmortem",
            body_html="<p>Done</p>",
        )

        assert result.success
        assert result.recipients == recipients
        # sendmail phải nhận đủ 3 người nhận
        call_args = mock_server.sendmail.call_args
        assert call_args[0][1] == recipients

    def test_build_message_co_html_va_plaintext(self):
        """Message phải có cả HTML và plaintext part."""
        client = GmailClient("agent@gmail.com", "xxxx")
        msg = client._build_message(
            to=["leader@gmail.com"],
            subject="Postmortem INC-1",
            body_html="<h1>Postmortem</h1><p>Root cause: OOM</p>",
            body_text="",
        )

        assert msg["To"] == "leader@gmail.com"
        assert msg["Subject"] == "Postmortem INC-1"
        assert msg["From"] == "agent@gmail.com"

        # MIMEMultipart("alternative") phải có 2 phần: text/plain + text/html
        payloads = msg.get_payload()
        assert len(payloads) == 2
        content_types = [p.get_content_type() for p in payloads]
        assert "text/plain" in content_types
        assert "text/html" in content_types

    def test_build_message_giu_nguyen_plaintext_truyen_san(self):
        """Nếu truyền body_text thì giữ nguyên, không strip HTML."""
        client = GmailClient("agent@gmail.com", "xxxx")
        msg = client._build_message(
            to=["a@x.com"],
            subject="Test",
            body_html="<p>HTML</p>",
            body_text="Custom plaintext",
        )
        payloads = msg.get_payload()
        plain = next(p for p in payloads if p.get_content_type() == "text/plain")
        assert "Custom plaintext" in plain.get_payload(decode=True).decode()
