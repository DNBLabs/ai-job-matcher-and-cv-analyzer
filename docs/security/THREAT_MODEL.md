# Threat Model: AI Job Matcher & CV Analyzer

**Status:** Accepted  
**Date:** 2026-06-05  
**Scope source:** docs/PRD.md, CONTEXT.md §2 Scope Guardrails

## 1. System Overview

A web application for UK Job Seekers to upload CV PDFs, define job searches, and receive AI-scored job matches from Indeed UK (scrape) and Adzuna (API). A React frontend talks to a FastAPI API; background workers consume Analysis Run jobs from a queue, read CVs from object storage, call OpenAI for scoring, and persist results to PostgreSQL. Production runs on Azure Container Apps with separate API and worker services, private data stores, Key Vault secrets, and GitHub Actions OIDC deploy from `main`. CVs are high-sensitivity PII.

## 2. Assets & Trust Boundaries

| Asset | Sensitivity | Boundary |
|-------|-------------|----------|
| CV PDF + parsed text | **High (PII)** | Internet → API → Blob Storage (`cvs/{user_id}/{uuid}.pdf`); worker read-only |
| User Account + session | **High** | API auth layer; PostgreSQL |
| Job Match Results + AI breakdown | **Medium** (derived PII) | PostgreSQL; owner-only API access |
| OpenAI API key | **Secret** | Key Vault → Worker MI only |
| Adzuna API key | **Secret** | Key Vault → Worker MI only |
| OAuth client secret / email API key | **Secret** | Key Vault → API MI only |
| Magic-link tokens | **High** | PostgreSQL (`token_hash` only); email in transit |
| Admin flags (`is_admin`, `is_unlimited`) | **High** | PostgreSQL; `/admin` API gated server-side |
| Container images (ACR) | **High** | GitHub Actions OIDC → ACR → ACA |
| Terraform state | **High** | Remote backend; no secrets in state |
| Audit log | **Medium** | PostgreSQL append-only table |
| FinOps metadata (tokens, $) | **Low** | PostgreSQL on `analysis_run`; no CV content |

### Trust boundaries

```
Internet
  │ HTTPS
  ▼
[API Container App] ──MI──► Blob (read/write cvs/), Service Bus (send), DB, Key Vault (OAuth/email)
  │
  │ enqueue analysis_run_id
  ▼
[Service Bus] ──MI──► [Worker Container App] ──► Blob (read cvs/), OpenAI, Indeed, Adzuna, DB
                                                          Key Vault (OpenAI/Adzuna)

[PostgreSQL / Redis / Blob / Service Bus] — private endpoints; no public internet access
[Worker ACA] — ingress disabled
[GitHub Actions main branch] ──OIDC──► Azure deploy (ACR push, ACA update, Terraform apply)
```

## 3. Data Flow (Security-Relevant)

1. **Sign-in:** Job Seeker → Google OAuth (with `state` nonce) or magic-link request (rate-limited) → token emailed → single-use verify → HttpOnly session cookie issued → auth event logged.
2. **CV upload:** Authenticated Job Seeker → `POST /cvs` → PDF validated (MIME, magic bytes, ≤5 MB) → safe parse (timeout/page limits) → Blob write under `{user_id}/{uuid}.pdf` → metadata in PostgreSQL.
3. **Title suggestion (sync):** API reads parsed text → OpenAI GPT-4o-mini (zero-retention API) → titles returned; **no CV content logged**.
4. **Analysis Run:** Authenticated owner → quota/concurrency check → run row created → message published to Service Bus → worker consumes.
5. **Worker pipeline:** Worker reads CV from Blob (MI read-only) → fetches listings (Indeed/Adzuna, retry 2×) → OpenAI GPT-4o scoring per listing (zero-retention) → results + FinOps tokens/$ persisted → completion email sent (deep-link requires sign-in).
6. **Results access:** Session required; all queries scoped by `user_id`; cross-account ID → 404.
7. **Admin:** `is_admin` session → search users → toggle `is_unlimited` → append-only audit log.
8. **Deploy:** Push to `main` → GitHub Actions OIDC → build SHA-tagged image → deploy to ACA; PR/fork workflows cannot reach prod.

