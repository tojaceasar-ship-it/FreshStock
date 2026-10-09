from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from typing import Optional
from app.core.database import get_db
from app.core.security import decode_token
from app.models.user import User
from enum import Enum

security = HTTPBearer()

class UserRole(str, Enum):
    OWNER = "OWNER"
    MANAGER = "MANAGER"
    WAREHOUSE = "WAREHOUSE"
    EMPLOYEE = "EMPLOYEE"
    VIEWER = "VIEWER"

ROLE_PERMISSIONS = {
    UserRole.OWNER: ["*"],
    UserRole.MANAGER: [
        "products:*", "categories:*", "inventory:*", "reports:*", "orders:*",
        "promotions:*", "suppliers:*", "locations:*", "deliveries:*", "counts:*",
        "users:read", "dashboard:read", "alerts:*", "sales:*", "waste:*",
        "stock:read", "stock-movements:read", "integrations:read", "onboarding:read",
    ],
    UserRole.WAREHOUSE: [
        "inventory:*", "deliveries:*", "stock:*", "locations:*", "products:read",
        "dashboard:read", "alerts:read", "counts:*", "orders:read",
        "suppliers:read", "categories:read", "stock-movements:read", "waste:read",
    ],
    UserRole.EMPLOYEE: [
        "products:read", "stock:read", "scan:*", "sales:create", "waste:create",
        "dashboard:read", "alerts:read", "inventory:read", "stock-movements:read",
        "waste:read", "promotions:read", "categories:read",
    ],
    UserRole.VIEWER: ["products:read", "stock:read", "reports:read", "dashboard:read", "sales:read"],
}

def has_permission(user_role: str, required_permission: str) -> bool:
    if user_role == UserRole.OWNER:
        return True
    permissions = ROLE_PERMISSIONS.get(UserRole(user_role), [])
    if "*" in permissions:
        return True
    for perm in permissions:
        if perm == required_permission:
            return True
        if perm.endswith(":*"):
            prefix = perm[:-2]
            if required_permission.startswith(prefix):
                return True
    return False

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)) -> User:
    token = credentials.credentials
    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    user_id = payload.get("sub")
    token_tenant_id = payload.get("tenant_id")
    if not user_id or token_tenant_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
    try:
        user_id = int(user_id)
        token_tenant_id = int(token_tenant_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

    # Bind the session to the signed tenant claim before any authenticated
    # ORM query. The explicit tenant predicate also protects this bootstrap
    # lookup before the global loader criterion is applied.
    db.info["tenant_id"] = token_tenant_id
    user = db.query(User).filter(User.id == user_id, User.tenant_id == token_tenant_id).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")
    return user

def require_roles(*roles):
    def role_checker(current_user: User = Depends(get_current_user)):
        if current_user.role not in [r.value if isinstance(r, Enum) else r for r in roles]:
            # OWNER can access everything
            if current_user.role != UserRole.OWNER.value:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return current_user
    return role_checker

def require_permission(permission: str):
    def perm_checker(current_user: User = Depends(get_current_user)):
        if not has_permission(current_user.role, permission):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Missing permission: {permission}")
        return current_user
    return perm_checker
