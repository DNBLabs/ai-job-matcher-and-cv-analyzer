"""Tests for Issue #74: promote API custom domain to canonical and revert SameSite=Lax.

Each test corresponds to one acceptance criterion. These tests are written
first (Phase C) and must all fail with assertion errors before the production
code is written.

Tests are static where the config lives outside Python (Terraform, YAML) and
unit-level where the behaviour is owned by the Python Settings class.
"""

import re
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Helpers: locate files relative to the repo root regardless of CWD.
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).parents[3]


def _read(relative: str) -> str:
    return (_REPO_ROOT / relative).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# AC1 — api_public_url is the custom domain
#
# Given the PR is merged and deployed, when the API container env is inspected,
# then API_BASE_URL is https://api.getmeajob.dnblabs.co.uk and
# GOOGLE_OAUTH_REDIRECT_URI is https://api.getmeajob.dnblabs.co.uk/auth/google/callback
# ---------------------------------------------------------------------------

_API_CUSTOM_DOMAIN = "api.getmeajob.dnblabs.co.uk"
_CONTAINERAPPS_TF = "infra/app/containerapps.tf"


def test_api_public_url_local_uses_custom_domain_variable() -> None:
    """api_public_url local must be derived from var.api_custom_domain, not the ACA default FQDN."""
    content = _read(_CONTAINERAPPS_TF)

    # Find the api_public_url local definition line
    match = re.search(r'api_public_url\s*=\s*"([^"]+)"', content)
    assert match is not None, "api_public_url local not found in containerapps.tf"

    value = match.group(1)
    assert "var.api_custom_domain" in value, (
        f"api_public_url must reference var.api_custom_domain but got: {value!r}"
    )
    # Must NOT use the computed ACA default domain expression
    assert "azurerm_container_app_environment" not in value, (
        f"api_public_url must not use the ACA default domain expression but got: {value!r}"
    )


def test_api_base_url_env_var_references_api_public_url() -> None:
    """API_BASE_URL env var in the API container must reference local.api_public_url."""
    content = _read(_CONTAINERAPPS_TF)

    # The env block for API_BASE_URL must set value = local.api_public_url
    # Locate the env block: name = "API_BASE_URL" followed by value
    api_base_url_block = re.search(
        r'name\s*=\s*"API_BASE_URL"\s*\n\s*value\s*=\s*([^\n]+)', content
    )
    assert api_base_url_block is not None, "API_BASE_URL env block not found in API container"

    value_expr = api_base_url_block.group(1).strip()
    assert "local.api_public_url" in value_expr, (
        f"API_BASE_URL must reference local.api_public_url, got: {value_expr!r}"
    )


# ---------------------------------------------------------------------------
# AC2 — RUNBOOK has Google Console operator step for custom domain
#
# Given a user visits https://www.getmeajob.dnblabs.co.uk and clicks
# "Sign in with Google", when the OAuth flow completes, then the user lands on
# /dashboard with no redirect_uri_mismatch error.
# ---------------------------------------------------------------------------

_RUNBOOK = "docs/ops/RUNBOOK.md"
_API_CALLBACK_URL = f"https://{_API_CUSTOM_DOMAIN}/auth/google/callback"


def test_runbook_has_google_console_step_for_custom_api_callback() -> None:
    """RUNBOOK §7c must document adding the custom domain OAuth redirect URI in Google Console."""
    content = _read(_RUNBOOK)

    assert _API_CALLBACK_URL in content, (
        f"RUNBOOK must contain the Google Console step for {_API_CALLBACK_URL!r} "
        "as an Authorized redirect URI (pre-deploy HITL gate)"
    )


def test_runbook_has_redirect_uri_mismatch_post_deploy_verification() -> None:
    """RUNBOOK §7c must document post-deploy verification that OAuth completes without redirect_uri_mismatch."""
    content = _read(_RUNBOOK)

    assert "redirect_uri_mismatch" in content, (
        "RUNBOOK must contain post-deploy verification step referencing redirect_uri_mismatch "
        "to confirm the Google Console URI was correctly added"
    )


