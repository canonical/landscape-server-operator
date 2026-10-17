# Copyright 2026 Canonical Ltd

"""Unit tests for routing hostagent-messenger over HTTPS."""

from configparser import ConfigParser
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from ops.testing import Context, Relation, State, StoredState
import pytest

from charm import LandscapeServerCharm
import settings_files

CERT = "-----BEGIN CERTIFICATE-----\nleaf\n-----END CERTIFICATE-----"
CA = "-----BEGIN CERTIFICATE-----\nca\n-----END CERTIFICATE-----"
KEY = "-----BEGIN PRIVATE KEY-----\nkey\n-----END PRIVATE KEY-----"
SECTION = "hostagent_server"
SERVICE = "landscape-hostagent-messenger"
ROUTE = "hostagent-messenger-haproxy-route"
GET_ASSIGNED = (
    "charmlibs.interfaces.tls_certificates.TLSCertificatesRequiresV4"
    ".get_assigned_certificate"
)
PATCH_PROVIDE = (
    "charms.haproxy.v2.haproxy_route.HaproxyRouteRequirer"
    ".provide_haproxy_route_requirements"
)


@pytest.fixture(autouse=True)
def tls_dir(tmp_path, monkeypatch):
    path = tmp_path / "hostagent-messenger"
    monkeypatch.setattr(settings_files, "HOSTAGENT_MESSENGER_TLS_DIR", str(path))
    return path


@pytest.fixture(autouse=True)
def landscape_user(monkeypatch):
    monkeypatch.setattr(
        "charm.user_exists", lambda name: SimpleNamespace(pw_uid=1000, pw_gid=1000)
    )


@pytest.fixture(autouse=True)
def restart_mock(monkeypatch):
    mock = MagicMock()
    monkeypatch.setattr("charm.service_restart", mock)
    return mock


@pytest.fixture(autouse=True)
def no_side_effects(monkeypatch):
    monkeypatch.setattr(
        LandscapeServerCharm, "_configure_ubuntu_installer_attach", lambda *a: None
    )
    monkeypatch.setattr("charm.update_default_settings", lambda *a, **kw: None)


@pytest.fixture
def server_without_tls_support(monkeypatch):
    """
    Simulate a Landscape Server whose service.conf migration drops the
    `hostagent_server` ssl_server_* settings, because it can't serve TLS.
    """

    def migrate():
        config = ConfigParser()
        config.read(settings_files.SERVICE_CONF)
        if config.has_section(SECTION):
            config.remove_option(SECTION, "ssl_server_cert")
            config.remove_option(SECTION, "ssl_server_private_key")
        with open(settings_files.SERVICE_CONF, "w") as fp:
            config.write(fp)

    monkeypatch.setattr(settings_files, "migrate_service_conf", migrate)


ISSUED = (
    SimpleNamespace(
        certificate=CERT, chain=[CERT, CA], ca=CA, certificate_signing_request="csr"
    ),
    KEY,
)


def _relations(network_state, certificates=True):
    relations = list(network_state["relations"])
    if certificates:
        relations.append(
            Relation(endpoint="certificates", interface="tls-certificates")
        )
    relations.append(
        Relation(
            endpoint=ROUTE,
            interface="haproxy-route",
            local_app_data={"service": '"stale"'},
            local_unit_data={"address": '"10.0.0.1"'},
        )
    )
    return relations


def _state(network_state, enabled=True, **relations):
    return State(
        leader=True,
        relations=_relations(network_state, **relations),
        networks=network_state["networks"],
        config={"enable_hostagent_messenger": enabled},
        stored_states=[
            StoredState(
                owner_path="LandscapeServerCharm", content={"leader_ip": "10.0.0.1"}
            )
        ],
    )


def _run(state, certificate=(None, None), event=None):
    """
    Run `event` (config_changed by default), returning the output state and
    the route requirements published for hostagent-messenger.
    """
    ctx = Context(LandscapeServerCharm)
    with (
        patch(GET_ASSIGNED, return_value=certificate),
        patch(PATCH_PROVIDE) as provide,
    ):
        out = ctx.run(event or ctx.on.config_changed(), state)
    route_calls = [
        c
        for c in provide.call_args_list
        if "hostagent-messenger" in c.kwargs.get("service", "")
    ]
    return out, route_calls


def _route_data(state):
    relation = next(r for r in state.relations if r.endpoint == ROUTE)
    return dict(relation.local_app_data), dict(relation.local_unit_data)


def test_publishes_https_route_once_serving_tls(
    replicas_network_state, tls_dir, capture_service_conf
):
    _, route_calls = _run(_state(replicas_network_state), certificate=ISSUED)

    kwargs = route_calls[-1].kwargs
    assert kwargs["service"].startswith("landscape-hostagent-messenger-")
    assert kwargs["protocol"] == "https"
    assert kwargs["external_grpc_port"] == 6554
    assert kwargs["ports"] == [50052]
    assert "paths" not in kwargs


class TestRouteWithdrawn:
    """
    The HTTPS route re-encrypts to the backend, so it is only published once the
    backend serves TLS; otherwise any stale route data is withdrawn.
    """

    def test_without_certificates(self, replicas_network_state, tls_dir):
        out, route_calls = _run(
            _state(replicas_network_state, certificates=False), certificate=ISSUED
        )

        assert route_calls == []
        assert _route_data(out) == ({}, {})

    def test_until_certificate_issued(self, replicas_network_state, tls_dir):
        out, route_calls = _run(_state(replicas_network_state))

        assert route_calls == []
        assert _route_data(out) == ({}, {})

    def test_when_server_cannot_serve_tls(
        self,
        replicas_network_state,
        tls_dir,
        restart_mock,
        server_without_tls_support,
    ):
        out, route_calls = _run(_state(replicas_network_state), certificate=ISSUED)

        assert not tls_dir.exists()
        assert SERVICE not in [c.args[0] for c in restart_mock.call_args_list]
        assert route_calls == []
        assert _route_data(out) == ({}, {})

    def test_when_disabled(self, replicas_network_state, tls_dir):
        out, route_calls = _run(
            _state(replicas_network_state, enabled=False), certificate=ISSUED
        )

        assert route_calls == []
        assert _route_data(out) == ({}, {})

    def test_certificates_broken(
        self, replicas_network_state, tls_dir, capture_service_conf
    ):
        state = _state(replicas_network_state)
        _run(state, certificate=ISSUED)

        relation = next(r for r in state.relations if r.endpoint == "certificates")
        ctx = Context(LandscapeServerCharm)
        out, route_calls = _run(
            state, certificate=ISSUED, event=ctx.on.relation_broken(relation)
        )

        assert route_calls == []
        assert _route_data(out) == ({}, {})


def test_route_joined_publishes_https_route(
    replicas_network_state, tls_dir, capture_service_conf
):
    state = _state(replicas_network_state)
    _run(state, certificate=ISSUED)
    relation = next(r for r in state.relations if r.endpoint == ROUTE)
    ctx = Context(LandscapeServerCharm)
    _, route_calls = _run(
        state, certificate=ISSUED, event=ctx.on.relation_joined(relation)
    )

    assert route_calls[-1].kwargs["external_grpc_port"] == 6554
