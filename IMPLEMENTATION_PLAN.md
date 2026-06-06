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
- [x] CI baseline (post–Task 0): `.github/workflows/ci.yml` on PR/push to `main` — backend pytest (explicit `tests/ports/` Task 1 gate + full suite), frontend lint/test/build/audit, `docker compose config` + `docker compose build` with Azurite/RabbitMQ services (Terraform validate + CVE scan deferred to Task 28).
- [x] Task 1: Infrastructure ports and local adapters — Added BlobStore/JobQueue/SecretProvider ports, memory/in-process/env local adapters, Azurite/RabbitMQ Compose adapters, factory wiring from Settings, boundary validation (key traversal, secret names, queue payloads), and contract tests under `tests/ports/`.
- [ ] Task 2: Domain core and PostgreSQL schema migrations

#### Checkpoint: Foundation
- [ ] `docker compose up` starts API, worker, Postgres, queue emulator, blob emulator
- [ ] Migrations apply cleanly; health endpoint returns 200
- [ ] Unit tests for domain quota/state machine pass

---

### Phase 1: Authentication

- [ ] Task 3: Session store and auth middleware (Postgres-backed)
- [ ] Task 4: Google OAuth sign-in flow
- [ ] Task 5: Magic link sign-in flow
- [ ] Task 6: Sign-out, rate limits, and IDOR-safe routing

#### Checkpoint: Auth
- [ ] Job Seeker can sign in via Google or magic link locally
- [ ] Session persists across browser restart; sign-out clears cookie
- [ ] Cross-account resource IDs return 404

---

### Phase 2: CV Management & Title Suggestions

- [ ] Task 7: CV upload, validation, and encrypted blob storage
- [ ] Task 8: CV list, delete-with-retain-runs, and PDF parse
- [ ] Task 9: Sync Suggested Job Titles (GPT-4o-mini)

#### Checkpoint: CV + Titles
- [ ] Upload PDF → see named CV in list → delete with confirmation
- [ ] Title suggestions return in &lt;10s with 3–5 titles + rationales
- [ ] Integration tests pass for CV lifecycle

---

### Phase 3: Analysis Run Core (Queue + Worker Skeleton)

- [ ] Task 10: Analysis orchestrator, quota, and concurrency rules
- [ ] Task 11: Run API endpoints and status state machine
- [ ] Task 12: Worker consumer skeleton and queue wiring

#### Checkpoint: Run Orchestration
- [ ] POST `/runs` enqueues job; status transitions Queued → Scraping → Scoring
- [ ] Quota (3/24h) and concurrent-run block enforced
- [ ] Worker processes message and updates run status (no external APIs yet)

---

### Phase 4: Adzuna Path End-to-End (First Vertical Slice)

- [ ] Task 13: Job Source registry and Adzuna adapter
- [ ] Task 14: Scoring service (GPT-4o, schema validation, FinOps logging)
- [ ] Task 15: Worker pipeline — fetch Adzuna → score → persist results

#### Checkpoint: Adzuna-Only Run
- [ ] Full run completes with scored Adzuna listings in DB
- [ ] GET `/runs/{id}/results` returns ranked results with breakdown JSON
- [ ] FinOps metadata recorded on `analysis_run.finops_json`

---

### Phase 5: Indeed Scraper & Partial Success

- [ ] Task 16: Indeed UK scraper adapter (fixture-tested parser)
- [ ] Task 17: Multi-source worker pipeline with retry and partial failure
- [ ] Task 18: Source-failure metadata and run outcome rules

#### Checkpoint: Hybrid Sourcing
- [ ] Run with both sources completes; partial failure shows banner metadata
- [ ] Zero listings after retries → `Failed` with distinct error messages
- [ ] Indeed parser unit tests use fixtures only (no live network in CI)

---

### Phase 6: Notifications & Frontend Core

- [ ] Task 19: Transactional email service (magic link + run complete)
- [ ] Task 20: React SPA scaffold, auth pages, and API client
- [ ] Task 21: Dashboard, CV wizard, run status polling, and cold-start UX

