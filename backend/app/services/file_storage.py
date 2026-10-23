import uuid
from pathlib import Path

from app.config import settings


# ── Content sniffing ──────────────────────────────────────────────────────────
# The client-supplied Content-Type header is trivially spoofable, so we verify
# the actual file signature (magic bytes) before trusting/storing an upload.
# Maps a canonical content-type to a list of acceptable leading byte signatures.
_MAGIC_SIGNATURES = {
    "application/pdf": [b"%PDF"],
    "image/jpeg": [b"\xff\xd8\xff"],
    "image/png": [b"\x89PNG\r\n\x1a\n"],
    "image/tiff": [b"II*\x00", b"MM\x00*"],
    # Office Open XML (.docx/.xlsx) are ZIP containers; legacy .doc/.xls are OLE2.
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [b"PK\x03\x04"],
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [b"PK\x03\x04"],
    "application/msword": [b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"],
    "application/vnd.ms-excel": [b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"],
}


def content_matches_type(file_content: bytes, content_type: str) -> bool:
    """Return True if the file's magic bytes match the claimed content type.

    Returns True for content types we don't have a signature for (we can't
    disprove them) so callers stay permissive for unknown-but-allowed types,
    and False only when we KNOW the signature and it doesn't match.
    """
    signatures = _MAGIC_SIGNATURES.get(content_type)
    if not signatures:
        return True
    head = file_content[:16]
    return any(head.startswith(sig) for sig in signatures)


def save_uploaded_file(file_content: bytes, original_filename: str) -> str:
    """Save file to local storage and return the stored path."""
    upload_dir = Path(settings.UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)

    ext = Path(original_filename).suffix
    stored_name = f"{uuid.uuid4().hex}{ext}"
    stored_path = upload_dir / stored_name

    with open(stored_path, "wb") as f:
        f.write(file_content)

    return str(stored_path)
