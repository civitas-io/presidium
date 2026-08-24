"""Binds a real SpiffeIdentitySource to a real AgentRegistry -- initial sync
plus real, ongoing rotation.
"""

from __future__ import annotations

import logging

from presidium.registry import AgentRegistry
from presidium_contrib.spiffe.source import SpiffeIdentitySource

logger = logging.getLogger(__name__)


async def bind_identity_to_registry(
    source: SpiffeIdentitySource, registry: AgentRegistry, name: str
) -> None:
    """Real, initial identity sync -- updates ``name``'s stored
    ``public_key``/``public_key_algorithm`` to match ``source``'s CURRENT
    SVID, then subscribes for real, ongoing rotation: every future SVID
    renewal calls ``registry.update_identity()`` again automatically,
    keeping the registry's stored identity live for the lifetime of
    ``source``.

    The agent named ``name`` must already be registered -- this calls
    ``update_identity()``, which raises ``AgentNotFoundError`` for an
    unknown agent, matching that method's own documented contract. This
    function deliberately does NOT create the ``AgentRecord`` itself: real
    ``agent_id``/grants/trust assembly at registration time is the caller's
    own concern (it may want ``source.agent_id`` for the record's
    ``agent_id``, but that's a real, deliberate choice this function
    doesn't make on the caller's behalf), not something an identity-binding
    helper should assume or hide.
    """

    async def _sync() -> None:
        await registry.update_identity(name, source.public_key_b64, source.public_key_algorithm)
        logger.info(
            "spiffe.identity_synced agent=%s algorithm=%s",
            name,
            source.public_key_algorithm,
        )

    await _sync()
    source.subscribe_for_updates(_sync)