## 4. STRIDE Analysis

| Component / Flow | STRIDE | Threat | Likelihood | Impact | Mitigation | Owner |
|------------------|--------|--------|------------|--------|------------|-------|
| Google OAuth login | S | CSRF / session fixation via missing `state` | Medium | High | Validate OAuth `state`; rotate session on login | API |
| Magic-link auth | S, I | Token brute-force or replay | Low | High | ≥256-bit token; single-use; 15 min expiry; store hash only | API |
| Session cookie | S, I | Session hijacking / theft | Medium | High | HttpOnly + Secure + SameSite=Lax; idle 24h / absolute 7d expiry | API |
| `POST /auth/magic-link` | D | Email bombing / provider abuse | Medium | Medium | 3/email/hour + 10/IP/hour rate limits | API |
| Public API ingress | D | Request flood / resource exhaustion | Medium | Medium | ACA/WAF ~100 req/min/IP; run quota 3/24h; 1 concurrent run | API + Ops |
| `POST /cvs` | T, D | Malicious PDF / parser exploit / upload bomb | Medium | High | MIME + magic bytes; 5 MB cap; safe parse timeout/pages; text extraction only | API |
| Blob Storage keys | I, E | Guessable paths → cross-user CV read | Low | Critical | `{user_id}/{uuid}.pdf`; public access disabled; MI-only | API + IaC |
| `GET /runs/{id}`, `/cvs/{id}` | E, I | IDOR — access another user's data | Medium | Critical | Owner-only queries; 404 on mismatch; session required | API |
| Completion email deep-link | I | Forwarded link exposes results | Medium | High | Deep-link requires sign-in as owner; no public/signed URL tokens | API + Frontend |
| OpenAI API calls | I | CV content retained/training by third party | Medium | Critical | Zero-retention / no-training API settings; document in posture | Worker |
| Application logs / FinOps | I | CV text or full prompts in logs | Medium | Critical | Log tokens and `$` only; never log CV content or prompts | API + Worker |
| Worker → Indeed scrape | T, E | Malicious HTML → RCE in scraper | Low | High | Parse HTML defensively; no JS execution; worker ingress disabled; minimal MI | Worker |
| API Managed Identity | E | Over-privileged API compromises all CVs | Low | Critical | Blob R/W `cvs/` only; SB send only; KV get OAuth/email only | IaC |
| Worker Managed Identity | E | Compromised worker exfiltrates/deletes all data | Low | Critical | Blob read-only; SB receive only; no admin DB writes; KV OpenAI/Adzuna only | IaC |
| `/admin` endpoints | E | Non-admin grants unlimited runs | Low | High | `is_admin` checked server-side from DB; not client-supplied | API |
| Admin session theft | E, R | Attacker toggles unlimited on abuse account | Low | High | Append-only audit log; auth event logging | API |
| PostgreSQL | I | Public DB endpoint / credential leak | Low | Critical | Private VNet only; no public endpoint; MI auth where supported | IaC |
| Redis / Service Bus | I, D | Public endpoint / message injection | Low | High | Private endpoints; MI scoped send/receive | IaC |
| Unlimited allowlist accounts | D | Queue/OpenAI cost blowout | Medium | Medium | 1 concurrent run cap retained; spend + queue depth alerts | Ops |
| GitHub Actions → Azure | S, E | Fork PR deploys malicious image to prod | Medium | Critical | OIDC only; federated cred restricted to repo + `main`; SHA-tagged images | CI/CD |
| Container images | T | Vulnerable base image / supply chain | Medium | High | Non-root user; scan in CI; pin base image digests | CI/CD |
| CV deletion | I | Deleted PDF still in backups | Low | Medium | Immediate blob delete; document backup retention in ops runbook | Ops |

All six STRIDE categories are covered above.

## 5. Risk Register

