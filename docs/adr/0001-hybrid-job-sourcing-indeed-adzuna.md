# ADR-0001: Hybrid Job Sourcing (Indeed Scrape + Adzuna API)

## Status

Accepted

## Context

Analysis Runs need job listings to score against a Job Seeker's CV. Listings must come from real job boards, scoped by the Job Seeker's Job Search criteria (role, UK location or remote).

We considered three approaches:

1. **Scrape-only** — fetch listings by scraping one or more boards (e.g. Indeed, LinkedIn).
2. **API-only** — fetch listings exclusively through official job search APIs (e.g. Adzuna).
3. **Hybrid** — combine a scraper for breadth/demonstration value with an API for reliability and legal clarity.

Additional constraints:

- MVP geographic scope is **UK only** (Adzuna `gb`, Indeed UK).
- Workers cap listings at **50 per Job Source per Analysis Run** to control AI cost.
- The architecture must support **pluggable Job Source adapters** so new boards can be added without rewriting the pipeline.
- Partial success is acceptable: a run completes if at least one source returns listings (see ADR context in `CONTEXT.md`).
- This is a portfolio flagship project that must demonstrate **async scraping**, **worker scaling on queue depth**, and **resilient failure handling**.

LinkedIn scraping was explicitly rejected: aggressive anti-bot measures make it unsuitable as an MVP dependency. A scraper-only Indeed approach leaves no legal fallback when rate-limited or blocked.

## Decision

MVP uses a **hybrid Job Source strategy**:

| Job Source | Mechanism | Role |
|---|---|---|
| **Indeed UK** | Background worker scraper (`uk.indeed.com`) | Primary volume; demonstrates async scrape + worker scaling |
| **Adzuna** | Official REST API (`country=gb`) | Legal, predictable fallback when scraping fails or rate-limits |

Each Job Source is implemented as a **pluggable adapter** behind a common interface. Workers fetch up to 50 listings per source per Analysis Run, retry each source up to 2 times on transient failure, and proceed with partial results when one source fails.

## Consequences

### Positive

- Demonstrates real async scraping and queue-driven worker scaling (portfolio goal).
- Adzuna provides a reliable fallback when Indeed is blocked or returns empty, improving run completion rates.
- API-backed source reduces legal/ToS exposure compared to scrape-only.
- Adapter pattern keeps adding Glassdoor, Reed, etc. as post-MVP work without pipeline changes.

### Negative

- Indeed scraper is **brittle**: HTML changes, CAPTCHAs, and IP blocks require ongoing maintenance.
- Two integration surfaces to build, test, and monitor (scraper + API).
- Scraping Indeed may violate its Terms of Service; this is a known risk mitigated by Adzuna fallback and UK-only MVP scope, not eliminated.
- Normalising listing shape across scrape and API responses adds mapping overhead in each adapter.

### Follow-ups

- Monitor Indeed scrape success rate; if it falls below an acceptable threshold, consider replacing with a second API source (e.g. Reed API) rather than adding more scrapers.
- Log per-source fetch counts and failure reasons on every Analysis Run for operational visibility.
