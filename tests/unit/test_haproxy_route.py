# Copyright 2026 Canonical Ltd

from unittest.mock import MagicMock, patch

from charmlibs.interfaces.tls_certificates import CertificateRequestAttributes
from ops.testing import Context, Relation, State
import pytest

from charm import LandscapeServerCharm

LEADER_IP = "10.0.0.1"
PATCH_PROVIDE = (
    "charms.haproxy.v2.haproxy_route.HaproxyRouteRequirer"
    ".provide_haproxy_route_requirements"
)


@pytest.fixture(autouse=True)
def mock_update_default_settings(monkeypatch):
    monkeypatch.setattr("charm.update_default_settings", lambda *a, **kw: None)


@pytest.fixture(autouse=True)
def mock_configure_ubuntu_installer_attach(monkeypatch):
    monkeypatch.setattr(
        LandscapeServerCharm,
        "_configure_ubuntu_installer_attach",
        lambda *a, **kw: None,
    )


def _services_called(mock):
    return [c.kwargs.get("service", "") for c in mock.call_args_list]


def _calls_for(mock, service_fragment):
    return [
        c
        for c in mock.call_args_list
        if service_fragment in c.kwargs.get("service", "")
    ]


GET_ASSIGNED_CERTIFICATE = (
    "charmlibs.interfaces.tls_certificates.TLSCertificatesRequiresV4"
    ".get_assigned_certificate"
)


def _run_provide(context, state, leader_ip=LEADER_IP):
    """
    Run config_changed, then directly invoke _provide_all_haproxy_route_requirements
    with a known leader_ip. Returns the mock capturing provide_ calls.
    """
    with patch(PATCH_PROVIDE) as mock_provide:
        with context(context.on.config_changed(), state) as mgr:
            mgr.charm._stored.leader_ip = leader_ip
            mgr.charm._provide_all_haproxy_route_requirements()
    return mock_provide


class TestCalledOnEvents:
    """_provide_all_haproxy_route_requirements is called on the right events."""

    def test_called_on_config_changed(self, replicas_network_state):
        context = Context(LandscapeServerCharm)
        state = State(**replicas_network_state)
        with patch.object(
            LandscapeServerCharm, "_provide_all_haproxy_route_requirements"
        ) as mock:
            context.run(context.on.config_changed(), state)
        assert mock.called

    def test_called_on_haproxy_route_relation_joined(self, haproxy_route_state):
        context = Context(LandscapeServerCharm)
        state = State(**haproxy_route_state)
        appserver_rel = next(
            r for r in state.relations if r.endpoint == "appserver-haproxy-route"
        )
        with patch.object(
            LandscapeServerCharm, "_provide_all_haproxy_route_requirements"
        ) as mock:
            context.run(context.on.relation_joined(appserver_rel), state)
        assert mock.called

    def test_called_on_leader_elected(self, replicas_network_state):
        context = Context(LandscapeServerCharm)
        state = State(**replicas_network_state)
        with patch.object(
            LandscapeServerCharm, "_provide_all_haproxy_route_requirements"
        ) as mock:
            context.run(context.on.leader_elected(), state)
        assert mock.called

    def test_called_on_upgrade_charm(self, replicas_network_state):
        context = Context(LandscapeServerCharm)
        state = State(**replicas_network_state)
        with patch.object(
            LandscapeServerCharm, "_provide_all_haproxy_route_requirements"
        ) as mock:
            context.run(context.on.upgrade_charm(), state)
        assert mock.called

    def test_not_called_when_no_leader_ip(self, replicas_network_state):
        """Empty leader_ip → early return, nothing published."""
        context = Context(LandscapeServerCharm)
        state = State(**replicas_network_state)
        with patch(PATCH_PROVIDE) as mock_provide:
            context.run(context.on.config_changed(), state)
        assert not mock_provide.called


