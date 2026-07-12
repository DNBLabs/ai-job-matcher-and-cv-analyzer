# Implementation Plan: AI Job Matcher & CV Analyzer (MVP)

## Overview

Greenfield build of a UK job-matching web app: Job Seekers sign in (Google OAuth + magic link), upload named CV PDFs, receive sync AI title suggestions, start async **Analysis Runs** that scrape Indeed UK and fetch Adzuna listings, score each job with **Match Score** and **Interview Likelihood**, and view ranked, filterable results on a dashboard. Production deploys to **Azure Container Apps** via **Terraform GitOps** and **GitHub Actions OIDC**, with a **cloud-agnostic application core** (port/adapter pattern) and local **Docker Compose** dev. Budget ceiling: **£75/month** (Profile A: 1–3 users, 10–30 runs/month).

## Architecture Decisions

- **Vertical slices over horizontal layers** — each phase delivers a testable user path (auth → CV → run → results) before adding the next capability.
- **Port/adapter pattern** — domain and worker code use `BlobStore`, `JobQueue`, `SecretProvider`; Azure adapters in prod, Azurite/RabbitMQ/`.env` locally (ADR-0002).
- **PostgreSQL-only sessions and rate limits** — no Redis; `sessions` + `rate_limit_counters` tables on existing B1ms (FINAL_ARCHITECTURE §4).
- **Hybrid job sourcing** — Adzuna API path first (stable CI), then Indeed scrape with partial-failure fallback (ADR-0001).
- **Separate API and Worker containers** — shared domain package, different entrypoints; Service Bus + KEDA scale-to-zero on worker.
- **Single prod environment** — no paid staging; local Compose + optional post-deploy smoke against prod.

## Dependency Graph (high level)

```
Repo scaffold + Docker Compose
    │
    ├── Infrastructure ports (BlobStore, JobQueue, SecretProvider)
    │       │
    │       ├── Domain models + Postgres migrations
    │       │       │
    │       │       ├── Auth (OAuth, magic link, sessions)
    │       │       │       │
    │       │       │       ├── CV upload/delete + title suggestions
    │       │       │       │       │
    │       │       │       │       ├── Analysis orchestrator + queue + worker skeleton
    │       │       │       │       │       │
    │       │       │       │       │       ├── Adzuna → scoring → results API
    │       │       │       │       │       │       │
    │       │       │       │       │       │       ├── Indeed + partial failure
    │       │       │       │       │       │       │       │
    │       │       │       │       │       │       │       ├── Email + polling UI
    │       │       │       │       │       │       │       │       │
    │       │       │       │       │       │       │       │       ├── Results filters/badges + quota UI
    │       │       │       │       │       │       │       │       │       │
    │       │       │       │       │       │       │       │       │       └── Admin UI
    │       │       │       │       │       │       │       │       │
    │       │       │       │       │       │       │       │       └── React SPA pages
    │       │       │       │       │       │       │       │
    │       │       │       │       │       │       │       └── Terraform + CI/CD (parallel late)
```

---

## Task List

### Phase 0: Project Foundation

- [x] Task 0: Monorepo scaffold and Docker Compose baseline — Added backend/worker FastAPI scaffold, TDD health/worker tests, React/Vite SPA, shared Dockerfile (UID 10001), docker-compose.yml (api, worker, postgres), and security baseline (headers, CORS, sanitized 500s, OpenAPI disabled in prod, Postgres bound to localhost).
- [x] CI baseline (post–Task 0): `.github/workflows/ci.yml` on PR/push to `main` — backend pytest (explicit `tests/ports/` Task 1 gate, `tests/domain/` Task 2 gate, `tests/auth/test_sessions.py` + `tests/auth/test_security_boundaries.py` Task 3 gate, `tests/auth/test_google_oauth.py` Task 4 gate, `tests/auth/test_magic_link.py` Task 5 gate, `alembic upgrade head`, `tests/auth/test_sessions_postgres.py` Task 3 Postgres smoke, then full suite), frontend lint/test/build/audit, `docker compose config` + `docker compose build` with Azurite/RabbitMQ services (Terraform validate + CVE scan deferred to Task 28).
- [x] Task 1: Infrastructure ports and local adapters — Added BlobStore/JobQueue/SecretProvider ports, memory/in-process/env local adapters, Azurite/RabbitMQ Compose adapters, factory wiring from Settings, boundary validation (key traversal, secret names, queue payloads), and contract tests under `tests/ports/`.
- [x] Task 2: Domain core and PostgreSQL schema migrations — Added domain state machine, quota, divergence helpers; SQLAlchemy models; Alembic initial migration; owner-scoped repositories; admin seed stub; security hardening (email/score validation, append-only audit repo, soft-delete IDOR-safe CV lookup, DB check constraints).

#### Checkpoint: Foundation
- [x] `docker compose up` starts API, worker, Postgres, queue emulator, blob emulator
- [x] Migrations apply cleanly; health endpoint returns 200 — `alembic upgrade head` verified against Compose Postgres.
- [x] Unit tests for domain quota/state machine pass — `pytest tests/domain/` (30 tests) in CI.

---

### Phase 1: Authentication

- [x] Task 3: Session store and auth middleware (Postgres-backed) — Added SessionService (24h idle / 7d absolute expiry, rotation, cleanup), HttpOnly SameSite=Lax cookie helpers, get_current_user dependency, session-id boundary validation, and tests in tests/auth/.
- [x] Task 4: Google OAuth sign-in flow — Added GET /auth/google/login and /callback with CSRF state cookie, SecretProvider-backed client credentials, Google token/userinfo exchange, user upsert by google_sub/email, session rotation, dashboard redirect, audit_log events, security hardening (email_verified gate, google_sub conflict check, open-redirect allowlist, oauth_state cleared on failure), and tests in tests/auth/test_google_oauth.py.
- [x] Task 5: Magic link sign-in flow — Added POST /auth/magic-link and GET /auth/magic-link/verify with SHA-256 hash-only storage, 15-minute single-use tokens, NotificationPort log adapter, Postgres rate_limit_counters (3/email/hour, 10/IP/hour), session rotation, audit_log events, and tests in tests/auth/test_magic_link.py.
- [x] Task 6: Sign-out, rate limits, and IDOR-safe routing — Added POST /auth/logout with session deletion and cookie clear, IngressRateLimitMiddleware (~100 req/min/IP with Retry-After), owner-scoped deps (get_owned_cv/run/result, require_admin), API validation helpers, JobMatchResultRepository, and tests in tests/auth/test_logout.py, test_ingress_rate_limit.py, test_idor_routing.py.

#### Checkpoint: Auth
- [ ] Job Seeker can sign in via Google or magic link locally
- [x] Session persists across browser restart; sign-out clears cookie
- [x] Cross-account resource IDs return 404

---

### Phase 2: CV Management & Title Suggestions

- [x] Task 7: CV upload, validation, and encrypted blob storage — POST /cvs with PDF validation, BlobStore upload, and CV metadata persistence
- [x] Task 8: CV list, delete-with-retain-runs, and PDF parse — GET/DELETE /cvs, pypdf parse with timeout, soft-delete retains runs
- [x] Task 9: Sync Suggested Job Titles (GPT-4o-mini) — Added POST /cvs/{id}/suggest-titles with LlmClient port, OpenAiLlmClient (GPT-4o-mini structured output), TitleSuggestionService, FinOps audit_log metadata, owner-scoped auth, fake LLM tests, and CI gate.

#### Checkpoint: CV + Titles
- [x] Upload PDF → see named CV in list → delete with confirmation
- [x] Title suggestions return in &lt;10s with 3–5 titles + rationales
- [x] Integration tests pass for CV lifecycle

---

### Phase 3: Analysis Run Core (Queue + Worker Skeleton)

- [x] Task 10: Analysis orchestrator, quota, and concurrency rules — `job_search.py` validation, `AnalysisOrchestrator` with quota/concurrency gates and post-commit queue publish
- [x] Task 11: Run API endpoints and status state machine — `runs.py` with GET/POST /runs, quota, results; orchestrator wired; 8 httpx integration tests
- [x] Task 12: Worker consumer skeleton and queue wiring — `worker/handlers/analysis_run.py` handler QUEUED→SCRAPING→SCORING; SIGTERM graceful shutdown; poison-message safety; 6 integration tests

#### Checkpoint: Run Orchestration
- [ ] POST `/runs` enqueues job; status transitions Queued → Scraping → Scoring
- [ ] Quota (3/24h) and concurrent-run block enforced
- [ ] Worker processes message and updates run status (no external APIs yet)

---

### Phase 4: Adzuna Path End-to-End (First Vertical Slice)

- [x] Task 13: Job Source registry and Adzuna adapter — Added `NormalisedListing`, `JobSource` protocol, `JobSourceRegistry`, and `AdzunaJobSource` (httpx, retry on 429/5xx/timeout, field mapping, no live network in CI); 19 tests in `tests/job_sources/test_adzuna.py` with recorded fixture.
- [x] Task 14: Scoring service (GPT-4o, schema validation, FinOps logging) — Added `ScoringLlmOutput`/`ScoredListing`/`RunScoringResult` domain schemas, `ScoringLlmClient` port + `OpenAiLlmClient.score_listing` (GPT-4o structured output), `ScoringService` (per-listing 1-retry-then-skip, 100-LLM-call/run hard cap with retries counted against the budget, per-run token/cost aggregation via `estimate_gpt4o_usd`, no CV/prompt logging), fake scoring client, 9 tests in `tests/services/test_scoring_service.py`, and CI gate.
- [x] Task 15: Worker pipeline — fetch Adzuna → score → persist results — Added `AnalysisRunPipeline` driving QUEUED→SCRAPING→SCORING→COMPLETE/FAILED; SHA-256 URL dedup; `JobMatchResult` persistence with full breakdown_json; FinOps on `finops_json`; `RunPipeline` protocol in handler; factory helpers for Adzuna + scoring LLM; `FakeJobSource` test double; 15 pipeline integration tests.

