# FreshStock Preview Validation Report

## Final decision

**NOT READY FOR PRODUCTION**

Validation timestamp: `2026-10-08T23:39:37+02:00` (Europe/Amsterdam)

The preview deployments exist, but the required real-preview validation cannot be completed safely. Vercel Authentication blocks direct access, no Preview Protection bypass token is available, and the backend project does not expose Preview-scoped database variables. Data isolation and migration state therefore cannot be independently verified.

No production approval request may be prepared from this result.

## Deployment identity

| Component | Preview URL | Deployment ID | Vercel state |
|---|---|---|---|
| Backend | `https://freshstock-d6b58iq9c-czezars-projects.vercel.app` | `dpl_HepeUBveKd9knM5D6wGD12q6XFjF` | Ready |
| Frontend | `https://frontend-hrgcnd3yr-czezars-projects.vercel.app` | `dpl_FfgqeCSQC764M5SGdHitDQYohmnB` | Ready |

Both deployments have target `preview`. A Vercel `Ready` state proves that the deployment build completed; it does not prove application health, database isolation, or functional correctness.

## Database and migration verification

- Preview DB branch/name: **UNKNOWN / NOT VERIFIED**.
- Isolation method: **NOT VERIFIED**.
- `alembic current = 012`: **NOT INDEPENDENTLY VERIFIED**.
- The handoff states that migration `012` was applied on a preview DB, but no safe database access or command output was available to validate that assertion.
- Vercel lists no Preview-scoped `DATABASE_URL` or `DATABASE_URL_ASYNC` for the backend project.
- Vercel lists `DATABASE_URL` and `DATABASE_URL_ASYNC` only in Production scope.
- The backend also lacks Preview-scoped `BACKEND_CORS_ORIGINS`.
- The frontend `VITE_API_URL` is shared across Production, Preview, and Development rather than being visibly isolated to Preview.
- The known committed Neon credentials were not used.
- No database connection or migration command was executed during this validation.

This evidence is insufficient to prove that the backend, frontend, and database form an isolated preview environment. Testing against this deployment could touch an unintended database and is therefore prohibited.

## Vercel Authentication verification

No Vercel Protection bypass secret is present in the execution environment. Unauthenticated direct requests produced:

| Request | Observed result |
|---|---|
| `GET <backend>/health` | HTTP `302` |
| `GET <backend>/ready` | HTTP `302` |
| `GET <backend>/api/monitoring/metrics` | HTTP `302` |
| `GET <frontend>/` | HTTP `302` |

These redirects confirm that direct requests are intercepted by Vercel Authentication. The following required checks could not be performed:

- request with bypass reaches the backend;
- backend application authentication still applies after bypass;
- mutating endpoints without an application token return `401`;
- Playwright can access the protected preview frontend and API.

No bypass token was fabricated, extracted, or replaced with a production secret.

## Eleven-point preview test plan

Local tests and local builds are not counted as preview PASS results.

| # | Test | Result | Evidence / blocker |
|---:|---|---|---|
| 1 | Double-submit E2E | **BLOCKED** | Clean tenant/database isolation is not proven; frontend and API are blocked by Vercel Authentication. |
| 2 | Scanner keyboard E2E | **BLOCKED** | Playwright cannot access the protected frontend; preview API/data context is unverified. |
| 3 | Orders cycle E2E | **BLOCKED** | Playwright cannot access preview and isolated order/product data is not available. |
| 4 | Orders suggestions 200 OK | **BLOCKED** | Direct API request is intercepted with HTTP `302`; no bypass or safe application token context. |
| 5 | Generic CSV smoke | **BLOCKED** | UI/API access is blocked and stock isolation cannot be proven. |
| 6 | Idempotency replay | **BLOCKED** | Mutating API test cannot safely run without bypass and isolated DB. No replay header was observed. |
| 7 | Idempotency key reused with different body | **BLOCKED** | Mutating API test cannot safely run without bypass and isolated DB. |
| 8 | Keyless double-submit | **BLOCKED** | Mutating API test cannot safely run without bypass and isolated DB. |
| 9 | RBAC monitoring | **BLOCKED** | Monitoring request is intercepted with HTTP `302`; role-specific application responses cannot be observed. |
| 10 | Mutating endpoints auth | **BLOCKED** | Vercel bypass is absent, so Vercel auth cannot be separated from backend auth. |
| 11 | Full orders cycle | **BLOCKED** | No safe access to a confirmed isolated Preview DB and no protected-preview bypass. |

