# ADR-0009: Replace Indeed Scrape with Reed API

## Status

Accepted — supersedes the **Indeed** half of [ADR-0001](0001-hybrid-job-sourcing-indeed-adzuna.md). The Adzuna API source from ADR-0001 is unchanged.

## Context

ADR-0001 chose a hybrid strategy: scrape **Indeed UK** for volume and call the **Adzuna** API as a legal, reliable fallback. Its own follow-up anticipated this reversal:

> *Monitor Indeed scrape success rate; if it falls below an acceptable threshold, consider replacing with a second API source (e.g. Reed API) rather than adding more scrapers.*

That threshold was reached in production:

- **Indeed returns HTTP 403 from the Azure Container Apps egress IP on every run** (issue #56), while the identical request succeeds from a residential IP.
- The adapter already defeats Cloudflare's **JA3/JA4 TLS fingerprinting** via `curl_cffi` Chrome impersonation. That clears one Cloudflare layer but not the next: **IP reputation**. Cloudflare blocks the datacenter IP range regardless of a perfect TLS fingerprint, which TLS impersonation cannot change.
- The only ways to make Indeed work from the datacenter are (a) a **residential/unlocker proxy** — recurring cost, ongoing ToS exposure, and it does **not** stop Indeed's HTML from changing (the parser still needs maintenance); or (b) accept permanent failure of that source.
- A **NAT gateway** does not help: it yields a stable IP but still a datacenter IP, so the reputation block stands. (NAT only helps where a publisher will *allowlist* a fixed IP.)

Adzuna is an **aggregator** that already pulls from Indeed, Reed, and other UK boards, so much of Indeed's volume is already present in our Adzuna results. The marginal, non-overlapping value of Indeed does not justify a recurring proxy bill plus permanent parser maintenance plus ToS risk.

**Reed** is one of the largest UK job boards with strong tech/IT coverage and an **official Jobseeker REST API** that is tolerant of server-to-server traffic — no scraping, no proxy, no Cloudflare. It complements Adzuna with some direct UK postings Adzuna misses.

## Decision

**Remove the Indeed scrape source and add a Reed API source.** Production job sourcing becomes two official APIs:

| Job Source | Mechanism | Role |
|---|---|---|
| **Adzuna** | Official REST API (`country=gb`) | Aggregated UK breadth |
| **Reed** | Official Jobseeker REST API (`/api/1.0/search`) | Direct UK listings, strong tech coverage |

Reed integration follows the same pluggable-adapter contract as Adzuna:

- **Endpoint:** `GET https://www.reed.co.uk/api/1.0/search`
- **Auth:** HTTP Basic — the API key is the username, the password is empty.
- **Request params:** `keywords` (role), `locationName` (omitted for remote searches), `resultsToTake` (capped at 50 per the per-source ADR rule).
- **Response → `NormalisedListing`:** `jobTitle → title`, `employerName → company`, `locationName → location`, `jobUrl → url`, `jobDescription → description`, `source = "reed"`.
- **Resilience:** retries up to 2 times on transient failure (429/5xx/timeout) with the shared exponential-backoff-plus-jitter helper added for issue #58.
- **Secret:** `REED_API_KEY`, resolved through the `SecretProvider` port (env locally, Key Vault in production under the Worker Managed Identity scope). The value is set out of band at go-live, exactly like the Adzuna credentials.

Indeed-specific machinery is deleted: the `IndeedJobSource` adapter and its tests, its worker registration, and the now-unused `curl_cffi` and `beautifulsoup4` dependencies (no other module uses them).

Partial-success behaviour is unchanged: a run completes if at least one source returns listings, and the UI banners a failed source.

## Consequences

### Positive

- **No datacenter-IP blocking, no Cloudflare, no proxy bill.** Both sources are official APIs that expect server traffic.
- **Lower maintenance:** a stable JSON contract replaces brittle HTML selectors that broke on every Indeed layout change.
- **Lower legal/ToS risk:** no scraping anywhere in the system.
- **Better UK tech coverage** than Indeed-via-datacenter (which returned nothing), and complementary to Adzuna's aggregation.
- The adapter pattern from ADR-0001 made this a source swap, not a pipeline rewrite.

### Negative

- **Loses the live-scraping showcase** that ADR-0001 valued for the portfolio narrative. Async worker scaling and queue-depth behaviour are unaffected and still demonstrable; only the scrape-specific story is gone.
- **Overlap with Adzuna:** because Adzuna aggregates Reed, some Reed listings duplicate Adzuna results. The pipeline's existing dedup (by listing URL) absorbs this; coverage gain is the non-overlapping subset.
- **New secret to provision** (`REED_API_KEY`) in production Key Vault — a one-time operator step.
- Reed is UK-only, which is fine for the MVP's UK-only scope but is not a path to international coverage.

### Follow-ups

- Operator: create the `reed-api-key` secret in the production Key Vault and confirm the Worker Managed Identity can read it (same pattern as the Adzuna secrets).
- Issue #58 **problem 1** (datacenter egress reliability) is largely retired by removing the scrape source; any residual Adzuna 503s are now handled by backoff alone. Close #56 (Indeed 403) as won't-fix — the source is gone.
- Consider a UK tech-specialist board (e.g. CWJobs, Technojobs) post-MVP if coverage depth in tech proves thin.
