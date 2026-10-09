# FreshStock Security Incident and Preview Handoff

**SECURITY ISSUE: DATABASE CREDENTIALS COMMITTED TO REPOSITORY**

**PREVIEW BLOCKED: ISOLATED DATABASE_URL REQUIRED**

**SECURITY ACTION REQUIRED: ROTATE COMMITTED NEON CREDENTIALS**

Prepared: 2026-10-08

## 1. Incident scope

The following Git-tracked files contain a hard-coded Neon PostgreSQL connection string:

- `create_tables_neon.py`
- `run_seed_neon.py`

Both paths occur in Git history in commit `e3a3f9c` (`chore: recover backend source from Vercel deployment`). Treat the credentials as compromised even if the repository was believed to be private.

The report intentionally does not reproduce any credential value, username, password, hostname, or complete connection string.

Other PostgreSQL URLs found in `app/core/config.py`, `alembic/env.py`, and `alembic.ini` are local/default example values rather than the identified Neon credential. They should still be reviewed and replaced with non-secret, clearly fictional examples where practical.

## 2. Exposed secret types

The two affected files expose:

- a complete `DATABASE_URL`-style PostgreSQL connection string;
- the Neon database endpoint/hostname;
- the database username;
- the database password embedded in the URI;
- connection parameters included in the URI.

No separate Neon API token or bearer token was detected in the two affected files during this review. This does not reduce the severity of the exposed database password.

## 3. Required immediate remediation

1. Revoke or rotate the committed Neon password immediately. Do not wait for code cleanup or a new deployment.
2. Generate new, production-only database credentials. Do not reuse the exposed password.
3. Create an isolated Neon preview branch or a separate preview database and generate separate preview-only credentials.
4. Remove the hard-coded connection strings from both affected files. Read configuration exclusively from environment variables and fail safely when required configuration is absent.
5. Store production and preview configuration in Vercel Environment Variables with the correct environment scope.
6. Add `.env`, `.env.*`, and other local secret files to `.gitignore`, while optionally allowing a sanitized `.env.example`.
7. If the affected commit was ever pushed or shared, clean the Git history with `git filter-repo` or BFG and coordinate the required force-push. Rotation remains mandatory because history rewriting does not revoke a leaked credential.
8. Add automated secret scanning to CI and enable repository-host secret scanning/push protection where available. Recommended tools include Gitleaks or TruffleHog.
9. Review Neon connection and audit logs for unexpected access, queries, exports, schema changes, or new roles since the credential was first committed.
10. Check forks, CI logs, build artifacts, deployment bundles, caches, and backups for copies of the exposed string.

## 4. Preview environment variables

Backend Vercel project, **Preview** scope:

- `DATABASE_URL` — synchronous connection URL for the isolated preview database;
- `DATABASE_URL_ASYNC` — async-driver connection URL for the same isolated preview database;
- `BACKEND_CORS_ORIGINS` — exact preview frontend origin plus explicitly approved local development origins.

Frontend Vercel project, **Preview** scope:

- `VITE_API_URL` — HTTPS URL of the deployed preview backend.

Already configured on the backend in Preview scope: an independent `SECRET_KEY`, JWT settings, token expiry settings, `ENVIRONMENT=preview`, rate limits, and `DOUBLE_SUBMIT_GUARD_WINDOW=2`.

## 5. Instructions for the Neon operator

1. Rotate the exposed production database password and update only the production-scoped secret consumers with the newly generated production credential.
2. In Neon, create a preview branch from production or create a separate preview database. Prefer a branch with an explicit name such as `freshstock-preview` and an appropriate lifecycle/expiry policy.
3. Create a dedicated preview database role and password. Grant only the permissions required by the application and Alembic migrations.
4. Never provide or reuse the production database credential for Preview.
5. Obtain two URLs for the same isolated preview database:
   - a synchronous URL suitable for `DATABASE_URL`;
   - an asyncpg-compatible URL suitable for `DATABASE_URL_ASYNC`.
6. Add both values directly to the `freshstock-api` Vercel project with **Preview** scope. Do not paste them into tickets, chat, source files, command history, or this report.
7. Confirm the database/branch name and that both Vercel variables are present without disclosing their values.
8. After the backend preview URL is known, set `BACKEND_CORS_ORIGINS` to the exact preview frontend origin and set the frontend Preview `VITE_API_URL` to the backend preview URL.

## 6. Deployment gate

Do not run Alembic migration `012` until the operator has independently verified that `DATABASE_URL` resolves to the isolated preview database. Never run migration `012` against production as part of this preview procedure.

Do not deploy the preview backend against production, do not use the committed credentials, and do not start preview tests without the isolated preview database.

Deployment may resume only after all of the following are confirmed:

- the exposed Neon credential has been rotated;
- isolated preview credentials exist;
- Preview-scoped `DATABASE_URL` and `DATABASE_URL_ASYNC` are configured;
- the target database identity has been independently verified;
- CORS and frontend API variables reference only preview deployments.

## Final status

**PREVIEW BLOCKED: ISOLATED DATABASE_URL REQUIRED**

**SECURITY ACTION REQUIRED: ROTATE COMMITTED NEON CREDENTIALS**