#### Checkpoint: End-to-End UX (Local)
- [ ] Job Seeker completes full flow in browser: sign-in → upload → search → results
- [ ] Dashboard polls run status; completion email sent (dev sink or provider sandbox)
- [ ] Cold-start loading state present for scale-to-zero messaging

---

### Phase 7: Results UI, Quota & Admin

- [ ] Task 22: Results view — sort, filters, divergence badges
- [ ] Task 23: Run history, quota display, and unlimited bypass
- [ ] Task 24: Admin UI (`/admin`) — search users, toggle unlimited

#### Checkpoint: Feature Complete (Application)
- [ ] All PRD user stories 1–50 verifiable locally
- [ ] Admin bootstrap seed creates operator `is_admin` account
- [ ] Component tests for filters/badges pass

---

### Phase 8: Azure Infrastructure & CI/CD

- [ ] Task 25: Terraform bootstrap stack (remote state)
- [ ] Task 26: Terraform application stack (ACA, Postgres, SB, Blob, KV, ACR)
- [ ] Task 27: Azure adapters (Blob, Service Bus, Key Vault) and MI wiring
- [ ] Task 28: GitHub Actions — PR gates (lint, test, validate, CVE scan)
- [ ] Task 29: GitHub Actions — prod deploy (OIDC, SHA tags, terraform apply)
- [ ] Task 30: Observability and FinOps alerts (Log Analytics, budgets)

#### Checkpoint: Production
- [ ] Deploy from `main` succeeds; API and worker reachable in Azure
- [ ] Smoke test: one Analysis Run in prod
- [ ] Budget and queue-depth alerts configured

---

## Detailed Tasks

---

## Task 0: Monorepo scaffold and Docker Compose baseline

**Description:** Create the repository layout (`backend/`, `frontend/`, `infra/`), Python package with FastAPI API entrypoint and worker entrypoint stubs, React SPA scaffold (Vite), shared `docker-compose.yml` with PostgreSQL, and non-root Dockerfiles (UID 10001). Establish pytest and Vitest tooling, `.env.example`, and a `/health` endpoint.

**Acceptance criteria:**
- [ ] Directory layout matches PRD module boundaries (domain, ports, api, worker, web)
- [ ] `docker compose up` builds and starts api, worker, postgres without errors
- [ ] API responds `200` on `GET /health`; worker process starts and logs ready
- [ ] Dockerfiles run as non-root user 10001

**Verification:**
- [ ] `docker compose up --build` succeeds
- [ ] `pytest` runs (even if zero tests initially)
- [ ] `npm run build` in frontend succeeds

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
- [ ] Migrations create: `user_account`, `cv`, `analysis_run`, `job_match_result`, `magic_link_token`, `sessions`, `rate_limit_counters`, `audit_log`
- [ ] Run state machine unit tests: valid transitions, terminal states, partial success
- [ ] Quota logic: 3 runs/24h rolling, 1 concurrent, unlimited bypass
- [ ] Repository layer (or SQLAlchemy models) with owner-scoped queries

**Verification:**
- [ ] `pytest tests/domain/` passes
- [ ] `alembic upgrade head` succeeds in Compose Postgres

**Dependencies:** Task 0

**Files likely touched:**
- `backend/app/domain/*.py`, `backend/app/db/models.py`, `backend/app/db/migrations/`
- `backend/tests/domain/test_quota.py`, `test_run_state_machine.py`

**Estimated scope:** Medium

---

## Task 3: Session store and auth middleware (Postgres-backed)

**Description:** Implement HttpOnly + Secure + SameSite=Lax session cookies backed by `sessions` table (24h idle / 7d absolute expiry, rotate on login). FastAPI dependency injects current user; unauthenticated requests to protected routes return 401. Session cleanup via `expires_at` predicate or periodic job.

**Acceptance criteria:**
- [ ] Session created on login, stored in Postgres with indexed session ID
- [ ] Middleware/dependency resolves `user_id` from cookie
- [ ] Idle and absolute expiry enforced
- [ ] Session rotation on successful authentication

