# ADR-0008: Production SPA Serving via Azure Static Web App

## Status

Accepted (2026-06-16). Resolves the "SPA serving" open question (IMPLEMENTATION_PLAN.md). Implemented by Task 30.

## Context

The React/Vite SPA is fully built (Tasks 20–24: auth pages, dashboard, run
wizard, results, admin). How it is **served in production** was deliberately left
as an open question during planning — "FastAPI static mount vs CDN on Blob (MVP:
FastAPI mount is simpler)". Task 29 deployed the API and worker Container Apps
only; nothing serves the SPA yet, so there is no browsable site — only the JSON
API.

Two viable approaches:

1. **Same-origin bundle** — compile the SPA into the API container image and
   serve it from FastAPI at the same origin as the API.
2. **Separate Azure Static Web App (SWA)** — host the built SPA on its own
   managed static host + CDN, distinct from the API.

## Decision

**Serve the SPA from a dedicated Azure Static Web App (Free SKU), separate from
the API Container App.**

Rationale:

- **Architecture quality / portfolio value:** demonstrates managed static
  hosting with global CDN edge caching and an independent frontend deploy
  pipeline — a more representative production topology than bundling static
  assets into an API image.
- **Separation of concerns:** frontend and API deploy, scale, and cache
  independently.
- **Cost:** SWA **Free** tier is £0 — within the £75/mo budget; no extra
  Container App or egress.

Trade-off accepted vs. the same-origin bundle: the bundle is simpler (one image,
no CORS, `SameSite=Lax` cookies "just work"), but it couples the frontend to the
API image and showcases nothing about static hosting. We accept the cross-origin
complexity below in exchange for the cleaner, more demonstrable architecture.

### Cross-origin authentication (the key design point)

The SWA (`*.azurestaticapps.net`) and the API (`*.azurecontainerapps.io`) are
**different sites**, so the API's current `SameSite=Lax` session cookies would
**not** be sent on credentialed cross-site `fetch` from the SPA. Resolution:

- In **production**, issue the session (and OAuth-state) cookies with
  **`SameSite=None; Secure`** so browsers include them on the SPA's
  `credentials: "include"` requests. Keep `SameSite=Lax` for local/dev.
- The API enables **credentialed CORS** restricted to the **SWA origin only**
  (`ALLOWED_ORIGINS`).
- **CSRF:** `SameSite=None` widens the CSRF surface. Mitigations: CORS is locked
  to the single SWA origin, the OAuth `state` nonce is already validated, and all
  mutating endpoints require the session. A double-submit CSRF token is a noted
  future hardening.
- **Alternative considered:** custom domains under a shared parent
  (`app.dnblabs.co.uk` / `api.dnblabs.co.uk`) would let `SameSite=Lax` work via
  `Domain=.dnblabs.co.uk`. Deferred (needs domain + cert setup); recorded as a
  hardening path.

### Deployment

- **Terraform** `azurerm_static_web_app` (Free SKU) in `infra/app`, FinOps-tagged.
- **Frontend deploy** via GitHub Actions (`Azure/static-web-apps-deploy` with the
  SWA deployment token), built with `VITE_API_BASE_URL` = the API's public URL.
- **API config:** `ALLOWED_ORIGINS` = SWA URL; `POST_AUTH_REDIRECT_URL` → SWA
  dashboard; Google OAuth callback stays API-side (`/auth/google/callback`),
  redirecting to the SWA after sign-in. Run-complete email deep links use the SWA
  origin.

## Consequences

**Positive:** CDN-backed managed static hosting, independent deploys, £0 hosting,
a more credible production topology.

**Negative / accepted:** cross-origin auth requires `SameSite=None; Secure`
cookies + locked-down CORS; a second deploy path; Google OAuth redirect/origin
updates; the cookie-SameSite change must be environment-aware.

## References

- IMPLEMENTATION_PLAN.md — Task 30; resolved "SPA serving" open question.
- ADR-0006 (zero-touch deploy), ADR-0007 (blob networking).
- CONTEXT.md §Identity & access (cookie posture), §Network.
