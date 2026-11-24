from configparser import ConfigParser
import subprocess
from unittest.mock import ANY, DEFAULT, MagicMock, Mock, patch

from ops.model import BlockedStatus
from ops.testing import Context, Harness, State, StoredState
import pytest

from charm import (
    DEB_TO_SNAP_MIGRATION_PATHS,
    LANDSCAPE_OUTBOX_SNAP,
    LANDSCAPE_SNAP,
    LANDSCAPE_SCRIPT_TIMEOUT,
    LANDSCAPE_SNAP_UPGRADE_SCHEMA,
    LANDSCAPE_SNAP_WITH_HASH_IDS,
    LandscapeServerCharm,
    SNAP_CORE_SERVICES,
    SNAP_HOST_APT_PACKAGES,
    SNAP_TIMER_SERVICES,
)
from database import execute_psql
from helpers import get_landscape_command
import settings_files


@pytest.fixture(autouse=True)
def reset_install_source():
    settings_files.set_active_install_source("deb")
    yield
    settings_files.set_active_install_source("deb")


@pytest.fixture(autouse=True)
def pin_snap_revision(monkeypatch):
    monkeypatch.setattr("charm.get_snap_revision", lambda _: "78")


@pytest.fixture
def deb_charm():
    harness = Harness(LandscapeServerCharm)
    harness.begin()
    charm = harness.charm
    charm._stored.install_source = "deb"
    settings_files.set_active_install_source("deb")
    yield charm
    harness.cleanup()


@pytest.fixture
def snap_charm():
    harness = Harness(LandscapeServerCharm)
    harness.begin()
    charm = harness.charm
    charm.charm_config = charm.charm_config.model_copy(
        update={"landscape_install_source": "snap"}
    )
    charm._stored.install_source = "snap"
    settings_files.set_active_install_source("snap")
    yield charm
    harness.cleanup()


def test_deb_command_is_unchanged():
    command = ["/usr/bin/landscape-schema", "--bootstrap"]
    assert get_landscape_command(command, "deb") is command


def test_snap_command_uses_snap_run_and_quotes_arguments():
    command = get_landscape_command(
        ["/opt/canonical/landscape/schema", "--password", "two words"], "snap"
    )
    assert command == [
        "snap",
        "run",
        "--shell",
        "landscape-server.setup",
        "-c",
        "exec /opt/canonical/landscape/schema --password 'two words'",
    ]


def test_snap_service_conf_uses_host_path_and_modern_names(tmp_path, monkeypatch):
    monkeypatch.setattr(settings_files, "SNAP_DATA_ROOT", str(tmp_path))
    monkeypatch.setattr(settings_files, "SERVICE_CONF", "/etc/landscape/service.conf")
    settings_files.set_active_install_source("snap")
    conf_path = tmp_path / "etc" / "landscape" / "service.conf"
    conf_path.parent.mkdir(parents=True)
    conf_path.write_text("[global]\ndeployment-mode = standalone\n")

    with (
        patch("settings_files.migrate_service_conf") as migrate,
        patch("settings_files.sync_service_conf_to_host"),
    ):
        settings_files.update_service_conf(
            {
                "global": {"root-url": "https://landscape.example/"},
                "landscape": {"secret-token": "secret"},
                "api": {"cookie-encryption-key": "cookie"},
                "message-server": {"base_port": "8090"},
            }
        )

    config = ConfigParser()
    config.read(conf_path)
    assert config["system"]["deployment_mode"] == "standalone"
    assert config["system"]["root_url"] == "https://landscape.example/"
    assert config["appserver"]["secret_token"] == "secret"
    assert config["api"]["cookie_encryption_key"] == "cookie"
    assert config["message_server"]["base_port"] == "8090"
    assert "global" not in config.sections()
    assert "landscape" not in config.sections()
    migrate.assert_called_once_with("snap")


