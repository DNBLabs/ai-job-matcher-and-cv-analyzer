# Research #102 — What does one Analysis Run cost today?

**Branch:** `research/best-fit-run-cost`
**Date:** 2026-07-21
**Status:** Read-only research. No code changed.

---

## Question

Establish, from the codebase + provider pricing, the real per-run cost of a single-role
Analysis Run so a cost cap can be sized. Specifically:

1. How many job listings a single run fetches (page sizes, caps, pages-per-role).
2. The LLM scoring cost per listing (model, token profile in/out, per-token price).
3. £ per run, and the **marginal £ of adding one more title** to a best-fit search.
4. Any other per-run costs (embeddings, re-scoring, multiple LLM calls per listing).

---

## Method

### Files inspected (code citations are `file:line`)

- `backend/app/config.py:102-109` — scoring model config (`openai_scoring_model` default `gpt-4o`).
- `backend/worker/pipeline.py:30,64,148` — per-source listing cap (`_MAX_LISTINGS_PER_SOURCE = 50`), fetch loop.
- `backend/worker/main.py:71-85` — which sources are registered (Adzuna + Reed).
- `backend/app/job_sources/adzuna.py:64-141` — Adzuna single-page fetch, `results_per_page` capped at 50.
- `backend/app/job_sources/reed.py:36-144` — Reed single-request fetch, `resultsToTake` capped at 50 (Reed API max is 100).
- `backend/app/job_sources/base.py:91-106` — `JobSource` port (`max_results` default 50).
- `backend/app/services/scoring_service.py:25-29,93-150` — one scoring call per listing, hard cap 100 calls/run, ≤1 retry per listing.
- `backend/app/adapters/openai_client.py:16-23,99-134` — the actual scoring prompt (system + `CV:\n… + Listing:\n…`) and structured output call.
- `backend/app/domain/scoring_schema.py:12-41` — `ScoringLlmOutput` (the completion payload shape).
- `backend/app/domain/finops.py:8-41` — GPT-4o price constants and the USD estimator used per run.
- `backend/app/domain/job_search.py:65-71` — `JobSearch` is **single** `role: str` (best-fit multi-title not implemented).
- `docs/finance/BUDGET.md` and `CONTEXT.md:128,210` — existing cost/guardrail assumptions to reconcile against.

### Pricing sources

- **GPT-4o list price** (used in code): `_GPT4O_INPUT_USD_PER_MILLION = 2.50`, `_GPT4O_OUTPUT_USD_PER_MILLION = 10.00`
  — `backend/app/domain/finops.py:10-11`. In-code source comment:
  `https://developers.openai.com/api/docs/pricing` (verified 2026-06-09).
  This matches OpenAI's published GPT-4o rate ($2.50 / 1M input, $10.00 / 1M output).
- **FX:** GBP/USD = **1.27** (i.e. £1 = $1.27, so £ = USD ÷ 1.27), matching the planning FX in
  `docs/finance/BUDGET.md:21`.

---

## Findings

### 1. Listings per run

- **Two sources are registered**, each fetched independently: Adzuna and Reed
  (`backend/worker/main.py:73,77`).
- **Each source fetches a single page**, capped at **50 listings**:
  - Pipeline passes `max_results=self._max_listings` where `_MAX_LISTINGS_PER_SOURCE = 50`
    (`backend/worker/pipeline.py:30,148`).
  - Adzuna: `results_per_page = min(max_results, 50)`, page 1 only — the URL is hardcoded to
    `.../jobs/gb/search/1` (`backend/app/job_sources/adzuna.py:27,137`). No pagination loop.
  - Reed: `resultsToTake = min(max_results, 100)` but `max_results` is 50, so **50**
    (`backend/app/job_sources/reed.py:37,140`). Single request, no pagination.
- **Listings are deduped by URL across sources** (first-seen wins)
  (`backend/worker/pipeline.py:150-153`).
- **Upper bound fetched per run:** 50 (Adzuna) + 50 (Reed) = **100 listings**, minus cross-source
  URL duplicates.
- **Scoring is separately hard-capped at 100 calls per run** — `_MAX_SCORING_CALLS_PER_RUN = 100`
  (`backend/app/services/scoring_service.py:27`), enforced against actual LLM calls including
  retries (`scoring_service.py:119-128`). So even if >100 listings were ever fetched, at most 100
  are scored.
- **Realistic per-run listing count:** a single role rarely fills both 50-caps after dedup;
  `docs/finance/BUDGET.md:14` assumes **40–80 listings/run** (cap 100). Central estimate **~60**.

### 2. LLM scoring cost per listing

