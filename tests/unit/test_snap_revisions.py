import pytest

import snap_revisions
from snap_revisions import get_architecture, get_snap_revision, SnapRevisionError


@pytest.mark.parametrize(
    "machine,architecture",
    [
        ("x86_64", "amd64"),
        ("AMD64", "amd64"),
        ("aarch64", "arm64"),
        ("arm64", "arm64"),
    ],
)
def test_get_architecture(monkeypatch, machine, architecture):
    monkeypatch.setattr(snap_revisions.platform, "machine", lambda: machine)

    assert get_architecture() == architecture


def test_get_architecture_rejects_unsupported_machine(monkeypatch):
    monkeypatch.setattr(snap_revisions.platform, "machine", lambda: "s390x")

    with pytest.raises(SnapRevisionError, match="Unsupported snap architecture"):
        get_architecture()


def test_get_snap_revision_uses_machine_architecture(monkeypatch):
    monkeypatch.setattr(snap_revisions.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(
        snap_revisions,
        "_load_snap_revisions",
        lambda: {"test-snap": {"amd64": "78", "arm64": "77"}},
    )

    assert get_snap_revision("test-snap") == "78"


def test_get_snap_revision_rejects_missing_architecture(monkeypatch):
    monkeypatch.setattr(snap_revisions.platform, "machine", lambda: "aarch64")
    monkeypatch.setattr(
        snap_revisions,
        "_load_snap_revisions",
        lambda: {"test-snap": {"amd64": "78"}},
    )

    with pytest.raises(SnapRevisionError, match="No revision pinned.*arm64"):
        get_snap_revision("test-snap")


@pytest.mark.parametrize(
    "machine,revision",
    [("x86_64", "82"), ("aarch64", "81")],
)
def test_landscape_server_revision_is_pinned(monkeypatch, machine, revision):
    monkeypatch.setattr(snap_revisions.platform, "machine", lambda: machine)
    monkeypatch.setattr(
        snap_revisions,
        "_load_snap_revisions",
        lambda: {"landscape-server": {"amd64": "82", "arm64": "81"}},
    )

    assert get_snap_revision("landscape-server") == revision
