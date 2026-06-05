# PRD: AI Job Matcher & CV Analyzer (MVP)

## Problem Statement

Job Seekers applying for roles in the UK spend hours searching job boards and manually comparing each listing against their CV. They lack a clear view of which roles they fit best, whether they are competitive enough to pass initial screening, and what specific gaps or talking points to address before applying. Existing tools often reduce everything to a single misleading "match percentage" or require pasting individual job descriptions by hand rather than discovering opportunities at scale.

## Solution

A web application where a Job Seeker signs in, uploads one or more named CV PDFs, receives AI-generated Suggested Job Titles, defines a UK-scoped Job Search, and starts an Analysis Run. Background workers scrape Indeed UK and fetch listings from the Adzuna API, then score each listing with a dual-score model (Match Score + Interview Likelihood) and a full AI breakdown. Results appear on a dashboard sorted and filterable by score and likelihood, with links back to original postings. The Job Seeker is notified by email when async runs complete and can return later via their User Account. Operators manage fair-use exceptions through a basic Admin UI.

---

## User Stories

### Authentication & Account

1. As a Job Seeker, I want to sign in with Google OAuth, so that I can access my account quickly without creating a password.
2. As a Job Seeker, I want to sign in with an email magic link, so that I can use the app if I prefer not to OAuth with Google.
3. As a Job Seeker, I want my session to persist across browser visits, so that I can return to my dashboard without signing in every time.
4. As a Job Seeker, I want to sign out, so that I can protect my account on shared devices.
5. As a new Job Seeker, I want an account created automatically on first successful sign-in, so that I do not need a separate registration step.

### CV Management

6. As a Job Seeker, I want to upload a PDF CV with a custom name, so that I can keep multiple tailored versions (e.g. "React-focused", "General").
7. As a Job Seeker, I want to view a list of my saved CVs with upload dates, so that I know which versions I have available.
8. As a Job Seeker, I want to upload a new CV without replacing existing ones, so that I can maintain multiple versions for different role types.
9. As a Job Seeker, I want to delete a CV, so that I can remove PII I no longer want stored.
10. As a Job Seeker, I want confirmation before CV deletion, so that I do not accidentally remove a file.
11. As a Job Seeker, I want past Analysis Runs to remain visible after I delete a CV, so that I can still access job links and scores from previous searches.
12. As a Job Seeker, I want to be unable to re-run an Analysis Run with a deleted CV, so that the system does not reference removed PII.
13. As a Job Seeker, I want my CV stored encrypted at rest, so that my sensitive personal data is protected.

### Suggested Job Titles

14. As a Job Seeker, I want AI to suggest 3–5 job titles after I upload a CV, so that I know which role keywords fit my experience.
15. As a Job Seeker, I want each suggested title to include a brief rationale, so that I understand why it was recommended.
16. As a Job Seeker, I want title suggestions returned within a few seconds, so that I am not waiting for a full Analysis Run.
17. As a Job Seeker, I want to select a suggested title to pre-fill my Job Search, so that I can start searching faster.
18. As a Job Seeker, I want to ignore suggestions and type my own role keywords, so that I stay in control of my search intent.
19. As a Job Seeker, I want to edit a pre-filled title before starting a run, so that I can refine the suggestion.

### Job Search & Analysis Run

20. As a Job Seeker, I want to define a Job Search with role/keywords, UK location or Remote, and optional filters (experience level, employment type), so that scraped listings match my intent.
21. As a Job Seeker, I want to select which saved CV to use when starting an Analysis Run, so that I can compare how different CVs perform against the same search.
22. As a Job Seeker, I want to explicitly confirm and start an Analysis Run, so that expensive scraping and AI scoring never happen without my consent.
23. As a Job Seeker, I want to see my remaining daily run quota, so that I know how many searches I have left.
24. As a Job Seeker, I want to be blocked from starting a new run while one is in progress, so that the system stays predictable and costs are controlled.
25. As a Job Seeker, I want to be blocked from starting more than 3 runs in a rolling 24-hour period, so that fair-use limits are enforced unless I am on the unlimited allowlist.
26. As a Job Seeker on the unlimited allowlist, I want no daily run cap, so that I can use the product freely as an invited user.

### Run Status & Notifications

27. As a Job Seeker, I want to see Analysis Run status progress through Queued → Scraping → Scoring → Complete (or Failed), so that I know what the system is doing.
28. As a Job Seeker, I want the dashboard to poll for status updates while I am on the page, so that I see progress without manually refreshing.
29. As a Job Seeker, I want to receive an email when my Analysis Run completes, so that I can leave the site and return later via the link.
30. As a Job Seeker, I want the completion email to deep-link directly to my results, so that I can act on matches immediately.
31. As a Job Seeker, I want a clear failure message when a run finds zero jobs, so that I know whether to broaden my search or retry later.
32. As a Job Seeker, I want failure messages to distinguish "no jobs found" from "scraping failed", so that I know the appropriate next step.
33. As a Job Seeker, I want a banner on partial results when one Job Source failed, so that I understand incomplete coverage (e.g. "Indeed unavailable — showing results from Adzuna").

