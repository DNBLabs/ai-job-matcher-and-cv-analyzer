"""BlobStore port for encrypted CV object storage without cloud SDK coupling."""

from typing import Protocol


class BlobNotFoundError(LookupError):
    """Raised when a blob key does not exist in the store."""


class InvalidBlobKeyError(ValueError):
    """Raised when a blob key fails boundary validation."""


class BlobStore(Protocol):
    """Port for storing and retrieving binary objects by key."""

    def put(self, key: str, data: bytes) -> None:
        """Store bytes at the given logical key.

        Args:
            key: Object key relative to the configured prefix (e.g. ``user_id/uuid.pdf``).
            data: Raw object bytes to persist.

        Raises:
            InvalidBlobKeyError: When the key fails boundary validation.
        """
        ...

    def get(self, key: str) -> bytes:
        """Return bytes stored at the given logical key.

        Args:
            key: Object key relative to the configured prefix.

        Returns:
            bytes: Stored object content.

        Raises:
            BlobNotFoundError: When no object exists for the key.
            InvalidBlobKeyError: When the key fails boundary validation.
        """
        ...

    def delete(self, key: str) -> None:
        """Remove the object at the given logical key.

        Args:
            key: Object key relative to the configured prefix.

        Raises:
            BlobNotFoundError: When no object exists for the key.
            InvalidBlobKeyError: When the key fails boundary validation.
        """
        ...
