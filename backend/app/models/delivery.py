from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Numeric, Enum as SAEnum, Date, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
from app.core.database import Base

class DeliveryStatus(str, enum.Enum):
    PENDING = "pending"
    RECEIVED = "received"
    PARTIAL = "partial"
    CANCELLED = "cancelled"
    ISSUE = "issue"

class Delivery(Base):
    __tablename__ = "deliveries"
    
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, nullable=False, default=1, server_default="1", index=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True, index=True)
    purchase_order_id = Column(Integer, ForeignKey("purchase_orders.id", ondelete="SET NULL"), nullable=True, index=True)
    document_number = Column(String(100), nullable=False, index=True)
    status = Column(SAEnum(DeliveryStatus), default=DeliveryStatus.PENDING)
    total_value = Column(Numeric(10,2), default=0)
    notes = Column(Text, nullable=True)
    delivered_at = Column(DateTime(timezone=True), nullable=True)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    supplier = relationship("Supplier", backref="deliveries")
    creator = relationship("User", backref="deliveries")
    items = relationship("DeliveryItem", back_populates="delivery", cascade="all, delete-orphan")
    purchase_order = relationship("PurchaseOrder", backref="deliveries")
    __table_args__ = (UniqueConstraint("tenant_id", "document_number", name="uq_delivery_tenant_document"),)

class DeliveryItem(Base):
    __tablename__ = "delivery_items"
    
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, nullable=False, default=1, server_default="1", index=True)
    delivery_id = Column(Integer, ForeignKey("deliveries.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    batch_id = Column(Integer, ForeignKey("batches.id", ondelete="SET NULL"), nullable=True)
    quantity_ordered = Column(Numeric(14, 3), default=0)
    quantity_received = Column(Numeric(14, 3), nullable=False)
    purchase_price = Column(Numeric(10,2), nullable=False)
    expiry_date = Column(Date, nullable=True)
    batch_number = Column(String(100), nullable=True)
    location_id = Column(Integer, ForeignKey("warehouse_locations.id", ondelete="SET NULL"), nullable=True)
    notes = Column(Text, nullable=True)
    
    delivery = relationship("Delivery", back_populates="items")
    product = relationship("Product", backref="delivery_items")
    location = relationship("WarehouseLocation")
