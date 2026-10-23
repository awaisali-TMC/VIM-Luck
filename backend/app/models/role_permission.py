from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, DateTime, UniqueConstraint

from app.models.invoice import Base


class RolePermission(Base):
    """One row = 'this role may open this sidebar page'.

    Admin is implicit (always everything) and never stored. Seeded from the
    default matrix on first read; edited via the admin Roles & Permissions page.
    """
    __tablename__ = "role_permissions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    role = Column(String(50), nullable=False, index=True)     # e.g. "ap_operator"
    page_key = Column(String(100), nullable=False)            # route path, e.g. "/ap"
    level = Column(String(10), default="edit")                # "view" (read-only) | "edit"; no row = no access
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (UniqueConstraint("role", "page_key", name="uq_role_page"),)


class SeededPage(Base):
    """Marker: this catalog page has had its default grants applied once.

    Lets a release that ADDS a page to the PAGES catalog auto-apply that page's
    DEFAULT_MATRIX grants on databases seeded by an older release — exactly once,
    so later admin edits (including revoking the page from every role) stick.
    """
    __tablename__ = "rbac_seeded_pages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    page_key = Column(String(100), nullable=False, unique=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
