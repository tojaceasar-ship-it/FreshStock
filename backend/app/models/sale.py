from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Numeric, Enum as SAEnum, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
from app.core.database import Base

class SaleSource(str, enum.Enum):
    POS = "pos"
    CSV = "csv"
    API = "api"
    MANUAL = "manual"

class Sale(Base):
    __tablename__ = "sales"
    
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, nullable=False, default=1, server_default="1", index=True)
    sale_number = Column(String(100), nullable=False, index=True)
    sale_date = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    total_amount = Column(Numeric(10,2), default=0)
    source = Column(SAEnum(SaleSource), default=SaleSource.MANUAL)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    creator = relationship("User", backref="sales")
    items = relationship("SaleItem", back_populates="sale", cascade="all, delete-orphan")
    __table_args__ = (UniqueConstraint("tenant_id", "sale_number", name="uq_sale_tenant_number"),)

class SaleItem(Base):
    __tablename__ = "sale_items"
    
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, nullable=False, default=1, server_default="1", index=True)
    sale_id = Column(Integer, ForeignKey("sales.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    batch_id = Column(Integer, ForeignKey("batches.id", ondelete="SET NULL"), nullable=True, index=True)
    promotion_id = Column(Integer, ForeignKey("promotions.id", ondelete="SET NULL"), nullable=True, index=True)
    quantity = Column(Numeric(14, 3), nullable=False)
    unit_price = Column(Numeric(10,2), nullable=False)
    regular_unit_price = Column(Numeric(10,2), nullable=True)
    total_price = Column(Numeric(10,2), nullable=False)
    markdown_discount_value = Column(Numeric(12,2), nullable=False, default=0, server_default="0")
    recovered_revenue = Column(Numeric(12,2), nullable=False, default=0, server_default="0")
    protected_cost = Column(Numeric(12,2), nullable=False, default=0, server_default="0")
    
    sale = relationship("Sale", back_populates="items")
    product = relationship("Product", backref="sale_items")
    batch = relationship("Batch", backref="sale_items")
    promotion = relationship("Promotion", backref="sale_items")
