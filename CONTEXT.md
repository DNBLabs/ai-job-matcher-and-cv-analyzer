# Context

Domain glossary for the AI Job Matcher & CV Analyzer.

## 2. Scope Guardrails

### In-Scope (derived from PRD)

- Job Seeker authentication (Google OAuth + email magic link; no passwords)
- User Account with persistent session and dashboard
- Multiple named CV PDF uploads per account (encrypted at rest, user-deletable)
- Sync AI Suggested Job Titles after CV upload (OpenAI GPT-4o-mini)
- UK-scoped Job Search (role/keywords, UK city or Remote, optional filters)
- Analysis Runs: async scrape Indeed UK + fetch Adzuna API (`gb`), cap 50 listings per source
- AI scoring per listing: Match Score, Interview Likelihood, full breakdown (OpenAI GPT-4o)
- Job Match Results dashboard with sort, filters, and divergence badges
- Run status lifecycle (Queued → Scraping → Scoring → Complete / Failed) with partial success
- Dashboard polling + transactional email on run completion
- Fair-use limits (3 runs / 24h, 1 concurrent) with unlimited allowlist for selected accounts
- Basic Admin UI (`/admin`): search users by email, toggle unlimited flag (`is_admin` gate)
- FinOps logging per Analysis Run (tokens, estimated cost)
- Azure production (Container Apps, Service Bus, PostgreSQL, Blob Storage, Key Vault, Managed Identity; sessions/rate limits in PostgreSQL — no Redis)
- Cloud-agnostic application ports (`BlobStore`, `JobQueue`, `SecretProvider`) with local Docker Compose dev
- Terraform IaC + GitHub Actions deploy (OIDC to Azure)

### Out-of-Scope

- Gemini or multi-provider AI
- Countries beyond UK
- LinkedIn or additional Job Sources beyond Indeed + Adzuna
- Billing, paid tiers, or self-service unlimited upgrade
- CV auto version history (multiple named CVs cover the use case)
- Expandable lazy-load deep dive per job (full breakdown included in MVP scoring call)
- Native mobile apps (responsive web only)
- Apply-on-behalf or auto-apply to listings
- Job alerts, watchlists, or long-term listing storage beyond Analysis Run results
- Recruiter/HR multi-candidate workflows
- Empirical interview probability from historical outcome data

## 3. Security Posture

### Identity & access

- Google OAuth must validate `state` nonce on callback
- Magic links: ≥256-bit random token, single-use, 15-minute expiry; store `token_hash` only in database
- Sessions: HttpOnly + Secure + SameSite=Lax cookies; 24h idle / 7d absolute expiry; rotate on login
- All CV, run, and result endpoints require authenticated session scoped to owner `user_id`
- Cross-account resource access returns **404** (not 403)
- Email completion deep-links require sign-in as owner; no public or signed share URLs in MVP
- Admin routes (`/admin`, `PATCH is_unlimited`) require `is_admin = true` from database; never trust client flags

### Secrets

- No secrets in git, container images, or Terraform state plaintext
- Production secrets in Azure Key Vault only; loaded via Managed Identity at runtime
- API MI: Key Vault **get** on OAuth + email secrets only
- Worker MI: Key Vault **get** on OpenAI + Adzuna secrets only
- OpenAI API: zero-retention / no-training configuration; policy documented and verified at deploy

### Data & logging

- Never log CV content, parsed text, or full LLM prompts
- FinOps logs `prompt_tokens`, `completion_tokens`, and estimated `$` only
- CV PDFs encrypted at rest in Blob Storage; parsed text in PostgreSQL
- Append-only `audit_log` for admin toggles and auth events (login success/failure, magic-link requested)

### Upload & processing

- Accept PDF only: MIME + magic-byte validation, max **5 MB**
- Safe PDF parse: page limit, **30s timeout**, text extraction only; no JS/render/execute
- Blob keys: `cvs/{user_id}/{uuid}.pdf` — no sequential or guessable paths
- CV download served as `Content-Disposition: attachment`; no inline PDF render in browser

### Network & exposure

- PostgreSQL: private VNet access only; **no public endpoint**
- Blob Storage: **public access disabled**; MI-only access
- Service Bus: private endpoint; no internet exposure
- API Container App: public **HTTPS ingress only**
- Worker Container App: **ingress disabled** (outbound only)