Result: **0 PASS / 0 FAIL / 11 BLOCKED**.

## Evidence inventory

Available evidence:

- Vercel deployment inspection output with preview targets, deployment IDs, URLs, states, and creation times.
- Vercel environment-variable listing showing variable names and scopes without values.
- HTTP status checks showing `302` for backend health/readiness/monitoring and frontend root.
- Local backend result from the handoff: `2 passed` (not counted as Preview).
- Local frontend result from the handoff: build successful (not counted as Preview).

Unavailable evidence because validation is blocked:

- screenshots of functional preview flows;
- successful preview API response logs;
- `X-Idempotent-Replay` response headers;
- `409 IDEMPOTENCY_KEY_REUSED` and `409 DOUBLE_SUBMIT_DETECTED` bodies;
- preview DB identity and `alembic current` output;
- isolated tenant ID/test context;
- stock deltas, delivery history, and report outputs.

## Status matrix

| Component | Local | Preview | Production |
|---|---|---|---|
| Backend package | Commit `4572b4b`; 2 tests passed | Deployed, not validated | Unchanged per handoff |
| Frontend package | Commit `3679e50`; build successful | Deployed, not validated | Unchanged per handoff |
| Migration `012` | Present | Claimed applied, not independently verified | Not applied per handoff |
| Data isolation | Local test context only | Not proven | Not touched |
| Idempotency/double-submit | Locally implemented | Not tested | Not approved |
| Monitoring/RBAC | Locally implemented | Not tested | Not approved |
| Orders/CSV/scanner flows | Local artifacts exist | Not tested | Not approved |

## FAIL list

No functional test reached the application, so no functional result is labelled FAIL. This does not imply success.

## BLOCKED list

1. No Preview-scoped `DATABASE_URL` is visible in Vercel.
2. No Preview-scoped `DATABASE_URL_ASYNC` is visible in Vercel.
3. No Preview-scoped `BACKEND_CORS_ORIGINS` is visible in Vercel.
4. Preview DB branch/name and isolation are unknown.
5. The database reportedly contains production-derived data; clean tenant isolation is not demonstrated.
6. No Vercel Protection bypass token or equivalent safe mechanism is available.
7. Direct backend and frontend requests are intercepted with HTTP `302`.
8. Frontend `VITE_API_URL` is not independently scoped to Preview.
9. No safe preview application credentials/test users were available for role-based tests.

## Risks

- Running mutating tests could affect an unintended or production-derived database.
- A shared frontend API URL could route Preview traffic to a non-preview backend.
- Vercel Authentication can mask backend authentication failures and false-positive health checks.
- The previously committed Neon password remains a security risk until rotation is confirmed.
- A deployment marked `Ready` may still fail at runtime because required Preview variables are absent.

## Required remediation before rerun

1. Rotate the committed Neon credentials and confirm revocation of the old password.
2. Create or reset an isolated Preview DB/branch with Preview-only credentials.
3. Configure Preview-scoped `DATABASE_URL`, `DATABASE_URL_ASYNC`, and `BACKEND_CORS_ORIGINS`.
4. Configure a Preview-only frontend `VITE_API_URL` that points to the preview backend.
5. Provide a Preview-only Vercel Protection bypass mechanism through a secure environment variable, not chat or source control.
6. Verify the database identity before running any migration.
7. Run `alembic upgrade head` only against the verified Preview DB and capture `alembic current` showing `012`.
8. Create an isolated test tenant and preview-only test users/tokens for required roles.
9. Redeploy both Preview projects after environment changes.
10. Rerun all 11 tests and collect status codes, response headers, logs, and screenshots.

## Decision

The preview has not passed the required test plan. All eleven checks remain blocked by missing isolation evidence and protected-preview access.

**NOT READY FOR PRODUCTION**