**Verification:**
- [ ] Integration test: create session → access protected route → expire → 401
- [ ] `pytest tests/auth/test_sessions.py` passes

**Dependencies:** Task 2

**Files likely touched:**
- `backend/app/auth/session.py`, `backend/app/auth/middleware.py`
- `backend/app/api/deps.py`

**Estimated scope:** Small

---

## Task 4: Google OAuth sign-in flow

**Description:** Implement `GET /auth/google/login` (redirect with `state` nonce) and `GET /auth/google/callback` (validate state, exchange code, upsert user by email/google_sub, create session). Store OAuth client secrets via `SecretProvider`. Log auth events to `audit_log`.

**Acceptance criteria:**
- [ ] OAuth `state` validated on callback; invalid state returns 400
- [ ] New user created on first sign-in; existing user matched by google_sub or email
- [ ] Redirect to dashboard after success
- [ ] Auth success/failure appended to `audit_log`

**Verification:**
- [ ] Integration test with mocked Google token endpoint
- [ ] Manual OAuth flow against Google Cloud console test client (optional)

**Dependencies:** Task 1, Task 3

**Files likely touched:**
- `backend/app/auth/google_oauth.py`, `backend/app/api/routes/auth.py`

**Estimated scope:** Medium

---

## Task 5: Magic link sign-in flow

**Description:** Implement `POST /auth/magic-link` (issue token) and `GET /auth/magic-link/verify` (verify, single-use, 15 min expiry). Store `token_hash` only (SHA-256 of ≥256-bit token). Send email via notification port (console/log adapter for local dev). Enforce rate limits via `rate_limit_counters` (3/email/hour, 10/IP/hour).

**Acceptance criteria:**
- [ ] Plain token never persisted; only hash in `magic_link_token`
- [ ] Second use or expired token rejected
- [ ] Rate limits return 429 when exceeded
- [ ] Successful verify creates session and marks token used

**Verification:**
- [ ] `pytest tests/auth/test_magic_link.py` passes
- [ ] Rate limit test: 4th request in hour → 429

**Dependencies:** Task 3

**Files likely touched:**
- `backend/app/auth/magic_link.py`, `backend/app/auth/rate_limit.py`

**Estimated scope:** Medium

---

## Task 6: Sign-out, rate limits, and IDOR-safe routing

**Description:** Implement `POST /auth/logout`, API ingress rate limit (~100 req/min/IP via Postgres counters), and owner-scoped resource access returning **404** on cross-account IDs (not 403). Add API-level request validation helpers.

**Acceptance criteria:**
- [ ] Logout deletes session row and clears cookie
- [ ] IP rate limit returns 429 with Retry-After semantics
- [ ] CV/run/result endpoints scoped to session `user_id`; foreign IDs → 404
- [ ] Admin routes return 404 for non-admin (consistent with IDOR policy)

**Verification:**
- [ ] Integration tests for 404 on wrong user's CV/run ID
- [ ] Rate limit unit test with fake clock or counter fixture

**Dependencies:** Task 4, Task 5

**Files likely touched:**
- `backend/app/api/routes/auth.py`, `backend/app/api/middleware/rate_limit.py`
- `backend/app/api/errors.py`

**Estimated scope:** Small

---

## Task 7: CV upload, validation, and encrypted blob storage

**Description:** Implement `POST /cvs` (multipart: PDF + name) with MIME + magic-byte validation, 5 MB cap, safe parse timeout stub. Store PDF at `cvs/{user_id}/{uuid}.pdf` via `BlobStore`. Persist CV metadata in Postgres.

**Acceptance criteria:**
- [ ] Rejects non-PDF, oversize files, and malformed magic bytes
- [ ] Blob key non-guessable (UUID); user-scoped prefix
- [ ] Returns CV record with id, name, uploaded_at
- [ ] No CV content in logs

**Verification:**
- [ ] Integration test: upload valid PDF → blob exists → DB row created
- [ ] Upload `.exe` renamed to `.pdf` rejected

**Dependencies:** Task 1, Task 6

**Files likely touched:**
- `backend/app/services/cv_service.py`, `backend/app/api/routes/cvs.py`
- `backend/app/validation/pdf.py`

