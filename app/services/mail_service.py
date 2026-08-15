"""Email sending utilities (SMTP). Logs instead of sending when not configured."""

import asyncio
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.config import settings

logger = logging.getLogger(__name__)


def send_email(to_email: str, subject: str, html_body: str) -> bool:
    """Send an email via SMTP. Returns True if sent, False if only logged."""
    if not (settings.SMTP_HOST and settings.SMTP_USER and settings.SMTP_PASSWORD):
        logger.warning("[MAIL] SMTP not configured; skipping actual send.")
        logger.warning("[MAIL] To: %s | Subject: %s", to_email, subject)
        logger.warning("[MAIL] Body: %s", html_body)
        return False

    msg = MIMEMultipart("alternative")
    sender = settings.SMTP_FROM or settings.SMTP_USER
    msg["From"] = sender
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as server:
            server.starttls()
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.send_message(msg)
        logger.info("[MAIL] Sent to %s", to_email)
        return True
    except Exception as exc:  # pragma: no cover
        logger.error("[MAIL] Failed to send to %s: %s", to_email, exc)
        return False


async def send_email_async(to_email: str, subject: str, html_body: str) -> bool:
    """Send email without blocking the event loop (runs in a thread pool)."""
    return await asyncio.to_thread(send_email, to_email, subject, html_body)


def build_password_reset_email(reset_url: str) -> str:
    """HTML email body for password reset."""
    return f"""
    <div style="max-width:520px;margin:0 auto;font-family:Arial,sans-serif;color:#333">
      <div style="background:#27889b;border-radius:12px 12px 0 0;padding:20px;text-align:center">
        <h2 style="color:#fff;margin:0">禾笙文理補習班</h2>
      </div>
      <div style="border:1px solid #eee;border-top:none;border-radius:0 0 12px 12px;padding:24px">
        <p>您好，</p>
        <p>我們收到您重設密碼的請求。請在 <b>30 分鐘內</b> 點擊下方按鈕重設密碼：</p>
        <p style="text-align:center;margin:28px 0">
          <a href="{reset_url}" style="display:inline-block;background:#27889b;color:#fff;text-decoration:none;padding:12px 28px;border-radius:8px;font-weight:bold">重設密碼</a>
        </p>
        <p style="font-size:13px;color:#888">若按鈕無法使用，請複製以下網址到瀏覽器開啟：<br/>{reset_url}</p>
        <p style="font-size:13px;color:#888">此連結僅可使用一次，若您沒有申請重設密碼，請忽略此信件。</p>
        <hr style="border:none;border-top:1px solid #eee;margin:20px 0"/>
        <p style="font-size:12px;color:#aaa;text-align:center">禾笙文理補習班</p>
      </div>
    </div>
    """