### Results & Scoring

34. As a Job Seeker, I want to see a ranked list of Job Match Results sorted by Match Score descending by default, so that the best-fitting roles appear first.
35. As a Job Seeker, I want each result to show job title, company, Job Source, and a link to the original posting, so that I can apply on the source board.
36. As a Job Seeker, I want each result to show a Match Score (0–100), so that I can compare requirement alignment across listings.
37. As a Job Seeker, I want each result to show Interview Likelihood (High / Medium / Low), so that I can gauge competitiveness separate from skills fit.
38. As a Job Seeker, I want Interview Likelihood labeled as an AI estimate rather than a guarantee, so that I am not misled about outcomes.
39. As a Job Seeker, I want a full AI breakdown per result (matched skills, skill gaps, red flags, talking points), so that I can tailor my application or interview prep.
40. As a Job Seeker, I want to filter results by Interview Likelihood, so that I can focus on roles where I am most competitive.
41. As a Job Seeker, I want to filter results by Job Source (Indeed / Adzuna), so that I can compare coverage across boards.
42. As a Job Seeker, I want to filter results by minimum Match Score, so that I can hide low-fit listings.
43. As a Job Seeker, I want a badge when Match Score and Interview Likelihood diverge (e.g. "Skills fit, seniority gap"), so that I notice roles that look good on paper but may be risky to pursue.
44. As a Job Seeker, I want to view past Analysis Runs from my dashboard, so that I can revisit previous searches.
45. As a Job Seeker, I want to see which CV and Job Search criteria were used for each past run, so that I can reproduce or refine searches.

### Admin

46. As an Admin User, I want to access an Admin UI at `/admin`, so that I can manage allowlisted users.
47. As an Admin User, I want the admin nav link visible only when I have `is_admin = true`, so that regular Job Seekers do not see operator tools.
48. As an Admin User, I want to search User Accounts by email, so that I can find friends/family to grant unlimited access.
49. As an Admin User, I want to toggle the unlimited allowlist flag on a user, so that I can grant or revoke uncapped run access.
50. As an Admin User, I want to sign in with the same Google OAuth / magic-link flow as Job Seekers, so that there is no separate admin password system.

### Portfolio / Operational (implicit Job Seeker benefit)

51. As a Job Seeker, I want Analysis Runs to complete reliably even when one Job Source fails, so that I still receive useful results.
52. As a Job Seeker, I want the system to retry failed Job Source fetches automatically, so that transient rate limits do not unnecessarily fail my run.

---

## Implementation Decisions

### Major Modules (deep modules first)

The codebase is greenfield. Modules below are ordered by dependency. Each **deep module** exposes a narrow, stable interface hiding volatile details (HTML scraping, cloud SDKs, LLM prompts).

| Module | Responsibility | Deep-module? |
|---|---|---|
| **Domain core** | Entities: User Account, CV, Job Search, Analysis Run, Job Match Result, Run status state machine, quota rules | Yes |
| **Infrastructure ports** | `BlobStore`, `JobQueue`, `SecretProvider` interfaces + Azure/local adapters | Yes |
| **Auth service** | Google OAuth, magic-link issuance/verification, session/JWT, `is_admin` gate | Yes |
| **CV service** | Upload validation (PDF only, size cap), encrypted storage, parse-to-text, delete-with-retain-runs | Yes |
| **Title suggestion service** | Sync OpenAI call (GPT-4o-mini), structured title+rationale response | Yes |
| **Job Source registry** | Pluggable adapters: `IndeedJobSource` (scrape), `AdzunaJobSource` (API), normalised listing shape | Yes |
| **Analysis orchestrator** | Enqueue run, enforce quota/concurrency, transition run status, partial-success rules | Yes |
| **Worker pipeline** | Consume queue messages: fetch listings (retry 2× per source, cap 50/source) → score each listing → persist results → notify | Yes |
| **Scoring service** | OpenAI GPT-4o structured JSON scoring, schema validation, 1 retry on malformed output, FinOps token/cost logging | Yes |
| **Notification service** | Transactional email (magic link + run complete), template rendering | Moderate |
| **Admin service** | Email search, toggle unlimited flag | Shallow (thin over user repo) |
| **API layer (FastAPI)** | REST endpoints, auth middleware, request validation, error mapping | Boundary |
| **Web app (React)** | Dashboard, CV management, run wizard, results view with filters, admin page | Boundary |
| **Terraform (Azure)** | ACA, Service Bus, PostgreSQL, Blob, Redis, Key Vault, Managed Identity | IaC only |

