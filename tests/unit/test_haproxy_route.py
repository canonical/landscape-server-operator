# Copyright 2026 Canonical Ltd

from unittest.mock import patch

from ops.testing import Context, State
import pytest

from charm import LandscapeServerCharm

LEADER_IP = "10.0.0.1"
PATCH_PROVIDE = (
    "charms.haproxy.v1.haproxy_route.HaproxyRouteRequirer"
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
        assert calls[0].kwargs.get("check_interval") == 2000
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

    def test_hostname_falls_back_to_leader_ip_when_no_root_url(
        self, replicas_network_state
    ):
        context = Context(LandscapeServerCharm)
        state = State(config={}, **replicas_network_state)
        mock = _run_provide(context, state, leader_ip=LEADER_IP)
        assert mock.called
        for c in mock.call_args_list:
            assert c.kwargs.get("hostname") == LEADER_IP, (
                f"Expected leader IP as hostname for {c.kwargs.get('service')}"
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


class TestConditionalRoutes:
    """hostagent-messenger and ubuntu-installer-attach routes are conditional."""

    def test_hostagent_messenger_published_when_enabled(self, replicas_network_state):
        context = Context(LandscapeServerCharm)
        state = State(
            config={"enable_hostagent_messenger": True}, **replicas_network_state
        )
        mock = _run_provide(context, state)
        assert any("hostagent-messenger" in s for s in _services_called(mock))

    def test_hostagent_messenger_not_published_when_disabled(
        self, replicas_network_state
    ):
        context = Context(LandscapeServerCharm)
        state = State(
            config={"enable_hostagent_messenger": False}, **replicas_network_state
        )
        mock = _run_provide(context, state)
        assert not any("hostagent-messenger" in s for s in _services_called(mock))

    def test_ubuntu_installer_attach_published_when_enabled(
        self, replicas_network_state
    ):
        context = Context(LandscapeServerCharm)
        state = State(
            config={"enable_ubuntu_installer_attach": True}, **replicas_network_state
        )
        mock = _run_provide(context, state)
        assert any("ubuntu-installer-attach" in s for s in _services_called(mock))

    def test_ubuntu_installer_attach_not_published_when_disabled(
        self, replicas_network_state
    ):
        context = Context(LandscapeServerCharm)
        state = State(
            config={"enable_ubuntu_installer_attach": False}, **replicas_network_state
        )
        mock = _run_provide(context, state)
        assert not any("ubuntu-installer-attach" in s for s in _services_called(mock))

    def test_hostagent_messenger_uses_correct_grpc_port(self, replicas_network_state):
        context = Context(LandscapeServerCharm)
        state = State(
            config={"enable_hostagent_messenger": True}, **replicas_network_state
        )
        mock = _run_provide(context, state)
        calls = _calls_for(mock, "hostagent-messenger")
        assert calls
        assert calls[0].kwargs.get("external_grpc_port") == 6554

    def test_ubuntu_installer_attach_uses_correct_grpc_port(
        self, replicas_network_state
    ):
        context = Context(LandscapeServerCharm)
        state = State(
            config={"enable_ubuntu_installer_attach": True}, **replicas_network_state
        )
        mock = _run_provide(context, state)
        calls = _calls_for(mock, "ubuntu-installer-attach")
        assert calls
        assert calls[0].kwargs.get("external_grpc_port") == 50051