- **Model:** `gpt-4o` (`backend/app/config.py:107-108`; default in `ScoringService` is
  `_DEFAULT_SCORING_MODEL = "gpt-4o"`, `scoring_service.py:30`).
- **Exactly one structured LLM call per listing** (ADR-0003), with **at most one retry** on
  malformed output — `_MAX_ATTEMPTS_PER_LISTING = 2` (`scoring_service.py:29`). Retries only fire
  on `LlmClientError`/`ValueError` (`scoring_service.py:172-187`), so in the normal case it is
  **1 call/listing**. All breakdown fields come from that single call — no lazy-load / second call
  (`CONTEXT.md:248`).
- **Prompt (input) composition per call** (`backend/app/adapters/openai_client.py:99-114`):
  - System prompt `_SCORING_SYSTEM_PROMPT` (`openai_client.py:16-23`) — a fixed ~90 tokens.
  - User message = **the full parsed CV text** (`CV:\n{cv_text}`) + the listing block
    (title, company, location, and **full `description`**).
  - **The entire CV is re-sent on every listing** — CV tokens are paid per listing, not once.
- **Completion (output) composition** (`backend/app/domain/scoring_schema.py:12-27`):
  `match_score` (int), `interview_likelihood` (enum), and four string arrays
  (`matched_skills`, `skill_gaps`, `red_flags`, `talking_points`). Bounded, small JSON.

**Token profile (ESTIMATED — see gaps).** The code does **not** hardcode token counts; usage is
read back from the provider at runtime (`openai_client.py:126-134`) and only aggregated for
FinOps. So the following is a reasoned estimate, not a measurement:

| Component | Tokens (central) | Range |
|---|---|---|
| System prompt | ~90 | 90 |
| CV text (1–2 page CV) | ~800 | 500–1,100 |
| Listing block (title/company/location + description) | ~320 | 200–500 |
| **Input total** | **~1,200** | **900–1,600** |
| **Output (score + 4 short arrays)** | **~250** | **150–400** |

(For reference, the unit test uses an illustrative 1,000 input / 300 output per listing —
`backend/tests/services/test_scoring_service.py:89-90` — a fixture, not an observed value; it sits
in the same ballpark as the estimate above.)

**Per-listing cost (GPT-4o @ $2.50/1M in, $10.00/1M out):**

- Input: 1,200 ÷ 1e6 × $2.50 = **$0.0030**
- Output: 250 ÷ 1e6 × $10.00 = **$0.0025**
- **Total ≈ $0.0055 / listing ≈ £0.0043 / listing** (÷1.27)
- Range: **$0.0038–$0.0080** (£0.0030–£0.0063) per listing.

Note: output tokens are the more expensive half despite being fewer, because GPT-4o output is
4× the input rate. The bounded array output keeps this small.

### 3. Other per-run costs

- **No embeddings anywhere** — no embedding model, vector store, or `embeddings` API call exists in
  the codebase (searched `backend/`; the only "embed" hits are unrelated substrings in URL/scrape
  comments).
- **No re-scoring / no second LLM call per listing** — single call, breakdown included
  (`CONTEXT.md:248`).
- **Title suggestions are NOT part of an Analysis Run.** `suggest_job_titles` uses `gpt-4o-mini`
  and runs synchronously at **CV upload** (`openai_client.py:41-82`, `config.py:102-105`), one call
  per upload, not per run. Excluded from per-run cost.
- **Retries** (`scoring_service.py`) add cost only on malformed output (≤1 extra call/listing,
  expected to be rare); negligible in expectation.
- **Non-OpenAI per-run costs** (Postgres, ACA worker compute, Service Bus) are largely **fixed /
  amortised**, not marginal per run. `docs/finance/BUDGET.md:54` amortises these to ~£1.50–2.00 of
  a ~£2.50–3.50 "cost per run", but they do **not** scale with an extra listing or title, so they
  are excluded from the marginal figure below.

---

## Cost model

### Assumptions (stated)

- Model = GPT-4o at list price $2.50/1M input, $10.00/1M output (`finops.py:10-11`, verified 2026-06-09).
- FX £1 = $1.27 (`BUDGET.md:21`).
- Token profile per listing ≈ 1,200 input / 250 output (estimated; see gaps).
- One scoring call per listing; retries negligible; hard cap 100 calls/run.
- "Typical" run scores **60** listings; "cap" run scores **100**.
- Only the OpenAI scoring spend is treated as the true marginal per-run/per-title cost. Fixed Azure
  infra is excluded from marginal figures.

### £ per single-role Analysis Run (OpenAI scoring only)