### Analysis Run state machine

```
Queued → Scraping → Scoring → Complete
                           ↘ Failed (zero listings after retries)
```

Partial success: if ≥1 listing scored, status is `Complete` with optional per-source failure metadata on the run record.

### Infrastructure ports (ADR-0002)

Application code must not import Azure SDKs in domain or worker logic.

- **`BlobStore`**: `put(key, bytes)`, `get(key) → bytes`, `delete(key)`
- **`JobQueue`**: `publish(message)`, `consume(handler)` — message payload is `analysis_run_id`
- **`SecretProvider`**: `get(secret_name) → str`

Adapters: Azure (Blob Storage, Service Bus, Key Vault) for production; Azurite/MinIO, RabbitMQ or in-process queue, `.env` for local Docker Compose.

### Job Source adapter interface (ADR-0001)

```
fetch_listings(job_search, max_results=50) → list[NormalisedListing]
```

`NormalisedListing`: `external_id`, `source` (indeed | adzuna), `title`, `company`, `location`, `url`, `description_text`, `posted_at?`

- **Indeed UK**: worker HTTP scrape of `uk.indeed.com`; retry up to 2× on transient failure.
- **Adzuna**: REST API with `country=gb`; retry up to 2× on transient failure.

### Dual-score JSON schema (ADR-0003)

Scoring service returns validated JSON per listing:

```json
{
  "match_score": 0,
  "interview_likelihood": "high",
  "matched_skills": ["string"],
  "skill_gaps": ["string"],
  "red_flags": ["string"],
  "talking_points": ["string"]
}
```

`match_score`: integer 0–100. `interview_likelihood`: enum `high` | `medium` | `low`. Malformed LLM output: retry once, then mark listing as scoring-failed (log, skip, do not fail entire run unless all listings fail).

### Divergence badge logic

When `match_score >= 70` and `interview_likelihood == low`, surface badge **"Skills fit, seniority gap"**. When `match_score < 50` and `interview_likelihood == high`, surface **"Competitive profile, weak keyword fit"**. Additional rules can be added as static thresholds — no second AI call.

### Data model (PostgreSQL)

**user_account**: `id`, `email`, `google_sub?`, `is_admin`, `is_unlimited`, `created_at`

**cv**: `id`, `user_id`, `name`, `blob_key`, `parsed_text?`, `uploaded_at`, `deleted_at?`

**analysis_run**: `id`, `user_id`, `cv_id`, `status`, `job_search_json`, `source_failures_json?`, `finops_json`, `created_at`, `completed_at?`

**job_match_result**: `id`, `analysis_run_id`, `source`, `external_id`, `title`, `company`, `url`, `match_score`, `interview_likelihood`, `breakdown_json`, `created_at`

**magic_link_token**: `id`, `email`, `token_hash`, `expires_at`, `used_at?`

Quota enforcement: count `analysis_run` rows for `user_id` where `created_at > now() - 24h` and status not cancelled; skip if `is_unlimited`. Concurrency: reject new run if any run for user in `Queued | Scraping | Scoring`.

### API contracts (REST, JSON)

Auth:
- `GET /auth/google/login`, `GET /auth/google/callback`
- `POST /auth/magic-link` `{ email }`, `GET /auth/magic-link/verify?token=`
- `POST /auth/logout`

CVs:
- `GET /cvs`, `POST /cvs` (multipart PDF + name), `DELETE /cvs/{id}`
- `POST /cvs/{id}/suggest-titles` → `{ titles: [{ title, rationale }] }`

Analysis Runs:
- `GET /runs`, `GET /runs/{id}`, `GET /runs/{id}/results`
- `POST /runs` `{ cv_id, job_search: { role, location, remote, filters? } }`
- `GET /runs/quota` → `{ remaining, concurrent_blocked }`

Admin (requires `is_admin`):
- `GET /admin/users?email=`, `PATCH /admin/users/{id}` `{ is_unlimited: bool }`

All Job Seeker endpoints require authenticated session except auth callbacks.

### AI & FinOps

- Title suggestions: GPT-4o-mini, sync, log tokens/cost on CV record or separate audit row.
- Scoring: GPT-4o, async per listing, aggregate into `analysis_run.finops_json`: `{ title_suggestion: {...}, scoring: { total_prompt_tokens, total_completion_tokens, estimated_usd } }`.
- Hard cap: 50 listings × 2 sources = max 100 scoring calls per run.

### Email

Single transactional provider for magic links and run-complete notifications. Templates include deep links to `/runs/{id}`.

### Security