# ---------------------------------------------------------------------------
# AC3 — SameSite=Lax is enforced in production (no SameSite=None override)
#
# Given a user signs in via magic link, when the link is clicked, then the
# session cookie is set with SameSite=Lax (no SameSite=None present).
# ---------------------------------------------------------------------------


def test_cookie_samesite_is_lax_in_production() -> None:
    """Settings.cookie_samesite must return 'lax' in production (ADR-0011 hardening path)."""
    from app.config import Settings

    settings = Settings(
        app_env="production",
        allowed_origins="https://www.getmeajob.dnblabs.co.uk",
        post_auth_redirect_url="https://www.getmeajob.dnblabs.co.uk/dashboard",
    )

    assert settings.cookie_samesite == "lax", (
        f"cookie_samesite must be 'lax' in production (both domains share dnblabs.co.uk eTLD+1) "
        f"but got {settings.cookie_samesite!r}. Remove the SameSite=None override from config.py."
    )


def test_containerapps_tf_has_no_cookie_samesite_none_env_var() -> None:
    """containerapps.tf must not set COOKIE_SAMESITE=none via an env var override."""
    content = _read(_CONTAINERAPPS_TF)

    # The env var name and value should not both appear in an env block
    assert not re.search(r'"COOKIE_SAMESITE"[\s\S]{0,80}"none"', content), (
        "containerapps.tf must not override COOKIE_SAMESITE to 'none' — "
        "SameSite=Lax is correct for the shared dnblabs.co.uk eTLD+1 (ADR-0011)"
    )


# ---------------------------------------------------------------------------
# AC4 — SPA is built with VITE_API_BASE_URL pointing at the custom domain
#
# Given the SPA is built in CI, when VITE_API_BASE_URL is read from the bundle,
# then it is https://api.getmeajob.dnblabs.co.uk (not the native ACA FQDN).
# ---------------------------------------------------------------------------

_DEPLOY_YML = ".github/workflows/deploy.yml"


def test_deploy_yml_spa_build_uses_api_custom_fqdn_output() -> None:
    """deploy.yml SPA build step must use the api_custom_fqdn Terraform output, not api_fqdn."""
    content = _read(_DEPLOY_YML)

    # Find the VITE_API_BASE_URL assignment
    match = re.search(r'VITE_API_BASE_URL\s*:\s*(.+)', content)
    assert match is not None, "VITE_API_BASE_URL assignment not found in deploy.yml"

    assignment = match.group(1).strip()
    assert "api_custom_fqdn" in assignment, (
        f"VITE_API_BASE_URL must reference steps.tf.outputs.api_custom_fqdn but got: {assignment!r}"
    )
    assert "api_fqdn" not in assignment.replace("api_custom_fqdn", ""), (
        "VITE_API_BASE_URL must not reference the native api_fqdn ACA output"
    )


def test_deploy_yml_reads_api_custom_fqdn_from_terraform_outputs() -> None:
    """deploy.yml Read stack outputs step must capture the api_custom_fqdn Terraform output."""
    content = _read(_DEPLOY_YML)

    assert "api_custom_fqdn" in content, (
        "deploy.yml must read api_custom_fqdn from terraform outputs "
        "(terraform output -raw api_custom_fqdn)"
    )


def test_deploy_yml_stack_outputs_step_captures_api_custom_fqdn() -> None:
    """The 'Read stack outputs' step must run 'terraform output -raw api_custom_fqdn'.

    Without this capture, steps.tf.outputs.api_custom_fqdn resolves to an empty
    string and the SPA is built with VITE_API_BASE_URL=https:// (broken).
    Checking for 'api_custom_fqdn' anywhere in the file is not sufficient — it
    could be satisfied by the SPA build step alone.
    """
    content = _read(_DEPLOY_YML)

    assert "terraform output -raw api_custom_fqdn" in content, (
        "deploy.yml 'Read stack outputs' step must capture api_custom_fqdn via "
        "'terraform output -raw api_custom_fqdn' — without it, VITE_API_BASE_URL "
        "resolves to an empty string at SPA build time"
    )