**Estimated scope:** Medium

---

## Task 8: CV list, delete-with-retain-runs, and PDF parse

**Description:** Implement `GET /cvs`, `DELETE /cvs/{id}` with confirmation semantics (API idempotent delete). Safe PDF text extraction (page limit, 30s timeout, text only) stored in `parsed_text`. Soft-delete: remove blob + parsed text; retain past run metadata referencing cv_id.

**Acceptance criteria:**
- [ ] List returns non-deleted CVs with upload dates
- [ ] Delete removes blob and parsed_text; sets `deleted_at`
- [ ] Past analysis runs still visible; new run with deleted cv_id rejected
- [ ] Parse timeout kills runaway PDF processing

**Verification:**
- [ ] Integration test: delete CV → GET runs still shows historical run
- [ ] POST run with deleted cv_id → 400/404

**Dependencies:** Task 7

**Files likely touched:**
- `backend/app/services/cv_service.py`, `backend/app/services/pdf_parser.py`

**Estimated scope:** Medium

---

## Task 9: Sync Suggested Job Titles (GPT-4o-mini)

**Description:** Implement `POST /cvs/{id}/suggest-titles` calling OpenAI GPT-4o-mini with structured output (3–5 titles + rationale). Use fake LLM in tests. Log token/cost to FinOps audit (no CV content in logs). Enforce owner scope.

**Acceptance criteria:**
- [ ] Returns `{ titles: [{ title, rationale }] }` within sync API timeout
- [ ] Uses parsed CV text, not raw PDF bytes, in prompt
- [ ] FinOps tokens logged; malformed LLM response handled gracefully
- [ ] Requires authenticated owner

**Verification:**
- [ ] Unit test with fake LLM returning valid JSON
- [ ] Manual call returns titles for sample CV

**Dependencies:** Task 8

**Files likely touched:**
- `backend/app/services/title_suggestion_service.py`, `backend/app/adapters/openai_client.py`
- `backend/app/api/routes/cvs.py`

**Estimated scope:** Medium

---

## Task 10: Analysis orchestrator, quota, and concurrency rules

**Description:** Domain service to create Analysis Run records, validate Job Search input (UK cities, remote, filter enums, field length limits), enforce quota and concurrent-run rules, and publish `analysis_run_id` to `JobQueue`.

**Acceptance criteria:**
- [ ] Rejects run when quota exhausted (unless `is_unlimited`)
- [ ] Rejects run when another run in Queued/Scraping/Scoring for user
- [ ] Validates `job_search_json` schema
- [ ] Publishes queue message after DB commit

**Verification:**
- [ ] Unit tests: quota edge cases (rolling 24h window, unlimited flag)
- [ ] Unit test: concurrent block

**Dependencies:** Task 2, Task 1

**Files likely touched:**
- `backend/app/services/analysis_orchestrator.py`, `backend/app/domain/job_search.py`

**Estimated scope:** Medium

---

## Task 11: Run API endpoints and status state machine

**Description:** Implement `GET /runs`, `GET /runs/{id}`, `GET /runs/{id}/results`, `POST /runs`, `GET /runs/quota`. Wire orchestrator. Status enum: Queued → Scraping → Scoring → Complete | Failed.

**Acceptance criteria:**
- [ ] All endpoints match PRD contracts
- [ ] `GET /runs/quota` returns `{ remaining, concurrent_blocked }`
- [ ] Results endpoint only for Complete runs (or partial with status check)
- [ ] Owner-scoped 404 on foreign run IDs

**Verification:**
- [ ] httpx integration tests for happy path and quota 429
- [ ] OpenAPI schema generated and matches PRD

**Dependencies:** Task 10

**Files likely touched:**
- `backend/app/api/routes/runs.py`

**Estimated scope:** Small

---

## Task 12: Worker consumer skeleton and queue wiring

**Description:** Worker entrypoint consumes queue messages, loads run by ID, transitions status Queued → Scraping → Scoring, and exits. Graceful shutdown on SIGTERM. Structured logging without PII.

