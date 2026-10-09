# Decimal quantities migration runbook

Status: prepared only. Do not run against production without separate approval.

## Pre-flight and backup

1. Put write traffic into maintenance mode or stop API writers.
2. Record the current deployment and Alembic revision (`010`).
3. Create a provider snapshot and a logical PostgreSQL backup:
   `pg_dump --format=custom --no-owner --file=freshstock-pre-011.dump "$DATABASE_URL"`.
4. Verify the dump with `pg_restore --list freshstock-pre-011.dump` and store its checksum.
5. Restore the dump to an isolated database and run application smoke tests there.

## Staging verification

Run `alembic upgrade 011` only on the isolated staging database. Check column
types in `information_schema.columns`, then execute the 2.75 kg delivery,
0.35 kg sale and 0.10 kg waste scenario. Expected balance: 2.300 kg.

## Production rollout (requires explicit approval)

Apply `alembic upgrade 011`, deploy the matching backend and frontend, then run
read-only checks and a controlled decimal transaction. Keep the previous
deployment available until verification is complete.

## Rollback

Preferred rollback is to stop writers, restore the verified snapshot/dump and
redeploy the previous backend/frontend. `alembic downgrade 010` exists for local
testing only: it rounds fractional values and must not be used as the production
rollback strategy.
