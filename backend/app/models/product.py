from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, Numeric, Enum as SAEnum, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
from app.core.database import Base

class ProductUnit(str, enum.Enum):
    PCS = "szt"
    KG = "kg"
    L = "l"
    PACK = "opak"
    BOX = "karton"

class Product(Base):
    __tablename__ = "products"
    
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, nullable=False, default=1, server_default="1", index=True)
    sku = Column(String(100), nullable=False, index=True)
    ean = Column(String(50), nullable=True, index=True)  # barcode
    name = Column(String(255), nullable=False, index=True)
    brand = Column(String(100), nullable=True, index=True)
    description = Column(Text, nullable=True)
    category_id = Column(Integer, ForeignKey("categories.id", ondelete="SET NULL"), nullable=True, index=True)
    unit = Column(SAEnum(ProductUnit), default=ProductUnit.PCS, nullable=False)
    vat_rate = Column(Numeric(4,2), default=23.00)
    purchase_price = Column(Numeric(10,2), nullable=False, default=0)
    selling_price = Column(Numeric(10,2), nullable=False, default=0)
    min_stock = Column(Numeric(14, 3), default=5)
    target_stock = Column(Numeric(14, 3), default=20)
    safety_stock = Column(Numeric(14, 3), default=3)
    is_active = Column(Boolean, default=True)
    default_supplier_id = Column(Integer, ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True)
    image_url = Column(String(500), nullable=True)
    requires_expiry_control = Column(Boolean, default=True)
    expiry_warning_days = Column(Integer, default=7)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    category = relationship("Category", backref="products")
    default_supplier = relationship("Supplier", backref="default_products")
    suppliers = relationship("ProductSupplier", back_populates="product", cascade="all, delete-orphan")
    __table_args__ = (
        UniqueConstraint("tenant_id", "sku", name="uq_product_tenant_sku"),
        UniqueConstraint("tenant_id", "ean", name="uq_product_tenant_ean"),
    )

class ProductSupplier(Base):
    __tablename__ = "product_suppliers"
    
    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, nullable=False, default=1, server_default="1", index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False, index=True)
    supplier_sku = Column(String(100), nullable=True)
    purchase_price = Column(Numeric(10,2), nullable=True)
    is_preferred = Column(Boolean, default=False)
    lead_time_days = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    product = relationship("Product", back_populates="suppliers")
    supplier = relationship("Supplier", backref="product_links")
