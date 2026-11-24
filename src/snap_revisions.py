"""Load the Snap Store revisions pinned to this charm release."""

import json
from pathlib import Path
import platform


class SnapRevisionError(RuntimeError):
    """Raised when no snap revision is pinned for this unit."""


_ARCHITECTURE_ALIASES = {
    "x86_64": "amd64",
    "amd64": "amd64",
    "aarch64": "arm64",
    "arm64": "arm64",
}


def _load_snap_revisions() -> dict[str, dict[str, str]]:
    manifest_path = Path(__file__).parent / "snap_revisions.json"
    with manifest_path.open() as manifest_file:
        return json.load(manifest_file)


def get_architecture() -> str:
    """Return the snap architecture name for this machine."""
    machine = platform.machine().lower()
    try:
        return _ARCHITECTURE_ALIASES[machine]
    except KeyError as exc:
        raise SnapRevisionError(f"Unsupported snap architecture: {machine}") from exc


def get_snap_revision(snap_name: str) -> str:
    """Return the revision pinned for a snap on this machine's architecture."""
    architecture = get_architecture()
    try:
        return _load_snap_revisions()[snap_name][architecture]
    except KeyError as exc:
        raise SnapRevisionError(
            f"No revision pinned for {snap_name} on {architecture}"
        ) from exc
