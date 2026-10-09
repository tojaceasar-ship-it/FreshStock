from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
from decimal import Decimal
from app.core.database import get_db
from app.core.deps import get_current_user, require_permission
from app.models.stock_movement import StockMovement
from pydantic import BaseModel, ConfigDict

router = APIRouter()

class MovementOut(BaseModel):
    id: int
    product_id: int
    batch_id: Optional[int]
    quantity: Decimal
    movement_type: str
    source_location_id: Optional[int]
    destination_location_id: Optional[int]
    user_id: Optional[int]
    reason: Optional[str]
    reference_id: Optional[str]
    reference_type: Optional[str]
    created_at: datetime
    product_name: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)

@router.get("", response_model=List[MovementOut])
def list_movements(
    product_id: Optional[int] = None,
    movement_type: Optional[str] = None,
    limit: int = Query(100, le=500),
    db: Session = Depends(get_db),
    current_user = Depends(require_permission("stock-movements:read"))
):
    q = db.query(StockMovement).order_by(StockMovement.created_at.desc())
    if product_id:
        q = q.filter(StockMovement.product_id == product_id)
    if movement_type:
        q = q.filter(StockMovement.movement_type == movement_type)
    movements = q.limit(limit).all()
    result = []
    for m in movements:
        out = MovementOut.model_validate(m)
        if m.product:
            out.product_name = m.product.name
        result.append(out)
    return result
