#!/bin/bash
export USE_SQLITE=true
export DATABASE_URL=sqlite:///./freshstock.db
export SECRET_KEY=super-secret-key-change-in-production-32chars-min-32
export JWT_ALGORITHM=HS256
export ACCESS_TOKEN_EXPIRE_MINUTES=30
export REFRESH_TOKEN_EXPIRE_DAYS=7
export BACKEND_CORS_ORIGINS=http://localhost:3000,http://localhost:5173
export ENVIRONMENT=development
# Ensure DB exists
if [ ! -f freshstock.db ]; then
  echo "DB not found, seeding..."
  python3 -m app.seed
fi
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