def test_sync_service_conf_replaces_symlink_with_regular_host_copy(
    tmp_path, monkeypatch
):
    snap_root = tmp_path / "snap"
    host_conf = tmp_path / "host.conf"
    monkeypatch.setattr(settings_files, "SNAP_DATA_ROOT", str(snap_root))
    monkeypatch.setattr(settings_files, "SERVICE_CONF", str(host_conf))
    settings_files.set_active_install_source("snap")

    snap_conf = snap_root / str(host_conf).lstrip("/")
    snap_conf.parent.mkdir(parents=True)
    snap_conf.write_text("[system]\ndeployment_mode = standalone\n")
    host_conf.symlink_to(snap_conf)

    settings_files.sync_service_conf_to_host()

    assert not host_conf.is_symlink()
    assert host_conf.read_text() == "[system]\ndeployment_mode = standalone\n"


def test_install_snap_installs_component_and_postfix_without_ppa():
    harness = Harness(LandscapeServerCharm)
    harness.update_config({"landscape_install_source": "snap"})
    relation_id = harness.add_relation("replicas", "landscape-server")
    harness.update_relation_data(
        relation_id, "landscape-server", {"leader-ip": "192.0.2.1"}
    )

    with patch.multiple(
        "charm",
        check_call=DEFAULT,
        apt=DEFAULT,
        snap=DEFAULT,
        os=DEFAULT,
        sync_service_conf_to_host=DEFAULT,
        prepend_default_settings=DEFAULT,
        update_service_conf=DEFAULT,
    ) as mocks:
        landscape_snap = mocks["snap"].SnapCache.return_value.__getitem__.return_value
        landscape_snap.present = False
        harness.begin_with_initial_hooks()

    mocks["check_call"].assert_any_call(
        [
            "snap",
            "install",
            LANDSCAPE_SNAP_WITH_HASH_IDS,
            "--revision",
            "78",
        ]
    )
    mocks["apt"].add_package.assert_any_call(
        list(SNAP_HOST_APT_PACKAGES), update_cache=True
    )
    landscape_snap.ensure.assert_called_once_with(
        mocks["snap"].SnapState.Latest,
        revision="78",
    )
    landscape_snap.hold.assert_called_once_with()
    mocks["snap"].add.assert_any_call(LANDSCAPE_OUTBOX_SNAP, channel=ANY)
    assert not any(
        call.args and call.args[0][:2] == ["add-apt-repository", "-y"]
        for call in mocks["check_call"].call_args_list
    )
    assert harness.charm._stored.install_source == "snap"


def test_unavailable_hash_id_component_does_not_fail_install(snap_charm):
    charm = snap_charm

    with (
        patch("charm.apt"),
        patch("charm.snap"),
        patch("charm.os"),
        patch("charm.sync_service_conf_to_host"),
        patch("charm.check_call") as check_call,
        patch("charm.logger.warning") as warning,
    ):
        check_call.side_effect = subprocess.CalledProcessError(
            1, ["snap", "install", LANDSCAPE_SNAP_WITH_HASH_IDS]
        )
        charm._install_snap()

    warning.assert_any_call(
        "The hash-id-databases component is unavailable for "
        "landscape-server revision %s; continuing without pre-canned "
        "hash-id databases",
        "78",
    )


def test_refresh_landscape_snap_unholds_and_reholds_pinned_revision(snap_charm):
    charm = snap_charm

    with patch("charm.snap") as snap_module:
        landscape_snap = snap_module.SnapCache.return_value.__getitem__.return_value
        landscape_snap.present = True
        landscape_snap.held = True

        charm._ensure_landscape_snap(refresh=True)

    landscape_snap.unhold.assert_called_once_with()
    landscape_snap.ensure.assert_called_once_with(
        snap_module.SnapState.Latest,
        revision="78",
    )
    landscape_snap.hold.assert_called_once_with()


