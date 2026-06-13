# Bug: Indeed scraper returning 0 listings in local E2E run

**Discovered:** 2026-06-13 during Task 21 manual E2E verification  
**Status:** Fixed

---

## Symptoms

Analysis runs completed immediately with status `failed (0 results)`. No listings were
scraped despite Indeed UK being a configured Job Source.

Three separate root causes were found and fixed in sequence.

---

## Root cause 1 — Worker missing `env_file` in docker-compose.yml

**File:** `docker-compose.yml`

The `api` service had `env_file: .env` but the `worker` service did not. Secrets
(`OPENAI_API_KEY`, `GOOGLE_OAUTH_*`, etc.) were never injected into the worker
container, causing it to crash at startup with `SecretNotFoundError: OPENAI_API_KEY`.
The worker never consumed the queue, leaving all runs stuck on `queued`.

**Fix:** Added `env_file: - path: .env / required: false` to the `worker` service.

---

## Root cause 2 — Indeed blocked by Cloudflare TLS fingerprinting

**File:** `backend/app/job_sources/indeed.py`

The scraper used `httpx.Client` for HTTP requests. Python's TLS stack produces a
JA3/JA4 fingerprint that Cloudflare identifies as non-browser traffic and returns
HTTP 403. This is non-retryable per the adapter's `_is_transient` logic, so the
source failed immediately on every attempt.

**Fix:** Replaced the default `httpx.Client` with a `curl_cffi.requests.Session`
configured with `impersonate="chrome124"`. `curl_cffi` wraps libcurl and reproduces
Chrome's exact TLS handshake, bypassing Cloudflare fingerprint checks.

- Added `curl-cffi>=0.7.0` to `pyproject.toml` dependencies.
- Added `curl_cffi` exception types (`CurlTimeout`, `CurlHTTPError`) alongside the
  existing `httpx` exceptions in the `except` clause and `_is_transient`. Tests
  continue to inject `httpx` mock exceptions and pass unchanged (20/20 green).
- Worker startup now logs a warning and skips Adzuna gracefully when
  `ADZUNA_APP_ID`/`ADZUNA_APP_KEY` are absent, rather than crashing
  (`worker/main.py`).

---

## Root cause 3 — Indeed changed `h2.jobTitle` → `h3.jobTitle`

**File:** `backend/app/job_sources/indeed.py` — `_extract_listing`

After the TLS fix, requests returned HTTP 200 with valid HTML and 16
`div.job_seen_beacon` cards, but `_extract_listing` returned `None` for every card.
Indeed had changed their job title element from `<h2 class="jobTitle">` to
`<h3 class="jobTitle">`, breaking the CSS selector `h2.jobTitle a span[title]`.
The `.job-snippet` description element was also removed from search result cards.

**Fix:** Changed both title selectors from `h2.jobTitle` to `.jobTitle` (class-only,
tag-agnostic). The fixture HTML uses `h2` and continues to match. Description falls
back to empty string when `.job-snippet` is absent, which was already the existing
fallback behaviour.

```python
# Before
title_el = card.select_one("h2.jobTitle a span[title]")
link_el  = card.select_one("h2.jobTitle a")

# After
title_el = card.select_one(".jobTitle a span[title]")
link_el  = card.select_one(".jobTitle a")
```

---

## Verification

After all three fixes, a local E2E run scraped 16 real Indeed UK listings, scored
them via GPT-4o, and reached `complete` status. The worker log confirmed:

```
analysis run <id> → scraping
analysis run <id> → scoring (16 listings)
analysis run <id> → complete (16 results)
```
