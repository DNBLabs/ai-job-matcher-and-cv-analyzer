"""Load local ``.env`` files into ``os.environ`` for SecretProvider resolution."""

from pathlib import Path

_BOOTSTRAPPED = False


def bootstrap_process_environment() -> None:
    """Populate ``os.environ`` from local ``.env`` files when present.

    ``Settings`` reads declared fields from ``.env`` via pydantic-settings, but
    ``EnvSecretProvider`` resolves secrets with ``os.environ.get``. Undeclared
    keys such as ``GOOGLE_OAUTH_CLIENT_ID`` must therefore be loaded explicitly
    for local development. Source: https://docs.pydantic.dev/latest/concepts/pydantic_settings/

    Searches, in order: current working directory, ``backend/.env``, repo root ``.env``.
    Later files do not override variables already set in the process environment.
    """
    global _BOOTSTRAPPED
    if _BOOTSTRAPPED:
        return

    try:
        from dotenv import load_dotenv
    except ImportError:
        _BOOTSTRAPPED = True
        return

    backend_dir = Path(__file__).resolve().parent.parent
    repo_root = backend_dir.parent
    candidate_paths = (
        Path.cwd() / ".env",
        backend_dir / ".env",
        repo_root / ".env",
    )

    for env_path in candidate_paths:
        if env_path.is_file():
            load_dotenv(env_path, override=False)

    _BOOTSTRAPPED = True
