import re
import uuid
from pathlib import Path
from typing import Optional

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


# ── Serving stored files back ─────────────────────────────────────────────────
# Exactly the names save_uploaded_file() generates: 32 hex chars + an optional
# short extension. Nothing else is ever served.
_STORED_NAME = re.compile(r"^[0-9a-f]{32}(\.[A-Za-z0-9]{1,10})?$")

# Types that may be shown inline in the browser. Anything else goes out as a
# plain download, so a stored file can never render as HTML on the API origin.
_INLINE_TYPES = ("application/pdf", "image/jpeg", "image/png", "image/tiff")


def resolve_stored_file(stored_filepath: Optional[str]) -> Optional[Path]:
    """Return the file behind a stored path, or None if it can't be served.

    Invoice.stored_filepath is CLIENT-SUPPLIED on /api/invoices/save, so it is
    never used as a path. Only its final name is kept, and only if it is one
    save_uploaded_file() could have produced; that name is looked up inside
    UPLOAD_DIR. Absolute paths, "../", placeholders such as "po-flip", and
    files that no longer exist (e.g. lost on a container restart) give None.
    Looking up by name also keeps old rows working if UPLOAD_DIR moves.
    """
    if not stored_filepath:
        return None
    name = re.split(r"[\\/]", stored_filepath.strip())[-1]
    if not _STORED_NAME.match(name):
        return None
    root = Path(settings.UPLOAD_DIR).resolve()
    path = (root / name).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        return None
    return path


def sniff_inline_type(path: Path) -> Optional[str]:
    """The file's real type if it's safe to show inline, judged by its bytes."""
    with open(path, "rb") as f:
        head = f.read(16)
    for content_type in _INLINE_TYPES:
        if any(head.startswith(sig) for sig in _MAGIC_SIGNATURES[content_type]):
            return content_type
    return None
