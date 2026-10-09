from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Numeric, Enum as SAEnum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
from app.core.database import Base

class MovementType(str, enum.Enum):
    DELIVERY = "delivery"
    SALE = "sale"
    TRANSFER = "transfer"
    WASTE = "waste"
    RETURN = "return"
    CORRECTION = "correction"
    INVENTORY_ADJUSTMENT = "inventory_adjustment"
    DAMAGED = "damaged"
    EXPIRED = "expired"
    PROMOTION = "promotion"
    MANUAL_ADJUSTMENT = "manual_adjustment"
    SALE_REVERSAL = "sale_reversal"

class StockMovement(Base):
    __tablename__ = "stock_movements"
    
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, nullable=False, default=1, server_default="1", index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    batch_id = Column(Integer, ForeignKey("batches.id", ondelete="SET NULL"), nullable=True, index=True)
    quantity = Column(Numeric(14, 3), nullable=False)  # positive = in, negative = out
    movement_type = Column(SAEnum(MovementType), nullable=False, index=True)
    source_location_id = Column(Integer, ForeignKey("warehouse_locations.id", ondelete="SET NULL"), nullable=True)
    destination_location_id = Column(Integer, ForeignKey("warehouse_locations.id", ondelete="SET NULL"), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reason = Column(Text, nullable=True)
    reference_id = Column(String(100), nullable=True)  # delivery_id, sale_id etc
    reference_type = Column(String(50), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    
    product = relationship("Product", backref="movements")
    batch = relationship("Batch", backref="movements")
    user = relationship("User", backref="movements")
    source_location = relationship("WarehouseLocation", foreign_keys=[source_location_id])
    destination_location = relationship("WarehouseLocation", foreign_keys=[destination_location_id])
