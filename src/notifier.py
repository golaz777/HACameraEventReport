from __future__ import annotations
import base64
import logging
import re
from datetime import date
from email.mime.base import MIMEBase
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email import encoders

import aiosmtplib

from src.config import Config

logger = logging.getLogger(__name__)

EMAIL_LARGE_REPORT_THRESHOLD = 50


def _extract_inline_images(html: str) -> tuple[str, list[tuple[str, bytes]]]:
    """Replace data: image URIs with cid: references.

    Returns (modified_html, [(cid, jpeg_bytes), ...]).
    Email clients block data: URIs but render cid: inline images correctly.
    The JS lightbox anchor wrapper is removed entirely — Gmail and most email
    clients do not support cid:/data: hrefs, so images are shown inline at
    full width instead.
    """
    images: list[tuple[str, bytes]] = []

    def replace(match: re.Match) -> str:
        b64_data = match.group(1)
        attrs = match.group(2)
        img_bytes = base64.b64decode(b64_data)
        cid = f"snapshot_{len(images)}"
        images.append((cid, img_bytes))
        return f'<img src="cid:{cid}" {attrs} style="max-width:100%;border-radius:4px;display:block;">'

    # Match the entire lightbox anchor + img block and collapse it to just
    # the <img> with a cid: src so no broken links appear in email clients.
    modified = re.sub(
        r'<a\s[^>]*class="img-link"[^>]*>\s*'
        r'<img\s+src="data:image/jpeg;base64,([^"]+)"\s+([^>]*)>\s*'
        r'</a>',
        replace,
        html,
        flags=re.DOTALL,
    )

    # Fallback: bare <img src="data:..."> not wrapped in a lightbox anchor
    def replace_bare(match: re.Match) -> str:
        b64_data = match.group(1)
        img_bytes = base64.b64decode(b64_data)
        cid = f"snapshot_{len(images)}"
        images.append((cid, img_bytes))
        return f'src="cid:{cid}"'

    modified = re.sub(
        r'src="data:image/jpeg;base64,([^"]+)"',
        replace_bare,
        modified,
    )

    return modified, images


class Notifier:
    def __init__(self, config: Config, ha_client):
        self._config = config
        self._ha = ha_client

    async def send_ha_notification(
        self, night: date, event_count: int, report_path: str
    ) -> None:
        if not self._config.ha_persistent:
            return
        title = f"[HA] Motion Report – {night.isoformat()} ({event_count} events)"
        message = (
            f"Motion report ready: {event_count} event(s) detected. "
            f"Report saved to {report_path}"
        )
        await self._ha.send_notification(title, message)
        logger.info("HA persistent notification sent")

    async def _send_summary_email(
        self, night: date, event_count: int, subject: str
    ) -> None:
        """Send a lightweight summary email when event count exceeds the threshold."""
        body = (
            f"<p>Motion report for <strong>{night.isoformat()}</strong>: "
            f"<strong>{event_count} events</strong> detected.</p>"
            f"<p>Event count exceeds {EMAIL_LARGE_REPORT_THRESHOLD}. "
            f"Full report with snapshots is saved locally and available via the web UI.</p>"
        )
        msg = MIMEMultipart("mixed")
        recipients = [
            r.strip()
            for r in self._config.email.recipient.split(";")
            if r.strip()
        ]
        msg["Subject"] = subject
        msg["From"] = self._config.email.sender
        msg["To"] = ", ".join(recipients)
        msg.attach(MIMEText(body, "html", "utf-8"))

        try:
            await aiosmtplib.send(
                msg,
                hostname=self._config.email.smtp_host,
                port=self._config.email.smtp_port,
                username=self._config.email.smtp_user,
                password=self._config.email.smtp_password,
                start_tls=True,
                recipients=recipients,
            )
            logger.info(
                "Summary email sent (large report: %d events) to %s",
                event_count,
                ", ".join(recipients),
            )
        except Exception as exc:
            logger.error("Failed to send summary email: %s", exc)

    async def send_email(
        self, night: date, event_count: int, html_content: str
    ) -> None:
        if not self._config.email.enabled:
            return

        subject = (
            f"[HA] Motion Report – {night.isoformat()} ({event_count} events)"
        )

        if event_count > EMAIL_LARGE_REPORT_THRESHOLD:
            await self._send_summary_email(night, event_count, subject)
            return

        # Replace data: URIs with cid: so email clients render the images inline.
        email_html, cid_images = _extract_inline_images(html_content)

        # multipart/related bundles the HTML body with its inline images.
        related = MIMEMultipart("related")
        related.attach(MIMEText(email_html, "html", "utf-8"))
        for cid, img_bytes in cid_images:
            img_part = MIMEImage(img_bytes, "jpeg")
            img_part.add_header("Content-ID", f"<{cid}>")
            img_part.add_header("Content-Disposition", "inline")
            related.attach(img_part)

        # Outer multipart/mixed allows adding the standalone HTML as an attachment.
        msg = MIMEMultipart("mixed")
        recipients = [
            r.strip()
            for r in self._config.email.recipient.split(";")
            if r.strip()
        ]

        msg["Subject"] = subject
        msg["From"] = self._config.email.sender
        msg["To"] = ", ".join(recipients)
        msg.attach(related)

        # Attach the original HTML (with data: URIs) so it can be saved and viewed.
        attachment = MIMEBase("text", "html")
        attachment.set_payload(html_content.encode("utf-8"))
        encoders.encode_base64(attachment)
        attachment.add_header(
            "Content-Disposition",
            "attachment",
            filename=f"report-{night.isoformat()}.html",
        )
        msg.attach(attachment)

        try:
            await aiosmtplib.send(
                msg,
                hostname=self._config.email.smtp_host,
                port=self._config.email.smtp_port,
                username=self._config.email.smtp_user,
                password=self._config.email.smtp_password,
                start_tls=True,
                recipients=recipients,
            )
            logger.info("Report email sent to %s", ", ".join(recipients))
        except Exception as exc:
            logger.error("Failed to send report email: %s", exc)