**Acceptance criteria:**
- [ ] Worker receives message and updates run status in DB
- [ ] Invalid/missing run ID logged and acked without crash loop
- [ ] Worker runs in Compose alongside RabbitMQ/in-process queue
- [ ] Separate Docker image entrypoint from API

**Verification:**
- [ ] Integration test: enqueue → worker transitions status
- [ ] `docker compose up` shows worker consuming test message

**Dependencies:** Task 10, Task 1

**Files likely touched:**
- `backend/worker/main.py`, `backend/worker/handlers/analysis_run.py`

**Estimated scope:** Small

---

## Task 13: Job Source registry and Adzuna adapter

**Description:** Pluggable `JobSource` interface with registry. Implement `AdzunaJobSource.fetch_listings(job_search, max_results=50)` calling Adzuna REST API (`country=gb`). Normalise to `NormalisedListing`. Retry up to 2× on transient errors. Unit tests with recorded JSON fixtures.

**Acceptance criteria:**
- [ ] `NormalisedListing` shape matches PRD
- [ ] Adzuna adapter maps response fields correctly
- [ ] Retry logic on 429/5xx/timeouts
- [ ] No live network calls in CI tests

**Verification:**
- [ ] `pytest tests/job_sources/test_adzuna.py` passes
- [ ] Registry resolves source by name

**Dependencies:** Task 12

**Files likely touched:**
- `backend/app/job_sources/base.py`, `adzuna.py`, `registry.py`
- `backend/tests/fixtures/adzuna_response.json`

**Estimated scope:** Medium

---

## Task 14: Scoring service (GPT-4o, schema validation, FinOps logging)

**Description:** Implement scoring service accepting CV text + listing, calling GPT-4o for dual-score JSON (ADR-0003). Pydantic validation; 1 retry on malformed output; skip listing on second failure. Aggregate token counts for FinOps. Hard cap: 100 scoring calls/run enforced in worker.

**Acceptance criteria:**
- [ ] Validated output: match_score 0–100, interview_likelihood enum, breakdown arrays
- [ ] Malformed JSON retried once then skipped
- [ ] Per-call and per-run token/cost aggregation
- [ ] No full prompts or CV text in logs

**Verification:**
- [ ] Unit tests with fake LLM: valid JSON, invalid JSON, retry success
- [ ] Cap test: 101st listing not scored

**Dependencies:** Task 8

**Files likely touched:**
- `backend/app/services/scoring_service.py`, `backend/app/domain/scoring_schema.py`

**Estimated scope:** Medium

---

## Task 15: Worker pipeline — fetch Adzuna → score → persist results

**Description:** Complete worker handler: fetch Adzuna listings (cap 50), score each, insert `job_match_result` rows, update run to Complete, write `finops_json`. Handle "no listings" → Failed with clear message.

**Acceptance criteria:**
- [ ] End-to-end Adzuna-only run completes locally
- [ ] Results sorted by match_score in query default
- [ ] Run status Complete with ≥1 scored listing
- [ ] Zero listings → Failed status

**Verification:**
- [ ] Integration test with fake Adzuna + fake LLM
- [ ] GET `/runs/{id}/results` returns expected count

**Dependencies:** Task 13, Task 14, Task 12

**Files likely touched:**
- `backend/worker/handlers/analysis_run.py`, `backend/worker/pipeline.py`

**Estimated scope:** Medium

---

## Task 16: Indeed UK scraper adapter (fixture-tested parser)

**Description:** Implement `IndeedJobSource` scraping `uk.indeed.com` with HTML parser (BeautifulSoup/selectolax). Normalise to shared listing shape. Retry 2× on transient failure. **CI uses fixture HTML fragments only** — no live Indeed in unit tests.

**Acceptance criteria:**
- [ ] Parser extracts title, company, location, url, description from fixture HTML
- [ ] `fetch_listings` respects max_results=50
- [ ] Retry on timeout/5xx
- [ ] Live scrape optional behind manual smoke flag

**Verification:**
- [ ] `pytest tests/job_sources/test_indeed_parser.py` passes on fixtures
- [ ] Optional `SMOKE_INDEED=1` manual test documented in README