### Runtime & IAM

- Separate Managed Identities for API and Worker with least privilege (see THREAT_MODEL.md §2)
- API MI: Blob read/write/delete on `cvs/` prefix; Service Bus send; DB CRUD
- Worker MI: Blob **read-only** on `cvs/` prefix; Service Bus receive; DB read/write runs and results only (no admin fields)
- Containers run as **non-root** user (UID 10001)

### Abuse & availability

- Magic-link: max **3 requests per email per hour**, **10 per IP per hour**
- API ingress rate limit: ~**100 requests/minute/IP**
- Run quota: **3 runs / rolling 24h** per account; **1 concurrent active run** (applies to unlimited allowlist too)
- Alert on OpenAI daily spend threshold and sustained Service Bus queue depth

### Supply chain & CI/CD

- GitHub Actions → Azure via **OIDC only**; no long-lived Azure credentials in GitHub
- Production deploy workflow runs on **`main` branch only**; PR workflows plan/test/validate only
- Deploy immutable **SHA-tagged** container images; never `:latest` in production
- CI fails on Critical container CVEs with a published fix

### Resolved decisions

- **2026-06-05:** Threat model accepted — STRIDE grilling complete; see `docs/security/THREAT_MODEL.md`
- **2026-06-05:** FinOps budget accepted — Profile A traffic, £75/mo cap, scale-to-zero ACA; see `docs/finance/BUDGET.md`
- **2026-06-05:** Final architecture accepted — PostgreSQL-only sessions/rate limits (Redis eliminated); see `docs/adr/FINAL_ARCHITECTURE.md`
- **2026-06-05:** CV demo mode — keep prod stack deployed with scale-to-zero ACA (~£40–55/mo); loading UI for cold start; `terraform destroy` only off-season when demo URL removed from CV
- **2026-06-11:** Transactional email transport — **Microsoft 365 shared mailbox via Graph API** (`sendMail`), authenticated by Container App **Managed Identity** (no stored API key), replacing Resend. `Mail.Send` application permission **must** be scoped to the single shared mailbox via an Exchange Online **Application Access Policy**. From = shared mailbox address. See "Run Notification" §Email delivery and IMPLEMENTATION_PLAN Open Questions / Task 27.

## 4. Financial Guardrails

### Budget

- Monthly ceiling: **£75 hard**; soft alert at **£60 (80%)** via Azure Cost Management
- Exceed policy: alert + manual review; **no automatic teardown**
- Planning target at current traffic: **~£55–72/month** (mid-range ~£68)

### Scaling & idle

- API Container App: `minReplicas=0`, `maxReplicas=2`
- Worker Container App: `minReplicas=0`, `maxReplicas=2`; scale on Service Bus queue depth (KEDA)
- Scale-to-zero: **allowed** for API and worker — cold start (30–60s) accepted for solo demo traffic
- OpenAI: hard product cap **100 scoring calls/run**; org daily spend alert at **£2/day**

### Teardown

- Trigger: no demo or active users for **30 consecutive days**
- Procedure: `terraform destroy` application stack, then bootstrap; export CVs if needed — see `docs/finance/BUDGET.md` §4

### Tagging & accountability

- Required tags: `project=ai-job-matcher`, `env=prod`, `owner=<operator-email>`, `cost-center=portfolio`
- Cost owner: operator (portfolio subscription)

### Monitoring

- Azure budget alert: 80% and 100% of £75
- OpenAI daily spend alert: £2/day (~80% of monthly OpenAI allowance)
- Service Bus queue depth alert: sustained &gt;10 messages for 15 minutes
- Review cadence: after first invoice; on public launch; quarterly tag/SKU check

## Users

### Job Seeker
An individual looking for employment who uploads their own CV to discover which open roles they should apply to. The primary persona; all product decisions optimize for this actor.

**Example:** Alex uploads a 2-page PDF CV, signs in, returns later to a dashboard showing a ranked list of matching jobs with scores and interview-likelihood estimates, then clicks through to apply on the original job board.

### User Account
A persistent identity that owns uploaded CVs and Analysis Run history. Required to retrieve async results after leaving the site.

**Sign-in (MVP):** Google OAuth (primary) and email magic link (fallback). No passwords.