| ID | Risk | Severity | Mitigation status | Notes |
|----|------|----------|-------------------|-------|
| R1 | CV PII disclosed via OpenAI retention or logging | Critical | Mitigated | Zero-retention API + strict log hygiene |
| R2 | IDOR on runs/CVs/results | Critical | Mitigated | Owner-only session access |
| R3 | Public Blob or DB exposure | Critical | Mitigated | Private endpoints; public access disabled |
| R4 | Compromised worker with broad MI | High | Mitigated | Separate least-privilege Worker MI |
| R5 | Malicious PDF parser exploit | High | Mitigated | Validation + safe parse limits |
| R6 | Magic-link / session hijack | High | Mitigated | Single-use tokens; secure cookies |
| R7 | API abuse / OpenAI cost exhaustion | High | Mitigated | Rate limits + quota + alerts |
| R8 | Fork PR prod deploy via CI | Critical | Mitigated | OIDC + main-only prod |
| R9 | Indeed scrape ToS / legal exposure | Medium | Accepted | ADR-0001; Adzuna fallback |
| R10 | Forwarded completion email | Medium | Accepted | Session required on view; user education |
| R11 | No CV redaction before OpenAI | Medium | Accepted | Full context needed for scoring quality |
| R12 | No dedicated WAF / DDoS service | Low | Deferred | ACA ingress limits sufficient for MVP |
| R13 | No formal penetration test | Medium | Deferred | Pre-public-launch recommendation |

## 6. Security Controls Summary

- Zero-retention OpenAI API; no CV content or prompts in logs
- Owner-only resource access; session required; 404 on IDOR
- Layered DoS: magic-link limits, PDF 5 MB cap, ingress rate limits, run quota, spend/queue alerts
- Auth: single-use magic links (15 min), secure session cookies, OAuth `state` validation
- Separate API and Worker Managed Identities with split Key Vault access
- CV upload: MIME/magic-byte validation, safe parsing, UUID blob keys
- Append-only audit log for admin actions and auth events
- CI/CD: GitHub OIDC only; prod deploy from `main`; SHA-tagged images
- Network: private PostgreSQL, Blob, Redis, Service Bus; worker ingress disabled; HTTPS on API only
- Encryption at rest on Blob and PostgreSQL; TLS in transit
- Non-root container users; container scan in CI

## 7. Out of Scope & Accepted Risks

Aligned with PRD Out-of-Scope and grilling acceptances:

- **Accepted:** Indeed scraping ToS risk (mitigated by Adzuna API fallback)
- **Accepted:** Full CV text sent to OpenAI without field-level redaction
- **Accepted:** Completion email deep-links require re-auth (no signed URL convenience)
- **Deferred:** Azure Front Door / dedicated WAF
- **Deferred:** CV field redaction pipeline before LLM
- **Deferred:** Formal third-party penetration test
- **Deferred:** Multi-factor authentication for Admin Users
- **Out of scope:** Recruiter workflows, public result sharing, auto-apply

## 8. Day 2 Security Operations

### Metrics & alerts

- OpenAI daily spend exceeds threshold (e.g. 80% of budget)
- Service Bus queue depth sustained above baseline (worker scaling or abuse)
- Spike in `401/403` or magic-link rate-limit `429` responses
- Indeed scrape failure rate above threshold
- ACA 5xx error rate spike
- Container scan Critical CVE with published fix (CI gate failure)

### Incident response hooks

- **OpenAI key compromise:** Rotate Key Vault secret; redeploy worker; review FinOps for anomaly
- **Session widespread hijack suspicion:** Invalidate all sessions (rotate signing key); force re-auth
- **Malicious image deployed:** Roll back ACA revision to previous SHA; audit GitHub Actions run
- **Admin account compromise:** Revoke `is_admin` via DB seed/migration; review `audit_log`

### Review cadence

- Revisit this threat model on: MVP public launch, addition of new Job Source, multi-tenant/recruiter features, or change to OpenAI data policy
- Quarterly review of Managed Identity assignments and Key Vault access policies