**Dependencies:** Task 13

**Files likely touched:**
- `backend/app/job_sources/indeed.py`
- `backend/tests/fixtures/indeed_search.html`

**Estimated scope:** Medium

---

## Task 17: Multi-source worker pipeline with retry and partial failure

**Description:** Extend worker to fetch Indeed + Adzuna in parallel or sequence, merge listings (dedupe by URL if needed), cap 50/source. Per-source retry 2×. Continue if one source fails.

**Acceptance criteria:**
- [ ] Both sources invoked per run
- [ ] Independent retry per source
- [ ] Listings from successful source scored even if other fails

**Verification:**
- [ ] Integration test: Adzuna succeeds, Indeed fails → Complete with banner metadata
- [ ] Both fail after retries → Failed

**Dependencies:** Task 15, Task 16

**Files likely touched:**
- `backend/worker/pipeline.py`

**Estimated scope:** Medium

---

## Task 18: Source-failure metadata and run outcome rules

**Description:** Persist `source_failures_json` on run record. Implement partial-success rules from PRD: ≥1 scored → Complete; 0 listings → Failed with message distinguishing empty search vs scrape failure.

**Acceptance criteria:**
- [ ] `source_failures_json` lists failed sources with reason codes
- [ ] API exposes failure metadata for UI banner
- [ ] Distinct user-facing messages for no jobs vs scrape failure

**Verification:**
- [ ] Domain unit tests for outcome matrix
- [ ] API test: partial run includes `source_failures` field

**Dependencies:** Task 17

**Files likely touched:**
- `backend/app/domain/run_outcomes.py`, `backend/app/db/models.py`

**Estimated scope:** Small

---

## Task 19: Transactional email service (magic link + run complete)

**Description:** Email port with local log adapter and production provider adapter (e.g. Resend/SendGrid). Templates for magic link and run completion with deep link to `/runs/{id}`. Wire into auth and worker completion hook.

**Acceptance criteria:**
- [ ] Magic link email sent on request (local: logged URL)
- [ ] Completion email sent when run reaches Complete
- [ ] Deep link requires sign-in as owner (no public share token)
- [ ] Secrets loaded via SecretProvider

**Verification:**
- [ ] Integration test captures email payload in fake sink
- [ ] Template snapshot test for subject/body structure

**Dependencies:** Task 5, Task 15

**Files likely touched:**
- `backend/app/services/notification_service.py`, `backend/app/adapters/email/`

**Estimated scope:** Medium

---

## Task 20: React SPA scaffold, auth pages, and API client

**Description:** Vite + React + TypeScript SPA with routing, auth context, API client (credentials include for cookies), sign-in page (Google button + magic link form), and protected route wrapper. Serve built SPA from FastAPI static mount or separate dev proxy.

**Acceptance criteria:**
- [ ] Routes: `/login`, `/dashboard` (protected)
- [ ] Google OAuth redirect works from browser
- [ ] Magic link form submits and shows "check email" state
- [ ] Unauthenticated users redirected to login

**Verification:**
- [ ] `npm run build` succeeds
- [ ] Manual browser sign-in flow against local API

**Dependencies:** Task 6

**Files likely touched:**
- `frontend/src/App.tsx`, `frontend/src/pages/Login.tsx`, `frontend/src/api/client.ts`

**Estimated scope:** Medium

---

## Task 21: Dashboard, CV wizard, run status polling, and cold-start UX

**Description:** Pages: Dashboard (CV list + run history), CV upload with title suggestion step, Job Search form (UK location picker + Remote), run detail with polling (2–5s interval) for status transitions. Cold-start warming banner when API slow to respond.

**Acceptance criteria:**
- [ ] CV upload → title suggestions displayed → select/edit title → Job Search form
- [ ] Start run → navigate to run detail → poll until Complete/Failed
- [ ] Loading/warming UI shown when health check exceeds threshold
- [ ] Quota displayed before starting run

**Verification:**
- [ ] Manual E2E against local Compose
- [ ] Component test for polling hook status updates