## Data & Privacy

### CV
A Job Seeker's uploaded PDF resume. Stored encrypted at rest, tied to a User Account. A User Account may hold **multiple named CVs** (e.g. "React-focused", "General"); Alex selects which CV to use when starting each Analysis Run. Uploading a new CV does not replace existing ones.

**Deletion:** Alex may delete a CV at any time. Deletion removes the encrypted PDF and cached parsed text immediately. Past Analysis Runs tied to that CV are retained on the dashboard (job title, company, link, Match Score, Interview Likelihood, Job Search criteria) — Alex cannot re-run with a deleted CV and must upload a new one to run again.

## Outcomes

### Analysis Run
A single end-to-end pipeline execution comprising: CV upload → optional title suggestions → Job Search criteria → scrape job boards → evaluate each listing → return ranked results with Match Scores and Interview Likelihood ratings.

**Done** for the Job Seeker means receiving a ranked list of scraped jobs with Match Scores and Interview Likelihood ratings, with links back to the original postings.

### Run Notification
How a Job Seeker learns an Analysis Run has finished:

- **Dashboard polling** — while on-site, the UI polls run status (`Queued` → `Scraping` → `Scoring` → `Complete`).
- **Email** — on completion, one transactional email with a deep link to results (covers the "come back later" case).

Both channels are required for MVP.

**Email delivery (prod requirement):** Transactional email (magic link + run-complete) is sent from a **Microsoft 365 shared mailbox via the Graph API** (`POST /users/{mailbox}/sendMail`). `EMAIL_FROM` is the shared mailbox address; SPF/DKIM/DMARC are already established on the M365 domain, so deliverability does not depend on warming a new sender domain. The Container App authenticates to Graph with its **Managed Identity** — no API key is stored. **Least privilege:** the app's `Mail.Send` *application* permission grants send-as-any-mailbox by default and **must** be constrained to only the shared mailbox with an Exchange Online **Application Access Policy** (`New-ApplicationAccessPolicy`). Verify at build time that app-only `sendMail` to the shared mailbox does not require a per-mailbox licence. Plan a post-deploy real-inbox deliverability check. Local dev uses the `log` adapter (no actual send); sign-in is completed with a minted verify link.

### Job Search
The set of criteria a Job Seeker defines to scope which listings workers scrape: role/keywords, location (or remote), and optional filters (experience level, employment type). One Analysis Run pairs one CV with one Job Search.

**Geographic scope (MVP):** UK only. Location picker offers UK cities plus "Remote." Job Source adapters target Adzuna `gb` and Indeed UK (`uk.indeed.com`).

### Job Source
A pluggable adapter that fetches job listings from a specific board or API. MVP includes exactly two Job Sources:

- **Indeed** — scraped by background workers (demonstrates async scraping, queue depth, worker scaling).
- **Adzuna** — fetched via official API (legal, predictable fallback when scraping fails or rate-limits).

Workers cap listings per source per Analysis Run (e.g. top 50) to control AI API cost. Additional sources are out of MVP scope but must be addable without rewrites.

## AI & Cost

### AI Scoring
Each scraped listing is evaluated by a large language model that returns a structured response: Match Score (0–100) and Interview Likelihood (`High` / `Medium` / `Low`).

### AI Task Split (MVP)
OpenAI only for MVP; Gemini deferred post-MVP.

| Step | Model tier | When |
|---|---|---|
| Suggested Job Titles | Fast/cheap (e.g. GPT-4o-mini) | Sync, immediately after CV upload |
| Per-job scoring | Strong (e.g. GPT-4o) | Async, during Analysis Run |

### FinOps (per run)
Each Analysis Run logs `prompt_tokens`, `completion_tokens`, and estimated cost (`$`) per AI step. Listing caps per Job Source enforce a hard cost ceiling.

## Infrastructure

### Deployment Target (MVP)
**Azure** — production runs on Azure Container Apps (API + worker services), Azure Service Bus (job queue), Azure Database for PostgreSQL Flexible Server (sessions, rate limits, and app data), Azure Blob Storage (CV PDFs), Azure Key Vault (secrets), Managed Identity for least-privilege PII access.

