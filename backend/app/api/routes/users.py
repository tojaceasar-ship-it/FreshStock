from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.core.database import get_db
from app.core.deps import get_current_user, require_permission, require_roles
from app.models.user import User, UserRole
from app.schemas.user import UserOut, UserCreate, UserUpdate, PasswordChange
from app.core.security import get_password_hash, verify_password
from app.services.audit import add_audit_log
from app.services.plans import PlanService

router = APIRouter()

@router.post("/me/password")
def change_password(payload: PasswordChange, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not verify_password(payload.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Obecne hasło jest nieprawidłowe")
    if payload.current_password == payload.new_password:
        raise HTTPException(status_code=400, detail="Nowe hasło musi być inne")
    current_user.hashed_password = get_password_hash(payload.new_password)
    add_audit_log(db, user_id=current_user.id, action="PASSWORD_CHANGE", entity_type="user", entity_id=current_user.id, details="Użytkownik zmienił hasło")
    db.commit()
    return {"message": "Hasło zostało zmienione"}

@router.get("", response_model=List[UserOut])
def list_users(db: Session = Depends(get_db), current_user: User = Depends(require_permission("users:read"))):
    return db.query(User).filter(User.tenant_id == current_user.tenant_id).order_by(User.id).all()

@router.get("/{user_id}", response_model=UserOut)
def get_user(user_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("users:read"))):
    user = db.query(User).filter(User.id == user_id, User.tenant_id == current_user.tenant_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

@router.post("", response_model=UserOut)
def create_user(payload: UserCreate, db: Session = Depends(get_db), current_user: User = Depends(require_roles(UserRole.OWNER))):
    PlanService.assert_limit(db, current_user.tenant_id, "users")
    if db.query(User).filter((User.email == payload.email) | (User.username == payload.username)).first():
        raise HTTPException(status_code=400, detail="User exists")
    user = User(
        tenant_id=current_user.tenant_id,
        email=payload.email,
        username=payload.username,
        hashed_password=get_password_hash(payload.password),
        full_name=payload.full_name,
        role=payload.role
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user

@router.put("/{user_id}", response_model=UserOut)
def update_user(user_id: int, payload: UserUpdate, db: Session = Depends(get_db), current_user: User = Depends(require_roles(UserRole.OWNER))):
    user = db.query(User).filter(User.id == user_id, User.tenant_id == current_user.tenant_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if payload.email:
        user.email = payload.email
    if payload.full_name:
        user.full_name = payload.full_name
    if payload.role:
        user.role = payload.role
    if payload.is_active is not None:
        user.is_active = payload.is_active
    db.commit()
    db.refresh(user)
    return user

@router.delete("/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_roles(UserRole.OWNER))):
    user = db.query(User).filter(User.id == user_id, User.tenant_id == current_user.tenant_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Nie możesz usunąć siebie")
    if user.role == UserRole.OWNER:
        owners_count = db.query(User).filter(User.tenant_id == current_user.tenant_id, User.role == UserRole.OWNER, User.is_active == True).count()
        if owners_count <= 1:
            raise HTTPException(status_code=400, detail="Nie można usunąć ostatniego aktywnego właściciela")
    add_audit_log(
        db,
        user_id=current_user.id,
        action="DELETE",
        entity_type="user",
        entity_id=user.id,
        old_values={"email": user.email, "username": user.username, "full_name": user.full_name, "role": user.role, "is_active": user.is_active},
        details=f"Usunięto użytkownika {user.username}",
    )
    db.delete(user)
    db.commit()
    return {"message": "Użytkownik został usunięty"}
