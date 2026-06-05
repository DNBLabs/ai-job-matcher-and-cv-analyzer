# Architecture Diagrams (C4)

**Source:** CONTEXT.md (Product, Scope, Security, Financial guardrails)  
**Last generated:** 2026-06-05

---

## Level 1 — System Context

Who uses the system and which external systems it depends on.

```mermaid
C4Context
    title System Context — AI Job Matcher & CV Analyzer

    Person(jobSeeker, "Job Seeker", "Uploads CVs, defines UK Job Search, views ranked Match Results")
    Person(admin, "Admin User", "Manages unlimited allowlist for selected accounts")

    System(app, "AI Job Matcher & CV Analyzer", "UK job-matching web app: CV upload, async Analysis Runs, dual-score AI results (Match Score + Interview Likelihood)")

    System_Ext(googleOAuth, "Google OAuth", "Primary sign-in provider")
    System_Ext(emailProv, "Email Provider", "Magic-link auth and run-completion notifications")
    System_Ext(openai, "OpenAI", "Suggested Job Titles (GPT-4o-mini) and per-listing scoring (GPT-4o)")
    System_Ext(indeed, "Indeed UK", "Scraped job listings (uk.indeed.com)")
    System_Ext(adzuna, "Adzuna API", "Official gb job listings API")

    Rel(jobSeeker, app, "Signs in, uploads CV, starts Analysis Runs, views dashboard", "HTTPS")
    Rel(admin, app, "Searches users and toggles unlimited flag", "HTTPS")
    Rel(app, googleOAuth, "Authenticates Job Seekers", "HTTPS/OIDC")
    Rel(app, emailProv, "Sends magic links and completion emails", "HTTPS/TLS")
    Rel(app, openai, "Title suggestions and listing scoring", "HTTPS/TLS")
    Rel(app, indeed, "Fetches listings via background workers", "HTTPS/TLS")
    Rel(app, adzuna, "Fetches listings via official API", "HTTPS/TLS")
```

---

## Level 2 — Container Diagram

High-level technical building blocks, trust boundaries, and encrypted paths.

```mermaid
C4Container
    title Container Diagram — AI Job Matcher & CV Analyzer

    Person(jobSeeker, "Job Seeker", "Uses React dashboard via public API")
    Person(admin, "Admin User", "Uses /admin routes (is_admin gate)")

    System_Boundary(github, "GitHub") {
        Container(ghActions, "GitHub Actions", "CI/CD workflows", "OIDC to Azure; deploy from main only; SHA-tagged images; PR plan/test only")
    }

    Enterprise_Boundary(azure, "Azure — uksouth") {
        Container_Boundary(prod, "Application stack (Terraform)") {
            Container(apiApp, "API Container App", "FastAPI + React SPA", "Public HTTPS ingress only; minReplicas=0 maxReplicas=2; sessions via Redis (private); non-root UID 10001; API MI")
            Container(workerApp, "Worker Container App", "Analysis Run pipeline", "Ingress disabled; minReplicas=0 maxReplicas=2; KEDA on Service Bus depth; Worker MI")
            ContainerDb(postgres, "PostgreSQL Flexible Server", "Burstable B1ms", "Private VNet; no public endpoint; users, CV metadata, runs, results, audit_log")
            ContainerDb(blob, "Blob Storage", "Azure Blob LRS", "CV PDFs encrypted at rest; public access disabled; MI-only cvs/ prefix")
            ContainerDb(serviceBus, "Service Bus", "Basic namespace", "Analysis Run job queue; private endpoint")
            ContainerDb(keyVault, "Key Vault", "Standard", "OAuth, email, OpenAI, Adzuna secrets; MI get at runtime")
            ContainerDb(acr, "Container Registry", "ACR Basic", "Immutable SHA tags; AcrPull MI")
        }
    }

    System_Ext(googleOAuth, "Google OAuth", "state nonce validated on callback")
    System_Ext(emailProv, "Email Provider", "Transactional email")
    System_Ext(openai, "OpenAI", "Zero-retention API; GPT-4o-mini + GPT-4o")
    System_Ext(indeed, "Indeed UK", "Scraped listings; cap 50/run")
    System_Ext(adzuna, "Adzuna API", "gb listings; cap 50/run")

    Rel(jobSeeker, apiApp, "Dashboard, CV upload, start runs", "HTTPS/TLS")
    Rel(admin, apiApp, "Admin UI /admin", "HTTPS/TLS")
    Rel(apiApp, googleOAuth, "OAuth sign-in/callback", "HTTPS/OIDC")
    Rel(apiApp, emailProv, "Magic link + run complete", "HTTPS/TLS")
    Rel(apiApp, openai, "Sync Suggested Job Titles", "HTTPS/TLS")
    Rel(apiApp, postgres, "CRUD scoped by user_id", "TLS/Private")
    Rel(apiApp, blob, "Upload/read/delete CV PDFs", "MI/Private")
    Rel(apiApp, serviceBus, "Enqueue Analysis Run", "MI/Private")
    Rel(apiApp, keyVault, "Load OAuth and email secrets", "MI")
    Rel(serviceBus, workerApp, "Deliver run jobs; KEDA scale trigger", "MI/Private")
    Rel(workerApp, blob, "Read CV PDFs (read-only MI)", "MI/Private")
    Rel(workerApp, postgres, "Write runs, results, FinOps tokens", "TLS/Private")
    Rel(workerApp, openai, "Per-listing scoring", "HTTPS/TLS")
    Rel(workerApp, indeed, "Scrape UK listings", "HTTPS/TLS")
    Rel(workerApp, adzuna, "Fetch gb listings", "HTTPS/TLS")
    Rel(workerApp, keyVault, "Load OpenAI and Adzuna secrets", "MI")
    Rel(ghActions, acr, "Push api/worker images", "HTTPS/OIDC")
    Rel(ghActions, apiApp, "Deploy ACA revision", "HTTPS/OIDC")
    Rel(ghActions, workerApp, "Deploy ACA revision", "HTTPS/OIDC")
    Rel(acr, apiApp, "Pull image", "AcrPull MI")
    Rel(acr, workerApp, "Pull image", "AcrPull MI")
```