- CV PDFs in encrypted Blob Storage; API never logs CV content.
- Workers access Blob via Managed Identity (prod) with read-only scope for CV keys referenced by active jobs.
- Input validation at API boundary: PDF MIME/size, email format, job search field length limits, enum validation for filters.
- Admin routes gated by `is_admin` from DB, not client-supplied flags.

### Frontend (React)

Pages: Sign-in, Dashboard (CV list + run history), CV upload + title suggestion step, Job Search form, Run detail (status polling), Results (sort/filter), Admin.

Responsive web only; no native app.

### Deployment

- Docker images: `api`, `worker` (shared domain package, different entrypoints).
- Azure Container Apps: separate apps for API and worker; worker scales on Service Bus queue depth (KEDA).
- Local: `docker compose up` — API, worker, Postgres, RabbitMQ, Azurite/MinIO.
- Terraform modules for Azure resources; GitHub Actions for build/deploy (OIDC to Azure).

---

## Testing Decisions

### What makes a good test

- Test **observable behavior** at module boundaries: given inputs, assert outputs and side effects on ports — not internal call order or private methods.
- Prefer **fake implementations** of `BlobStore`, `JobQueue`, `JobSource`, and LLM client over mocks that mirror implementation.
- Integration tests use Docker Compose local adapters; no Azure required in CI.
- Do not snapshot raw HTML from Indeed in unit tests — use recorded fixture fragments.

### Modules to test (recommended)

| Module | Test type | Rationale |
|---|---|---|
| **Domain core** (quota, run state machine, partial-success rules) | Unit | Pure logic; high value, no I/O |
| **Scoring service** (JSON schema validation, retry-on-malformed) | Unit | Critical correctness; use fake LLM returning valid/invalid JSON |
| **Job Source adapters** (normalisation) | Unit | Indeed/Adzuna mapping from fixtures; no live network in CI |
| **Analysis orchestrator** | Unit + integration | Quota/concurrency enforcement with fake queue and repo |
| **CV service** | Integration | Upload/delete lifecycle against fake BlobStore |
| **Auth service** | Integration | Magic-link expiry and single-use semantics |
| **Infrastructure ports** | Contract tests | Local adapters honour same semantics as Azure adapters |
| **API layer** | Integration (httpx/pytest) | End-to-end request/response for happy paths and 403/429 quota |
| **React results view** | Component tests | Filter/sort/badge rendering from fixture result sets |

### Modules deprioritised for automated test in MVP

- **Indeed live scraper** — manual/smoke only; too brittle for CI; unit-test parser against fixtures.
- **Terraform** — `terraform validate` + plan in CI; not unit-tested in application test suite.
- **Email templates** — snapshot subject/body in one integration test; no live send in CI.

### Prior art

Greenfield — no existing test patterns in repo. Follow pytest + httpx for API, Vitest + React Testing Library for frontend, consistent with common FastAPI/React conventions.

---

## Out of Scope

Per `CONTEXT.md` and ADRs:

- Gemini or multi-provider AI
- Countries beyond UK
- LinkedIn or additional Job Sources beyond Indeed + Adzuna
- Billing, paid tiers, or self-service unlimited upgrade
- CV auto version history (multiple named CVs cover the use case)
- Expandable lazy-load deep dive per job (full breakdown included in MVP scoring call)
- Native mobile apps
- Apply-on-behalf or auto-apply to listings
- Job alerts, watchlists, or long-term listing storage beyond Analysis Run results
- Recruiter/HR multi-candidate workflows
- Empirical interview probability from historical outcome data

---

## Further Notes

### Related documents

- Domain glossary: `CONTEXT.md`
- ADR-0001: Hybrid Job Sourcing (Indeed + Adzuna)
- ADR-0002: Azure Production with Cloud-Agnostic Ports
- ADR-0003: Dual-Score Model (Match Score + Interview Likelihood)

### Suggested implementation order (vertical slices)

1. Infrastructure ports + Docker Compose + domain models + Postgres migrations
2. Auth (Google + magic link) + User Account
3. CV upload/delete + title suggestion (sync)
4. Analysis Run creation + queue + worker skeleton (status transitions)
5. Adzuna adapter → scoring → results API (API-only path first)
6. Indeed adapter + partial failure handling
7. Email notifications + dashboard polling UI
8. Results filters, badges, quota UI
9. Admin UI + unlimited allowlist
10. Terraform + Azure Container Apps deploy + worker autoscale

### Admin bootstrap

Seed `is_admin = true` and `is_unlimited = true` for operator email via migration or seed script.

### Open technical risks

- Indeed scraper brittleness (mitigated by Adzuna fallback per ADR-0001)
- OpenAI cost at 100 listings/run — mitigated by quota (3/day) and 50/source cap
- Magic-link email deliverability — use reputable transactional provider; SPF/DKIM in prod
