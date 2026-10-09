from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List
from app.core.database import get_db
from app.core.deps import get_current_user, require_permission
from app.models.category import Category
from app.models.product import Product
from app.schemas.category import CategoryCreate, CategoryUpdate, CategoryOut

router = APIRouter()

@router.get("", response_model=List[CategoryOut])
def list_categories(db: Session = Depends(get_db), current_user = Depends(require_permission("categories:read"))):
    categories = db.query(Category).order_by(Category.name).all()
    result = []
    for cat in categories:
        count = db.query(func.count(Product.id)).filter(Product.category_id == cat.id).scalar()
        out = CategoryOut.model_validate(cat)
        out.product_count = count
        result.append(out)
    return result

@router.post("", response_model=CategoryOut)
def create_category(payload: CategoryCreate, db: Session = Depends(get_db), current_user = Depends(require_permission("categories:write"))):
    if db.query(Category).filter(Category.name == payload.name).first():
        raise HTTPException(status_code=400, detail="Kategoria już istnieje")
    cat = Category(**payload.model_dump())
    db.add(cat)
    db.commit()
    db.refresh(cat)
    out = CategoryOut.model_validate(cat)
    out.product_count = 0
    return out

@router.get("/{category_id}", response_model=CategoryOut)
def get_category(category_id: int, db: Session = Depends(get_db), current_user = Depends(require_permission("categories:read"))):
    cat = db.query(Category).filter(Category.id == category_id).first()
    if not cat:
        raise HTTPException(status_code=404, detail="Not found")
    count = db.query(func.count(Product.id)).filter(Product.category_id == cat.id).scalar()
    out = CategoryOut.model_validate(cat)
    out.product_count = count
    return out

@router.put("/{category_id}", response_model=CategoryOut)
def update_category(category_id: int, payload: CategoryUpdate, db: Session = Depends(get_db), current_user = Depends(require_permission("categories:write"))):
    cat = db.query(Category).filter(Category.id == category_id).first()
    if not cat:
        raise HTTPException(status_code=404, detail="Not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(cat, k, v)
    db.commit()
    db.refresh(cat)
    count = db.query(func.count(Product.id)).filter(Product.category_id == cat.id).scalar()
    out = CategoryOut.model_validate(cat)
    out.product_count = count
    return out

@router.delete("/{category_id}")
def delete_category(category_id: int, db: Session = Depends(get_db), current_user = Depends(require_permission("categories:write"))):
    cat = db.query(Category).filter(Category.id == category_id).first()
    if not cat:
        raise HTTPException(status_code=404, detail="Not found")
    if db.query(Product).filter(Product.category_id == category_id).first():
        raise HTTPException(status_code=400, detail="Nie można usunąć kategorii z produktami")
    db.delete(cat)
    db.commit()
    return {"message": "Deleted"}
