"""Job Source registry mapping source names to JobSource adapter instances.

The registry is the single point of discovery for the worker pipeline;
new sources (e.g. LinkedIn post-MVP) are added by registering an adapter
without modifying pipeline code.

Source names are canonical board identifiers (e.g. ``"adzuna"``, ``"reed"``).
"""

from app.job_sources.base import JobSource, JobSourceError


class JobSourceNotFoundError(JobSourceError):
    """Raised when the registry is asked for a source name that was never registered."""


class JobSourceRegistry:
    """In-process registry holding named JobSource adapters.

    Sources are registered at application startup and resolved by name during
    worker pipeline execution.
    """

    def __init__(self) -> None:
        """Initialise an empty registry."""
        self._sources: dict[str, JobSource] = {}

    def register(self, name: str, source: JobSource) -> None:
        """Add or replace a Job Source adapter under the given name.

        Args:
            name: Canonical source identifier (e.g. ``"adzuna"``, ``"reed"``).
            source: Adapter instance implementing the JobSource protocol.
        """
        self._sources[name] = source

    def get(self, name: str) -> JobSource:
        """Return the registered adapter for the given source name.

        Args:
            name: Canonical source identifier previously passed to :meth:`register`.

        Returns:
            JobSource: The registered adapter.

        Raises:
            JobSourceNotFoundError: When ``name`` has not been registered.
        """
        source = self._sources.get(name)
        if source is None:
            raise JobSourceNotFoundError(
                f"No Job Source registered under the name '{name}'. "
                f"Available sources: {sorted(self._sources)}"
            )
        return source

    def all_sources(self) -> list[JobSource]:
        """Return all registered adapters in insertion order.

        Returns:
            list[JobSource]: Every adapter currently held in the registry.
        """
        return list(self._sources.values())
