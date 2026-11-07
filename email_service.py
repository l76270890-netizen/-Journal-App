import logging
import os
import smtplib
import ssl
from email.message import EmailMessage

logger = logging.getLogger(__name__)


def send_welcome_email(recipient: str, name: str) -> None:
    host = os.getenv("SMTP_HOST", "").strip()
    sender = os.getenv("SMTP_FROM_EMAIL", "").strip()
    if not host and not sender:
        logger.info("Welcome email skipped because SMTP is not configured.")
        return
    if not host or not sender:
        logger.warning(
            "Welcome email skipped: configure both SMTP_HOST and "
            "SMTP_FROM_EMAIL."
        )
        return

    username = os.getenv("SMTP_USERNAME", "").strip()
    password = os.getenv("SMTP_PASSWORD", "")
    if bool(username) != bool(password):
        logger.warning(
            "Welcome email skipped: configure both SMTP_USERNAME and "
            "SMTP_PASSWORD, or neither."
        )
        return

    try:
        port = int(os.getenv("SMTP_PORT", "587"))
        use_starttls = os.getenv("SMTP_STARTTLS", "true").lower() in {
            "1", "true", "yes"
        }
        message = EmailMessage()
        message["Subject"] = "Welcome to Luma Journal — sign-in successful"
        message["From"] = sender
        message["To"] = recipient
        message.set_content(
            f"Hello {name},\n\n"
            "Your Luma Journal account was created and you have signed in "
            "successfully.\n\n"
            "If you did not create this account, please contact us.\n\n"
            "Make space for what matters,\n"
            "The Luma Journal team"
        )

        with smtplib.SMTP(host, port, timeout=10) as server:
            if use_starttls:
                server.starttls(context=ssl.create_default_context())
            if username:
                server.login(username, password)
            server.send_message(message)
    except (OSError, smtplib.SMTPException, ValueError) as exc:
        logger.warning("Welcome email could not be sent: %s", exc)
