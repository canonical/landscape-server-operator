from configparser import ConfigParser
import subprocess
from unittest.mock import MagicMock, Mock

import pytest
import scenario

import settings_files


class ConfigReader:
    def __init__(self, tempfile):
        self.tempfile = tempfile

    def get_config(self) -> ConfigParser:
        config = ConfigParser()
        config.read(self.tempfile)
        return config


@pytest.fixture(autouse=True)
def mock_write_deployment_mode_systemd_override(monkeypatch):
    monkeypatch.setattr(
        "charm.write_deployment_mode_systemd_override", lambda *a, **kw: None
    )


@pytest.fixture(autouse=True)
def capture_service_conf(tmp_path, monkeypatch) -> ConfigReader:
    """
    Redirect all writes to `SERVICE_CONF` to a tempfile within this fixture.
    Return a `ConfigReader` that reads from this file.

    This is set to `autouse=True` to avoid any attempts to write to the filesystem
    during tests, which typically throw an error if the real
    `/etc/landscape/service.conf` is not present.
    """
    conf_file = tmp_path / "service.conf"
    conf_file.write_text("")

    monkeypatch.setattr(settings_files, "SERVICE_CONF", str(conf_file))

    return ConfigReader(conf_file)


@pytest.fixture(autouse=True)
def ownership_fixture(monkeypatch) -> tuple[Mock, Mock, Mock]:
    """
    Mock os.chown, os.chmod, and shutil.chown
    to avoid doing ownership operations on files in unit tests.

    Returns the mocks for os.chown, os.chmod, and shutil.chown.
    """
    os_chown_mock = Mock()
    monkeypatch.setattr("os.chown", os_chown_mock)

    os_chmod_mock = Mock()
    monkeypatch.setattr("os.chmod", os_chmod_mock)

    shutil_chown_mock = Mock()
    monkeypatch.setattr("shutil.chown", shutil_chown_mock)

    return os_chown_mock, os_chmod_mock, shutil_chown_mock


@pytest.fixture(autouse=True, name="subprocess_fixture")
def subprocess_fixture(monkeypatch):
    monkeypatch.setattr(
        "subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args, 0, stdout=""),
    )


@pytest.fixture(autouse=True, name="check_call_fixture")
def check_call_fixture(monkeypatch):
    monkeypatch.setattr("charm.check_call", lambda *args, **kwargs: None)


@pytest.fixture(name="replicas_networks")
def replicas_networks_fixture():
    """
    Note: The addresses already have defaults.
    """
    # We need this for `unit_ip` and to get the leader IP
    return scenario.Network(
        binding_name="replicas",
    )


@pytest.fixture(name="replicas_network_state")
def replicas_network_state_fixture(
    replicas,
    replicas_networks,
) -> dict:
    return {
        "relations": [replicas],
        "networks": [replicas_networks],
    }


@pytest.fixture(name="haproxy_route_state")
def haproxy_route_state_fixture(
    replicas_network_state,
):
    rels = list(replicas_network_state.get("relations", []))
    for endpoint in [
        "appserver-haproxy-route",
        "pingserver-haproxy-route",
        "message-server-haproxy-route",
        "api-haproxy-route",
        "package-upload-haproxy-route",
        "repository-haproxy-route",
    ]:
        rels.append(scenario.Relation(endpoint=endpoint))

    return {
        "relations": rels,
        "networks": replicas_network_state.get("networks", []),
    }


@pytest.fixture(name="replicas")
def replicas_fixture() -> scenario.PeerRelation:
    return scenario.PeerRelation(
        endpoint="replicas",
        peers_data={},
    )


@pytest.fixture(name="systemd_fixture")
def systemd_fixture(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "charms.operator_libs_linux.v1.systemd.service_reload", MagicMock()
    )


@pytest.fixture(name="apt_fixture")
def apt_fixture(monkeypatch: pytest.MonkeyPatch):
    add_package_mock = MagicMock()
    remove_package_mock = MagicMock()
    monkeypatch.setattr(
        "charms.operator_libs_linux.v0.apt.add_package", add_package_mock
    )
    monkeypatch.setattr(
        "charms.operator_libs_linux.v0.apt.remove_package", remove_package_mock
    )
    return add_package_mock, remove_package_mock
