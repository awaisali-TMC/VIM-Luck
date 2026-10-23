"""
Gmail IMAP service — fetches emails using App Password authentication.

Prerequisites:
  1. IMAP must be enabled in Gmail → Settings → Forwarding and POP/IMAP → Enable IMAP
  2. Generate an App Password: Google Account → Security → 2-Step Verification → App passwords
  3. Set GMAIL_ADDRESS and GMAIL_APP_PASSWORD in .env
"""
import imaplib
import email
import email.header
import logging
import os
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# MIME types we support for invoice attachments (same as invoice upload endpoint)
SUPPORTED_MIME_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/tiff",
}


def _decode_header(raw_value: str | None) -> str:
    """Decode RFC 2047 encoded email header values to plain unicode string."""
    if not raw_value:
        return ""
    parts = email.header.decode_header(raw_value)
    decoded = []
    for part, charset in parts:
        if isinstance(part, bytes):
            decoded.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(part)
    return "".join(decoded)


def _extract_body_text(msg: email.message.Message) -> str:
    """Extract plain text body from an email message."""
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                charset = part.get_content_charset() or "utf-8"
                payload = part.get_payload(decode=True)
                if payload:
                    body += payload.decode(charset, errors="replace")
    else:
        if msg.get_content_type() == "text/plain":
            charset = msg.get_content_charset() or "utf-8"
            payload = msg.get_payload(decode=True)
            if payload:
                body = payload.decode(charset, errors="replace")
    return body.strip()


def _save_attachment(payload: bytes, filename: str, uid: str, upload_dir: str) -> str:
    """Save attachment bytes to disk and return the stored filepath."""
    attachments_dir = Path(upload_dir) / "email_attachments"
    attachments_dir.mkdir(parents=True, exist_ok=True)
    # Sanitize filename and prefix with UID to prevent collisions
    safe_name = "".join(c if c.isalnum() or c in "._- " else "_" for c in filename)
    stored_path = attachments_dir / f"{uid}_{safe_name}"
    stored_path.write_bytes(payload)
    return str(stored_path)


def fetch_new_emails(
    gmail_address: str,
    gmail_app_password: str,
    upload_dir: str,
    imap_host: str = "imap.gmail.com",
    imap_port: int = 993,
    folder: str = "INBOX",
    max_fetch: int = 50,
) -> list[dict]:
    """
    Connect to Gmail via IMAP, fetch UNSEEN emails, parse them.

    Returns a list of dicts, each containing:
      - message_uid: str (IMAP UID, used for deduplication)
      - from_address: str
      - subject: str
      - body_text: str
      - received_at: datetime | None
      - attachments: list of dicts with filename, content_type, file_size, stored_filepath, payload
    """
    if not gmail_address or not gmail_app_password:
        raise ValueError("GMAIL_ADDRESS and GMAIL_APP_PASSWORD must be set in .env")

    parsed_emails = []

    try:
        mail = imaplib.IMAP4_SSL(imap_host, imap_port)
        mail.login(gmail_address, gmail_app_password)
        mail.select(folder, readonly=False)

        # Search for UNSEEN emails; limit to max_fetch most recent
        status, data = mail.search(None, "UNSEEN")
        if status != "OK" or not data or not data[0]:
            mail.logout()
            return []

        uid_list = data[0].split()
        # Take most recent max_fetch UIDs
        uid_list = uid_list[-max_fetch:]

        for uid_bytes in uid_list:
            uid = uid_bytes.decode()
            try:
                fetch_status, msg_data = mail.fetch(uid_bytes, "(RFC822)")
                if fetch_status != "OK" or not msg_data or not msg_data[0]:
                    continue

                raw = msg_data[0][1]
                msg = email.message_from_bytes(raw)

                from_raw = msg.get("From", "")
                subject_raw = msg.get("Subject", "")
                date_raw = msg.get("Date", "")

                from_address = _decode_header(from_raw)
                subject = _decode_header(subject_raw)

                received_at = None
                if date_raw:
                    try:
                        received_at = parsedate_to_datetime(date_raw)
                        if received_at.tzinfo:
                            received_at = received_at.astimezone(timezone.utc).replace(tzinfo=None)
                    except Exception:
                        received_at = None

                body_text = _extract_body_text(msg)

                attachments = []
                if msg.is_multipart():
                    for part in msg.walk():
                        content_disposition = str(part.get("Content-Disposition", ""))
                        content_type = part.get_content_type()

                        if "attachment" in content_disposition or (
                            content_type in SUPPORTED_MIME_TYPES
                            and part.get_filename()
                        ):
                            filename = part.get_filename()
                            if not filename:
                                continue
                            filename = _decode_header(filename)
                            payload = part.get_payload(decode=True)
                            if not payload:
                                continue

                            # Normalize content type
                            if content_type == "image/jpg":
                                content_type = "image/jpeg"

                            if content_type not in SUPPORTED_MIME_TYPES:
                                logger.debug(f"Skipping attachment {filename} — unsupported type {content_type}")
                                continue

                            stored_path = _save_attachment(payload, filename, uid, upload_dir)
                            attachments.append({
                                "filename": filename,
                                "content_type": content_type,
                                "file_size": len(payload),
                                "stored_filepath": stored_path,
                            })

                parsed_emails.append({
                    "message_uid": uid,
                    "from_address": from_address,
                    "subject": subject,
                    "body_text": body_text,
                    "received_at": received_at,
                    "attachments": attachments,
                })

            except Exception as e:
                logger.warning(f"Failed to parse email UID {uid}: {e}")
                continue

        mail.logout()

    except imaplib.IMAP4.error as e:
        raise RuntimeError(f"IMAP connection/auth error: {e}") from e

    return parsed_emails
