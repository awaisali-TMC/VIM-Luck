from datetime import datetime, timezone

from sqlalchemy import Column, String, DateTime, Text

from app.models.invoice import Base


class AppSetting(Base):
    """Runtime key/value settings that admins change from the portal.

    Unlike app/config.py (environment, fixed per deployment), these live in the
    app database and take effect immediately, with no restart or redeploy.
    Current keys:
      supplier_demo_otp — fixed supplier login OTP for demos (see routers/auth.py);
                          absent or empty = disabled.
    """
    __tablename__ = "app_settings"

    key = Column(String(100), primary_key=True)
    value = Column(Text, nullable=True)
    updated_by = Column(String(255), nullable=True)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