| Scenario | Listings scored | USD | GBP |
|---|---|---|---|
| Typical | 60 | 60 × $0.0055 = **$0.33** | **£0.26** |
| Typical low–high | 60 | $0.23–$0.48 | **£0.18–£0.38** |
| At hard cap | 100 | 100 × $0.0055 = **$0.55** | **£0.43** |
| Cap, high token profile | 100 | $0.80 | **£0.63** |

**Headline: a typical single-role Analysis Run costs ≈ £0.26 (range £0.18–£0.43 up to the
100-listing cap) in OpenAI GPT-4o scoring spend.**

### Marginal £ of adding one more title to a best-fit search

**Important:** best-fit multi-title search is **not implemented** — `JobSearch.role` is a single
string (`backend/app/domain/job_search.py:68`), and no multi-title fetch/loop exists. So the
marginal cost depends on how best-fit is eventually built. Two interpretations:

- **(A) Each extra title = an extra role fetch + scoring pass** (the natural product meaning: one
  more title fetches up to 100 more listings and scores them). Marginal cost = one more per-run
  scoring pass:
  - **≈ £0.26 per extra title** (typical 60 listings), up to **≈ £0.43** if that title hits the
    100-listing cap. This is the figure to size a cap against.
- **(B) Extra titles share ONE run's 100-call cap.** Because the 100-scoring-call cap and URL
  dedup are per-run (`scoring_service.py:27`, `pipeline.py:150-153`), if best-fit fetched several
  titles into a single run, total scoring is still bounded at 100 calls (~£0.43 max) regardless of
  title count — the marginal title approaches **£0** once the cap is reached. This would require a
  code change to the per-run model.

**Recommended planning figure for a cost cap: treat each added title as ~£0.26–0.43 of marginal
OpenAI spend (interpretation A).** N titles ≈ N × a single-role run.

### Reconciliation with existing docs

`docs/finance/BUDGET.md:42,54` estimates **~£0.04–0.06/listing** and **~£0.75–1.00 OpenAI/run** —
noticeably higher than this code-derived **~£0.004/listing / ~£0.26/run**. The BUDGET figure looks
like a conservative over-estimate (to hit £0.05/listing on GPT-4o you'd need ~4,000 output tokens,
but the output here is a few short arrays). The code's bounded output schema makes real per-run
scoring spend roughly **3–4× cheaper** than the BUDGET planning number. Either way it sits far
below the **£2/day OpenAI spend alert** (`CONTEXT.md:128,143`).

---

## Confidence & gaps

- **HIGH confidence (from code):** model = GPT-4o; 2 sources × 50-cap = ≤100 listings fetched;
  100-scoring-call hard cap; exactly one scoring call per listing; no embeddings; no re-scoring;
  title suggestions are out-of-run; GPT-4o price constants and FX.
- **MEDIUM confidence:** listings-per-typical-run (~60) — taken from `BUDGET.md:14` (40–80), not
  measured from production data.
- **UNVERIFIED — token profile.** Input/output token counts per listing are **estimated**, not
  measured. The code reads real usage from the provider at runtime but does not persist an average
  anywhere I could read. To harden this, query stored `analysis_run.finops_json`
  (`prompt_tokens`/`completion_tokens`, written at `pipeline.py:210`) from a real run and divide by
  `listings_scored`. Actual £/run scales linearly with these tokens.
- **UNVERIFIED — prompt caching.** No OpenAI prompt caching is exploited: the cacheable identical
  prefix is only the ~90-token system prompt (below the 1,024-token caching threshold), and the CV
  (which repeats across all listings in a run) sits in the user message and changes position, so it
  is **not** cached. Re-sending the full CV per listing is the single biggest lever on input cost —
  a potential optimization, but currently every listing pays full CV input tokens.
- **UNVERIFIED — best-fit design.** Multi-title best-fit is not built; the marginal-per-title
  figure depends on whether it is implemented as separate runs (interpretation A) or one shared-cap
  run (interpretation B).

---

## Bottom line

- **£ per single-role Analysis Run:** **≈ £0.26** typical OpenAI scoring spend
  (range **£0.18–£0.43** up to the 100-listing cap; ~£0.63 worst-case high-token/cap).
- **Marginal £ per added title (best-fit):** **≈ £0.26–0.43** per title (one extra fetch+score
  pass), i.e. N titles ≈ N single-role runs — unless best-fit is built to share one run's 100-call
  cap, in which case total stays bounded at ~£0.43.
- **Other per-run costs:** none marginal — no embeddings, no re-scoring, one LLM call per listing;
  title suggestion (gpt-4o-mini) is a separate per-upload cost, not per run.
