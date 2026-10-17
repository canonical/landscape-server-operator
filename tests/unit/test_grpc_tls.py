# Copyright 2026 Canonical Ltd

"""Unit tests for serving the gRPC services over TLS."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from ops.testing import Context, Relation, State, StoredState
import pytest

from charm import LandscapeServerCharm
import settings_files

CERT = "-----BEGIN CERTIFICATE-----\nleaf\n-----END CERTIFICATE-----"
CA = "-----BEGIN CERTIFICATE-----\nca\n-----END CERTIFICATE-----"
KEY = "-----BEGIN PRIVATE KEY-----\nkey\n-----END PRIVATE KEY-----"
GET_ASSIGNED = (
    "charmlibs.interfaces.tls_certificates.TLSCertificatesRequiresV4"
    ".get_assigned_certificate"
)

GRPC_SERVICES = {
    "ubuntu-installer-attach": SimpleNamespace(
        service="landscape-ubuntu-installer-attach",
        section="ubuntu_installer_attach",
        tls_dir_attr="UBUNTU_INSTALLER_ATTACH_TLS_DIR",
        enable_option="enable_ubuntu_installer_attach",
    ),
    "hostagent-messenger": SimpleNamespace(
        service="landscape-hostagent-messenger",
        section="hostagent_server",
        tls_dir_attr="HOSTAGENT_MESSENGER_TLS_DIR",
        enable_option="enable_hostagent_messenger",
    ),
}


@pytest.fixture(params=GRPC_SERVICES.values(), ids=GRPC_SERVICES.keys())
def grpc(request):
    return request.param


@pytest.fixture
def tls_dir(grpc, tmp_path, monkeypatch):
    path = tmp_path / "tls"
    monkeypatch.setattr(settings_files, grpc.tls_dir_attr, str(path))
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


def _provider_certificate(chain=(CERT, CA)):
    return SimpleNamespace(
        certificate=CERT, chain=list(chain), ca=CA, certificate_signing_request="csr"
    )


def _state(replicas_network_state, grpc=None, relation=True, paused=False, **config):
    """State with only `grpc` enabled, or no gRPC service when it is None."""
    relations = list(replicas_network_state["relations"])
    if relation:
        relations.append(
            Relation(endpoint="certificates", interface="tls-certificates")
        )
    enabled = {s.enable_option: s is grpc for s in GRPC_SERVICES.values()}
    return State(
        relations=relations,
        networks=replicas_network_state["networks"],
        config={**enabled, **config},
        stored_states=[
            StoredState(
                owner_path="LandscapeServerCharm",
                content={
                    "enable_ubuntu_installer_attach": enabled[
                        "enable_ubuntu_installer_attach"
                    ],
                    "paused": paused,
                },
            )
        ],
    )


def _conf(capture_service_conf, grpc) -> dict:
    config = capture_service_conf.get_config()
    if not config.has_section(grpc.section):
        return {}
    return {k: v for k, v in config[grpc.section].items() if k.startswith("ssl_")}


class TestCertificateRequest:
    def _requests(self, replicas_network_state, grpc, **kwargs):
        ctx = Context(LandscapeServerCharm)
        state = _state(replicas_network_state, grpc, **kwargs)
        with ctx(ctx.on.update_status(), state) as mgr:
            return mgr.charm._get_certificate_requests(), mgr.charm.unit_ip

    def test_domain_root_url(self, replicas_network_state, grpc):
        requests, unit_ip = self._requests(
            replicas_network_state, grpc, root_url="https://landscape.example.com/"
        )
        (request,) = requests
        assert request.common_name == "landscape.example.com"
        assert list(request.sans_dns) == ["landscape.example.com"]
        assert list(request.sans_ip) == [unit_ip]

    @pytest.mark.parametrize("root_url", ["", "https://10.1.2.3/"])
    def test_non_domain_root_url_uses_unit_ip(
        self, replicas_network_state, grpc, root_url
    ):
        requests, unit_ip = self._requests(
            replicas_network_state, grpc, root_url=root_url
        )
        (request,) = requests
        assert request.common_name == unit_ip
        assert not request.sans_dns
        assert list(request.sans_ip) == [unit_ip]

    def test_no_request_when_no_grpc_service_enabled(self, replicas_network_state):
        requests, _ = self._requests(replicas_network_state, None)
        assert requests == []


class TestSyncTls:
    def test_writes_files_and_service_conf_and_restarts(
        self,
        replicas_network_state,
        grpc,
        tls_dir,
        capture_service_conf,
        restart_mock,
        ownership_fixture,
    ):
        ctx = Context(LandscapeServerCharm)
        with patch(GET_ASSIGNED, return_value=(_provider_certificate(), KEY)):
            ctx.run(ctx.on.config_changed(), _state(replicas_network_state, grpc))

        assert (tls_dir / "server.crt").read_text() == f"{CERT}\n{CA}"
        assert (tls_dir / "server.key").read_text() == KEY
        assert _conf(capture_service_conf, grpc) == {
            "ssl_server_cert": str(tls_dir / "server.crt"),
            "ssl_server_private_key": str(tls_dir / "server.key"),
        }
        os_chown, os_chmod, _ = ownership_fixture
        os_chmod.assert_any_call(str(tls_dir / "server.key"), 0o640)
        os_chown.assert_any_call(str(tls_dir / "server.key"), 1000, 0)
        restart_mock.assert_any_call(grpc.service)

    def test_leaf_not_duplicated_in_chain(self, replicas_network_state, grpc, tls_dir):
        ctx = Context(LandscapeServerCharm)
        cert = _provider_certificate(chain=(CERT,))
        with patch(GET_ASSIGNED, return_value=(cert, KEY)):
            ctx.run(ctx.on.config_changed(), _state(replicas_network_state, grpc))

        assert (tls_dir / "server.crt").read_text() == CERT

    def test_no_restart_when_unchanged(
        self, replicas_network_state, grpc, restart_mock, tls_dir
    ):
        ctx = Context(LandscapeServerCharm)
        with patch(GET_ASSIGNED, return_value=(_provider_certificate(), KEY)):
            ctx.run(ctx.on.config_changed(), _state(replicas_network_state, grpc))
            restart_mock.reset_mock()
            ctx.run(ctx.on.config_changed(), _state(replicas_network_state, grpc))

        assert grpc.service not in [c.args[0] for c in restart_mock.call_args_list]

    def test_rotation_rewrites_and_restarts(
        self, replicas_network_state, grpc, restart_mock, tls_dir
    ):
        ctx = Context(LandscapeServerCharm)
        with patch(GET_ASSIGNED, return_value=(_provider_certificate(), KEY)):
            ctx.run(ctx.on.config_changed(), _state(replicas_network_state, grpc))
        restart_mock.reset_mock()

        renewed = _provider_certificate(chain=(CERT.replace("leaf", "new"), CA))
        renewed.certificate = CERT.replace("leaf", "new")
        with patch(GET_ASSIGNED, return_value=(renewed, KEY)):
            ctx.run(ctx.on.config_changed(), _state(replicas_network_state, grpc))

        assert "new" in (tls_dir / "server.crt").read_text()
        restart_mock.assert_called_once_with(grpc.service)

    def test_no_restart_while_paused(
        self, replicas_network_state, grpc, restart_mock, tls_dir
    ):
        ctx = Context(LandscapeServerCharm)
        with patch(GET_ASSIGNED, return_value=(_provider_certificate(), KEY)):
            ctx.run(
                ctx.on.config_changed(),
                _state(replicas_network_state, grpc, paused=True),
            )

        assert (tls_dir / "server.crt").exists()
        assert grpc.service not in [c.args[0] for c in restart_mock.call_args_list]

    def test_no_certificate_yet_stays_plaintext(
        self, replicas_network_state, grpc, tls_dir, capture_service_conf, restart_mock
    ):
        ctx = Context(LandscapeServerCharm)
        with patch(GET_ASSIGNED, return_value=(None, None)):
            ctx.run(ctx.on.config_changed(), _state(replicas_network_state, grpc))

        assert not tls_dir.exists()
        assert _conf(capture_service_conf, grpc).get("ssl_server_cert") is None
        assert grpc.service not in [c.args[0] for c in restart_mock.call_args_list]

    def test_removed_when_relation_absent(
        self, replicas_network_state, grpc, tls_dir, capture_service_conf, restart_mock
    ):
        ctx = Context(LandscapeServerCharm)
        with patch(GET_ASSIGNED, return_value=(_provider_certificate(), KEY)):
            ctx.run(ctx.on.config_changed(), _state(replicas_network_state, grpc))
        restart_mock.reset_mock()

        ctx.run(
            ctx.on.config_changed(),
            _state(replicas_network_state, grpc, relation=False),
        )

        assert not (tls_dir / "server.crt").exists()
        assert not (tls_dir / "server.key").exists()
        assert not _conf(capture_service_conf, grpc).get("ssl_server_cert")
        restart_mock.assert_called_once_with(grpc.service)

    def test_removed_on_relation_broken(
        self, replicas_network_state, grpc, tls_dir, capture_service_conf, restart_mock
    ):
        ctx = Context(LandscapeServerCharm)
        state = _state(replicas_network_state, grpc)
        with patch(GET_ASSIGNED, return_value=(_provider_certificate(), KEY)):
            ctx.run(ctx.on.config_changed(), state)
        restart_mock.reset_mock()

        relation = next(r for r in state.relations if r.endpoint == "certificates")
        with patch(GET_ASSIGNED, return_value=(_provider_certificate(), KEY)):
            ctx.run(ctx.on.relation_broken(relation), state)

        assert not (tls_dir / "server.key").exists()
        assert not _conf(capture_service_conf, grpc).get("ssl_server_cert")
        restart_mock.assert_called_once_with(grpc.service)