### Cloud-Agnostic Application Code
Application logic must not depend on Azure SDKs directly. Infrastructure is Azure-specific (Terraform); code talks to narrow internal interfaces (`BlobStore`, `JobQueue`, `SecretProvider`) with swappable adapters:

| Interface | Azure (prod) | Local dev |
|---|---|---|
| `BlobStore` | Blob Storage | Azurite or MinIO |
| `JobQueue` | Service Bus | RabbitMQ or in-process |
| `SecretProvider` | Key Vault | `.env` / Docker secrets |
| Database | PostgreSQL | PostgreSQL (Docker Compose) |

Containers are standard Docker images deployable to any host. No Azure-only APIs in domain/worker code.

### Suggested Job Titles
AI-generated role title recommendations derived from reading a Job Seeker's CV (e.g. "Frontend Developer", "React Engineer", "UI Engineer"). Produced synchronously immediately after CV upload, before scraping begins. Alex selects one title to pre-fill the Job Search role field, ignores suggestions and types their own, or edits the pre-filled value. Suggestions are non-binding; Alex must confirm Job Search criteria and explicitly start the Analysis Run.

## Scoring

### Match Score
A 0–100 numeric score measuring how well a Job Seeker's CV aligns with a job listing's requirements (skills, experience, keywords). Pure fit metric; not a hiring outcome prediction.

### Interview Likelihood
A categorical estimate (`High`, `Medium`, `Low`) of whether the Job Seeker is likely competitive enough to pass initial screening for a given listing. Produced by AI reasoning over seniority fit, skill gaps, and red flags. An *estimate*, not a statistical probability — UI must not imply guaranteed outcomes.

### Job Match Result
One scraped listing evaluated against a CV within an Analysis Run. Each result includes:

- Job title, company, source (Indeed / Adzuna), link to original posting
- **Match Score** (0–100)
- **Interview Likelihood** (`High` / `Medium` / `Low`)
- **Full AI breakdown:** matched skills, skill gaps, red flags, suggested talking points for an application or interview

All breakdown fields are produced in a single structured scoring call per listing (no lazy-load / second API call).

## Usage Limits

### Run Quota
Each User Account may start **3 Analysis Runs per rolling 24 hours** and may have **1 concurrent active run** at a time. The UI shows remaining quota (e.g. "2 runs left today").

### Unlimited Allowlist
Specific User Accounts (friends/family) may be flagged as **unlimited** — exempt from the daily run cap. Managed via a **basic Admin UI** (MVP): search user by email, toggle unlimited on/off. Not self-service; no billing tiers for MVP.

### Results View
Job Match Results for a completed Analysis Run are shown sorted by **Match Score descending** by default. Alex may filter by Interview Likelihood (`High` / `Medium` / `Low`), Job Source (Indeed / Adzuna), and minimum Match Score. When Match Score and Interview Likelihood diverge meaningfully (e.g. strong skills fit but seniority gap), the UI surfaces a short badge (e.g. "Skills fit, seniority gap").

### Run Failure & Partial Success
Workers **retry each Job Source up to 2 times** on transient failure (rate limit, timeout).

| Outcome | Status | Alex sees |
|---|---|---|
| ≥1 listing scraped and scored | `Complete` | Results list; banner if any source failed (e.g. "Indeed unavailable — showing 42 results from Adzuna") |
| 0 listings after all retries | `Failed` | Clear message distinguishing "No jobs found for this search" from "Scraping failed — try again later" |

FinOps logs cost for whatever AI steps actually ran, including partial runs.

## MVP Scope

### Out of Scope (deferred)
- Gemini / multi-provider AI
- Countries beyond UK
- LinkedIn scraping
- Billing / paid tiers
- CV auto version history
- Expandable per-job deep dive (full breakdown already included)
- Mobile-native app (responsive web only)
- Apply-on-behalf / auto-apply
- Job alerts / long-term listing watchlists

## Admin

### Admin User
A User Account with `is_admin = true`, bootstrapped via DB seed for the operator's email. Admins sign in with the same Google OAuth / magic-link flow as Job Seekers; no separate admin login.

### Admin UI (MVP)
Route: `/admin` (visible in nav only for Admin Users). Capabilities:

- Search users by email
- Toggle **unlimited** allowlist flag on/off

No billing, analytics dashboard, or content moderation in MVP.
