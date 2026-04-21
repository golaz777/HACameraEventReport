import base64
import email
import pytest
from datetime import date
from unittest.mock import AsyncMock, patch
from src.notifier import Notifier
from src.config import Config, EmailConfig


@pytest.fixture
def config():
    return Config(
        cameras=[],
        email=EmailConfig(
            enabled=True,
            smtp_host="smtp.gmail.com",
            smtp_port=587,
            smtp_user="user@gmail.com",
            smtp_password="pass",
            recipient="dest@gmail.com",
            sender="ha@gmail.com",
        ),
        ha_persistent=True,
        event_cooldown_seconds=30,
    )


async def test_send_ha_notification_calls_ha_client(config):
    mock_ha = AsyncMock()
    notifier = Notifier(config, mock_ha)

    await notifier.send_ha_notification(
        night=date(2026, 4, 12),
        event_count=5,
        report_path="/media/onvif_events/2026-04-12/report.html",
    )

    mock_ha.send_notification.assert_called_once()
    title, message = mock_ha.send_notification.call_args[0]
    assert "2026-04-12" in title
    assert "5" in message


async def test_send_ha_notification_skipped_when_disabled(config):
    config.ha_persistent = False
    mock_ha = AsyncMock()
    notifier = Notifier(config, mock_ha)

    await notifier.send_ha_notification(
        night=date(2026, 4, 12),
        event_count=5,
        report_path="/media/onvif_events/2026-04-12/report.html",
    )

    mock_ha.send_notification.assert_not_called()


async def test_send_email_uses_smtp_config(config):
    notifier = Notifier(config, AsyncMock())

    with patch("src.notifier.aiosmtplib.send", new_callable=AsyncMock) as mock_send:
        await notifier.send_email(
            night=date(2026, 4, 12),
            event_count=5,
            html_content="<html><body>report</body></html>",
        )
        mock_send.assert_called_once()
        kwargs = mock_send.call_args[1]
        assert kwargs["hostname"] == "smtp.gmail.com"
        assert kwargs["port"] == 587
        assert kwargs["username"] == "user@gmail.com"
        assert kwargs["password"] == "pass"


async def test_send_email_skipped_when_disabled(config):
    config.email.enabled = False
    notifier = Notifier(config, AsyncMock())

    with patch("src.notifier.aiosmtplib.send", new_callable=AsyncMock) as mock_send:
        await notifier.send_email(
            night=date(2026, 4, 12),
            event_count=0,
            html_content="<html/>",
        )
        mock_send.assert_not_called()


async def test_send_email_attaches_images_as_cid_parts(config):
    """data: URIs in the HTML are replaced with cid: and attached as inline MIME images."""
    fake_bytes = b"\xff\xd8\xff" + b"\x00" * 20
    b64 = base64.b64encode(fake_bytes).decode()
    html_with_image = f'<html><img src="data:image/jpeg;base64,{b64}"></html>'

    sent_msg = None

    async def capture_send(msg, **kwargs):
        nonlocal sent_msg
        sent_msg = msg

    notifier = Notifier(config, AsyncMock())
    with patch("src.notifier.aiosmtplib.send", side_effect=capture_send):
        await notifier.send_email(
            night=date(2026, 4, 12),
            event_count=1,
            html_content=html_with_image,
        )

    assert sent_msg is not None
    parts = list(sent_msg.walk())

    # HTML body must use cid: not data:
    html_parts = [p for p in parts if p.get_content_type() == "text/html"
                  and p.get("Content-Disposition") is None]
    assert html_parts, "Expected an inline text/html part"
    body = html_parts[0].get_payload(decode=True).decode()
    assert "cid:" in body
    assert "data:image/jpeg" not in body

    # At least one inline image MIME part
    image_parts = [p for p in parts if p.get_content_type() == "image/jpeg"]
    assert image_parts, "Expected at least one image/jpeg MIME part"
    assert image_parts[0].get("Content-ID") is not None
    assert image_parts[0].get_payload(decode=True) == fake_bytes


async def test_lightbox_anchor_stripped_for_email(config):
    """Lightbox anchor wrapper is removed; bare <img cid:> remains so Gmail doesn't 410."""
    from src.notifier import _extract_inline_images
    fake_bytes = b"\xff\xd8\xff" + b"\x00" * 20
    b64 = base64.b64encode(fake_bytes).decode()
    html = (
        f'<a class="img-link" href="#" onclick="openLightbox(this);return false;">'
        f'<img src="data:image/jpeg;base64,{b64}" alt="snap"></a>'
    )

    modified, images = _extract_inline_images(html)

    assert len(images) == 1
    cid = images[0][0]
    assert f'src="cid:{cid}"' in modified
    assert '<a' not in modified          # anchor stripped entirely
    assert 'href=' not in modified
    assert 'onclick=' not in modified
    assert 'data:image' not in modified


async def test_send_email_multiple_recipients(config):
    """Semicolon-separated recipients are all included in To header and SMTP envelope."""
    config.email.recipient = "alice@example.com; bob@example.com ; carol@example.com"

    sent_msg = None
    sent_recipients = None

    async def capture_send(msg, **kwargs):
        nonlocal sent_msg, sent_recipients
        sent_msg = msg
        sent_recipients = kwargs.get("recipients")

    notifier = Notifier(config, AsyncMock())
    with patch("src.notifier.aiosmtplib.send", side_effect=capture_send):
        await notifier.send_email(
            night=date(2026, 4, 12),
            event_count=1,
            html_content="<html/>",
        )

    assert sent_recipients == ["alice@example.com", "bob@example.com", "carol@example.com"]
    assert sent_msg["To"] == "alice@example.com, bob@example.com, carol@example.com"


async def test_send_email_failure_does_not_raise(config):
    notifier = Notifier(config, AsyncMock())

    with patch(
        "src.notifier.aiosmtplib.send",
        new_callable=AsyncMock,
        side_effect=Exception("SMTP error"),
    ):
        # Must not raise — failure is logged only
        await notifier.send_email(
            night=date(2026, 4, 12),
            event_count=3,
            html_content="<html/>",
        )
