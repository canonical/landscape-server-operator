# Copyright 2026 Canonical Ltd

"""Unit tests for serving and routing hostagent-messenger over TLS."""

from configparser import ConfigParser
from dataclasses import replace
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


def _provider_certificate():
    return SimpleNamespace(
        certificate=CERT, chain=[CERT, CA], ca=CA, certificate_signing_request="csr"
    )


def _relations(network_state, certificates=True, route=True):
    relations = list(network_state["relations"])
    if certificates:
        relations.append(
            Relation(endpoint="certificates", interface="tls-certificates")
        )
    if route:
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


def _conf(capture_service_conf) -> dict:
    config = capture_service_conf.get_config()
    return dict(config[SECTION]) if config.has_section(SECTION) else {}


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


def _local_data(state, endpoint):
    relation = next(r for r in state.relations if r.endpoint == endpoint)
    return dict(relation.local_app_data), dict(relation.local_unit_data)


ISSUED = (_provider_certificate(), KEY)


class TestCertificateRequest:
    def test_requested_for_hostagent_messenger_alone(self, replicas_network_state):
        ctx = Context(LandscapeServerCharm)
        state = State(
            relations=replicas_network_state["relations"],
            networks=replicas_network_state["networks"],
            config={
                "enable_hostagent_messenger": True,
                "enable_ubuntu_installer_attach": False,
                "root_url": "https://landscape.example.com/",
            },
        )
        with ctx(ctx.on.update_status(), state) as mgr:
            (request,) = mgr.charm._get_certificate_requests()
            unit_ip = mgr.charm.unit_ip

        assert request.common_name == "landscape.example.com"
        assert list(request.sans_ip) == [unit_ip]

    def test_not_requested_when_no_grpc_service_enabled(self, replicas_network_state):
        ctx = Context(LandscapeServerCharm)
        state = State(
            relations=replicas_network_state["relations"],
            networks=replicas_network_state["networks"],
            config={
                "enable_hostagent_messenger": False,
                "enable_ubuntu_installer_attach": False,
            },
        )
        with ctx(ctx.on.update_status(), state) as mgr:
            assert mgr.charm._get_certificate_requests() == []


class TestServeTls:
    def test_serves_tls_and_publishes_https_route(
        self, replicas_network_state, tls_dir, capture_service_conf, restart_mock
    ):
        _, route_calls = _run(_state(replicas_network_state), certificate=ISSUED)

        assert (tls_dir / "server.crt").read_text() == f"{CERT}\n{CA}"
        assert (tls_dir / "server.key").read_text() == KEY
        assert _conf(capture_service_conf) == {
            "ssl_server_cert": str(tls_dir / "server.crt"),
            "ssl_server_private_key": str(tls_dir / "server.key"),
        }
        restart_mock.assert_any_call(SERVICE)

        kwargs = route_calls[-1].kwargs
        assert kwargs["service"].startswith("landscape-hostagent-messenger-")
        assert kwargs["protocol"] == "https"
        assert kwargs["external_grpc_port"] == 6554
        assert kwargs["ports"] == [50052]
        assert "paths" not in kwargs

    def test_hostname_is_root_url_hostname(self, replicas_network_state):
        state = replace(
            _state(replicas_network_state),
            config={
                "enable_hostagent_messenger": True,
                "root_url": "https://my.landscape.example.com/",
            },
        )
        _, route_calls = _run(state, certificate=ISSUED)

        assert route_calls[-1].kwargs["hostname"] == "my.landscape.example.com"

    def test_no_restart_when_unchanged(self, replicas_network_state, restart_mock):
        _run(_state(replicas_network_state), certificate=ISSUED)
        restart_mock.reset_mock()

        _run(_state(replicas_network_state), certificate=ISSUED)

        assert SERVICE not in [c.args[0] for c in restart_mock.call_args_list]

    def test_rotation_rewrites_and_restarts(
        self, replicas_network_state, tls_dir, restart_mock
    ):
        _run(_state(replicas_network_state), certificate=ISSUED)
        restart_mock.reset_mock()

        renewed = _provider_certificate()
        renewed.certificate = CERT.replace("leaf", "new")
        renewed.chain = [renewed.certificate, CA]
        _run(_state(replicas_network_state), certificate=(renewed, KEY))

        assert "new" in (tls_dir / "server.crt").read_text()
        restart_mock.assert_any_call(SERVICE)

    def test_serves_tls_before_route_is_related(
        self, replicas_network_state, capture_service_conf
    ):
        """The certificate doesn't depend on the route, so TLS is ready for it."""
        _run(_state(replicas_network_state, route=False), certificate=ISSUED)

        assert _conf(capture_service_conf).get("ssl_server_cert")


class TestRouteWithdrawn:
    """
    The HTTPS route re-encrypts to the backend, so it is only published once the
    backend serves TLS; otherwise any stale route data is withdrawn.
    """

    def test_without_certificates(
        self, replicas_network_state, tls_dir, capture_service_conf
    ):
        out, route_calls = _run(
            _state(replicas_network_state, certificates=False), certificate=ISSUED
        )

        assert not tls_dir.exists()
        assert not _conf(capture_service_conf).get("ssl_server_cert")
        assert route_calls == []
        assert _local_data(out, ROUTE) == ({}, {})

    def test_until_certificate_issued(
        self, replicas_network_state, tls_dir, restart_mock
    ):
        out, route_calls = _run(_state(replicas_network_state))

        assert not tls_dir.exists()
        restart_mock.assert_not_called()
        assert route_calls == []
        assert _local_data(out, ROUTE) == ({}, {})

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
        assert _local_data(out, ROUTE) == ({}, {})

    def test_when_disabled(self, replicas_network_state, tls_dir):
        out, route_calls = _run(
            _state(replicas_network_state, enabled=False), certificate=ISSUED
        )

        assert not tls_dir.exists()
        assert route_calls == []
        assert _local_data(out, ROUTE) == ({}, {})

    def test_certificates_broken(
        self, replicas_network_state, tls_dir, capture_service_conf, restart_mock
    ):
        state = _state(replicas_network_state)
        _run(state, certificate=ISSUED)
        restart_mock.reset_mock()

        relation = next(r for r in state.relations if r.endpoint == "certificates")
        ctx = Context(LandscapeServerCharm)
        out, route_calls = _run(
            state, certificate=ISSUED, event=ctx.on.relation_broken(relation)
        )

        assert not (tls_dir / "server.key").exists()
        assert not _conf(capture_service_conf).get("ssl_server_cert")
        restart_mock.assert_any_call(SERVICE)
        assert route_calls == []
        assert _local_data(out, ROUTE) == ({}, {})


def test_route_joined_publishes_https_route(replicas_network_state):
    state = _state(replicas_network_state)
    relation = next(r for r in state.relations if r.endpoint == ROUTE)
    ctx = Context(LandscapeServerCharm)
    _, route_calls = _run(
        state, certificate=ISSUED, event=ctx.on.relation_joined(relation)
    )

    assert route_calls[-1].kwargs["external_grpc_port"] == 6554