**Dependencies:** Task 9, Task 11, Task 20

**Files likely touched:**
- `frontend/src/pages/Dashboard.tsx`, `CvUpload.tsx`, `RunDetail.tsx`, `JobSearchForm.tsx`

**Estimated scope:** Large → split if needed; treat as one vertical slice session

---

## Task 22: Results view — sort, filters, divergence badges

**Description:** Results page: default sort Match Score desc, filters (Interview Likelihood, Job Source, min Match Score), full AI breakdown per card, divergence badges per PRD thresholds, external apply links open in new tab.

**Acceptance criteria:**
- [ ] Filters compose correctly on fixture data
- [ ] Badges: "Skills fit, seniority gap" and "Competitive profile, weak keyword fit"
- [ ] Interview Likelihood labeled as AI estimate
- [ ] Partial failure banner when `source_failures` present

**Verification:**
- [ ] Vitest component tests with fixture result sets
- [ ] Manual filter interaction

**Dependencies:** Task 21, Task 18

**Files likely touched:**
- `frontend/src/pages/Results.tsx`, `frontend/src/components/ResultCard.tsx`

**Estimated scope:** Medium

---

## Task 23: Run history, quota display, and unlimited bypass

**Description:** Dashboard shows past runs with CV name, Job Search summary, status, date. Quota widget ("2 runs left today"). Unlimited users see no cap UI. Block UI when concurrent run active.

**Acceptance criteria:**
- [ ] Run history lists all user runs with metadata
- [ ] Quota from `GET /runs/quota` displayed accurately
- [ ] Start button disabled when concurrent_blocked
- [ ] Unlimited flag hides daily cap message

**Verification:**
- [ ] Component test for quota states
- [ ] Integration test: third run in 24h shows blocked UI

**Dependencies:** Task 11, Task 21

**Files likely touched:**
- `frontend/src/components/QuotaBanner.tsx`, `RunHistory.tsx`

**Estimated scope:** Small

---

## Task 24: Admin UI (`/admin`) — search users, toggle unlimited

**Description:** Admin page at `/admin` (nav link only if `is_admin` from session/user endpoint). Search by email, toggle `is_unlimited`. API: `GET /admin/users?email=`, `PATCH /admin/users/{id}`. Audit log on toggle.

**Acceptance criteria:**
- [ ] Non-admin receives 404 on admin routes and no nav link
- [ ] Search returns matching users
- [ ] PATCH updates `is_unlimited`; audit_log entry created
- [ ] Admin bootstrap seed sets operator email `is_admin=true`

**Verification:**
- [ ] Integration test: admin toggle; non-admin 404
- [ ] Seed script documented in README

**Dependencies:** Task 6, Task 20

**Files likely touched:**
- `backend/app/api/routes/admin.py`, `backend/app/services/admin_service.py`
- `frontend/src/pages/Admin.tsx`, `backend/scripts/seed_admin.py`

**Estimated scope:** Small

---

## Task 25: Terraform bootstrap stack (remote state)

**Description:** Bootstrap Terraform in `infra/bootstrap/`: resource group, storage account for remote state (geo-redundant), container for state blob. Document one-time apply procedure. Required tags on all resources.

**Acceptance criteria:**
- [ ] Bootstrap applies cleanly in empty subscription
- [ ] Remote backend config documented for app stack
- [ ] Tags: project, env, owner, cost-center

**Verification:**
- [ ] `terraform validate` in CI
- [ ] `terraform plan` succeeds (against backend or `-backend=false` in PR)

**Dependencies:** None (can parallelize early)

**Files likely touched:**
- `infra/bootstrap/*.tf`, `infra/README.md`

**Estimated scope:** Small

---

## Task 26: Terraform application stack (ACA, Postgres, SB, Blob, KV, ACR)

**Description:** Application stack modules: PostgreSQL Flexible B1ms (private VNet), Blob Storage (public access disabled), Service Bus Basic, Key Vault, ACR Basic, Log Analytics, Container Apps Environment, API app (ingress HTTPS, min 0/max 2), Worker app (ingress disabled, KEDA Service Bus scaler). Private endpoints for Postgres, Blob, Service Bus. **No Redis.**

