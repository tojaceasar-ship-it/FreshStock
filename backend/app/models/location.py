from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Enum as SAEnum, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
from app.core.database import Base

class LocationType(str, enum.Enum):
    STORE = "store"
    WAREHOUSE = "warehouse"
    FRIDGE = "fridge"
    FREEZER = "freezer"
    SHELF = "shelf"
    AISLE = "aisle"
    BACKROOM = "backroom"
    OTHER = "other"

class WarehouseLocation(Base):
    __tablename__ = "warehouse_locations"
    
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, nullable=False, default=1, server_default="1", index=True)
    name = Column(String(255), nullable=False)
    code = Column(String(50), nullable=False, index=True)
    type = Column(SAEnum(LocationType), default=LocationType.SHELF, nullable=False)
    parent_id = Column(Integer, ForeignKey("warehouse_locations.id", ondelete="SET NULL"), nullable=True, index=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    parent = relationship("WarehouseLocation", remote_side=[id], backref="children")
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_location_tenant_code"),)
