# Copyright 2026 Canonical Ltd

from ops.testing import Context, State

from charm import LandscapeServerCharm


def test_haproxy_route_requirers_always_initialized(apt_fixture):
    """
    All four HaproxyRouteRequirer instances are always created.
    """
    context = Context(LandscapeServerCharm)
    state = State(config={})

    with context(context.on.config_changed(), state) as mgr:
        charm = mgr.charm

    assert hasattr(charm, "http_haproxy_route")
