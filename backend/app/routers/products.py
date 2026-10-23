from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.product import Product

router = APIRouter(prefix="/api/products", tags=["products"])


class ProductResponse(BaseModel):
    id: int
    code: str
    name: str
    category: str
    description: str
    unit: str
    default_price: float

    model_config = {"from_attributes": True}


class ProductListResponse(BaseModel):
    products: list[ProductResponse]
    total: int


@router.get("/", response_model=ProductListResponse)
async def list_products(
    skip: int = 0,
    limit: int = 50,
    search: str = Query(default="", description="Search by name, code, or category"),
    category: str = Query(default="", description="Filter by category"),
    db: AsyncSession = Depends(get_db),
):
    """List products with optional search and category filter."""
    query = select(Product)

    if search:
        pattern = f"%{search}%"
        query = query.where(
            Product.name.ilike(pattern)
            | Product.code.ilike(pattern)
            | Product.category.ilike(pattern)
            | Product.description.ilike(pattern)
        )

    if category:
        query = query.where(Product.category == category)

    # Count
    count_query = select(func.count()).select_from(query.subquery())
    count_result = await db.execute(count_query)
    total = count_result.scalar()

    # Fetch
    query = query.order_by(Product.code).offset(skip).limit(limit)
    result = await db.execute(query)
    products = result.scalars().all()

    return ProductListResponse(products=products, total=total)


@router.get("/categories", response_model=list[str])
async def list_categories(db: AsyncSession = Depends(get_db)):
    """List all distinct product categories."""
    result = await db.execute(
        select(Product.category).distinct().order_by(Product.category)
    )
    return [row[0] for row in result.all()]
