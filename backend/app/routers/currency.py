"""Multi-currency exchange rate endpoints."""

import logging
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.comment import CurrencyRate

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/currency", tags=["currency"])


@router.get("/rates")
async def list_rates(
    from_currency: str | None = None,
    to_currency: str = "PKR",
    db: AsyncSession = Depends(get_db),
):
    q = select(CurrencyRate).where(CurrencyRate.to_currency == to_currency)
    if from_currency:
        q = q.where(CurrencyRate.from_currency == from_currency)
    q = q.order_by(CurrencyRate.effective_date.desc()).limit(100)
    result = await db.execute(q)
    rates = result.scalars().all()
    return {
        "rates": [
            {
                "id": r.id, "from_currency": r.from_currency,
                "to_currency": r.to_currency, "rate": r.rate,
                "effective_date": r.effective_date, "source": r.source,
            }
            for r in rates
        ]
    }


@router.post("/rates")
async def create_rate(
    from_currency: str,
    rate: str,
    effective_date: str,
    to_currency: str = "PKR",
    source: str = "manual",
    db: AsyncSession = Depends(get_db),
):
    entry = CurrencyRate(
        from_currency=from_currency.upper(),
        to_currency=to_currency.upper(),
        rate=rate,
        effective_date=effective_date,
        source=source,
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return {"id": entry.id, "from_currency": entry.from_currency, "rate": entry.rate}


@router.get("/convert")
async def convert_amount(
    amount: float,
    from_currency: str,
    to_currency: str = "PKR",
    date: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Convert an amount using the latest available rate."""
    if from_currency.upper() == to_currency.upper():
        return {"original": amount, "converted": amount, "rate": "1", "currency": to_currency}

    q = select(CurrencyRate).where(
        and_(
            CurrencyRate.from_currency == from_currency.upper(),
            CurrencyRate.to_currency == to_currency.upper(),
        )
    )
    if date:
        q = q.where(CurrencyRate.effective_date <= date)
    q = q.order_by(CurrencyRate.effective_date.desc()).limit(1)

    result = await db.execute(q)
    rate_entry = result.scalar_one_or_none()
    if not rate_entry:
        raise HTTPException(404, f"No exchange rate found for {from_currency} → {to_currency}")

    rate_val = float(rate_entry.rate)
    converted = round(amount * rate_val, 2)
    return {
        "original": amount,
        "from_currency": from_currency.upper(),
        "converted": converted,
        "to_currency": to_currency.upper(),
        "rate": rate_entry.rate,
        "effective_date": rate_entry.effective_date,
    }
