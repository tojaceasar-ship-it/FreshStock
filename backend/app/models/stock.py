from sqlalchemy import Column, Integer, DateTime, ForeignKey, Numeric, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base

class Stock(Base):
    __tablename__ = "stock"
    
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, nullable=False, default=1, server_default="1", index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    location_id = Column(Integer, ForeignKey("warehouse_locations.id", ondelete="CASCADE"), nullable=False, index=True)
    quantity = Column(Numeric(14, 3), default=0, nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    product = relationship("Product", backref="stock_entries")
    location = relationship("WarehouseLocation", backref="stock_entries")
    
    __table_args__ = (
        UniqueConstraint('tenant_id', 'product_id', 'location_id', name='uq_tenant_product_location'),
    )
