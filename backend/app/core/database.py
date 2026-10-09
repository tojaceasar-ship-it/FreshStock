from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker, Session, with_loader_criteria
from sqlalchemy import event
from app.core.config import settings
import os
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

def normalize_database_url(value: str) -> tuple[str, dict]:
    if value.startswith("postgres://"):
        value = "postgresql://" + value[len("postgres://"):]
    if value.startswith("postgresql://"):
        value = "postgresql+pg8000://" + value[len("postgresql://"):]
    elif value.startswith("postgresql+psycopg2://"):
        value = "postgresql+pg8000://" + value[len("postgresql+psycopg2://"):]
    connect_args = {}
    if value.startswith("postgresql+pg8000://"):
        parts = urlsplit(value)
        query = [(key, item) for key, item in parse_qsl(parts.query) if key not in {"sslmode", "channel_binding"}]
        value = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
        connect_args["ssl_context"] = True
    return value, connect_args


def select_database_url(configured_url: str, use_sqlite: bool) -> str:
    """Honor an explicit SQLite target while retaining the local fallback.

    Test and maintenance commands use uniquely named SQLite files for data
    isolation. Replacing those URLs with ``freshstock.db`` risks mutating the
    normal local database.
    """
    if use_sqlite and not configured_url.startswith("sqlite"):
        return "sqlite:///./freshstock.db"
    return configured_url


raw_database_url = os.getenv("DATABASE_URL", settings.DATABASE_URL)
raw_database_url = select_database_url(raw_database_url, os.getenv("USE_SQLITE", "false").lower() == "true")
database_url, database_connect_args = normalize_database_url(raw_database_url)

if database_url.startswith("sqlite"):
    engine = create_engine(database_url, connect_args={"check_same_thread": False})
elif database_url.startswith("postgresql+pg8000"):
    engine = create_engine(database_url, pool_pre_ping=True, pool_recycle=300, connect_args=database_connect_args)
else:
    engine = create_engine(database_url, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


@event.listens_for(Session, "do_orm_execute")
def _tenant_filter(execute_state):
    tenant_id = execute_state.session.info.get("tenant_id")
    if tenant_id is None or execute_state.execution_options.get("skip_tenant_scope"):
        return
    statement = execute_state.statement
    for mapper in list(Base.registry.mappers):
        model = mapper.class_
        if hasattr(model, "tenant_id"):
            statement = statement.options(
                with_loader_criteria(model, lambda entity: entity.tenant_id == tenant_id, include_aliases=True)
            )
    execute_state.statement = statement


@event.listens_for(Session, "before_flush")
def _tenant_write_guard(session, flush_context, instances):
    tenant_id = session.info.get("tenant_id")
    if tenant_id is None:
        return
    for obj in session.new:
        if hasattr(obj, "tenant_id"):
            assigned = getattr(obj, "tenant_id", None)
            if assigned is None:
                setattr(obj, "tenant_id", tenant_id)
            elif assigned != tenant_id:
                raise ValueError("Cross-tenant write blocked")
    for obj in session.dirty.union(session.deleted):
        if hasattr(obj, "tenant_id") and getattr(obj, "tenant_id", tenant_id) != tenant_id:
            raise ValueError("Cross-tenant mutation blocked")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
