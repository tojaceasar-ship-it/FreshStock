"""Local development launcher: forces SQLite so the API can run
without a Postgres instance. Never use in production."""
import os

os.environ["USE_SQLITE"] = "true"
os.environ.setdefault("DATABASE_URL", "sqlite:///./freshstock.db")

import uvicorn  # noqa: E402

uvicorn.run("app.main:app", host="127.0.0.1", port=8000, log_level="info")
