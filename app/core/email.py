import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List

from app.core.config import settings

logger = logging.getLogger(__name__)


def _send_email(to_email: str, subject: str, plain_text: str, html_text: str) -> None:
    """Low-level helper to send one email via SMTP."""
    if not all([settings.SMTP_HOST, settings.SMTP_USER, settings.SMTP_PASSWORD, settings.FROM_EMAIL]):
        logger.warning("SMTP not fully configured; skipping email to %s.", to_email)
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.FROM_EMAIL
    msg["To"] = to_email
    if settings.REPLY_TO_EMAIL:
        msg["Reply-To"] = settings.REPLY_TO_EMAIL

    msg.attach(MIMEText(plain_text, "plain"))
    msg.attach(MIMEText(html_text, "html"))

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT or 587) as server:
        server.ehlo()
        server.starttls()
        server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        server.sendmail(settings.FROM_EMAIL, to_email, msg.as_string())


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
        _send_email(to_email, subject, plain_text, html_text)
        logger.info(f"Password reset email sent to {to_email}")
    except Exception as exc:
        logger.error(f"Failed to send password reset email to {to_email}: {exc}")
        raise


def send_scheduler_report(
    to_emails: List[str],
    closed_loans: List[dict],
    excess_transfers: List[dict],
) -> None:
    """Send a summary report of automatic book updates to all treasurer emails.

    Only call this when there is at least one change to report.
    Each closed_loan dict: {"member_name": str, "loan_amount": float}
    Each excess_transfer dict: {"member_name": str, "social_excess": float, "admin_excess": float}
    """
    if not to_emails:
        return

    subject = "Luboss95 VB - Automatic Book Update Report"

    # ---- plain text --------------------------------------------------------
    lines = ["Luboss95 Village Banking - Automatic Book Update Report", ""]

    if closed_loans:
        lines.append(f"LOANS AUTO-CLOSED ({len(closed_loans)}):")
        for item in closed_loans:
            lines.append(f"  - {item['member_name']}: K {item['loan_amount']:,.2f}")
        lines.append("")

    if excess_transfers:
        lines.append(f"EXCESS FUND TRANSFERS TO SAVINGS ({len(excess_transfers)}):")
        for item in excess_transfers:
            parts = []
            if item["social_excess"] > 0:
                parts.append(f"Social K {item['social_excess']:,.2f}")
            if item["admin_excess"] > 0:
                parts.append(f"Admin K {item['admin_excess']:,.2f}")
            lines.append(f"  - {item['member_name']}: {', '.join(parts)}")
        lines.append("")

    lines.append("This is an automated notification from the Luboss95 VB system.")
    plain_text = "\n".join(lines)

    # ---- HTML --------------------------------------------------------------
    loan_rows = ""
    if closed_loans:
        for item in closed_loans:
            loan_rows += (
                f'<tr><td style="padding:6px 12px;border-bottom:1px solid #e2e8f0;">{item["member_name"]}</td>'
                f'<td style="padding:6px 12px;border-bottom:1px solid #e2e8f0;text-align:right;">K {item["loan_amount"]:,.2f}</td></tr>'
            )

    transfer_rows = ""
    if excess_transfers:
        for item in excess_transfers:
            parts = []
            if item["social_excess"] > 0:
                parts.append(f"Social K {item['social_excess']:,.2f}")
            if item["admin_excess"] > 0:
                parts.append(f"Admin K {item['admin_excess']:,.2f}")
            transfer_rows += (
                f'<tr><td style="padding:6px 12px;border-bottom:1px solid #e2e8f0;">{item["member_name"]}</td>'
                f'<td style="padding:6px 12px;border-bottom:1px solid #e2e8f0;">{", ".join(parts)}</td></tr>'
            )

    loan_section = ""
    if closed_loans:
        loan_section = f"""
        <h3 style="color:#1d4ed8;margin-top:24px;">Loans Auto-Closed ({len(closed_loans)})</h3>
        <table style="width:100%;border-collapse:collapse;font-size:14px;">
          <tr style="background:#eff6ff;">
            <th style="padding:8px 12px;text-align:left;">Member</th>
            <th style="padding:8px 12px;text-align:right;">Loan Amount</th>
          </tr>
          {loan_rows}
        </table>"""

    transfer_section = ""
    if excess_transfers:
        transfer_section = f"""
        <h3 style="color:#1d4ed8;margin-top:24px;">Excess Fund Transfers to Savings ({len(excess_transfers)})</h3>
        <table style="width:100%;border-collapse:collapse;font-size:14px;">
          <tr style="background:#eff6ff;">
            <th style="padding:8px 12px;text-align:left;">Member</th>
            <th style="padding:8px 12px;text-align:left;">Amount Transferred</th>
          </tr>
          {transfer_rows}
        </table>"""

    html_text = f"""
    <html>
    <body style="font-family:Arial,sans-serif;color:#1e3a5f;background:#f0f4ff;padding:24px;">
      <div style="max-width:560px;margin:0 auto;background:#ffffff;border-radius:12px;
                  border:2px solid #bfdbfe;padding:32px;">
        <h2 style="color:#1d4ed8;margin-bottom:4px;">Automatic Book Update Report</h2>
        <p style="font-size:13px;color:#64748b;margin-top:0;">Luboss95 Village Banking System</p>
        {loan_section}
        {transfer_section}
        <p style="font-size:12px;color:#94a3b8;margin-top:24px;">
          This is an automated notification. No action is required unless you spot a discrepancy.
        </p>
      </div>
    </body>
    </html>
    """

    for email_addr in to_emails:
        try:
            _send_email(email_addr, subject, plain_text, html_text)
            logger.info("Scheduler report email sent to %s", email_addr)
        except Exception:
            logger.exception("Failed to send scheduler report to %s", email_addr)
