from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Numeric, Enum as SAEnum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
from app.core.database import Base

class WasteReason(str, enum.Enum):
    EXPIRED = "expired"
    DAMAGED = "damaged"
    SPOILED = "spoiled"
    THEFT = "theft"
    INVENTORY_DIFFERENCE = "inventory_difference"
    SUPPLIER_DAMAGE = "supplier_damage"
    INTERNAL_USE = "internal_use"
    RECALL = "recall"
    OTHER = "other"

class Waste(Base):
    __tablename__ = "waste"
    
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, nullable=False, default=1, server_default="1", index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    batch_id = Column(Integer, ForeignKey("batches.id", ondelete="SET NULL"), nullable=True, index=True)
    quantity = Column(Numeric(14, 3), nullable=False)
    purchase_value = Column(Numeric(10,2), default=0)
    sale_value = Column(Numeric(10,2), default=0)
    reason = Column(SAEnum(WasteReason), nullable=False, index=True)
    notes = Column(Text, nullable=True)
    reported_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    location_id = Column(Integer, ForeignKey("warehouse_locations.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    
    product = relationship("Product", backref="waste_entries")
    batch = relationship("Batch", backref="waste_entries")
    reporter = relationship("User", backref="waste_reports")
    location = relationship("WarehouseLocation")
