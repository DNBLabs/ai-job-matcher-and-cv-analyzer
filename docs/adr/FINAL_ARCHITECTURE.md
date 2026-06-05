# AI Job Matcher & CV Analyzer — Final Architecture

> Status: Accepted  
> Last updated: 2026-06-05  
> Source: CONTEXT.md (Scope Guardrails, Security Posture, Financial Guardrails), docs/PRD.md, docs/security/THREAT_MODEL.md, docs/finance/BUDGET.md, docs/architecture/DIAGRAMS.md

---

## 1. Executive Summary & Problem Statement

UK Job Seekers spend hours manually comparing CVs against job listings and lack a clear view of skills fit versus screening competitiveness. The product solves this by letting a signed-in Job Seeker upload named CV PDFs, receive AI Suggested Job Titles, define a UK-scoped Job Search, and start an **Analysis Run** that asynchronously scrapes Indeed UK and fetches Adzuna listings, scores each job with **Match Score** and **Interview Likelihood**, and returns a ranked, filterable dashboard with full AI breakdowns and links to original postings.

The architecture delivers that outcome on **Azure Container Apps** with a **cloud-agnostic application core** (port/adapter pattern), **Terraform GitOps**, **GitHub Actions OIDC deploy**, and a **£75/month hard FinOps ceiling** tuned for solo portfolio demo traffic (Profile A: 1–3 users, 10–30 runs/month). Security treats CVs as high-sensitivity PII: private data plane, separate Managed Identities, zero-retention OpenAI, and owner-only access with 404 on cross-account IDs.

---

## 2. The Final Tech Stack & "The Why"

| Layer | Choice | Rationale |
|-------|--------|-----------|
| **Compute** | Azure Container Apps — API + Worker (separate apps) | Serverless containers with KEDA scale on Service Bus queue depth; API public HTTPS ingress, worker ingress disabled; `minReplicas=0` / `maxReplicas=2` fits Profile A and £75 cap |
| **State / IaC** | Terraform + Azure Storage remote backend | Declarative prod stack in git; bootstrap stack for state; no secrets in state; operator-controlled `terraform apply` via GitHub Actions on `main` |
| **Ingress** | ACA built-in HTTPS ingress (API only) | Sufficient for MVP demo traffic; dedicated WAF/Front Door deferred to save ~£15–35/mo; ingress rate limits (~100 req/min/IP) per security posture |
| **CI/CD** | GitHub Actions → Azure via OIDC | No long-lived Azure credentials in GitHub; PR workflows plan/test/validate only; prod deploy from `main` with immutable SHA-tagged images |
| **Observability** | ACA platform logs → Log Analytics workspace (cost-capped ingestion) + Azure Cost Management + OpenAI org spend alerts | Covers queue depth, 5xx, auth anomalies, and FinOps without a separate Prometheus/Grafana stack; aligns with single-operator Day 2 burden |

### Stack narrative

The **FastAPI + React SPA API** handles auth, CV upload, sync title suggestions (GPT-4o-mini), run orchestration, and dashboard reads. It enqueues work to **Azure Service Bus** and persists state in **PostgreSQL Flexible Server (Burstable B1ms)** — including **sessions and rate-limit counters** (no Redis). The **worker Container App** consumes queue messages, reads CV PDFs from **Blob Storage** via read-only Managed Identity, scrapes Indeed / calls Adzuna, scores listings with GPT-4o, writes results and FinOps metadata, and triggers completion email. **Key Vault** supplies secrets to API and Worker via split Managed Identities. Local development uses Docker Compose with Azurite/MinIO, RabbitMQ or in-process queue, and `.env` secrets — same domain code, different adapters.

---

## 3. Implementation of the Four Pillars

### Velocity (DevOps)

- **Pipeline:** PR → lint, unit tests, `terraform validate/plan`, container build, Critical CVE gate → merge to `main` → build/push SHA-tagged `api` and `worker` images to ACR → `terraform apply` → ACA revision update.
- **Reproducible infrastructure:** Application stack Terraform modules (ACA, Service Bus, PostgreSQL, Blob, Key Vault, ACR, Log Analytics); bootstrap stack for remote state; required tags on all resources (`project`, `env`, `owner`, `cost-center`).
- **Developer experience:** `docker compose up` boots API, worker, PostgreSQL, queue emulator, and blob emulator; integration tests against local adapters; operator warms API URL before demos to mask scale-to-zero cold start (30–60s).

### Security (DevSecOps)

- **Identity & access:** Google OAuth with `state` validation; magic links (≥256-bit, single-use, 15 min, hash-only storage); HttpOnly + Secure + SameSite=Lax sessions (24h idle / 7d absolute); owner-scoped queries with **404 on IDOR**; `/admin` gated by `is_admin` from DB.
- **Secrets:** Azure Key Vault only in prod; API MI → OAuth + email secrets; Worker MI → OpenAI + Adzuna; no secrets in git, images, or Terraform state plaintext.
- **Network & data:** PostgreSQL, Blob, Service Bus on private endpoints; Blob public access disabled; CV PDFs encrypted at rest under `cvs/{user_id}/{uuid}.pdf`; PDF upload validation (MIME, magic bytes, 5 MB, safe parse 30s timeout); zero-retention OpenAI API; never log CV content or full prompts.
- **Pipeline gates:** OIDC federated credential restricted to repo + `main`; fork PRs cannot deploy prod; container scan fails on Critical CVEs with published fix; non-root containers (UID 10001).

