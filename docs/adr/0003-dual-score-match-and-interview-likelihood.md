# ADR-0003: Dual-Score Model (Match Score + Interview Likelihood)

## Status

Accepted

## Context

The product's core output is an AI evaluation of how well a Job Seeker's CV fits each scraped job listing. The init brief described this as **"interview probabilities"**, which implies a statistical likelihood of receiving an interview.

The system has **no historical outcome data** (apply → interview conversion rates). An LLM cannot produce calibrated probabilities without training on real hiring funnel data. Presenting a single percentage (e.g. "92% interview probability") would mislead Job Seekers when outcomes depend on factors the model cannot observe (referrals, company hiring freezes, unconscious bias, application volume).

We evaluated output models:

| Option | Output | Problem |
|---|---|---|
| A | Single 0–100 "interview probability" | Misleading label; conflates fit with competitiveness |
| B | Likelihood band only (High / Medium / Low) | Loses granularity for ranking and filtering |
| C | **Match Score** (0–100) + **Interview Likelihood** (H/M/L) | Two distinct dimensions; honest labeling |
| D | Empirical probability from historical data | Requires data unavailable at launch |

Job Seekers need both **"how well do I fit on paper?"** and **"am I likely competitive for this role?"** — these can diverge (e.g. strong skill match but under-qualified on seniority).

Each Job Match Result also includes a **full AI breakdown** (matched skills, gaps, red flags, talking points) produced in a single structured scoring call per listing.

## Decision

Adopt a **dual-score model**:

### Match Score (0–100)

Numeric measure of CV-to-listing **requirement alignment** (skills, experience, keywords). Used as the **default sort order** on the results dashboard. Pure fit metric — not a hiring outcome prediction.

### Interview Likelihood (High / Medium / Low)

Categorical **estimate** of whether the Job Seeker is likely competitive enough to pass initial screening, based on seniority fit, skill gaps, and red flags. Explicitly labeled as an AI estimate, **not** a statistical probability. UI must not imply guaranteed outcomes.

### Full breakdown (same API call)

Each scoring response returns structured JSON:

- `match_score` (integer 0–100)
- `interview_likelihood` (enum: `high` | `medium` | `low`)
- `matched_skills`, `skill_gaps`, `red_flags`, `talking_points` (arrays/strings)

When Match Score and Interview Likelihood diverge meaningfully, the UI shows a badge (e.g. "Skills fit, seniority gap"). Results are filterable by likelihood, source, and minimum Match Score.

## Consequences

### Positive

- Honest product positioning: avoids deceptive "probability" language that erodes trust after a rejection.
- Two dimensions support better Job Seeker decisions (apply despite low fit, or skip despite high fit).
- Single structured LLM call per listing keeps FinOps predictable; breakdown is included without a second API round-trip.
- Clear separation simplifies prompt engineering and future calibration if outcome data becomes available.

### Negative

- More complex UI and API schema than a single number.
- Job Seekers may still misinterpret Interview Likelihood as probability despite disclaimers — copy and UX must reinforce "estimate."
- Ranking defaults to Match Score, which may surface high-fit but low-competitiveness roles first; filters and badges mitigate but require user action.
- Prompt must reliably produce both scores plus breakdown in one JSON response; schema validation and retry logic needed for malformed LLM output.

### Follow-ups

- Define prompt templates and JSON schema validation in the scoring worker; reject and retry on malformed responses (max 1 retry per listing).
- UI copy review: every surface showing Interview Likelihood includes qualifier text ("AI estimate, not a guarantee").
- If outcome data is collected post-MVP (with consent), a future ADR may introduce calibrated probabilities as a third metric — not a replacement for Match Score.
