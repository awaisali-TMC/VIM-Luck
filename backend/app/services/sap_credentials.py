"""Per-user SAP credentials: encryption at rest + request-scoped identity.

Each internal user may have their own SAP login (``internal_users.sap_username``
+ ``sap_password_enc``). The password is stored encrypted — SAP needs it in
cleartext to authenticate over RFC, so it cannot be hashed like the app login
password; it is Fernet-encrypted with a key derived from ``SAP_CRED_KEY``.

When a user parks/posts an invoice, the SAP router sets the request's SAP
identity here (``set_sap_identity``) and the connector's ``connect()`` reads it
via ``current_sap_user`` / ``current_sap_passwd``, falling back to the global
``SAP_USER`` / ``SAP_PASSWD`` when the user has no SAP login of their own. The
identity is held in a ``contextvars.ContextVar``, so it is scoped to the single
request task and never leaks to other requests.
"""

import base64
import contextvars
import hashlib
import logging

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings

logger = logging.getLogger(__name__)

# ── Encryption at rest ───────────────────────────────────────────────────────

_FALLBACK_SECRET = b"vim-luck-sap-cred-fallback-key"


def _fernet() -> Fernet:
    """Build the Fernet cipher from SAP_CRED_KEY.

    A valid 32-byte urlsafe-base64 Fernet key is used directly; any other
    non-empty string is hashed (SHA-256) into one so operators can set a plain
    passphrase. With no key configured, a fixed derived key keeps the feature
    working in dev — but it offers no real protection, so a warning is logged.
    """
    key = (settings.SAP_CRED_KEY or "").strip()
    if not key:
        logger.warning(
            "SAP_CRED_KEY is not set — SAP passwords are encrypted with a fixed "
            "derived key, which is not real at-rest protection. Set SAP_CRED_KEY "
            "(a Fernet key or passphrase) in production."
        )
        derived = base64.urlsafe_b64encode(hashlib.sha256(_FALLBACK_SECRET).digest())
        return Fernet(derived)
    try:
        return Fernet(key.encode())
    except (ValueError, TypeError):
        # Not a raw Fernet key — derive one deterministically from the string.
        derived = base64.urlsafe_b64encode(hashlib.sha256(key.encode()).digest())
        return Fernet(derived)


def encrypt_sap_password(plain: str | None) -> str | None:
    """Encrypt a SAP password for storage. Empty/None → None (no password)."""
    if not plain:
        return None
    return _fernet().encrypt(plain.encode()).decode()


def decrypt_sap_password(token: str | None) -> str:
    """Decrypt a stored SAP password. Returns "" if absent or undecryptable
    (e.g. SAP_CRED_KEY changed since it was stored)."""
    if not token:
        return ""
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        logger.error(
            "Could not decrypt a stored SAP password — SAP_CRED_KEY may have "
            "changed. The user must re-enter their SAP password."
        )
        return ""


# ── Request-scoped SAP identity ──────────────────────────────────────────────

# (user, passwd) for the current request, or None to use the global SAP login.
_sap_identity: contextvars.ContextVar[tuple[str, str] | None] = contextvars.ContextVar(
    "sap_identity", default=None
)


def set_sap_identity(user: str | None, passwd: str | None) -> None:
    """Set the SAP login for the current request. A blank user clears it, so
    the connector falls back to the global SAP_USER/SAP_PASSWD."""
    if user and user.strip():
        _sap_identity.set((user.strip(), passwd or ""))
    else:
        _sap_identity.set(None)


def current_sap_user() -> str:
    ident = _sap_identity.get()
    return ident[0] if ident else settings.SAP_USER


def current_sap_passwd() -> str:
    ident = _sap_identity.get()
    return ident[1] if ident else settings.SAP_PASSWD
