from sqlalchemy import Column, Integer, String, Float, Text

from app.models.invoice import Base


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    category = Column(String(100), nullable=False)
    description = Column(Text, default="")
    unit = Column(String(50), default="Each")
    default_price = Column(Float, default=0.0)
