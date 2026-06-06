"""In-memory BlobStore adapter for contract tests and local development."""

from app.adapters.boundary_validation import validate_blob_logical_key
from app.ports.blob_store import BlobNotFoundError


class MemoryBlobStore:
    """Process-local BlobStore backed by an in-memory dict with optional key prefix."""

    def __init__(self, key_prefix: str = "") -> None:
        """Initialize the store with an optional logical key prefix.

        Args:
            key_prefix: Prefix prepended to all keys (e.g. ``cvs/``). Trailing slash optional.
        """
        normalized_prefix = key_prefix.strip("/")
        self._key_prefix = f"{normalized_prefix}/" if normalized_prefix else ""
        self._objects: dict[str, bytes] = {}

    def _storage_key(self, key: str) -> str:
        """Return the fully qualified storage key for a logical key.

        Args:
            key: Caller-supplied logical key.

        Returns:
            str: Prefix-scoped storage key.
        """
        logical_key = validate_blob_logical_key(key)
        return f"{self._key_prefix}{logical_key}"

    def put(self, key: str, data: bytes) -> None:
        """Store bytes in memory under the prefix-scoped key."""
        self._objects[self._storage_key(key)] = data

    def get(self, key: str) -> bytes:
        """Return bytes from memory or raise when missing."""
        storage_key = self._storage_key(key)
        if storage_key not in self._objects:
            raise BlobNotFoundError(f"Blob not found: {key}")
        return self._objects[storage_key]

    def delete(self, key: str) -> None:
        """Remove bytes from memory or raise when missing."""
        storage_key = self._storage_key(key)
        if storage_key not in self._objects:
            raise BlobNotFoundError(f"Blob not found: {key}")
        del self._objects[storage_key]