# ---------------------------------------------------------------------------
# AC5 — Smoke test verifies the custom API domain returns 200
#
# Given the smoke test runs after deploy, when
# curl -fsS https://api.getmeajob.dnblabs.co.uk/health is executed,
# then it returns 200.
# ---------------------------------------------------------------------------


def test_deploy_yml_smoke_test_hits_custom_api_domain() -> None:
    """deploy.yml smoke test step must verify https://api.getmeajob.dnblabs.co.uk/health returns 200."""
    content = _read(_DEPLOY_YML)

    assert _API_CUSTOM_DOMAIN in content, (
        f"deploy.yml smoke test must curl https://{_API_CUSTOM_DOMAIN}/health "
        "but the custom domain is not referenced in the workflow"
    )


def test_deploy_yml_smoke_test_includes_health_check_for_custom_api_domain() -> None:
    """deploy.yml smoke test must curl the /health endpoint at the custom API domain.

    Checking for the domain name alone is not sufficient — it could appear in
    a comment or the outputs capture step without the /health path being targeted.
    This test verifies the full URL https://api.getmeajob.dnblabs.co.uk/health
    is present in the workflow file (the smoke test hard-codes the custom domain
    per the issue spec: 'verify https://api.getmeajob.dnblabs.co.uk/health returns 200').
    """
    content = _read(_DEPLOY_YML)

    assert f"https://{_API_CUSTOM_DOMAIN}/health" in content, (
        f"deploy.yml smoke test must explicitly curl https://{_API_CUSTOM_DOMAIN}/health — "
        "the domain alone appearing in the workflow does not verify the health endpoint "
        "is checked at the custom domain"
    )


# ---------------------------------------------------------------------------
# AC6 — Completion email deep link uses the www custom domain
#
# Given a signed-in user starts an Analysis Run, when the run completes,
# then the completion email deep link uses https://www.getmeajob.dnblabs.co.uk
# (not the raw SWA hostname).
# ---------------------------------------------------------------------------

_FRONTEND_CUSTOM_DOMAIN = "https://www.getmeajob.dnblabs.co.uk"


def test_runbook_has_post_deploy_signin_verification_at_custom_domain() -> None:
    """RUNBOOK §7c must document post-deploy verification of Google sign-in at the www custom domain.

    This is the post-deploy gate for the full OAuth → session → email deep link flow,
    confirming the completion email carries https://www.getmeajob.dnblabs.co.uk.
    """
    content = _read(_RUNBOOK)

    assert _FRONTEND_CUSTOM_DOMAIN in content, (
        f"RUNBOOK must reference {_FRONTEND_CUSTOM_DOMAIN!r} in a post-deploy verification step "
        "confirming the custom domain is live and the OAuth + email deep link flow works end-to-end"
    )


def test_worker_frontend_base_url_uses_custom_domain_local_in_terraform() -> None:
    """Worker FRONTEND_BASE_URL in containerapps.tf must use local.frontend_url (the www custom domain)."""
    content = _read(_CONTAINERAPPS_TF)

    # Find the worker container's FRONTEND_BASE_URL env block
    # The worker section comes after the API section; FRONTEND_BASE_URL appears in both,
    # but the worker's block uses local.frontend_url.
    frontend_base_url_blocks = re.findall(
        r'name\s*=\s*"FRONTEND_BASE_URL"\s*\n\s*value\s*=\s*([^\n]+)',
        content,
    )
    assert frontend_base_url_blocks, "FRONTEND_BASE_URL env block not found in containerapps.tf"

    for block in frontend_base_url_blocks:
        value = block.strip()
        assert "local.frontend_url" in value, (
            f"FRONTEND_BASE_URL must reference local.frontend_url (the www custom domain), got: {value!r}"
        )