def test_upgrade_charm_refreshes_to_pinned_revision(snap_charm):
    charm = snap_charm

    with (
        patch("charm.apt"),
        patch.object(charm, "_ensure_landscape_snap") as ensure_snap,
        patch.object(charm, "_install_hash_id_component") as install_component,
        patch.object(charm, "_provide_all_haproxy_route_requirements"),
    ):
        charm._on_upgrade_charm(None)

    ensure_snap.assert_called_once_with(refresh=True)
    install_component.assert_called_once_with()


def test_upgrade_action_uses_pinned_revision(snap_charm):
    charm = snap_charm
    charm._stored.running = False
    event = MagicMock()

    with (
        patch.object(charm, "_ensure_landscape_snap") as ensure_snap,
        patch.object(charm, "_install_hash_id_component") as install_component,
    ):
        charm._upgrade(event)

    ensure_snap.assert_called_once_with(refresh=True)
    install_component.assert_called_once_with()
    event.fail.assert_not_called()


def test_psql_runs_inside_snap():
    with patch("database.check_call") as check_call:
        execute_psql(
            "db.example",
            "5432",
            "relation-8",
            "password",
            "GRANT charmed_dml TO landscape;",
            install_source="snap",
        )

    command = check_call.call_args.args[0]
    assert command[:5] == ["snap", "run", "--shell", "landscape-server.setup", "-c"]
    assert "psql" in command[5]
    assert check_call.call_args.kwargs["env"]["PGPASSWORD"] == "password"


def test_demo_data_is_only_created_once(snap_charm):
    charm = snap_charm

    with (
        patch("charm.check_call") as check_call,
        patch.object(charm, "_schema_supports_flag", return_value=False),
        patch.object(charm, "_bootstrap_account"),
        patch.object(charm, "_set_autoregistration"),
    ):
        assert charm._migrate_schema_bootstrap(demo_data=True)
        assert charm._migrate_schema_bootstrap(demo_data=True)

    first_command = check_call.call_args_list[0].args[0]
    second_command = check_call.call_args_list[1].args[0]
    assert "--with-computers" in first_command
    assert "--with-computers" not in second_command


def test_package_upload_is_started_when_snap_provides_it(snap_charm):
    charm = snap_charm
    charm.unit.is_leader = Mock(return_value=True)
    landscape_snap = MagicMock()
    landscape_snap.services = {"package-upload": {}}

    with patch("charm.snap.SnapCache", return_value={LANDSCAPE_SNAP: landscape_snap}):
        charm._start_snap_services()

    assert "package-upload" in landscape_snap.start.call_args.args[0]


def test_start_snap_services_enables_core_leader_and_optional_daemons(snap_charm):
    charm = snap_charm
    charm.unit.is_leader = Mock(return_value=True)
    charm.charm_config = charm.charm_config.model_copy(
        update={"enable_hostagent_messenger": True}
    )
    charm._stored.enable_ubuntu_installer_attach = True
    landscape_snap = MagicMock()

    with patch("charm.snap.SnapCache", return_value={LANDSCAPE_SNAP: landscape_snap}):
        charm._start_snap_services()

    started = set(landscape_snap.start.call_args.args[0])
    assert started == {
        *SNAP_CORE_SERVICES,
        *SNAP_TIMER_SERVICES,
        "package-search",
        "hostagent-messenger",
        "ubuntu-installer-attach-messenger",
    }
    assert landscape_snap.start.call_args.kwargs == {"enable": True}
    landscape_snap.stop.assert_not_called()


def test_start_snap_services_disables_leader_services_on_follower(snap_charm):
    charm = snap_charm
    charm.unit.is_leader = Mock(return_value=False)
    landscape_snap = MagicMock()
    landscape_snap.services = {"package-search": {}}

    with patch("charm.snap.SnapCache", return_value={LANDSCAPE_SNAP: landscape_snap}):
        charm._start_snap_services()

    assert set(landscape_snap.start.call_args.args[0]) == set(SNAP_CORE_SERVICES)
    assert set(landscape_snap.stop.call_args.args[0]) == {
        *SNAP_TIMER_SERVICES,
        "package-search",
        "hostagent-messenger",
        "ubuntu-installer-attach-messenger",
    }
    assert landscape_snap.stop.call_args.kwargs == {"disable": True}


