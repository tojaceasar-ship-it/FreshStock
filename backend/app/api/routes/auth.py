from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import verify_password, get_password_hash, create_access_token, create_refresh_token, decode_token
from app.models.onboarding import OnboardingProgress, StoreSettings
from app.models.tenant import Tenant
from app.models.user import User, UserRole
from app.models.subscription import Subscription, SubscriptionEvent, TenantStore
from app.schemas.auth import BootstrapOwnerRequest, LoginRequest, StoreRegistrationRequest, TokenResponse, RefreshRequest, UserResponse
from app.core.deps import get_current_user, require_roles
from app.core.config import settings
from datetime import timedelta

router = APIRouter()


def _tokens_for(user: User) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(data={"sub": str(user.id), "role": user.role.value, "tenant_id": user.tenant_id}),
        refresh_token=create_refresh_token(data={"sub": str(user.id), "tenant_id": user.tenant_id}),
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.get("/bootstrap-status")
def bootstrap_status(db: Session = Depends(get_db)):
    return {"required": db.query(User.id).first() is None}


@router.post("/bootstrap", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def bootstrap_owner(request: BootstrapOwnerRequest, db: Session = Depends(get_db)):
    # Serialize the one-time bootstrap on PostgreSQL to prevent two concurrent
    # requests from creating separate owners while the table is empty.
    if db.bind and db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(46737241)"))
    if db.query(User.id).first() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Pierwszy właściciel został już utworzony")

    tenant = Tenant(name="FreshStock")
    db.add(tenant)
    db.flush()
    owner = User(
        tenant_id=tenant.id,
        email=request.email,
        username=request.username,
        hashed_password=get_password_hash(request.password),
        full_name=request.full_name,
        role=UserRole.OWNER,
        is_active=True,
    )
    db.add_all([owner, Subscription(tenant_id=tenant.id, plan="PRO", status="ACTIVE"), TenantStore(tenant_id=tenant.id, name="FreshStock", code="MAIN")])
    try:
        db.commit()
        db.refresh(owner)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Nie można utworzyć właściciela z podanymi danymi")
    return _tokens_for(owner)


@router.post("/register-store", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register_store(request: StoreRegistrationRequest, db: Session = Depends(get_db)):
    """Create an independent tenant and its first OWNER in one transaction."""
    if db.bind and db.bind.dialect.name == "postgresql":
        # Keep the uniqueness check and tenant creation serialized across Vercel instances.
        db.execute(text("SELECT pg_advisory_xact_lock(46737242)"))

    email = str(request.email).strip().lower()
    username = request.username.strip().lower()
    if db.query(User.id).filter((User.email == email) | (User.username == username)).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Konto z tym adresem e-mail lub loginem już istnieje")

    tenant = Tenant(name=request.store_name)
    db.add(tenant)
    db.flush()
    owner = User(
        tenant_id=tenant.id,
        email=email,
        username=username,
        hashed_password=get_password_hash(request.password),
        full_name=request.full_name,
        role=UserRole.OWNER,
        is_active=True,
    )
    db.add_all([
        owner,
        Subscription(tenant_id=tenant.id, plan="PRO", status="TRIAL", trial_ends_at=__import__('datetime').datetime.now(__import__('datetime').timezone.utc) + timedelta(days=14)),
        SubscriptionEvent(tenant_id=tenant.id, old_plan=None, new_plan="PRO", event_type="TRIAL_STARTED"),
        TenantStore(tenant_id=tenant.id, name=request.store_name, code="MAIN"),
        StoreSettings(
            tenant_id=tenant.id,
            store_name=request.store_name,
            language=request.language,
            country="NL" if request.language == "nl" else "PL",
            currency="EUR" if request.language == "nl" else "PLN",
            timezone="Europe/Amsterdam" if request.language == "nl" else "Europe/Warsaw",
            expiry_rules=[],
            markdown_rules=[],
            dashboard_layout=[],
        ),
        OnboardingProgress(
            tenant_id=tenant.id,
            current_step=1,
            completed_steps=[],
            step_data={},
            status="NOT_STARTED",
        ),
    ])
    try:
        db.commit()
        db.refresh(owner)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Nie można utworzyć sklepu z podanymi danymi")
    return _tokens_for(owner)

@router.post("/login", response_model=TokenResponse)
def login(request: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(
        (User.username == request.username) | (User.email == request.username)
    ).first()
    if not user or not verify_password(request.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Nieprawidłowe dane logowania")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Konto nieaktywne")
    
    return _tokens_for(user)

@router.post("/refresh", response_model=TokenResponse)
def refresh(request: RefreshRequest, db: Session = Depends(get_db)):
    payload = decode_token(request.refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
    user_id = payload.get("sub")
    token_tenant_id = payload.get("tenant_id")
    if not user_id or token_tenant_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token payload")
    try:
        user_id = int(user_id)
        token_tenant_id = int(token_tenant_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token payload")
    db.info["tenant_id"] = token_tenant_id
    user = db.query(User).filter(User.id == user_id, User.tenant_id == token_tenant_id).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    
    access_token = create_access_token(data={"sub": str(user.id), "role": user.role.value, "tenant_id": user.tenant_id})
    refresh_token = create_refresh_token(data={"sub": str(user.id), "tenant_id": user.tenant_id})
    
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )

@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user

@router.post("/register", response_model=UserResponse)
def register(data: dict, db: Session = Depends(get_db), current_user: User = Depends(require_roles(UserRole.OWNER))):
    
    from app.schemas.user import UserCreate
    try:
        user_data = UserCreate(**data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    if db.query(User).filter((User.email == user_data.email) | (User.username == user_data.username)).first():
        raise HTTPException(status_code=400, detail="Użytkownik już istnieje")
    
    new_user = User(
        tenant_id=current_user.tenant_id,
        email=user_data.email,
        username=user_data.username,
        hashed_password=get_password_hash(user_data.password),
        full_name=user_data.full_name,
        role=user_data.role
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user
