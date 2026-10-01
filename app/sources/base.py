"""Job source abstraction — one Protocol per provider.

Modeled on the provider pattern of zackangelo/gkhr-interview-assistant
(`TelnyxClient` Protocol + `HttpTelnyxClient` impl): the sync service talks
only to `JobSource`, never to a concrete provider. Every implementation
returns items already normalized to the `upsert_job` shape, so the
classifier (Laya/heuristic) is provider-agnostic.

All sources are read-only by design: there is intentionally no interface
here that writes to any provider.
"""

from typing import Protocol


class SourceUnavailableError(Exception):
    """The source cannot serve requests (missing session, network, upstream)."""


class JobSource(Protocol):
    """A read-only provider of normalized job items."""

    name: str

    async def search(self, keywords: str, location: str, limit: int = 25) -> list[dict]:
        """Return up to `limit` normalized job items for one keyword.

        Each item MUST contain at least `source`, `source_id` and `title`,
        and SHOULD carry `company`, `location`, `remote`, `url`,
        `description`, `posted_at` and `raw`.
        """
        ...

    async def details(self, item: dict) -> dict:
        """Return `item` enriched with the full description from upstream.

        Implementations must never wipe good search data (partial-success):
        only non-empty detail fields overwrite. Raises `KeyError` when the
        job does not exist upstream.
        """
        ...