def test_schema_command_uses_upgrade_schema_app(snap_charm):
    charm = snap_charm

    command = charm._schema_command(["--bootstrap"])

    assert command == [LANDSCAPE_SNAP_UPGRADE_SCHEMA, "--bootstrap"]


def test_autoregistration_is_staged_in_snap_data(tmp_path, monkeypatch, snap_charm):
    charm = snap_charm
    charm.unit.is_leader = Mock(return_value=True)
    charm._stored.account_bootstrapped = True
    monkeypatch.setattr(settings_files, "SNAP_DATA_ROOT", str(tmp_path))
    (tmp_path / "var" / "lib" / "landscape").mkdir(parents=True)

    with patch("charm.subprocess.run") as run:
        run.return_value = subprocess.CompletedProcess([], 0, stdout="", stderr="")
        charm._set_autoregistration()

    staged = tmp_path / "var" / "lib" / "landscape" / "autoregistration.py"
    assert staged.exists()
    command = run.call_args.args[0]
    assert command[:5] == ["snap", "run", "--shell", "landscape-server.setup", "-c"]
    assert "/var/lib/landscape/autoregistration.py off" in command[5]


def test_check_account_exists_is_staged_in_snap_data(
    tmp_path, monkeypatch, snap_charm
):
    charm = snap_charm
    monkeypatch.setattr(settings_files, "SNAP_DATA_ROOT", str(tmp_path))
    (tmp_path / "var" / "lib" / "landscape").mkdir(parents=True)

    with patch("charm.subprocess.run") as run:
        run.return_value = subprocess.CompletedProcess([], 0, stdout="", stderr="")
        assert charm._check_account_exists()

    staged = tmp_path / "var" / "lib" / "landscape" / "check_account.py"
    assert staged.exists()
    command = run.call_args.args[0]
    assert command[:5] == ["snap", "run", "--shell", "landscape-server.setup", "-c"]
    assert "/var/lib/landscape/check_account.py" in command[5]
    assert run.call_args.kwargs["timeout"] == LANDSCAPE_SCRIPT_TIMEOUT
    assert charm._stored.account_bootstrapped


def test_wsl_update_uses_catalog_packaged_in_snap(snap_charm):
    charm = snap_charm

    with patch("charm.check_call") as check_call:
        assert charm._update_wsl_distributions()

    assert check_call.call_args.args[0] == [
        "snap",
        "run",
        "--shell",
        "landscape-server.setup",
        "-c",
        "exec /opt/canonical/landscape/update-wsl-distributions",
    ]


def test_outbox_uses_landscape_conf_content_interface(snap_charm):
    charm = snap_charm
    with (
        patch("charm.subprocess.run") as run,
        patch("charm.sync_service_conf_to_host") as sync,
    ):
        run.return_value = subprocess.CompletedProcess([], 0)
        charm._configure_outbox_config()

    assert run.call_args.args[0] == [
        "snap",
        "connect",
        "landscape-outbox:landscape-conf",
        "landscape-server:landscape-conf",
    ]
    sync.assert_not_called()


def test_outbox_falls_back_to_host_config_copy(snap_charm):
    charm = snap_charm
    with (
        patch("charm.subprocess.run") as run,
        patch("charm.sync_service_conf_to_host") as sync,
    ):
        run.return_value = subprocess.CompletedProcess([], 1)
        charm._configure_outbox_config()

    sync.assert_called_once_with()


