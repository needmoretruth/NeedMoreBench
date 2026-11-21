"""Every test runs on throwaway folders: the user's settings and records are never read or written.

Without NMB_CONFIG and NMB_HOME the app's folder functions raise (only `python -m nmb` and `nmb.cli` may use the
user's folders), so a test that forgets a folder fails instead of touching their lobby or games.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

_ROOT = Path(tempfile.mkdtemp(prefix="nmb-tests-"))
os.environ["NMB_CONFIG"] = str(_ROOT / "config")
os.environ["NMB_HOME"] = str(_ROOT / "home")
os.environ.setdefault("NMB_NO_SOUND", "1")


class _EmptyKeyring:
    """Tests never read or write the computer's key store."""

    def get_password(self, _service: str, _route: str) -> None:
        return None

    def set_password(self, _service: str, _route: str, _key: str) -> None:
        raise RuntimeError("tests do not store keys")

    def delete_password(self, _service: str, _route: str) -> None:
        return None


from nmb import keys as _keys  # noqa: E402

_keys._backend = _EmptyKeyring()
