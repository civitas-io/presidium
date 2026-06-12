"""CredentialProvider Protocol and default implementations (Env, File)."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Protocol, runtime_checkable

from presidium.model import Grant

logger = logging.getLogger(__name__)


def _has_credential_grant(grants: list[Grant], credential_name: str) -> bool:
    resource = f"credential:{credential_name}"
    return any(resource in g.resources and "read" in g.actions for g in grants)


@runtime_checkable
class CredentialProvider(Protocol):
    """Protocol for governed credential resolution.

    Implementations check grants before returning credential values.
    Returns None if no grant matches or credential not found.
    """

    async def get(
        self,
        agent_id: str,
        credential_name: str,
        grants: list[Grant],
    ) -> str | None: ...

    async def close(self) -> None: ...


class EnvCredentialProvider:
    """Reads credentials from os.environ with grant checking.

    Looks up ``credential_name`` then ``credential_name.upper()`` in the
    environment. Returns None and logs a warning if the agent lacks a
    matching grant (``credential:{name}`` resource with ``read`` action).
    """

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

        value = os.environ.get(credential_name) or os.environ.get(credential_name.upper())

        if value is not None:
            logger.info(
                "credential.granted agent=%s credential=%s",
                agent_id,
                credential_name,
            )
        else:
            logger.warning(
                "credential.not_found agent=%s credential=%s source=env",
                agent_id,
                credential_name,
            )
        return value

    async def close(self) -> None:
        pass


class FileCredentialProvider:
    """Reads credentials from a key=value file with grant checking.

    File format: one ``KEY=VALUE`` per line. Lines starting with ``#``
    are comments. Blank lines are ignored. The file is read once at
    construction time.
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._secrets: dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            logger.warning("credential file not found: %s", self._path)
            return
        for line in self._path.read_text().splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            key, _, val = stripped.partition("=")
            if key:
                self._secrets[key.strip()] = val.strip()

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

        value = self._secrets.get(credential_name) or self._secrets.get(credential_name.upper())

        if value is not None:
            logger.info(
                "credential.granted agent=%s credential=%s",
                agent_id,
                credential_name,
            )
        else:
            logger.warning(
                "credential.not_found agent=%s credential=%s source=file",
                agent_id,
                credential_name,
            )
        return value

    async def close(self) -> None:
        self._secrets.clear()