class TestRedirectHttps:
    """allow_http flag on each route reflects the redirect_https config."""

    def test_redirect_https_none_all_routes_allow_http(self, replicas_network_state):
        context = Context(LandscapeServerCharm)
        state = State(config={"redirect_https": "none"}, **replicas_network_state)
        mock = _run_provide(context, state)
        assert mock.called
        for c in mock.call_args_list:
            service = c.kwargs.get("service", "")
            if "pingserver" in service or "repository" in service:
                continue
            assert c.kwargs.get("allow_http") is True, (
                f"Expected allow_http=True for {service}"
            )

    def test_redirect_https_default_only_ping_repository_message_allow_http(
        self, replicas_network_state
    ):
        context = Context(LandscapeServerCharm)
        state = State(config={"redirect_https": "default"}, **replicas_network_state)
        mock = _run_provide(context, state)
        assert mock.called
        for c in mock.call_args_list:
            service = c.kwargs.get("service", "")
            allow_http = c.kwargs.get("allow_http", False)
            if "pingserver" in service or "repository" in service:
                assert allow_http, f"Expected allow_http=True for {service}"
            else:
                assert not allow_http, f"Expected allow_http=False for {service}"

    def test_redirect_https_all_no_routes_allow_http(self, replicas_network_state):
        context = Context(LandscapeServerCharm)
        state = State(config={"redirect_https": "all"}, **replicas_network_state)
        mock = _run_provide(context, state)
        assert mock.called
        for c in mock.call_args_list:
            allow_http = c.kwargs.get("allow_http", False)
            service = c.kwargs.get("service", "")
            assert not allow_http, f"Expected allow_http=False for {service}"


class TestLeaderRoutes:
    """All units publish the same route configurations."""

    def test_appserver_includes_hashid_paths(self, replicas_network_state):
        context = Context(LandscapeServerCharm)
        state = State(leader=True, **replicas_network_state)
        mock = _run_provide(context, state)
        calls = _calls_for(mock, "appserver")
        assert calls
        paths = calls[0].kwargs["paths"]
        assert "/hash-id-databases" in paths
        assert "/repository" not in paths
        deny_paths = calls[0].kwargs["deny_paths"]
        assert "/ping" in deny_paths
        assert "/api" in deny_paths
        assert "/upload" in deny_paths
        assert "/repository" in deny_paths
        assert "/message-system" in deny_paths
        assert "/attachment" in deny_paths

    def test_repository_route_published_by_all_units(self, replicas_network_state):
        context = Context(LandscapeServerCharm)
        state = State(leader=False, **replicas_network_state)
        mock = _run_provide(context, state)
        assert any("repository" in s for s in _services_called(mock))

    def test_all_units_publish_package_upload_route(self, replicas_network_state):
        context = Context(LandscapeServerCharm)
        state = State(leader=False, **replicas_network_state)
        mock = _run_provide(context, state)
        assert any("package-upload" in s for s in _services_called(mock))

    def test_package_upload_has_health_checks(self, replicas_network_state):
        context = Context(LandscapeServerCharm)
        state = State(**replicas_network_state)
        mock = _run_provide(context, state)
        calls = _calls_for(mock, "package-upload")
        assert calls
        assert calls[0].kwargs.get("check_interval") == 2
        assert calls[0].kwargs.get("check_rise") == 2
        assert calls[0].kwargs.get("check_fall") == 3


class TestHostname:
    """hostname reflects root_url config or falls back to leader_ip."""

    def test_hostname_from_root_url(self, replicas_network_state):
        context = Context(LandscapeServerCharm)
        state = State(
            config={"root_url": "https://my.landscape.example.com/"},
            **replicas_network_state,
        )
        mock = _run_provide(context, state)
        assert mock.called
        for c in mock.call_args_list:
            assert c.kwargs.get("hostname") == "my.landscape.example.com", (
                f"Wrong hostname for {c.kwargs.get('service')}"
            )

    def test_hostname_omitted_when_no_root_url(self, replicas_network_state):
        context = Context(LandscapeServerCharm)
        state = State(config={}, **replicas_network_state)
        mock = _run_provide(context, state, leader_ip=LEADER_IP)
        assert mock.called
        for c in mock.call_args_list:
            assert c.kwargs.get("hostname") is None, (
                f"A leader IP is not a valid hostname for {c.kwargs.get('service')}"
            )


