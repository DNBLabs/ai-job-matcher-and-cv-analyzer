"""Shared fixtures for infrastructure port contract tests."""

import pytest

from app.adapters.local.env_secret_provider import EnvSecretProvider
from app.adapters.local.in_process_job_queue import InProcessJobQueue
from app.adapters.local.memory_blob_store import MemoryBlobStore
from app.ports.blob_store import BlobStore
from app.ports.job_queue import JobQueue
from app.ports.secret_provider import SecretProvider


@pytest.fixture
def secret_provider() -> SecretProvider:
    """Return the local environment-backed SecretProvider adapter."""
    return EnvSecretProvider()


@pytest.fixture
def blob_store() -> BlobStore:
    """Return an in-memory BlobStore scoped to the CV key prefix."""
    return MemoryBlobStore(key_prefix="cvs/")


@pytest.fixture
def job_queue() -> JobQueue:
    """Return an in-process JobQueue for publish/consume contract tests."""
    return InProcessJobQueue()