**Acceptance criteria:**
- [ ] All PRD Azure resources provisioned with private networking
- [ ] API public ingress only; worker ingress disabled
- [ ] KEDA scaler on queue depth configured
- [ ] PostgreSQL no public endpoint

**Verification:**
- [ ] `terraform plan` review against BUDGET.md line items
- [ ] `terraform validate` in CI

**Dependencies:** Task 25

**Files likely touched:**
- `infra/app/*.tf`, `infra/modules/*`

**Estimated scope:** Large (split module-by-module if needed)

---

## Task 27: Azure adapters (Blob, Service Bus, Key Vault) and MI wiring

**Description:** Production adapters for three ports using Azure SDK. Startup wiring from env/identity. Separate Managed Identities: API (blob RW cvs/, SB send, KV OAuth+email), Worker (blob read cvs/, SB receive, KV OpenAI+Adzuna). Non-root containers.

**Acceptance criteria:**
- [ ] Adapters pass same contract tests as local (with Azure emulator or mocked SDK)
- [ ] MI role assignments match THREAT_MODEL least privilege
- [ ] No secrets in image or Terraform state plaintext

**Verification:**
- [ ] Contract tests with mocked Azure clients
- [ ] Deployed smoke: blob put/get via API MI

**Dependencies:** Task 1, Task 26

**Files likely touched:**
- `backend/app/adapters/azure/*.py`

**Estimated scope:** Medium

---

## Task 28: GitHub Actions — PR gates (lint, test, validate, CVE scan)

**Description:** PR workflow: Python lint (ruff), pytest with Compose services, frontend lint/build/test, `terraform validate` + plan (no apply), Docker build api+worker, Trivy/Grype scan failing on Critical CVEs with fix available. Fork PRs cannot deploy.

**Acceptance criteria:**
- [ ] PR workflow runs on all branches except deploy
- [ ] Critical CVE gate blocks merge
- [ ] Tests use local adapters only (no Azure secrets in CI)
- [ ] Caching for pip/npm layers

**Verification:**
- [ ] Open test PR; all checks green
- [ ] Introduce dummy CVE test confirms gate fails

**Dependencies:** Task 0, Task 25

**Files likely touched:**
- `.github/workflows/pr.yml`, `.github/workflows/ci.yml`

**Estimated scope:** Medium

---

## Task 29: GitHub Actions — prod deploy (OIDC, SHA tags, terraform apply)

**Description:** Deploy workflow on `main` only: OIDC to Azure, build/push SHA-tagged images to ACR, `terraform apply`, update ACA revisions to new SHA. No `:latest` in prod. Immutable tags.

**Acceptance criteria:**
- [ ] OIDC federated credential scoped to repo + main branch
- [ ] Images tagged with git SHA
- [ ] ACA revisions pin to SHA tag after apply
- [ ] Workflow requires successful PR checks

**Verification:**
- [ ] Deploy to prod subscription; verify revision SHA matches commit
- [ ] Rollback procedure documented (redeploy prior SHA)

**Dependencies:** Task 26, Task 27, Task 28

**Files likely touched:**
- `.github/workflows/deploy.yml`

**Estimated scope:** Medium

---

## Task 30: Observability and FinOps alerts (Log Analytics, budgets)

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

- [ ] **Transactional email provider** — Resend, SendGrid, or Azure Communication Services? (Cost and SPF/DKIM setup)
- [ ] **Indeed scraping ethics/legal** — Confirm operator accepts scrape + Adzuna fallback for portfolio demo only
- [ ] **Google OAuth prod domains** — Exact callback URLs for ACA ingress (known after Task 26)
- [ ] **Admin operator email** — Confirm seed email for `is_admin` + `is_unlimited` bootstrap
- [ ] **UK city list source** — Static JSON in repo vs external geocoding API (prefer static for cost/simplicity)
- [ ] **SPA serving** — FastAPI static mount vs CDN on Blob (MVP: FastAPI mount is simpler)

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