def test_copy_migration_path_handles_files_and_directories(deb_charm):
    charm = deb_charm

    with (
        patch("charm.os.path.exists", return_value=True),
        patch("charm.os.path.isdir", side_effect=[False, True]),
        patch("charm.os.makedirs"),
        patch("charm.check_call") as check_call,
    ):
        charm._copy_migration_path("/source/file", "/dest/file")
        charm._copy_migration_path("/source/dir", "/dest/dir")

    assert check_call.call_args_list[0].args[0] == [
        "cp",
        "-a",
        "/source/file",
        "/dest/file",
    ]
    assert check_call.call_args_list[1].args[0] == [
        "chown",
        "-R",
        "root:root",
        "/dest/file",
    ]
    assert check_call.call_args_list[2].args[0] == [
        "cp",
        "-a",
        "/source/dir/.",
        "/dest/dir/",
    ]
    assert check_call.call_args_list[3].args[0] == [
        "chown",
        "-R",
        "root:root",
        "/dest/dir",
    ]


def test_deb_to_snap_migration_copies_state_and_marks_success(deb_charm):
    charm = deb_charm
    charm._stored.running = True
    charm.unit.is_leader = Mock(return_value=True)

    with (
        patch("charm.check_call") as check_call,
        patch.object(charm, "_backup_deb_config") as backup_config,
        patch.object(charm, "_install_snap") as install_snap,
        patch.object(charm, "_copy_migration_path") as copy_path,
        patch("charm.migrate_service_conf") as migrate_conf,
        patch("charm.sync_service_conf_to_host") as sync,
        patch.object(charm, "_configure_outbox_config") as configure_outbox,
    ):
        assert charm._migrate_deb_to_snap()

    backup_config.assert_called_once_with()
    check_call.assert_any_call(["/usr/bin/lsctl", "stop"], env=ANY)
    check_call.assert_any_call(
        [LANDSCAPE_SNAP_UPGRADE_SCHEMA, "--allow-connections"], env=ANY
    )
    install_snap.assert_called_once_with()
    assert copy_path.call_count == len(DEB_TO_SNAP_MIGRATION_PATHS)
    migrate_conf.assert_called_once_with("snap")
    check_call.assert_any_call(
        [
            LANDSCAPE_SNAP_UPGRADE_SCHEMA,
            "--bootstrap",
            "--allow-connections",
        ],
        env=None,
    )
    sync.assert_called_once_with()
    configure_outbox.assert_called_once_with()
    assert charm._stored.install_source == "snap"
    assert not charm._stored.running


def test_failed_deb_to_snap_migration_restores_deb(deb_charm):
    charm = deb_charm
    charm._stored.running = True
    landscape_snap = Mock()

    with (
        patch("charm.check_call") as check_call,
        patch.object(charm, "_backup_deb_config"),
        patch.object(charm, "_restore_deb_config_backup") as restore_config,
        patch.object(
            charm, "_install_snap", side_effect=RuntimeError("install failed")
        ),
        patch("charm.sync_service_conf_to_host") as sync,
        patch("charm.snap.SnapCache", return_value={LANDSCAPE_SNAP: landscape_snap}),
    ):
        assert not charm._migrate_deb_to_snap()

    restore_config.assert_called_once_with()
    check_call.assert_any_call(["/usr/bin/lsctl", "start"], env=ANY)
    landscape_snap.stop.assert_called_once_with()
    sync.assert_not_called()
    assert charm._stored.install_source == "deb"
    assert charm._stored.running
    assert isinstance(charm.unit.status, BlockedStatus)
    assert "deb services restored" in charm.unit.status.message


def test_snap_to_deb_change_is_blocked():
    context = Context(LandscapeServerCharm)
    state = State(
        config={"landscape_install_source": "deb"},
        stored_states=[
            StoredState(
                owner_path="LandscapeServerCharm",
                content={"install_source": "snap"},
            )
        ],
    )

    result = context.run(context.on.config_changed(), state)

    assert isinstance(result.unit_status, BlockedStatus)
    assert "only supported from deb to snap" in result.unit_status.message
