# ADR-0011: Custom Domains via Cloudflare — `www.getmeajob.dnblabs.co.uk` (SWA) and `api.getmeajob.dnblabs.co.uk` (ACA)

This executes the deferred "alternative considered" path from ADR-0008: both the frontend and API are placed under the shared parent domain `dnblabs.co.uk`, which makes them **same-site** and allows the session cookie posture to revert from `SameSite=None` (current) back to `SameSite=Lax` (stricter CSRF surface).

## Decision

- **Frontend:** `www.getmeajob.dnblabs.co.uk` → Azure Static Web App custom domain
- **API:** `api.getmeajob.dnblabs.co.uk` → Azure Container App custom domain (managed cert)
- **Cloudflare DNS:** both CNAMEs are DNS-only (no Cloudflare proxy) so Azure manages TLS end-to-end. Cloudflare DNS records are provisioned via Terraform (Cloudflare provider) — not manual operator steps.
- **Cookie posture:** `SameSite=Lax` in production (both origins share eTLD+1 `dnblabs.co.uk`); CORS headers still required (different origins). `SameSite=None` is removed.
- **Canonical URL:** `www.getmeajob.dnblabs.co.uk` replaces the `*.azurestaticapps.net` URL in `ALLOWED_ORIGINS`, `POST_AUTH_REDIRECT_URL`, and email deep links. The raw Azure URLs remain accessible but are not advertised.
- **Google OAuth:** `https://api.getmeajob.dnblabs.co.uk/auth/google/callback` is added as an authorized redirect URI in Google Console (old ACA URL kept as fallback until verified).

## Considered options

- **Frontend-only custom domain:** leaves cookie posture as `SameSite=None`; misses the hardening ADR-0008 already identified.
- **Cloudflare proxy on:** adds WAF/DDoS edge but conflicts with Azure's managed TLS cert provisioning and masks real IPs from ACA rate limiting. SWA already has global CDN; proxy is redundant.

## Consequences

- New Terraform dependency: Cloudflare provider (`cloudflare/cloudflare`). Requires `CLOUDFLARE_API_TOKEN` GitHub secret and `cloudflare_zone_id` Terraform variable.
- ACA managed cert provisioning happens asynchronously after `terraform apply`; deployment sequencing must ensure DNS CNAMEs resolve before Terraform registers the custom domain resources, and `VITE_API_BASE_URL` should not switch to the new domain until the ACA cert is confirmed active.
- Google Console authorized redirect URI list must be updated (additive) before the new OAuth callback URL is used in production.
