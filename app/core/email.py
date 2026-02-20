import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.core.config import settings

logger = logging.getLogger(__name__)


def send_password_reset_email(to_email: str, reset_link: str, first_name: str = "Member") -> None:
    """Send a password reset email via SMTP."""
    if not all([settings.SMTP_HOST, settings.SMTP_USER, settings.SMTP_PASSWORD, settings.FROM_EMAIL]):
        logger.warning("SMTP not fully configured; skipping password reset email.")
        return

    subject = "Reset Your Luboss95 VB Password"

    plain_text = (
        f"Hello {first_name},\n\n"
        f"We received a request to reset your password for your Luboss95 Village Banking account.\n\n"
        f"Click the link below to set a new password (valid for 1 hour):\n\n"
        f"{reset_link}\n\n"
        f"If you did not request a password reset, you can safely ignore this email.\n\n"
        f"Luboss95 Village Banking"
    )

    html_text = f"""
    <html>
    <body style="font-family: Arial, sans-serif; color: #1e3a5f; background: #f0f4ff; padding: 24px;">
      <div style="max-width: 480px; margin: 0 auto; background: #ffffff; border-radius: 12px;
                  border: 2px solid #bfdbfe; padding: 32px;">
        <h2 style="color: #1d4ed8; margin-bottom: 8px;">Password Reset Request</h2>
        <p>Hello {first_name},</p>
        <p>We received a request to reset your password for your <strong>Luboss95 Village Banking</strong> account.</p>
        <p style="margin: 24px 0;">
          <a href="{reset_link}"
             style="background: #2563eb; color: #ffffff; padding: 12px 24px; border-radius: 8px;
                    text-decoration: none; font-weight: bold; display: inline-block;">
            Reset My Password
          </a>
        </p>
        <p style="font-size: 13px; color: #64748b;">
          This link expires in <strong>1 hour</strong>. If you did not request a password reset,
          you can safely ignore this email.
        </p>
        <p style="font-size: 13px; color: #64748b;">
          Or copy and paste this URL into your browser:<br/>
          <a href="{reset_link}" style="color: #2563eb;">{reset_link}</a>
        </p>
      </div>
    </body>
    </html>
    """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.FROM_EMAIL
    msg["To"] = to_email
    if settings.REPLY_TO_EMAIL:
        msg["Reply-To"] = settings.REPLY_TO_EMAIL

    msg.attach(MIMEText(plain_text, "plain"))
    msg.attach(MIMEText(html_text, "html"))

    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT or 587) as server:
            server.ehlo()
            server.starttls()
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.sendmail(settings.FROM_EMAIL, to_email, msg.as_string())
        logger.info(f"Password reset email sent to {to_email}")
    except Exception as exc:
        logger.error(f"Failed to send password reset email to {to_email}: {exc}")
        raise
