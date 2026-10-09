from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Numeric, Enum as SAEnum, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
from app.core.database import Base

class CountStatus(str, enum.Enum):
    DRAFT = "draft"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

class InventoryCount(Base):
    __tablename__ = "inventory_counts"
    
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, nullable=False, default=1, server_default="1", index=True)
    count_number = Column(String(100), nullable=False, index=True)
    location_id = Column(Integer, ForeignKey("warehouse_locations.id", ondelete="SET NULL"), nullable=True, index=True)
    status = Column(SAEnum(CountStatus), default=CountStatus.DRAFT, index=True)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    location = relationship("WarehouseLocation", backref="inventory_counts")
    creator = relationship("User", backref="inventory_counts")
    items = relationship("InventoryCountItem", back_populates="inventory_count", cascade="all, delete-orphan")
    __table_args__ = (UniqueConstraint("tenant_id", "count_number", name="uq_count_tenant_number"),)

class InventoryCountItem(Base):
    __tablename__ = "inventory_count_items"
    
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, nullable=False, default=1, server_default="1", index=True)
    count_id = Column(Integer, ForeignKey("inventory_counts.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    batch_id = Column(Integer, ForeignKey("batches.id", ondelete="SET NULL"), nullable=True)
    system_quantity = Column(Numeric(14, 3), default=0)
    counted_quantity = Column(Numeric(14, 3), nullable=False)
    difference = Column(Numeric(14, 3), default=0)
    reason = Column(Text, nullable=True)
    counted_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    
    inventory_count = relationship("InventoryCount", back_populates="items")
    product = relationship("Product", backref="count_items")
    batch = relationship("Batch")
    counter = relationship("User")