class TestServiceNames:
    """Service names include the model UUID to ensure uniqueness across models."""

    def test_service_names_include_model_uuid(self, replicas_network_state):
        context = Context(LandscapeServerCharm)
        state = State(**replicas_network_state)
        with patch(PATCH_PROVIDE) as mock_provide:
            with context(context.on.config_changed(), state) as mgr:
                model_uuid = mgr.charm.model.uuid
                mgr.charm._stored.leader_ip = LEADER_IP
                mgr.charm._provide_all_haproxy_route_requirements()
        assert mock_provide.called
        for c in mock_provide.call_args_list:
            service = c.kwargs.get("service", "")
            assert model_uuid in service, (
                f"Expected model UUID in service name: {service}"
            )

    def test_appserver_service_name_prefix(self, replicas_network_state):
        context = Context(LandscapeServerCharm)
        state = State(**replicas_network_state)
        mock = _run_provide(context, state)
        calls = _calls_for(mock, "appserver")
        assert calls
        assert calls[0].kwargs["service"].startswith("landscape-appserver-")

    def test_pingserver_service_name_prefix(self, replicas_network_state):
        context = Context(LandscapeServerCharm)
        state = State(**replicas_network_state)
        mock = _run_provide(context, state)
        calls = _calls_for(mock, "pingserver")
        assert calls
        assert calls[0].kwargs["service"].startswith("landscape-pingserver-")


class TestHealthChecks:
    """Each route uses check_path with the path the backend actually serves."""

    def test_no_check_port_on_any_route(self, replicas_network_state):
        context = Context(LandscapeServerCharm)
        state = State(**replicas_network_state)
        mock = _run_provide(context, state)
        for c in mock.call_args_list:
            assert "check_port" not in c.kwargs, (
                f"check_port should not be set for {c.kwargs.get('service')}"
            )

    def test_appserver_check_path(self, replicas_network_state):
        context = Context(LandscapeServerCharm)
        state = State(**replicas_network_state)
        mock = _run_provide(context, state)
        calls = _calls_for(mock, "appserver")
        assert calls[0].kwargs.get("check_path") == "/"

    def test_pingserver_check_path(self, replicas_network_state):
        context = Context(LandscapeServerCharm)
        state = State(**replicas_network_state)
        mock = _run_provide(context, state)
        calls = _calls_for(mock, "pingserver")
        assert calls[0].kwargs.get("check_path") == "/ping"

    def test_message_server_check_path(self, replicas_network_state):
        context = Context(LandscapeServerCharm)
        state = State(**replicas_network_state)
        mock = _run_provide(context, state)
        calls = _calls_for(mock, "message-server")
        assert calls[0].kwargs.get("check_path") == "/message-system"

    def test_api_check_path(self, replicas_network_state):
        context = Context(LandscapeServerCharm)
        state = State(**replicas_network_state)
        mock = _run_provide(context, state)
        calls = _calls_for(mock, "api")
        assert calls[0].kwargs.get("check_path") == "/api/about"

    def test_package_upload_check_path(self, replicas_network_state):
        context = Context(LandscapeServerCharm)
        state = State(**replicas_network_state)
        mock = _run_provide(context, state)
        calls = _calls_for(mock, "package-upload")
        assert calls[0].kwargs.get("check_path") == "/upload"

    def test_repository_has_no_health_check(self, replicas_network_state):
        context = Context(LandscapeServerCharm)
        state = State(**replicas_network_state)
        mock = _run_provide(context, state)
        calls = _calls_for(mock, "repository")
        assert "check_path" not in calls[0].kwargs
        assert "check_interval" not in calls[0].kwargs

    def test_appserver_has_health_check_timing(self, replicas_network_state):
        context = Context(LandscapeServerCharm)
        state = State(**replicas_network_state)
        mock = _run_provide(context, state)
        calls = _calls_for(mock, "appserver")
        assert calls[0].kwargs.get("check_interval") == 2
        assert calls[0].kwargs.get("check_rise") == 2
        assert calls[0].kwargs.get("check_fall") == 3

    def test_pingserver_has_health_check_timing(self, replicas_network_state):
        context = Context(LandscapeServerCharm)
        state = State(**replicas_network_state)
        mock = _run_provide(context, state)
        calls = _calls_for(mock, "pingserver")
        assert calls[0].kwargs.get("check_interval") == 2
        assert calls[0].kwargs.get("check_rise") == 2
        assert calls[0].kwargs.get("check_fall") == 3

    def test_message_server_has_health_check_timing(self, replicas_network_state):
        context = Context(LandscapeServerCharm)
        state = State(**replicas_network_state)
        mock = _run_provide(context, state)
        calls = _calls_for(mock, "message-server")
        assert calls[0].kwargs.get("check_interval") == 2
        assert calls[0].kwargs.get("check_rise") == 2
        assert calls[0].kwargs.get("check_fall") == 3

    def test_api_has_health_check_timing(self, replicas_network_state):
        context = Context(LandscapeServerCharm)
        state = State(**replicas_network_state)
        mock = _run_provide(context, state)
        calls = _calls_for(mock, "api")
        assert calls[0].kwargs.get("check_interval") == 2
        assert calls[0].kwargs.get("check_rise") == 2
        assert calls[0].kwargs.get("check_fall") == 3