### Cost (FinOps)

- **Budget ceiling:** **£75/month hard**; soft alert at **£60 (80%)**; exceed policy = alert + manual review (no auto-teardown).
- **Auto-scaling boundaries:** API and Worker `minReplicas=0`, `maxReplicas=2`; worker KEDA on Service Bus queue depth; OpenAI hard cap **100 scoring calls/run**; org daily spend alert **£2/day**.
- **Waste eradication:** Scale-to-zero ACA (compute idles; data plane stays up); ACR retain last 5 SHA tags; **PostgreSQL-only** session/rate-limit store eliminates Redis Basic C0 (~£12–15/mo savings). **Full `terraform destroy`** only when the project is intentionally paused (not while a live demo URL is on CV).
- **Cost alerting:** Azure budget 80%/100%; OpenAI daily £2; Service Bus queue depth >10 for 15 min.

### State (GitOps)

- **Source of truth:** Application code + adapter wiring in git; Terraform modules under infra paths; environment config via Terraform variables and Key Vault secret references (not committed).
- **Reconciliation:** GitHub Actions `terraform apply` on `main` after image push; ACA revisions pinned to SHA tags.
- **Drift correction:** PR `terraform plan` detects drift; portal changes to ACA/Postgres treated as incidents — revert manually or re-apply from git; quarterly tag/SKU review per BUDGET.md.
- **Environment promotion:** **Single prod** only; no paid staging — local Docker Compose + optional pre-prod smoke against prod after deploy (operator-triggered, low traffic).

---

## 4. Engineering Trade-offs (The Interview Edge)

### Session and rate-limit store (user-confirmed 2026-06-05)

| | Detail |
|---|--------|
| **Chosen** | **PostgreSQL-only** — `sessions` table + `rate_limit_counters` (or equivalent) on existing Burstable B1ms |
| **Why** | Reclaims **~£12–15/month** (~20% of £75 cap) by removing always-on Redis while API/worker scale to zero; Profile A traffic (1–3 users, low auth/request rate) tolerates slightly slower limit checks; `maxReplicas=2` still requires a **shared store** — Postgres satisfies that without a second always-on tier |
| **Rejected** | **Azure Cache for Redis Basic C0** |
| **Why rejected** | Fixed cost with minimal utilization when ACA is idle; duplicate always-on footprint alongside Postgres B1ms; FinOps headroom needed for OpenAI variable spend at 30 runs × 100 listings |

**Implementation notes:** Use Postgres `UPSERT` or advisory locks for magic-link limits (3/email/hour, 10/IP/hour) and API ingress counters; session rows indexed by session ID with TTL cleanup job or `expires_at` predicate; accept modest added query load on B1ms — monitor connection count and p95 auth latency in Log Analytics.

### Message queue

| | Detail |
|---|--------|
| **Chosen** | **Azure Service Bus Basic** |
| **Why** | Native KEDA trigger for worker scale-to-zero; Managed Identity send/receive; private endpoint; ~£8/mo fits budget; demonstrates async portfolio narrative |
| **Rejected** | Self-hosted RabbitMQ on ACA, in-process queue in prod |
| **Why rejected** | RabbitMQ adds ops burden and second always-on cost; in-process queue breaks multi-replica worker scaling and violates async demo requirements |

### Compute platform

| | Detail |
|---|--------|
| **Chosen** | **Azure Container Apps** (API + Worker) |
| **Why** | Closest Azure equivalent to Fargate; KEDA integration; separate ingress policies; operator Azure preference (ADR-0002) |
| **Rejected** | AKS, single VPS, AWS ECS |
| **Why rejected** | AKS ops overhead for MVP; VPS lacks credible autoscale demo; AWS rejected by operator platform choice |

### Cloud coupling

| | Detail |
|---|--------|
| **Chosen** | **Cloud-agnostic ports** (`BlobStore`, `JobQueue`, `SecretProvider`) + Azure adapters |
| **Why** | Domain/worker code stays portable; local Docker Compose without Azure subscription; future migration path to S3/SQS |
| **Rejected** | Direct Azure SDK calls in domain layer |
| **Why rejected** | Violates portfolio portability goal; complicates local dev and testing |

### Job sourcing

| | Detail |
|---|--------|
| **Chosen** | **Hybrid Indeed scrape + Adzuna API** (ADR-0001) |
| **Why** | Demonstrates async scraping and worker scaling; Adzuna provides legal fallback on scrape failure |
| **Rejected** | Scrape-only Indeed, API-only, LinkedIn |
| **Why rejected** | Scrape-only has no fallback; API-only skips portfolio scrape story; LinkedIn anti-bot unsuitable for MVP |

