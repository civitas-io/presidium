"""OpenBaoCredentialProvider — reads secrets from OpenBao/Vault KV v2."""

from __future__ import annotations

import logging
from typing import Any

import hvac

from presidium.credentials import _has_credential_grant
from presidium.model import Grant

logger = logging.getLogger(__name__)


class OpenBaoCredentialProvider:
    """Reads credentials from an OpenBao or Vault KV v2 engine.

    API-compatible with both OpenBao (MPL 2.0, OpenSSF Sandbox) and
    HashiCorp Vault. Uses the ``hvac`` Python client.

    Secret path convention: ``{mount}/data/agents/{agent_name}/{credential_name}``

    Grant checking: requires ``credential:{name}`` resource with ``read``
    action in the agent's grants before resolving.
    """

    def __init__(
        self,
        url: str = "http://localhost:8200",
        token: str | None = None,
        mount_point: str = "secret",
        namespace: str | None = None,
    ) -> None:
        self._client = hvac.Client(url=url, token=token, namespace=namespace)
        self._mount = mount_point

    async def get(
        self,
        agent_id: str,
        credential_name: str,
        grants: list[Grant],
    ) -> str | None:
        if not _has_credential_grant(grants, credential_name):
            logger.warning(
                "credential.denied agent=%s credential=%s reason=no_matching_grant",
                agent_id,
                credential_name,
            )
            return None

        agent_name = agent_id.rsplit("/", 1)[-1]
        path = f"agents/{agent_name}/{credential_name}"

        try:
            response: dict[str, Any] = self._client.secrets.kv.v2.read_secret_version(
                path=path,
                mount_point=self._mount,
            )
            data = response.get("data", {}).get("data", {})
            value = data.get("value")
        except Exception:
            logger.exception(
                "credential.error agent=%s credential=%s source=openbao",
                agent_id,
                credential_name,
            )
            return None

        if value is not None:
            logger.info("credential.granted agent=%s credential=%s", agent_id, credential_name)
        else:
            logger.warning(
                "credential.not_found agent=%s credential=%s source=openbao",
                agent_id,
                credential_name,
            )
        return str(value) if value is not None else None

    async def close(self) -> None:
        pass