class TestUbuntuInstallerAttachRoute:
    """ubuntu-installer-attach serves TLS and is routed with haproxy-route (HTTPS)."""

    @staticmethod
    def _routes(
        network_state, with_certificates=True, certificate_assigned=True, **config
    ):
        """Route requirements published for ubuntu-installer-attach."""
        relations = list(network_state.get("relations", []))
        if with_certificates:
            relations.append(
                Relation(endpoint="certificates", interface="tls-certificates")
            )
        state = State(config=config, **{**network_state, "relations": relations})
        assigned = (MagicMock(), MagicMock()) if certificate_assigned else (None, None)
        with (
            patch.object(
                LandscapeServerCharm,
                "_get_certificate_requests",
                return_value=[CertificateRequestAttributes(common_name="landscape")],
            ),
            patch(GET_ASSIGNED_CERTIFICATE, return_value=assigned),
        ):
            mock = _run_provide(Context(LandscapeServerCharm), state)
        return _calls_for(mock, "ubuntu-installer-attach")

    def test_published_when_enabled(self, replicas_network_state):
        calls = self._routes(
            replicas_network_state, enable_ubuntu_installer_attach=True
        )
        assert calls

    def test_not_published_when_disabled(self, replicas_network_state):
        calls = self._routes(
            replicas_network_state, enable_ubuntu_installer_attach=False
        )
        assert calls == []

    def test_route_data(self, replicas_network_state):
        calls = self._routes(
            replicas_network_state,
            enable_ubuntu_installer_attach=True,
            root_url="https://my.landscape.example.com/",
            ubuntu_installer_attach_base_port=50123,
        )
        kwargs = calls[-1].kwargs
        assert kwargs["service"].startswith("landscape-ubuntu-installer-attach-")
        assert kwargs["protocol"] == "https"
        assert kwargs["external_grpc_port"] == 50051
        assert kwargs["ports"] == [50123]
        assert kwargs["hostname"] == "my.landscape.example.com"
        assert kwargs["unit_address"]
        assert "paths" not in kwargs

    def test_hostname_omitted_without_domain(self, replicas_network_state):
        calls = self._routes(
            replicas_network_state,
            enable_ubuntu_installer_attach=True,
            root_url="",
        )
        assert calls[-1].kwargs["hostname"] is None

    def test_not_published_until_certificate_assigned(self, replicas_network_state):
        calls = self._routes(
            replicas_network_state,
            certificate_assigned=False,
            enable_ubuntu_installer_attach=True,
        )
        assert calls == []

    def test_not_published_without_certificates(self, replicas_network_state):
        """gRPC routing needs an HTTPS backend, so no certificate means no route."""
        route = Relation(
            endpoint="ubuntu-installer-attach-haproxy-route",
            interface="haproxy-route",
            local_app_data={"service": '"landscape-ubuntu-installer-attach"'},
            local_unit_data={"address": '"10.0.0.1"'},
        )
        state = State(
            config={"enable_ubuntu_installer_attach": True},
            leader=True,
            **{
                **replicas_network_state,
                "relations": [
                    *replicas_network_state.get("relations", []),
                    route,
                ],
            },
        )
        context = Context(LandscapeServerCharm)
        with patch(PATCH_PROVIDE) as mock_provide:
            with context(context.on.config_changed(), state) as manager:
                manager.charm._stored.leader_ip = LEADER_IP
                manager.charm._provide_all_haproxy_route_requirements()
                result = manager.run()

        assert _calls_for(mock_provide, "ubuntu-installer-attach") == []
        cleared = result.get_relation(route.id)
        assert cleared.local_app_data == {}
        assert cleared.local_unit_data == {}
