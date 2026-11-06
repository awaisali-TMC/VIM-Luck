import re
import uuid
from concurrent.futures import ThreadPoolExecutor
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


def save_uploaded_file(
    file_content: bytes,
    original_filename: str,
    *,
    subdir: Optional[str] = None,
    prefix: str = "",
) -> str:
    """Save a file under UPLOAD_DIR and return the stored path.

    `subdir` nests it one level deeper (e.g. per uploader) and `prefix` is
    prepended to the generated name. Both must be safe tokens — resolve_stored_file
    only serves back names/subdirs matching the patterns below.
    """
    base = Path(settings.UPLOAD_DIR)
    target = (base / subdir) if subdir else base
    target.mkdir(parents=True, exist_ok=True)

    ext = Path(original_filename).suffix
    stored_name = f"{prefix}{uuid.uuid4().hex}{ext}"
    stored_path = target / stored_name

    with open(stored_path, "wb") as f:
        f.write(file_content)

    return str(stored_path)


# Marker stored on an invoice when upload persistence is off (Cloud Run,
# SAVE_UPLOADS=false): the file was extracted but intentionally not kept, so
# resolve_stored_file() returns None and the UI shows no View/Download.
UNSAVED_MARKER = "unsaved"


def slugify_name(name: Optional[str]) -> str:
    """A filesystem-safe token from a person/company name: lowercase, runs of
    non-alphanumerics collapsed to '_', trimmed. Falls back to 'unknown'."""
    slug = re.sub(r"[^a-z0-9]+", "_", (name or "").strip().lower()).strip("_")
    return slug[:60] or "unknown"


def invoice_upload_target(uploader_kind: str, uploader_name: str) -> tuple[str, str]:
    """(subdir, filename-prefix) for an invoice upload, organised by uploader:
    a vendor (supplier) -> folder <name>/, prefix 'vendor_<name>_';
    anyone internal (AP operator) -> folder <name>/, prefix 'apo_<name>_'."""
    slug = slugify_name(uploader_name)
    role = "vendor" if uploader_kind == "supplier" else "apo"
    return slug, f"{role}_{slug}_"


def save_invoice_file(
    file_content: bytes,
    original_filename: str,
    uploader_kind: str,
    uploader_name: str,
) -> str:
    """Persist an uploaded invoice file, organised by uploader, and return the
    stored path. Returns UNSAVED_MARKER when SAVE_UPLOADS is off (Cloud Run):
    extraction still runs on the in-memory bytes; nothing is written."""
    if not settings.SAVE_UPLOADS:
        return UNSAVED_MARKER
    subdir, prefix = invoice_upload_target(uploader_kind, uploader_name)
    return save_uploaded_file(file_content, original_filename, subdir=subdir, prefix=prefix)


# ── Serving stored files back ─────────────────────────────────────────────────
# Exactly the names save_uploaded_file()/save_invoice_file() generate: a bare
# 32-hex uuid (legacy + attachments), or a 'vendor_<slug>_'/'apo_<slug>_' prefix
# before the uuid, each with an optional short extension. Nothing else is served.
_STORED_NAME = re.compile(
    r"^(?:[0-9a-f]{32}|(?:vendor|apo)_[a-z0-9_]+_[0-9a-f]{32})(\.[A-Za-z0-9]{1,10})?$"
)
# A single uploader subfolder component (slugify_name output).
_SUBDIR = re.compile(r"^[a-z0-9_]{1,80}$")

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
    parts = [p for p in re.split(r"[\\/]+", stored_filepath.strip()) if p not in ("", ".")]
    if not parts:
        return None
    name = parts[-1]
    if not _STORED_NAME.match(name):
        return None
    root = Path(settings.UPLOAD_DIR).resolve()
    # Only the final name and (at most) its immediate parent are trusted, each
    # against a strict pattern; the resolved path must still land inside root.
    # New files live in UPLOAD_DIR/<uploader>/; legacy ones sit in root.
    candidates = []
    subdir = parts[-2] if len(parts) >= 2 else None
    if subdir and _SUBDIR.match(subdir):
        candidates.append(root / subdir / name)
    candidates.append(root / name)
    for cand in candidates:
        path = cand.resolve()
        if path.is_relative_to(root) and path.is_file():
            return path
    return None


def stored_files_available(stored_filepaths: list[Optional[str]]) -> list[bool]:
    """resolve_stored_file() for a page of rows, checked in parallel.

    On Cloud Run UPLOAD_DIR is a Cloud Storage mount, so each check is a
    metadata round trip; a small pool keeps a 100-row page fast. Blocking:
    call it via asyncio.to_thread from async code.
    """
    if not stored_filepaths:
        return []
    with ThreadPoolExecutor(max_workers=min(8, len(stored_filepaths))) as pool:
        return list(pool.map(lambda p: resolve_stored_file(p) is not None, stored_filepaths))


def sniff_inline_type(path: Path) -> Optional[str]:
    """The file's real type if it's safe to show inline, judged by its bytes."""
    with open(path, "rb") as f:
        head = f.read(16)
    for content_type in _INLINE_TYPES:
        if any(head.startswith(sig) for sig in _MAGIC_SIGNATURES[content_type]):
            return content_type
    return None
