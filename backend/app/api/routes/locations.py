from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.core.database import get_db
from app.core.deps import get_current_user, require_permission
from app.models.location import WarehouseLocation
from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import datetime

router = APIRouter()

class LocationCreate(BaseModel):
    name: str
    code: str
    type: str = "shelf"
    parent_id: Optional[int] = None
    description: Optional[str] = None

class LocationUpdate(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    type: Optional[str] = None
    parent_id: Optional[int] = None
    description: Optional[str] = None

class LocationOut(BaseModel):
    id: int
    name: str
    code: str
    type: str
    parent_id: Optional[int]
    description: Optional[str]
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

@router.get("", response_model=List[LocationOut])
def list_locations(db: Session = Depends(get_db), current_user = Depends(require_permission("locations:read"))):
    return db.query(WarehouseLocation).filter(WarehouseLocation.tenant_id == current_user.tenant_id).order_by(WarehouseLocation.name).all()

@router.post("", response_model=LocationOut)
def create_location(payload: LocationCreate, db: Session = Depends(get_db), current_user = Depends(require_permission("locations:write"))):
    if db.query(WarehouseLocation).filter(WarehouseLocation.code == payload.code).first():
        raise HTTPException(status_code=400, detail="Kod już istnieje")
    loc = WarehouseLocation(tenant_id=current_user.tenant_id, **payload.model_dump())
    db.add(loc)
    db.commit()
    db.refresh(loc)
    return loc

@router.get("/{location_id}", response_model=LocationOut)
def get_location(location_id: int, db: Session = Depends(get_db), current_user = Depends(require_permission("locations:read"))):
    loc = db.query(WarehouseLocation).filter(WarehouseLocation.id == location_id, WarehouseLocation.tenant_id == current_user.tenant_id).first()
    if not loc:
        raise HTTPException(status_code=404, detail="Not found")
    return loc

@router.put("/{location_id}", response_model=LocationOut)
def update_location(location_id: int, payload: LocationUpdate, db: Session = Depends(get_db), current_user = Depends(require_permission("locations:write"))):
    loc = db.query(WarehouseLocation).filter(WarehouseLocation.id == location_id, WarehouseLocation.tenant_id == current_user.tenant_id).first()
    if not loc:
        raise HTTPException(status_code=404, detail="Not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(loc, k, v)
    db.commit()
    db.refresh(loc)
    return loc

@router.delete("/{location_id}")
def delete_location(location_id: int, db: Session = Depends(get_db), current_user = Depends(require_permission("locations:write"))):
    loc = db.query(WarehouseLocation).filter(WarehouseLocation.id == location_id, WarehouseLocation.tenant_id == current_user.tenant_id).first()
    if not loc:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(loc)
    db.commit()
    return {"message": "Deleted"}

@router.get("/hierarchy/tree")
def get_hierarchy(db: Session = Depends(get_db), current_user = Depends(require_permission("locations:read"))):
    locations = db.query(WarehouseLocation).filter(WarehouseLocation.tenant_id == current_user.tenant_id).all()
    # build tree
    lookup = {loc.id: {"id": loc.id, "name": loc.name, "code": loc.code, "type": loc.type.value if hasattr(loc.type, 'value') else loc.type, "parent_id": loc.parent_id, "children": []} for loc in locations}
    roots = []
    for loc in locations:
        if loc.parent_id and loc.parent_id in lookup:
            lookup[loc.parent_id]["children"].append(lookup[loc.id])
        else:
            roots.append(lookup[loc.id])
    return roots
