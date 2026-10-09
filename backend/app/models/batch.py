from sqlalchemy import Column, Integer, String, Date, DateTime, ForeignKey, Numeric, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base

class Batch(Base):
    __tablename__ = "batches"
    
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, nullable=False, default=1, server_default="1", index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    batch_number = Column(String(100), nullable=False, index=True)
    expiry_date = Column(Date, nullable=True, index=True)
    manufacture_date = Column(Date, nullable=True)
    quantity_received = Column(Numeric(14, 3), nullable=False, default=0)
    quantity_available = Column(Numeric(14, 3), nullable=False, default=0, index=True)
    purchase_price = Column(Numeric(10,2), nullable=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True)
    delivery_id = Column(Integer, ForeignKey("deliveries.id", ondelete="SET NULL"), nullable=True)
    warehouse_location_id = Column(Integer, ForeignKey("warehouse_locations.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    product = relationship("Product", backref="batches")
    supplier = relationship("Supplier", backref="batches")
    location = relationship("WarehouseLocation", backref="batches")
    
    __table_args__ = (
        Index('ix_batch_product_expiry', 'product_id', 'expiry_date'),
    )