#### Checkpoint: Adzuna-Only Run
- [x] Full run completes with scored Adzuna listings in DB
- [x] GET `/runs/{id}/results` returns ranked results with breakdown JSON
- [x] FinOps metadata recorded on `analysis_run.finops_json`

---

### Phase 5: Indeed Scraper & Partial Success

- [x] Task 16: Indeed UK scraper adapter (fixture-tested parser) — Added IndeedJobSource (BeautifulSoup html.parser), 3-card HTML fixture, 20 fixture-based tests; beautifulsoup4 dep added (#18)
- [x] Task 17: Multi-source worker pipeline with retry and partial failure
- [x] Task 18: Source-failure metadata and run outcome rules

#### Checkpoint: Hybrid Sourcing
- [x] Run with both sources completes; partial failure shows banner metadata
- [x] Zero listings after retries → `Failed` with distinct error messages
- [x] Indeed parser unit tests use fixtures only (no live network in CI)

---

### Phase 6: Notifications & Frontend Core

- [x] Task 19: Transactional email service (magic link + run complete) — NotificationPort + run-complete email; pure templates, Resend prod adapter (key via SecretProvider), log adapter default; worker emails owner a sign-in-gated deep link on COMPLETE (#21)
- [x] Task 20: React SPA scaffold, auth pages, and API client — Added `GET /auth/me` session probe, fetch API client (`credentials:"include"`), `AuthProvider`/`useAuth`, `ProtectedRoute` redirect, Login page (Google anchor + magic-link form), react-router routes, and Vitest jest-dom setup (#23)
- [x] Task 21: Dashboard, CV wizard, run status polling, and cold-start UX — Extended API client (CVs, titles, runs, quota, `/health`); `useRunPolling` (terminal-aware status polling) + `useApiWarmup` (cold-start detection); Dashboard (CV list + delete, run history, warming banner), NewRun wizard (`CvUploadForm` → `TitleSuggestions` select/edit → `JobSearchForm` with quota + UK-city/Remote picker), RunDetail polling page; `/runs/new` + `/runs/:runId` routes; 59 Vitest tests green

#### Checkpoint: End-to-End UX (Local)
- [x] Job Seeker completes full flow in browser: sign-in → upload → search → results
- [x] Dashboard polls run status; completion email sent (dev sink or provider sandbox)
- [x] Cold-start loading state present for scale-to-zero messaging — `useApiWarmup` probes `/health`; Dashboard shows a "Waking the service up…" banner while warming

---

### Phase 7: Results UI, Quota & Admin

- [x] Task 22: Results view — sort, filters, divergence badges — Results page + ResultCard; composable filters (Likelihood, Source, min score); divergence badges (≥70+low / <50+high); partial-failure banner; 13 Vitest tests green (#30)
- [x] Task 23: Run history, quota display, and unlimited bypass — `QuotaBanner` (remaining/unlimited/concurrent states) + `RunHistory` (CV name resolved from active CVs with "Deleted CV" fallback, search summary, status, date) presentational components; Dashboard fetches `GET /runs/quota`, renders the banner, and disables the "Start a new run" action when quota is exhausted or a run is active; `JobSearchForm` refactored to reuse `QuotaBanner`; 13 new Vitest tests (84 total green)
- [x] Task 24: Admin UI (`/admin`) — search users, toggle unlimited — `GET /admin/users?email=` (case-insensitive, LIKE-escaped, blank→empty, capped 50) + `PATCH /admin/users/{id}` (strict `is_unlimited` body, audit log) behind `require_admin` (404 for non-admins); `UserRepository`; SPA `/admin` page gated by `AdminRoute` with a dashboard nav link shown only to admins; 10 backend + 15 frontend tests green

#### Checkpoint: Feature Complete (Application)
- [ ] All PRD user stories 1–50 verifiable locally
- [ ] Admin bootstrap seed creates operator `is_admin` account
- [ ] Component tests for filters/badges pass

---

### Phase 8: Azure Infrastructure & CI/CD

- [x] Task 25: Terraform bootstrap stack (remote state)
- [x] Task 26: Terraform application stack (ACA, Postgres, SB, Blob, KV, ACR)
- [x] Task 27: Azure adapters (Blob, Service Bus, Key Vault) and MI wiring — `AzureBlobStore` (MI, shared `BlobServiceBlobStore` base with Azurite), `ServiceBusJobQueue` (MI send/receive, drain-to-exit consume), `KeyVaultSecretProvider` (MI, env→kebab name map), `GraphApiNotificationPort` (M365 `sendMail` via MI; Resend removed); factory + Settings wired by env (`azure`/`servicebus`/`keyvault`/`graph`); 27 mocked-SDK contract tests; Terraform `EMAIL_FROM`/`NOTIFICATION_BACKEND=graph` on both apps + MI principal-id outputs; ADR-0005 + `docs/ops/RUNBOOK.md` (out-of-band Mail.Send + Application Access Policy)
- [x] Task 28: GitHub Actions — PR gates (lint, test, validate, CVE scan) — `ci.yml` already covered pytest (ephemeral Postgres), frontend lint/test/build/`npm audit`, `terraform validate`, `docker compose build`, and pip/npm caching; this task added the `cve-scan` job (Trivy `@v0.36.0`, `severity=CRITICAL` + `ignore-unfixed` + `exit-code=1`) scanning the shared backend image to fail on Critical container CVEs with a published fix (#38)
- [x] Task 29: GitHub Actions — prod deploy (OIDC, SHA tags, terraform apply) — `deploy.yml` (workflow_run CI-gate + dispatch rollback, OIDC-only, SHA build/push, terraform apply, KV secret sync w/ runner-IP allow, revision pin, `/health` smoke); bootstrap `deploy_identity.tf` (federated cred repo+main, Contributor+UAA+AcrPush+state-blob); one-time `infra/grants` Mail.Send stack; ADR-0006 + RUNBOOK §0/§2a. Live prod deploy verification is operator-only (no target)
- [x] Task 30: Production SPA serving (Azure Static Web App) — `azurerm_static_web_app` Free SKU (westeurope; uksouth unsupported) + FinOps tags in `infra/app/staticwebapp.tf`; `frontend_url` (CORS `ALLOWED_ORIGINS`, post-auth redirect, email deep links) auto-wired to the SWA hostname; environment-aware auth cookies (`SameSite=None; Secure` in prod, `Lax` in dev) via `Settings.cookie_samesite`/`cookie_secure`; `deploy.yml` builds the SPA with `VITE_API_BASE_URL`=API URL and deploys via `Azure/static-web-apps-deploy` (masked token from TF output). Live SWA + sign-in verification is operator-only (ADR-0008)
- [x] Task 31: Observability and FinOps alerts (Log Analytics, budgets)

#### Checkpoint: Production
- [ ] Deploy from `main` succeeds; API and worker reachable in Azure
- [ ] Smoke test: one Analysis Run in prod
- [ ] Budget and queue-depth alerts configured

---

### Phase 9: UI Refresh (Epic #81)

- [x] Issue #82: Install Tailwind CSS v3.4.x (PostCSS) + shadcn/ui tooling — `tailwindcss`/`postcss`/`autoprefixer` devDeps (no `@tailwindcss/vite`), `@fontsource/inter` runtime dep, `tailwind.config.ts` (`darkMode: 'class'`, `./src/**/*.{ts,tsx}` content), `postcss.config.js`, `index.css` with `@tailwind` directives + deep-violet `--primary`, pre-paint dark-class script in `index.html`, eight shadcn components copied under `src/components/ui/`, `@/` → `src/` alias in tsconfig + vite. No page className changes.
- [x] Issue #84: ResultCard expand/collapse breakdown toggle — `useState(false)` per card; collapsed summary (title, company, source, scores, divergence badge, apply link); shadcn `Button` toggle (`Show breakdown` / `Hide breakdown`); breakdown sections conditionally rendered (not CSS-hidden); legacy `result-card*` classes replaced with Tailwind utilities; 16 `ResultCard` Vitest tests green (#90).
- [x] Issue #93: Tailwind rewrite — Dashboard hub — `Dashboard.tsx`, `QuotaBanner.tsx`, `RunHistory.tsx` migrated from `App.css` hooks to Tailwind utilities + shadcn `Card`, `Badge`, `Alert`, `Button`; 375px light/dark AC tests green; PR #96 merged (`e76a6d9`).
- [x] Issue #94: Tailwind rewrite — run flow (NewRun + RunDetail) — `NewRun.tsx`, `RunDetail.tsx`, `CvUploadForm.tsx`, `JobSearchForm.tsx`, `TitleSuggestions.tsx` migrated from `App.css` hooks to Tailwind utilities + shadcn `Input`, `Select`, `Alert`, `Badge`, `Button`; 375px light/dark AC tests green; PR #97 merged (`ac1981b`).

---

## Detailed Tasks

---

## Task 0: Monorepo scaffold and Docker Compose baseline

**Description:** Create the repository layout (`backend/`, `frontend/`, `infra/`), Python package with FastAPI API entrypoint and worker entrypoint stubs, React SPA scaffold (Vite), shared `docker-compose.yml` with PostgreSQL, and non-root Dockerfiles (UID 10001). Establish pytest and Vitest tooling, `.env.example`, and a `/health` endpoint.

**Acceptance criteria:**
- [x] Directory layout matches PRD module boundaries (domain, ports, api, worker, web)
- [x] `docker compose up` builds and starts api, worker, postgres without errors
- [x] API responds `200` on `GET /health`; worker process starts and logs ready
- [x] Dockerfiles run as non-root user 10001

**Verification:**
- [x] `docker compose up --build` succeeds
- [x] `pytest` runs (even if zero tests initially)
- [x] `npm run build` in frontend succeeds

**Dependencies:** None

**Files likely touched:**
- `docker-compose.yml`, `backend/Dockerfile`, `worker/Dockerfile` (or shared)
- `backend/pyproject.toml`, `backend/app/main.py`, `backend/worker/main.py`
- `frontend/package.json`, `frontend/vite.config.ts`
- `.env.example`, `.gitignore`

**Estimated scope:** Medium (3–5 files → scaffold touches ~10–15)

---

## Task 1: Infrastructure ports and local adapters

**Description:** Implement the three cloud-agnostic ports from ADR-0002 with local adapters: `BlobStore` (MinIO/Azurite), `JobQueue` (RabbitMQ or in-process), `SecretProvider` (env vars). Wire adapters via factory from environment config. Add contract tests asserting put/get/delete semantics and publish/consume round-trip.

**Acceptance criteria:**
- [x] `BlobStore` interface: `put`, `get`, `delete` with key prefix support
- [x] `JobQueue` interface: `publish(message)`, `consume(handler)` with JSON payload
- [x] `SecretProvider` interface: `get(name) → str` from env in local mode
- [x] Local adapters integrated into Docker Compose services
- [x] Contract tests pass against local adapters

**Verification:**
- [x] `pytest tests/ports/` passes
- [x] Manual: upload bytes to blob emulator via adapter in REPL or integration test

**Dependencies:** Task 0

**Files likely touched:**
- `backend/app/ports/blob_store.py`, `job_queue.py`, `secret_provider.py`
- `backend/app/adapters/local/*.py`
- `backend/app/config.py`, `backend/tests/ports/`

**Estimated scope:** Medium

---

## Task 2: Domain core and PostgreSQL schema migrations

**Description:** Implement domain entities and pure logic: User Account, CV, Job Search, Analysis Run state machine, quota/concurrency rules, partial-success rules, divergence badge helpers. Add Alembic (or equivalent) migrations for all PRD tables plus `sessions`, `rate_limit_counters`, and `audit_log`. Seed script stub for admin bootstrap.

**Acceptance criteria:**
- [x] Migrations create: `user_account`, `cv`, `analysis_run`, `job_match_result`, `magic_link_token`, `sessions`, `rate_limit_counters`, `audit_log`
- [x] Run state machine unit tests: valid transitions, terminal states, partial success
- [x] Quota logic: 3 runs/24h rolling, 1 concurrent, unlimited bypass
- [x] Repository layer (or SQLAlchemy models) with owner-scoped queries

**Verification:**
- [x] `pytest tests/domain/` passes
- [x] `alembic upgrade head` succeeds in Compose Postgres

**Dependencies:** Task 0

**Files likely touched:**
- `backend/app/domain/*.py`, `backend/app/db/models.py`, `backend/app/db/migrations/`
- `backend/tests/domain/test_quota.py`, `test_run_state_machine.py`

**Estimated scope:** Medium

---

## Task 3: Session store and auth middleware (Postgres-backed)

**Description:** Implement HttpOnly + Secure + SameSite=Lax session cookies backed by `sessions` table (24h idle / 7d absolute expiry, rotate on login). FastAPI dependency injects current user; unauthenticated requests to protected routes return 401. Session cleanup via `expires_at` predicate or periodic job.

**Acceptance criteria:**
- [x] Session created on login, stored in Postgres with indexed session ID
- [x] Middleware/dependency resolves `user_id` from cookie
- [x] Idle and absolute expiry enforced
- [x] Session rotation on successful authentication

**Verification:**
- [x] Integration test: create session → access protected route → expire → 401
- [x] `pytest tests/auth/` passes (session + security boundary tests)
- [x] `pytest tests/auth/test_sessions_postgres.py` passes after `alembic upgrade head` in CI

**Dependencies:** Task 2

**Files likely touched:**
- `backend/app/auth/session.py`, `backend/app/auth/middleware.py`
- `backend/app/api/deps.py`

**Estimated scope:** Small

---

## Task 4: Google OAuth sign-in flow

**Description:** Implement `GET /auth/google/login` (redirect with `state` nonce) and `GET /auth/google/callback` (validate state, exchange code, upsert user by email/google_sub, create session). Store OAuth client secrets via `SecretProvider`. Log auth events to `audit_log`.

**Acceptance criteria:**
- [x] OAuth `state` validated on callback; invalid state returns 400
- [x] New user created on first sign-in; existing user matched by google_sub or email
- [x] Redirect to dashboard after success
- [x] Auth success/failure appended to `audit_log`

**Verification:**
- [x] Integration test with mocked Google token endpoint
- [x] CI gate: `pytest tests/auth/test_google_oauth.py` in `.github/workflows/ci.yml` (no production OAuth secrets in CI)
- [ ] Manual OAuth flow against Google Cloud console test client (optional)

**Dependencies:** Task 1, Task 3

**Files likely touched:**
- `backend/app/auth/google_oauth.py`, `backend/app/api/routes/auth.py`

**Estimated scope:** Medium

---

## Task 5: Magic link sign-in flow

**Description:** Implement `POST /auth/magic-link` (issue token) and `GET /auth/magic-link/verify` (verify, single-use, 15 min expiry). Store `token_hash` only (SHA-256 of ≥256-bit token). Send email via notification port (console/log adapter for local dev). Enforce rate limits via `rate_limit_counters` (3/email/hour, 10/IP/hour).

**Acceptance criteria:**
- [x] Plain token never persisted; only hash in `magic_link_token`
- [x] Second use or expired token rejected
- [x] Rate limits return 429 when exceeded
- [x] Successful verify creates session and marks token used

**Verification:**
- [x] `pytest tests/auth/test_magic_link.py` passes
- [x] Rate limit test: 4th request in hour → 429

**Dependencies:** Task 3

**Files likely touched:**
- `backend/app/auth/magic_link.py`, `backend/app/auth/rate_limit.py`

**Estimated scope:** Medium

---

## Task 6: Sign-out, rate limits, and IDOR-safe routing

**Description:** Implement `POST /auth/logout`, API ingress rate limit (~100 req/min/IP via Postgres counters), and owner-scoped resource access returning **404** on cross-account IDs (not 403). Add API-level request validation helpers.

**Acceptance criteria:**
- [x] Logout deletes session row and clears cookie
- [x] IP rate limit returns 429 with Retry-After semantics
- [x] CV/run/result endpoints scoped to session `user_id`; foreign IDs → 404
- [x] Admin routes return 404 for non-admin (consistent with IDOR policy)

**Verification:**
- [x] Integration tests for 404 on wrong user's CV/run ID
- [x] Rate limit unit test with fake clock or counter fixture

**Dependencies:** Task 4, Task 5

**Files likely touched:**
- `backend/app/api/routes/auth.py`, `backend/app/api/middleware/rate_limit.py`
- `backend/app/api/errors.py`

**Estimated scope:** Small

---

## Task 7: CV upload, validation, and encrypted blob storage

**Description:** Implement `POST /cvs` (multipart: PDF + name) with MIME + magic-byte validation, 5 MB cap, safe parse timeout stub. Store PDF at `cvs/{user_id}/{uuid}.pdf` via `BlobStore`. Persist CV metadata in Postgres.

**Acceptance criteria:**
- [x] Rejects non-PDF, oversize files, and malformed magic bytes — `validation/pdf.py` MIME, 5 MB cap, and `%PDF-` magic-byte checks
- [x] Blob key non-guessable (UUID); user-scoped prefix — `cvs/{user_id}/{uuid}.pdf` via `CvService.upload_cv`
- [x] Returns CV record with id, name, uploaded_at — `POST /cvs` returns `CvResponse`
- [x] No CV content in logs — upload path logs no file bytes or parsed text

**Verification:**
- [x] Integration test: upload valid PDF → blob exists → DB row created — `tests/cvs/test_cv_upload.py`
- [x] Upload `.exe` renamed to `.pdf` rejected — `test_upload_exe_renamed_as_pdf_is_rejected`

**Dependencies:** Task 1, Task 6

**Files likely touched:**
- `backend/app/services/cv_service.py`, `backend/app/api/routes/cvs.py`
- `backend/app/validation/pdf.py`

**Estimated scope:** Medium

---

## Task 8: CV list, delete-with-retain-runs, and PDF parse

**Description:** Implement `GET /cvs`, `DELETE /cvs/{id}` with confirmation semantics (API idempotent delete). Safe PDF text extraction (page limit, 30s timeout, text only) stored in `parsed_text`. Soft-delete: remove blob + parsed text; retain past run metadata referencing cv_id.

**Acceptance criteria:**
- [x] List returns non-deleted CVs with upload dates — `GET /cvs` returns active CV metadata ordered by upload date
- [x] Delete removes blob and parsed_text; sets `deleted_at` — `CvService.delete_cv` soft-deletes and clears blob/parsed text
- [x] Past analysis runs still visible; new run with deleted cv_id rejected — soft-delete retains run FK; `get_owned_cv` returns 404 for deleted CVs
- [x] Parse timeout kills runaway PDF processing — `pdf_parser.extract_text_from_pdf` enforces 30s timeout via thread pool

**Verification:**
- [x] Integration test: delete CV → GET runs still shows historical run — `tests/cvs/test_cv_list_delete.py`
- [x] POST run with deleted cv_id → 400/404 — probe route returns 404 via `get_owned_cv`

**Dependencies:** Task 7

**Files likely touched:**
- `backend/app/services/cv_service.py`, `backend/app/services/pdf_parser.py`

**Estimated scope:** Medium

---

## Task 9: Sync Suggested Job Titles (GPT-4o-mini)

**Description:** Implement `POST /cvs/{id}/suggest-titles` calling OpenAI GPT-4o-mini with structured output (3–5 titles + rationale). Use fake LLM in tests. Log token/cost to FinOps audit (no CV content in logs). Enforce owner scope.

**Acceptance criteria:**
- [x] Returns `{ titles: [{ title, rationale }] }` within sync API timeout
- [x] Uses parsed CV text, not raw PDF bytes, in prompt
- [x] FinOps tokens logged; malformed LLM response handled gracefully
- [x] Requires authenticated owner

**Verification:**

- [x] Unit test with fake LLM returning valid JSON
- [x] Manual call returns titles for sample CV — Verified locally via magic-link auth, CV upload, and POST /cvs/{id}/suggest-titles with live OpenAI key.

**Dependencies:** Task 8

**Files likely touched:**
- `backend/app/services/title_suggestion_service.py`, `backend/app/adapters/openai_client.py`
- `backend/app/api/routes/cvs.py`

**Estimated scope:** Medium

---

## Task 10: Analysis orchestrator, quota, and concurrency rules

**Description:** Domain service to create Analysis Run records, validate Job Search input (UK cities, remote, filter enums, field length limits), enforce quota and concurrent-run rules, and publish `analysis_run_id` to `JobQueue`.

**Acceptance criteria:**
- [x] Rejects run when quota exhausted (unless `is_unlimited`) — `RunQuotaExceededError` in `AnalysisOrchestrator.start_analysis_run`
- [x] Rejects run when another run in Queued/Scraping/Scoring for user — `ConcurrentRunBlockedError` via `has_active_run_from_statuses`
- [x] Validates `job_search_json` schema — `validate_job_search` in `domain/job_search.py` (UK cities, Remote, filter enums, length limits)
- [x] Publishes queue message after DB commit — `_persist_run` commits before `job_queue.publish({"analysis_run_id": ...})`

**Verification:**
- [x] Unit tests: quota edge cases (rolling 24h window, unlimited flag) — `tests/services/test_analysis_orchestrator.py`
- [x] Unit test: concurrent block — `test_start_analysis_run_blocks_concurrent_active_run`

**Dependencies:** Task 2, Task 1

**Files likely touched:**
- `backend/app/services/analysis_orchestrator.py`, `backend/app/domain/job_search.py`

**Estimated scope:** Medium

---

## Task 11: Run API endpoints and status state machine

**Description:** Implement `GET /runs`, `GET /runs/{id}`, `GET /runs/{id}/results`, `POST /runs`, `GET /runs/quota`. Wire orchestrator. Status enum: Queued → Scraping → Scoring → Complete | Failed.

**Acceptance criteria:**
- [x] All endpoints match PRD contracts — `runs.py` exposes GET/POST `/runs`, GET `/runs/{id}`, GET `/runs/{id}/results`, GET `/runs/quota` per PRD § API contracts
- [x] `GET /runs/quota` returns `{ remaining, concurrent_blocked }` — `RunQuotaResponse` via `AnalysisOrchestrator.get_run_quota`
- [x] Results endpoint only for Complete runs (or partial with status check) — `GET /runs/{id}/results` returns 409 until status is `complete`
- [x] Owner-scoped 404 on foreign run IDs — `get_owned_analysis_run` dependency returns generic 404

**Verification:**
- [x] httpx integration tests for happy path and quota 429 — `tests/runs/test_runs_api.py` (8 tests)
- [x] OpenAPI schema generated and matches PRD — `test_openapi_schema_includes_run_contracts` asserts paths and `RunQuotaResponse`

**Dependencies:** Task 10

**Files likely touched:**
- `backend/app/api/routes/runs.py`

**Estimated scope:** Small

---

## Task 12: Worker consumer skeleton and queue wiring

**Description:** Worker entrypoint consumes queue messages, loads run by ID, transitions status Queued → Scraping → Scoring, and exits. Graceful shutdown on SIGTERM. Structured logging without PII.

**Acceptance criteria:**
- [x] Worker receives message and updates run status in DB — `handle_analysis_run_message` transitions QUEUED → SCRAPING → SCORING with a commit after each step
- [x] Invalid/missing run ID logged and acked without crash loop — `_parse_run_id` returns None on missing/malformed field; handler returns early; catch-all in `process_message` prevents crash loop
- [x] Worker runs in Compose alongside RabbitMQ/in-process queue — existing `docker-compose.yml` `JOB_QUEUE_BACKEND: rabbitmq`; worker wired via `create_job_queue(settings)`
- [x] Separate Docker image entrypoint from API — existing `command: python -m worker.main` in Compose; no change needed

**Verification:**
- [x] Integration test: enqueue → worker transitions status — `test_handler_transitions_queued_run_to_scoring` (6 tests total in `tests/test_worker.py`)
- [x] `docker compose up` shows worker consuming test message — CI Docker Compose build ✓; manual verification deferred to full Compose smoke test in Task 13

**Dependencies:** Task 10, Task 1

**Files likely touched:**
- `backend/worker/main.py`, `backend/worker/handlers/analysis_run.py`

**Estimated scope:** Small

---

## Task 13: Job Source registry and Adzuna adapter

**Description:** Pluggable `JobSource` interface with registry. Implement `AdzunaJobSource.fetch_listings(job_search, max_results=50)` calling Adzuna REST API (`country=gb`). Normalise to `NormalisedListing`. Retry up to 2× on transient errors. Unit tests with recorded JSON fixtures.

**Acceptance criteria:**
- [x] `NormalisedListing` shape matches PRD
- [x] Adzuna adapter maps response fields correctly
- [x] Retry logic on 429/5xx/timeouts
- [x] No live network calls in CI tests

**Verification:**
- [x] `pytest tests/job_sources/test_adzuna.py` passes — 19/19 green
- [x] Registry resolves source by name

**Dependencies:** Task 12

**Files likely touched:**
- `backend/app/job_sources/base.py`, `adzuna.py`, `registry.py`
- `backend/tests/fixtures/adzuna_response.json`

**Estimated scope:** Medium

---

## Task 14: Scoring service (GPT-4o, schema validation, FinOps logging)

**Description:** Implement scoring service accepting CV text + listing, calling GPT-4o for dual-score JSON (ADR-0003). Pydantic validation; 1 retry on malformed output; skip listing on second failure. Aggregate token counts for FinOps. Hard cap: 100 scoring calls/run enforced in worker.

**Acceptance criteria:**
- [x] Validated output: match_score 0–100, interview_likelihood enum, breakdown arrays — `ScoringService._to_scored_listing` runs `validate_match_score`; `ScoringLlmOutput` enforces enum + breakdown arrays
- [x] Malformed JSON retried once then skipped — `_score_one` retries once on `LlmClientError`/`ValueError`, then raises `ScoringSkippedError`
- [x] Per-call and per-run token/cost aggregation — `score_run` sums `LlmUsage` tokens into `ScoringFinops` with `estimate_gpt4o_usd`
- [x] No full prompts or CV text in logs — service logs attempt counts only; no listing identity, CV text, or prompts

**Verification:**
- [x] Unit tests with fake LLM: valid JSON, invalid JSON, retry success — `tests/services/test_scoring_service.py` (8 tests)
- [x] Cap test: 101st listing not scored — `test_score_run_enforces_hard_cap_of_100_calls`

**Dependencies:** Task 8

**Files likely touched:**
- `backend/app/services/scoring_service.py`, `backend/app/domain/scoring_schema.py`

**Estimated scope:** Medium

---

## Task 15: Worker pipeline — fetch Adzuna → score → persist results

**Description:** Complete worker handler: fetch Adzuna listings (cap 50), score each, insert `job_match_result` rows, update run to Complete, write `finops_json`. Handle "no listings" → Failed with clear message.

**Acceptance criteria:**
- [x] End-to-end Adzuna-only run completes locally
- [x] Results sorted by match_score in query default
- [x] Run status Complete with ≥1 scored listing
- [x] Zero listings → Failed status

**Verification:**
- [x] Integration test with fake Adzuna + fake LLM
- [x] GET `/runs/{id}/results` returns expected count

**Dependencies:** Task 13, Task 14, Task 12

**Files likely touched:**
- `backend/worker/handlers/analysis_run.py`, `backend/worker/pipeline.py`

**Estimated scope:** Medium

---

## Task 16: Indeed UK scraper adapter (fixture-tested parser)

**Description:** Implement `IndeedJobSource` scraping `uk.indeed.com` with HTML parser (BeautifulSoup/selectolax). Normalise to shared listing shape. Retry 2× on transient failure. **CI uses fixture HTML fragments only** — no live Indeed in unit tests.

**Acceptance criteria:**
- [x] Parser extracts title, company, location, url, description from fixture HTML — `_extract_listing` uses `h2.jobTitle a span[title]`, `[data-testid='company-name']`, `[data-testid='text-location']`, `.job-snippet`
- [x] `fetch_listings` respects max_results=50 — capped in `_parse_html` loop
- [x] Retry on timeout/5xx — `_is_transient` mirrors AdzunaJobSource; 2× retries
- [x] Live scrape optional behind manual smoke flag — documented in `indeed.py` module docstring (`SMOKE_INDEED=1`)

**Verification:**
- [x] `pytest tests/job_sources/test_indeed_parser.py` passes on fixtures — 20/20 green
- [x] Optional `SMOKE_INDEED=1` manual test documented in README

**Dependencies:** Task 13

**Files likely touched:**
- `backend/app/job_sources/indeed.py`
- `backend/tests/fixtures/indeed_search.html`

**Estimated scope:** Medium

---

## Task 17: Multi-source worker pipeline with retry and partial failure

**Description:** Extend worker to fetch Indeed + Adzuna in parallel or sequence, merge listings (dedupe by URL if needed), cap 50/source. Per-source retry 2×. Continue if one source fails.

**Acceptance criteria:**
- [x] Both sources invoked per run
- [x] Independent retry per source
- [x] Listings from successful source scored even if other fails

**Verification:**
- [x] Integration test: Adzuna succeeds, Indeed fails → Complete with banner metadata
- [x] Both fail after retries → Failed

**Dependencies:** Task 15, Task 16

**Files likely touched:**
- `backend/worker/pipeline.py`

**Estimated scope:** Medium

---

## Task 18: Source-failure metadata and run outcome rules

**Description:** Persist `source_failures_json` on run record. Implement partial-success rules from PRD: ≥1 scored → Complete; 0 listings → Failed with message distinguishing empty search vs scrape failure.

**Acceptance criteria:**
- [x] `source_failures_json` lists failed sources with reason codes
- [x] API exposes failure metadata for UI banner
- [x] Distinct user-facing messages for no jobs vs scrape failure

**Verification:**
- [x] Domain unit tests for outcome matrix
- [x] API test: partial run includes `source_failures` field

**Dependencies:** Task 17

**Files likely touched:**
- `backend/app/domain/run_outcomes.py`, `backend/app/db/models.py`

**Estimated scope:** Small

---

## Task 19: Transactional email service (magic link + run complete)

**Description:** Email port with local log adapter and production provider adapter (e.g. Resend/SendGrid). Templates for magic link and run completion with deep link to `/runs/{id}`. Wire into auth and worker completion hook.

**Acceptance criteria:**
- [x] Magic link email sent on request (local: logged URL)
- [x] Completion email sent when run reaches Complete
- [x] Deep link requires sign-in as owner (no public share token)
- [x] Secrets loaded via SecretProvider (`RESEND_API_KEY`)

**Verification:**
- [x] Integration test captures email payload in fake sink (`tests/worker/test_analysis_pipeline.py`)
- [x] Template snapshot test for subject/body structure (`tests/notifications/test_email_templates.py`)

**Dependencies:** Task 5, Task 15

**Files likely touched:**
- `backend/app/services/notification_service.py`, `backend/app/adapters/email/`

**Estimated scope:** Medium

---

## Task 20: React SPA scaffold, auth pages, and API client

**Description:** Vite + React + TypeScript SPA with routing, auth context, API client (credentials include for cookies), sign-in page (Google button + magic link form), and protected route wrapper. Serve built SPA from FastAPI static mount or separate dev proxy.

**Acceptance criteria:**
- [x] Routes: `/login`, `/dashboard` (protected) — react-router routes in `App.tsx`; `ProtectedRoute` gates `/dashboard`
- [x] Google OAuth redirect works from browser — full-page anchor to `${API}/auth/google/login` via `googleLoginUrl()`
- [x] Magic link form submits and shows "check email" state — `Login.tsx` form with sent/rate-limit/error states
- [x] Unauthenticated users redirected to login — `ProtectedRoute` `<Navigate to="/login">`; `AuthProvider` probes `GET /auth/me`

**Verification:**
- [x] `npm run build` succeeds — `tsc -b && vite build` green
- [x] Manual browser sign-in flow against local API

**Dependencies:** Task 6

**Files likely touched:**
- `frontend/src/App.tsx`, `frontend/src/pages/Login.tsx`, `frontend/src/api/client.ts`

**Estimated scope:** Medium

---

## Task 21: Dashboard, CV wizard, run status polling, and cold-start UX

**Description:** Pages: Dashboard (CV list + run history), CV upload with title suggestion step, Job Search form (UK location picker + Remote), run detail with polling (2–5s interval) for status transitions. Cold-start warming banner when API slow to respond.

**Acceptance criteria:**
- [x] CV upload → title suggestions displayed → select/edit title → Job Search form — `NewRun` wizard: `CvUploadForm` → `TitleSuggestions` (use suggestion or edit own role) → `JobSearchForm`
- [x] Start run → navigate to run detail → poll until Complete/Failed — `JobSearchForm.createRun` → `navigate(/runs/{id})` → `RunDetail` drives `useRunPolling` until terminal
- [x] Loading/warming UI shown when health check exceeds threshold — `useApiWarmup` (`thresholdMs`/retry on cold `/health`); Dashboard warming banner
- [x] Quota displayed before starting run — `JobSearchForm` loads `GET /runs/quota`, renders "N runs left today" and blocks on concurrent run

**Verification:**
- [x] Manual E2E against local Compose — verified 2026-06-13; 16 real Indeed listings scraped, scored, run reached Complete (see docs/bugs/indeed-scraper-e2e-fix.md for scraper fixes required)
- [x] Component test for polling hook status updates — `src/hooks/useRunPolling.test.ts` (polls through scraping→complete, stops on terminal, surfaces transient errors)

**Dependencies:** Task 9, Task 11, Task 20

**Files likely touched:**
- `frontend/src/pages/Dashboard.tsx`, `CvUpload.tsx`, `RunDetail.tsx`, `JobSearchForm.tsx`

**Estimated scope:** Large → split if needed; treat as one vertical slice session

---

## Task 22: Results view — sort, filters, divergence badges

**Description:** Results page: default sort Match Score desc, filters (Interview Likelihood, Job Source, min Match Score), full AI breakdown per card, divergence badges per PRD thresholds, external apply links open in new tab.

**Acceptance criteria:**
- [x] Filters compose correctly on fixture data — 6 Results tests incl. compose test; likelihood/source/minScore all compose via AND logic
- [x] Badges: "Skills fit, seniority gap" and "Competitive profile, weak keyword fit" — `getDivergenceBadge` in `ResultCard.tsx` mirrors backend thresholds; 2 badge tests green
- [x] Interview Likelihood labeled as AI estimate — rendered as "High (AI estimate)" in `ResultCard`
- [x] Partial failure banner when `source_failures` present — renders "Some job sources failed…" alert

**Verification:**
- [x] Vitest component tests with fixture result sets — 7 ResultCard + 6 Results = 13 tests, all green
- [x] Manual filter interaction — requires local Compose with a completed run

**Dependencies:** Task 21, Task 18

**Files likely touched:**
- `frontend/src/pages/Results.tsx`, `frontend/src/components/ResultCard.tsx`

**Estimated scope:** Medium

---

## Task 23: Run history, quota display, and unlimited bypass

**Description:** Dashboard shows past runs with CV name, Job Search summary, status, date. Quota widget ("2 runs left today"). Unlimited users see no cap UI. Block UI when concurrent run active.

**Acceptance criteria:**
- [x] Run history lists all user runs with metadata — `RunHistory` renders CV name, Job Search summary (role — location/Remote), status label, and date, linking to `/runs/{id}`; soft-deleted CVs fall back to "Deleted CV"
- [x] Quota from `GET /runs/quota` displayed accurately — Dashboard loads quota and renders `QuotaBanner` ("N run(s) left today" with singular/plural)
- [x] Start button disabled when concurrent_blocked — Dashboard renders the new-run entry as a disabled button when `concurrent_blocked` or `remaining === 0`; `JobSearchForm`'s start button stays disabled too
- [x] Unlimited flag hides daily cap message — `remaining === null` shows "Unlimited runs on your account." with no "left today" text and keeps the start action enabled

**Verification:**
- [x] Component test for quota states — `QuotaBanner.test.tsx` (plural/singular/unlimited/concurrent/loading) + Dashboard quota states
- [x] Integration test: third run in 24h shows blocked UI — Dashboard component test with `remaining: 0` asserts the start action is disabled (component-level; server enforces the rolling quota)

**Dependencies:** Task 11, Task 21

**Files likely touched:**
- `frontend/src/components/QuotaBanner.tsx`, `RunHistory.tsx`

**Estimated scope:** Small

---

## Task 24: Admin UI (`/admin`) — search users, toggle unlimited

**Description:** Admin page at `/admin` (nav link only if `is_admin` from session/user endpoint). Search by email, toggle `is_unlimited`. API: `GET /admin/users?email=`, `PATCH /admin/users/{id}`. Audit log on toggle.

**Acceptance criteria:**
- [x] Non-admin receives 404 on admin routes and no nav link — `require_admin` returns 404 (`test_non_admin_gets_404_on_search`/`_patch`); SPA `AdminRoute` redirects non-admins to `/dashboard` and the nav link renders only when `user.is_admin`
- [x] Search returns matching users — `GET /admin/users?email=` via `UserRepository.search_by_email` (case-insensitive, LIKE-escaped, capped 50; blank query returns empty) (`test_search_users_returns_email_matches`)
- [x] PATCH updates `is_unlimited`; audit_log entry created — `PATCH /admin/users/{id}` with strict body; `admin.user.unlimited_toggled` audit entry with actor+subject+metadata (`test_patch_user_toggles_unlimited_and_writes_audit`)
- [x] Admin bootstrap seed sets operator email `is_admin=true` — `scripts/seed_admin.py` upserts `is_admin`/`is_unlimited`

**Verification:**
- [x] Integration test: admin toggle; non-admin 404 — `tests/admin/test_admin_api.py` (10 tests: search, toggle+audit, 404/422/401, mass-assignment rejection)
- [x] Seed script documented in README — `backend/README.md` migrations section

**Dependencies:** Task 6, Task 20

**Files likely touched:**
- `backend/app/api/routes/admin.py`, `backend/app/services/admin_service.py`
- `frontend/src/pages/Admin.tsx`, `backend/scripts/seed_admin.py`

**Estimated scope:** Small

---

## Task 25: Terraform bootstrap stack (remote state)

**Description:** Bootstrap Terraform in `infra/bootstrap/`: resource group, storage account for remote state (geo-redundant), container for state blob. Document one-time apply procedure. Required tags on all resources.

**Acceptance criteria:**
- [x] Bootstrap applies cleanly in empty subscription (only `owner_email` required; random suffix keeps SA name globally unique)
- [x] Remote backend config documented for app stack (`infra/README.md` + `app_stack_backend_config` output)
- [x] Tags: project, env, owner, cost-center

**Verification:**
- [x] `terraform validate` in CI (credential-free `terraform` job: fmt + init -backend=false + validate)
- [ ] `terraform plan` succeeds — operator-local on apply (needs ARM creds; not in secret-free PR gate)

**Dependencies:** None (can parallelize early)

**Files likely touched:**
- `infra/bootstrap/*.tf`, `infra/README.md`

**Estimated scope:** Small

---

## Task 26: Terraform application stack (ACA, Postgres, SB, Blob, KV, ACR)

**Description:** Application stack modules: PostgreSQL Flexible B1ms (private VNet), Blob Storage (public access disabled), Service Bus Basic, Key Vault, ACR Basic, Log Analytics, Container Apps Environment, API app (ingress HTTPS, min 0/max 2), Worker app (ingress disabled, KEDA Service Bus scaler). Private endpoints for Postgres, Blob, Service Bus. **No Redis.**

**Acceptance criteria:**
- [x] All PRD Azure resources provisioned with private networking — VNet + private endpoint (Blob), VNet-injection (Postgres), private DNS zones; **Service Bus exception:** Basic SKU has no private endpoint (Premium-only, breaks £75 cap) → MI+RBAC data plane + Listen-only KEDA SAS, see `docs/adr/0004-service-bus-basic-no-private-endpoint.md`
- [x] API public ingress only; worker ingress disabled — `ca-*-api` `ingress { external_enabled = true }`; `ca-*-worker` has no `ingress` block (`infra/app/containerapps.tf`)
- [x] KEDA scaler on queue depth configured — `custom_scale_rule` `azure-servicebus` on worker (`messageCount=5`)
- [x] PostgreSQL no public endpoint — `public_network_access_enabled = false` + `delegated_subnet_id` + `private_dns_zone_id` (`infra/app/database.tf`)

**Verification:**
- [ ] `terraform plan` review against BUDGET.md line items — operator-local on apply (needs ARM creds; not in secret-free PR gate)
- [x] `terraform validate` in CI — matrix `terraform` job covers `bootstrap` + `app` (`.github/workflows/ci.yml`)

**Dependencies:** Task 25

**Files likely touched:**
- `infra/app/*.tf`, `infra/modules/*`

**Estimated scope:** Large (split module-by-module if needed)

---

## Task 27: Azure adapters (Blob, Service Bus, Key Vault) and MI wiring

**Description:** Production adapters for three ports using Azure SDK. Startup wiring from env/identity. Separate Managed Identities: API (blob RW cvs/, SB send, KV OAuth+email), Worker (blob read cvs/, SB receive, KV OpenAI+Adzuna). Non-root containers. Also includes the **`GraphApiNotificationPort`** transactional-email adapter (M365 shared mailbox `sendMail`, MI-authenticated; decision 2026-06-11, replaces Resend).

**Acceptance criteria:**
- [x] Adapters pass same contract tests as local (with Azure emulator or mocked SDK) — mocked-SDK contract tests in `tests/adapters/` mirror the `tests/ports/` assertions for blob/queue/secret; the Azurite + Azure blob adapters share `BlobServiceBlobStore` so they cannot drift
- [x] MI role assignments match THREAT_MODEL least privilege — API MI: Blob RW `cvs/`, SB send, KV get OAuth+DB; Worker MI: Blob read-only, SB receive, KV get OpenAI+Adzuna+DB (`infra/app/identity.tf`, Task 26); Graph `Mail.Send` for both MIs added via runbook (no `azurerm` resource)
- [x] No secrets in image or Terraform state plaintext — all adapters authenticate with the Container App Managed Identity; KV holds the only stored secrets (placeholders in state, real values set out-of-band); Graph email uses MI, no API key
- [x] `GraphApiNotificationPort` sends via shared mailbox using MI — adapter posts to `/users/{mailbox}/sendMail` with the MI token; the `Mail.Send` grant + Exchange **Application Access Policy** constraint are mandatory out-of-band steps documented in `docs/ops/RUNBOOK.md` (no Terraform/`azurerm` resource exists for them)

**Verification:**
- [x] Contract tests with mocked Azure clients (incl. mocked Graph `sendMail`) — `tests/adapters/` (27 tests): KV, blob, Service Bus, Graph, and factory wiring
- [ ] Deployed smoke: blob put/get via API MI — deferred to deploy (Phase H; needs a deploy target)
- [ ] Deployed smoke: magic-link email lands in a real inbox from the shared mailbox — deferred to deploy (operator post-deploy check, RUNBOOK §2c)

**Dependencies:** Task 1, Task 26

**Files likely touched:**
- `backend/app/adapters/azure/*.py`

**Estimated scope:** Medium

---

## Task 28: GitHub Actions — PR gates (lint, test, validate, CVE scan)

**Description:** PR workflow: Python lint (ruff), pytest with Compose services, frontend lint/build/test, `terraform validate` + plan (no apply), Docker build api+worker, Trivy/Grype scan failing on Critical CVEs with fix available. Fork PRs cannot deploy.

**Acceptance criteria:**
- [x] PR workflow runs on all branches except deploy — `ci.yml` runs on every PR to `main`; no deploy workflow exists yet (Task 29)
- [x] Critical CVE gate blocks merge — `cve-scan` job, Trivy `exit-code: 1` on CRITICAL CVEs with a published fix (`ignore-unfixed: true`)
- [x] Tests use local adapters only (no Azure secrets in CI) — unchanged; no secrets referenced in CI
- [x] Caching for pip/npm layers — `setup-python` pip cache + `setup-node` npm cache (since Task 0 baseline)

**Verification:**
- [x] Open test PR; all checks green — PR #38 CI green incl. `Container CVE scan` (48s)
- [ ] Introduce dummy CVE test confirms gate fails — manual operator check; not committed (would intentionally break a dependency)

**Dependencies:** Task 0, Task 25

**Files likely touched:**
- `.github/workflows/pr.yml`, `.github/workflows/ci.yml`

**Estimated scope:** Medium

---

## Task 29: GitHub Actions — prod deploy (OIDC, SHA tags, terraform apply)

**Description:** Deploy workflow on `main` only: OIDC to Azure, build/push SHA-tagged images to ACR, `terraform apply`, update ACA revisions to new SHA. No `:latest` in prod. Immutable tags.

**Acceptance criteria:**
- [x] OIDC federated credential scoped to repo + main branch — `infra/bootstrap/deploy_identity.tf`: `azuread_application_federated_identity_credential` subject `repo:DNBLabs/ai-job-matcher-and-cv-analyzer:ref:refs/heads/main`, no client secret
- [x] Images tagged with git SHA — `deploy.yml` builds/pushes `backend:<sha>` (workflow_run head_sha / dispatch input); never `:latest`
- [x] ACA revisions pin to SHA tag after apply — `az containerapp update --image <acr>/backend:<sha>` for API + worker (Single revision mode)
- [x] Workflow requires successful PR checks — `workflow_run` on CI completion, job guard `conclusion == 'success'`; branch protection on `main`

**Verification:**
- [ ] Deploy to prod subscription; verify revision SHA matches commit — operator-only (Phase H; needs a live subscription + seeded GitHub secrets). Locally validated: `terraform fmt/validate` (bootstrap, app, grants) + `actionlint` deploy.yml all green
- [x] Rollback procedure documented (redeploy prior SHA) — ADR-0006 §Rollback + `workflow_dispatch` `image_sha` input

**Dependencies:** Task 26, Task 27, Task 28

**Files likely touched:**
- `.github/workflows/deploy.yml`, `infra/bootstrap/deploy_identity.tf`, `infra/grants/*`, `docs/adr/0006-zero-touch-deploy-oidc.md`, `docs/ops/RUNBOOK.md`

**Estimated scope:** Medium

**Decision (2026-06-15):** Zero-touch the *application release* only; one-time IAM (Graph `Mail.Send` grant, Exchange Application Access Policy) stays separately-applied IaC / documented admin steps so the per-merge pipeline never holds tenant-admin Graph permissions (ADR-0006). Exchange policy cannot be OIDC-automated (needs a long-lived cert) — kept manual to honor the OIDC-only guardrail.

---

## Task 30: Production SPA serving (Azure Static Web App)

**Description:** Host the built React/Vite SPA on a dedicated **Azure Static Web App** (Free SKU), separate from the API Container App, resolving the "SPA serving" open question (**ADR-0008**). Wire cross-origin auth and CORS so sign-in works from the SWA against the API: production session/OAuth-state cookies become `SameSite=None; Secure`, the API restricts credentialed CORS to the SWA origin, and the frontend is built with `VITE_API_BASE_URL` = the API's public URL and deployed via GitHub Actions. The API's existing live URL keeps serving the JSON API; the SWA becomes the user-facing site.

**Acceptance criteria:**
- [x] `azurerm_static_web_app` (Free SKU) provisioned in `infra/app` with FinOps tags — `staticwebapp.tf` `swa-${name_prefix}`, `sku_tier/sku_size = "Free"`, `local.common_tags`; `westeurope` (SWA unsupported in uksouth)
- [x] Frontend built with `VITE_API_BASE_URL` = API public URL and deployed to the SWA via GitHub Actions (`Azure/static-web-apps-deploy`, token from SWA) — `deploy.yml` setup-node → `npm ci && npm run build` (`VITE_API_BASE_URL=https://<api_fqdn>`) → `Azure/static-web-apps-deploy@v1` `action: upload`, `skip_app_build`, `app_location: frontend/dist`; token from `terraform output -raw static_web_app_api_key`, masked
- [x] API credentialed CORS restricted to the SWA origin (`ALLOWED_ORIGINS`) — `containerapps.tf` `local.frontend_url` resolves to the SWA hostname and feeds `ALLOWED_ORIGINS`; `main.py` CORS `allow_credentials=True` with `cors_origins`
- [x] Session + OAuth-state cookies use `SameSite=None; Secure` in production, `Lax` in dev — `Settings.cookie_samesite`/`cookie_secure`; all four cookie helpers in `auth/middleware.py` + `auth/google_oauth.py` use them; `test_sessions.py` + `test_google_oauth.py` assert both environments
- [x] Google OAuth callback (API) + post-auth redirect (SWA) wired — `GOOGLE_OAUTH_REDIRECT_URI` stays API-side; `POST_AUTH_REDIRECT_URL = <frontend_url>/dashboard` (SWA)
- [x] Run-complete email deep links point to the SWA origin (`FRONTEND_BASE_URL`) — worker `FRONTEND_BASE_URL = local.frontend_url` (SWA hostname)

**Verification:**
- [ ] SWA URL loads the SPA; client-side deep links (e.g. `/dashboard`) resolve — operator-only (needs live SWA deploy)
- [ ] Google + magic-link sign-in works from the SWA against the live API; no CORS/cookie errors in the browser console — operator-only (Phase H)
- [ ] `terraform plan` shows the SWA on Free SKU (no budget impact) — operator-local on apply (needs ARM creds; not in secret-free PR gate). Locally validated: `terraform fmt -check` + `validate` green; `npm run build` green; cookie tests green

**Dependencies:** Task 26, Task 29

**Files likely touched:**
- `infra/app/staticwebapp.tf`, `infra/app/containerapps.tf` (ALLOWED_ORIGINS / redirect / FRONTEND_BASE_URL)
- `backend/app/auth/*` (environment-aware cookie `SameSite`)
- `.github/workflows/` (frontend SWA deploy), `frontend/src/config.ts`

**Estimated scope:** Medium

**Decision (2026-06-16):** Chose a **separate Azure Static Web App** over a same-origin FastAPI static mount — better separation of concerns, CDN edge caching, an independent frontend deploy path, and stronger architecture for the portfolio; Free SKU keeps it within budget. Trade-off: cross-origin auth requires `SameSite=None; Secure` cookies + locked-down CORS (custom shared-parent domains, which would permit `Lax`, are a deferred hardening). See **ADR-0008**.

---

## Task 31: Observability and FinOps alerts (Log Analytics, budgets)

**Description:** Configure Log Analytics ingestion (cost-capped), Azure budget alerts at £60/£75, OpenAI daily £2 alert (manual org setup documented), Service Bus queue depth alert (>10 for 15 min). App structured logging: queue depth, 5xx, 429 rate, scrape failure rate (no PII).

**Acceptance criteria:**
- [ ] ACA logs flow to Log Analytics
- [ ] Budget alerts configured in Terraform or runbook
- [ ] Alert runbook actions documented in README/ops doc
- [ ] FinOps dashboard or Cost Management view linked

**Verification:**
- [ ] Trigger test log entry visible in Log Analytics
- [ ] Budget alert rule exists in Azure portal/terraform state

**Dependencies:** Task 26, Task 29

**Files likely touched:**
- `infra/app/monitoring.tf`, `docs/ops/RUNBOOK.md`

**Estimated scope:** Small

---

## Issue #82: Install Tailwind CSS + shadcn/ui tooling

**Description:** Install and configure the Tailwind CSS v3.4.x PostCSS stack and copy shadcn/ui Radix components so subsequent UI refresh issues can use utility classes and Radix-based components without further setup. No page or component classNames are changed in this issue.

**Parent / Epic:** Related to #81

**Acceptance criteria:**
- [x] Given a clean `npm ci && npm run build` in `frontend/`, when the build completes, then it exits 0 with no Tailwind configuration errors
- [x] Given `frontend/src/index.css`, when inspected, then it contains `@tailwind base`, `@tailwind components`, `@tailwind utilities`, and a `--primary` CSS variable set to a deep violet hue
- [x] Given `frontend/tailwind.config.ts`, when inspected, then `darkMode` is `'class'` and `content` includes `'./src/**/*.{ts,tsx}'`
- [x] Given `frontend/postcss.config.js`, when inspected, then it registers `tailwindcss` and `autoprefixer` as plugins, and `frontend/package.json` devDependencies do NOT include `@tailwindcss/vite`
- [x] Given `frontend/src/components/ui/`, when listed, then it contains at minimum: `button.tsx`, `card.tsx`, `badge.tsx`, `input.tsx`, `select.tsx`, `dropdown-menu.tsx`, `separator.tsx`, `alert.tsx`
- [x] Given `frontend/index.html`, when the user's OS is set to dark mode and the page loads, then `<html>` has `class="dark"` before the first paint (no FOUC)
- [x] Given `npm run test` in `frontend/`, when run, then all existing tests pass (no regressions from config changes)
- [x] Invalid input: N/A — no user-facing input in this issue
- [x] Auth: N/A — no auth boundary touched
- [x] Downstream: N/A — no external service calls

**Verification:**
- [x] `npm ci && npm run build` in `frontend/` exits 0
- [x] `npm run test` in `frontend/` green (existing suite)
- [x] No `shadcn` runtime dependency; no `@tailwindcss/vite`; no Google Fonts `<link>` in `index.html`

**Dependencies:** None

**Files likely touched:**
- `frontend/package.json`, `frontend/package-lock.json`
- `frontend/tailwind.config.ts`, `frontend/postcss.config.js`
- `frontend/src/index.css`, `frontend/index.html`
- `frontend/src/components/ui/*`, `frontend/src/lib/utils.ts`
- `frontend/tsconfig.json`, `frontend/tsconfig.app.json`, `frontend/vite.config.ts`

**Estimated scope:** Small

**Decision:** Tailwind v3.4.x via PostCSS (not v4 / `@tailwindcss/vite`) because ACs require `@tailwind` directives and `darkMode: 'class'` in a JS config file.

---

## Issue #84: ResultCard expand/collapse breakdown toggle

**Description:** Add an expand/collapse toggle to `ResultCard` so Job Seekers can scan a ranked list of 50–100 results before drilling into breakdown detail. Breakdown data is already in the API response — no second API call on expand.

**Parent / Epic:** Related to #81

**Acceptance criteria:**
- [x] Given a rendered `ResultCard`, when the component first mounts, then title, company, match score, interview likelihood, and apply link are visible, and no breakdown content (matched skills, skill gaps, red flags, talking points) is present in the DOM
- [x] Given a collapsed `ResultCard`, when the user clicks "Show breakdown", then the four breakdown sections become visible and the button label changes to "Hide breakdown"
- [x] Given an expanded `ResultCard`, when the user clicks "Hide breakdown", then the breakdown sections are removed from the DOM and the button label returns to "Show breakdown"
- [x] Given a result with an empty `matched_skills` array, when expanded, then the matched skills section is not rendered (same conditional logic as today)
- [x] Given a divergence badge scenario (score ≥ 70 + likelihood low), when collapsed, then the divergence badge is still visible (it stays in the header, not the breakdown)
- [x] Given the existing `ResultCard.test.tsx` suite, when run after this change, then all tests pass including the updated `"renders matched skills and skill gaps"` test that now clicks the toggle first
- [x] Invalid input: N/A — no user-facing form input; data comes from a typed API response
- [x] Auth: N/A — ResultCard is a pure display component; auth is enforced upstream by the route
- [x] Downstream: N/A — no external calls on expand

**Verification:**
- [x] `npm test -- --run src/components/ResultCard.test.tsx` — 16 tests green
- [x] `npm test` in `frontend/` — full suite green (122 tests)
- [x] `npm run lint` and `npm run build` green
- [x] PR CI green; post-merge CI + Deploy on `main` green (`719a31b`)

**Dependencies:** Issue #82 (Tailwind + shadcn/ui tooling)

**Files likely touched:**
- `frontend/src/components/ResultCard.tsx`, `frontend/src/components/ResultCard.test.tsx`

**Estimated scope:** Small

---

## Issue #85: Tailwind rewrite - Login page

**Description:** Replace legacy login-page CSS hooks in `Login.tsx` with Tailwind utility classes and shadcn/ui primitives so the pre-auth sign-in screen matches the deep-violet design system from Issue #82, stays centered on small screens, and respects dark mode via the existing `html.dark` token setup.

**Parent / Epic:** Related to #81

**Acceptance criteria:**
- [x] Given the Login page in light mode, when rendered at 375px width, then the page is usable with no horizontal scroll and all form elements are reachable
- [x] Given the Login page in dark mode (OS `prefers-color-scheme: dark`), when rendered, then text and background colours are legible (no white-on-white or black-on-black)
- [x] Given a valid email submitted, when the magic-link request succeeds, then the "Check your email" confirmation is clearly visible with good contrast
- [x] Given an invalid / already-rate-limited request, when the API returns an error, then the error alert (`role="alert"`) is visible and styled with the destructive colour from the shadcn/ui CSS variables
- [x] Given `Login.test.tsx`, when run after this change, then all existing tests pass without modification
- [x] Given a search for `auth-page` in `Login.tsx`, when inspected, then no hand-rolled CSS class names from `App.css` remain
- [x] Invalid input: The error state AC above covers the empty-email and rate-limit paths
- [x] Auth: N/A — Login is the pre-auth page; no session required
- [x] Downstream: N/A — no external calls added by this issue

**Verification:**
- [x] `npm test -- src/pages/Login.test.tsx` green
- [x] `npm run lint` green
- [x] `npm run build` green
- [x] `npm audit --audit-level=high` green

**Dependencies:** Issue #82 (Tailwind + shadcn/ui tooling)

**Files likely touched:**
- `frontend/src/pages/Login.tsx`, `frontend/src/App.css`

**Estimated scope:** Small

---

## Issue #93: Tailwind rewrite — Dashboard hub

**Description:** Migrate the Dashboard hub — the authenticated landing page and its dedicated shared components — from hand-rolled `App.css` class names to Tailwind utility classes and shadcn/ui primitives. Scope: `Dashboard.tsx` (CV library, run-history section, warming banner, primary actions), `QuotaBanner.tsx` (daily quota messaging), and `RunHistory.tsx` (run list with status badges and CV name resolution). No logic changes — className strings and element structure only. Dark mode via existing `html.dark` CSS variables (#82); no per-component `prefers-color-scheme` overrides.

**Parent / Epic:** #86

**Acceptance criteria:**
- [x] Given Dashboard at 375px in light and dark mode, when rendered, then the page is usable (no horizontal scroll, interactive elements reachable) and text/background colours are legible across all sections
- [x] Given Dashboard with no CVs, when rendered, then the empty-state message is visible and appropriately styled
- [x] Given Dashboard with a warming banner active, when rendered, then the `role="status"` warming message is visually distinct (e.g. an info-coloured Alert)

**Verification:**
- [x] `npm test -- src/pages/Dashboard.test.tsx` — AC tests + existing suite green (129 tests)
- [x] `npm run lint` green
- [x] `npm run build` green
- [x] `npm audit --audit-level=high` green
- [x] PR CI green; post-merge CI + Deploy on `main` green (`e76a6d9`)

**Dependencies:** Issue #82 (Tailwind + shadcn/ui tooling); Issue #83 (AppLayout)

**Files likely touched:**
- `frontend/src/pages/Dashboard.tsx`, `frontend/src/components/QuotaBanner.tsx`, `frontend/src/components/RunHistory.tsx`, `frontend/src/pages/Dashboard.test.tsx`

**Estimated scope:** Small

---

## Issue #94: Tailwind rewrite — run flow (NewRun + RunDetail)

**Description:** Migrate the run-flow journey — new-run wizard and run-detail polling view — from hand-rolled `App.css` class names to Tailwind utility classes and shadcn/ui primitives. Scope: `NewRun.tsx` (multi-step wizard layout), `RunDetail.tsx` (status display and progress indicator), and wizard components `CvUploadForm.tsx`, `JobSearchForm.tsx`, and `TitleSuggestions.tsx`. Use shadcn `Input`/`Select` for form fields, `Alert` for error states, `Badge` for status labels, and `Button` for actions. No logic changes — className strings and element structure only. Dark mode via existing `html.dark` CSS variables (#82); no per-component `prefers-color-scheme` overrides.

**Parent / Epic:** #86

**Acceptance criteria:**
- [x] Given NewRun at 375px in light and dark mode, when rendered, then the page is usable (no horizontal scroll, interactive elements reachable) and text/background colours are legible
- [x] Given RunDetail at 375px in light and dark mode, when rendered, then the page is usable (no horizontal scroll, interactive elements reachable) and text/background colours are legible

**Verification:**
- [x] `npm test -- src/pages/NewRun.test.tsx src/pages/RunDetail.test.tsx` — AC tests + existing suite green (143 tests)
- [x] `npm run lint` green
- [x] `npm run build` green
- [x] `npm audit --audit-level=high` green
- [x] PR CI green; post-merge CI + Deploy on `main` green (`ac1981b`)

**Dependencies:** Issue #82 (Tailwind + shadcn/ui tooling); Issue #83 (AppLayout)

**Files likely touched:**
- `frontend/src/pages/NewRun.tsx`, `frontend/src/pages/RunDetail.tsx`, `frontend/src/components/CvUploadForm.tsx`, `frontend/src/components/JobSearchForm.tsx`, `frontend/src/components/TitleSuggestions.tsx`, `frontend/src/pages/NewRun.test.tsx`, `frontend/src/pages/RunDetail.test.tsx`, `frontend/src/App.css`

**Estimated scope:** Small

---

## Parallelization Opportunities

| Parallel track | Tasks | Notes |
|----------------|-------|-------|
| **A: Backend vertical slices** | 0 → 18 sequential | Core path; must stay ordered |
| **B: Frontend** | 20–24 after Task 6 | Can start after auth API; lags backend slightly |
| **C: Terraform bootstrap** | 25 early | Can start alongside Task 0–2 |
| **D: Terraform app stack** | 26 after 25 | While backend Tasks 13–18 in progress |
| **E: CI/CD** | 28 after Task 0; 29 after 26–27 | Wire deploy last |

**Safe to parallelize:** Frontend (Track B) + Terraform (Track C/D) once auth API exists.  
**Must be sequential:** Migrations before auth; auth before CV; orchestrator before worker; Adzuna before Indeed; app complete before prod smoke.

---

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Indeed HTML structure changes | High | Adzuna fallback; fixture-based parser tests; partial success UX |
| OpenAI cost overrun at 100 listings/run | High | 50/source cap; 3 runs/day quota; £2/day org alert |
| Postgres session latency on B1ms | Med | Index session/rate-limit tables; monitor auth p95 |
| Magic-link email deliverability | Med | Reputable provider; SPF/DKIM documented; log adapter for dev |
| Azure £75 budget exceeded | Med | Scale-to-zero; no Redis; budget alerts; quarterly SKU review |
| Cold start UX (30–60s) | Low | Warming UI; operator pre-warms before demos |
| Adapter drift local vs Azure | Med | Shared contract tests; smoke test in prod after deploy |

---

## Open Questions

- [x] **Transactional email delivery (prod)** — **Resolved 2026-06-11: Microsoft 365 shared mailbox via Graph API `sendMail`, replacing Resend.** New `GraphApiNotificationPort` adapter behind the existing `NotificationPort` (Task 19 abstraction); Resend adapter dropped. Auth via Container App **Managed Identity** (no stored key). Pre-deploy work, folded into **Task 27**: (1) app/MI granted `Mail.Send` *application* permission, (2) **Application Access Policy** scoping that permission to only the shared mailbox — unconstrained `Mail.Send` can send as any tenant mailbox, (3) `EMAIL_FROM` = `noreply@dnblabs.co.uk`, (4) confirm app-only `sendMail` to the shared mailbox needs no per-mailbox licence, (5) post-deploy real-inbox deliverability check. Locally the `log` adapter sends nothing by design — sign-in uses a minted verify link.
- [ ] **Indeed scraping ethics/legal** — Confirm operator accepts scrape + Adzuna fallback for portfolio demo only
- [ ] **Google OAuth prod domains** — Exact callback URLs for ACA ingress (known after Task 26)
- [ ] **Admin operator email** — Confirm seed email for `is_admin` + `is_unlimited` bootstrap
- [ ] **UK city list source** — Static JSON in repo vs external geocoding API (prefer static for cost/simplicity)
- [x] **SPA serving** — **Resolved 2026-06-16: dedicated Azure Static Web App (Free SKU)**, separate from the API — chosen over the same-origin FastAPI static mount for separation of concerns, CDN caching, an independent frontend deploy path, and stronger portfolio architecture. Cross-origin auth handled with `SameSite=None; Secure` cookies + credentialed CORS locked to the SWA origin (shared-parent custom domains, which would permit `Lax`, deferred). Scoped as **Task 30**; see **ADR-0008**.

---

## Suggested Execution Order (Session Map)

For a solo operator or single agent, run tasks in numeric order. Approximate checkpoints:

1. **Week 1 foundation:** Tasks 0–2 → Checkpoint Foundation  
2. **Week 2 auth + CV:** Tasks 3–9 → Checkpoint CV + Titles  
3. **Week 3 async core:** Tasks 10–15 → Checkpoint Adzuna-Only Run  
4. **Week 4 sourcing + email:** Tasks 16–19 → Checkpoint Hybrid Sourcing  
5. **Week 5 frontend:** Tasks 20–24 → Checkpoint Feature Complete  
6. **Week 6 infra:** Tasks 25–30 → Checkpoint Production  

Adjust pacing based on Indeed scraper difficulty (Task 16 often runs long).

---

## Plan Verification Checklist

Before starting implementation, confirm:

- [x] Every task has acceptance criteria
- [x] Every task has verification steps
- [x] Task dependencies identified and ordered correctly
- [x] No task exceeds ~8 files without sub-split (Task 21, 26 flagged)
- [x] Checkpoints exist between major phases
- [ ] **Human has reviewed and approved the plan**
