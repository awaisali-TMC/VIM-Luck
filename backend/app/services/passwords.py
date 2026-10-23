"""
Password hashing — PBKDF2-HMAC-SHA256 with transparent legacy upgrade.

Historically passwords were stored as ``{salt}:{sha256(salt+password)}``. A
single unsalted-per-iteration SHA-256 is fast and therefore weak against
offline brute force. We now hash with PBKDF2-HMAC-SHA256 (many iterations),
using only the Python standard library so no new dependency is required.

Stored format (new):  ``pbkdf2_sha256${iterations}${salt_hex}${hash_hex}``
Stored format (legacy, still verifiable): ``{salt_hex}:{sha256_hex}``

`verify_password` accepts both formats so existing accounts keep working.
`needs_rehash` lets callers transparently upgrade a legacy hash to PBKDF2 the
next time the user authenticates successfully.
"""

import hashlib
import hmac
import secrets

# OWASP-recommended floor for PBKDF2-HMAC-SHA256 (well above legacy single-SHA).
_ALGORITHM = "pbkdf2_sha256"
_ITERATIONS = 240_000
_SALT_BYTES = 16


def hash_password(password: str) -> str:
    """Hash a plaintext password with PBKDF2-HMAC-SHA256."""
    salt = secrets.token_hex(_SALT_BYTES)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), _ITERATIONS)
    return f"{_ALGORITHM}${_ITERATIONS}${salt}${dk.hex()}"


def _verify_pbkdf2(password: str, stored: str) -> bool:
    try:
        algorithm, iterations, salt, expected = stored.split("$", 3)
        if algorithm != _ALGORITHM:
            return False
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(iterations))
        return hmac.compare_digest(dk.hex(), expected)
    except (ValueError, TypeError):
        return False


def _verify_legacy(password: str, stored: str) -> bool:
    """Verify the old ``{salt}:{sha256(salt+password)}`` format."""
    try:
        salt, hashed = stored.split(":", 1)
        candidate = hashlib.sha256(f"{salt}{password}".encode()).hexdigest()
        return hmac.compare_digest(candidate, hashed)
    except (ValueError, TypeError):
        return False


def verify_password(password: str, stored: str) -> bool:
    """Verify a password against either the new PBKDF2 or the legacy hash."""
    if not stored:
        return False
    if stored.startswith(f"{_ALGORITHM}$"):
        return _verify_pbkdf2(password, stored)
    return _verify_legacy(password, stored)


def needs_rehash(stored: str) -> bool:
    """True if the stored hash uses an outdated scheme and should be upgraded."""
    if not stored:
        return False
    if not stored.startswith(f"{_ALGORITHM}$"):
        return True
    # Upgrade if iteration count has been raised since the hash was created.
    try:
        _, iterations, _, _ = stored.split("$", 3)
        return int(iterations) < _ITERATIONS
    except (ValueError, TypeError):
        return True