### Ingress / WAF

| | Detail |
|---|--------|
| **Chosen** | **ACA HTTPS ingress + application rate limits** |
| **Why** | Zero incremental infra cost; sufficient for Profile A; run quota and magic-link limits layer defense |
| **Rejected** | Azure Front Door + WAF |
| **Why rejected** | ~£15–35/mo against £75 cap; deferred per THREAT_MODEL R12 |

### Observability depth

| | Detail |
|---|--------|
| **Chosen** | **Log Analytics + Azure Monitor alerts + FinOps dashboards** |
| **Why** | Native ACA integration; no self-hosted Prometheus/Grafana ops; cost-capped ingestion for demo volume |
| **Rejected** | Full self-hosted Prometheus/Grafana stack |
| **Why rejected** | Additional compute cost and Day 2 burden for 1–3 users |

---

## 5. Day 2 Operations

### CV demo operational mode (default)

Production stays **deployed** while a live URL may appear on CV or in applications:

- **Compute:** API and worker `minReplicas=0` — first visit after idle may take **30–60 seconds**; UI must show a warming/loading state so cold start does not look broken.
- **Data plane:** PostgreSQL, Service Bus, Blob, and Key Vault remain provisioned so sign-in, sessions, and async runs work on first click.
- **Cost:** Plan **~£40–55/month** typical at Profile A traffic; scale-to-zero saves compute, not the always-on store floor (~£28–35/mo).
- **Teardown:** Run `terraform destroy` only in off-seasons when the demo link is removed or replaced with a static “offline” page — not as the default cost strategy while job hunting.
- **Rejected:** Wake-on-click full redeploy (20–45 min); incompatible with recruiter UX.

---

### Metrics & alerts

| Metric / SLI | Source | Alert threshold | Runbook action |
|--------------|--------|-----------------|----------------|
| Monthly Azure spend | Azure Cost Management | >£60 (80% of £75) | Review runs, OpenAI usage, SKU sizing; consider teardown if idle |
| OpenAI daily spend | OpenAI org dashboard | >£2/day | Check abuse/unlimited allowlist; rotate key if anomaly |
| Service Bus queue depth | Azure Monitor / SB metrics | >10 messages for 15 min | Inspect worker health, KEDA scaling, stuck runs; check for abuse |
| ACA API 5xx rate | Log Analytics / ACA metrics | Sustained spike vs baseline | Roll back revision; check DB connectivity and adapter errors |
| Magic-link / API 429 rate | App logs | Spike vs baseline | Investigate IP abuse; tighten limits if needed |
| Indeed scrape failure rate | Worker logs | High failure over 1 h | Expect Adzuna fallback banner; check Indeed blocking |
| Postgres connection saturation | PostgreSQL metrics | >80% max connections | Review session TTL; reduce pool size; consider SKU bump |
| Auth p95 latency (Postgres sessions) | Log Analytics | >500 ms sustained | Index session/rate-limit tables; review query patterns |
| Critical container CVE | GitHub Actions scan | CVE with published fix | Block merge; rebuild base image |
| Budget 100% | Azure Cost Management | £75 reached | Manual review per exceed policy — no auto-teardown |

### Disaster recovery & backup

- **RPO / RTO targets:** **RPO 24 h** (daily Postgres backup); **RTO 4 h** (single-operator redeploy from git + restore) — acceptable for portfolio/demo tier, not enterprise SLA.
- **Backup scope:** PostgreSQL automated backups (Azure Flexible Server default retention); Terraform state in geo-redundant storage backend; CV PDFs in Blob LRS (rely on Azure durability; export CVs before `terraform destroy` per BUDGET.md §4).
- **Recovery procedure:** (1) Identify last good ACA revision SHA or redeploy from `main`; (2) Restore Postgres from backup if data corruption; (3) Re-apply Terraform if infra drift; (4) Rotate Key Vault secrets if compromise suspected; (5) Invalidate sessions via DB truncate or signing-key rotation.
- **Game-day cadence:** Ad hoc before portfolio demos; full DR drill **before public launch** if traffic profile changes.

---

## Appendix: Resolved Decisions Log

| Date | Decision | Source |
|------|----------|--------|
| 2026-06-05 | Hybrid Indeed + Adzuna job sourcing | ADR-0001 |
| 2026-06-05 | Azure prod with cloud-agnostic ports | ADR-0002 |
| 2026-06-05 | Threat model accepted | THREAT_MODEL.md |
| 2026-06-05 | £75/mo cap, scale-to-zero ACA, Profile A traffic | BUDGET.md |
| 2026-06-05 | **PostgreSQL-only sessions and rate limits — Redis eliminated** | User confirmation (to-adr capstone) |
| 2026-06-05 | **CV demo mode:** stack deployed + scale-to-zero; no on-click redeploy; teardown only off-season | User confirmation |
