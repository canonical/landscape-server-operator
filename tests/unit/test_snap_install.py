import subprocess
from unittest.mock import ANY, DEFAULT, MagicMock, Mock, patch

from ops.model import BlockedStatus
from ops.testing import Context, Harness, State, StoredState
import pytest

from charm import (
    DEB_CRON_FILES,
    DEB_TO_SNAP_MIGRATION_PATHS,
    LANDSCAPE_OUTBOX_SNAP,
    LANDSCAPE_SCRIPT_TIMEOUT,
    LANDSCAPE_SNAP,
    LANDSCAPE_SNAP_UPGRADE_SCHEMA,
    LANDSCAPE_SNAP_WITH_HASH_IDS,
    LandscapeServerCharm,
    LEADER_SERVICES,
    SNAP_CORE_SERVICES,
    SNAP_DAEMON_NAMES,
    SNAP_HOST_APT_PACKAGES,
    SNAP_TIMER_SERVICES,
)
from database import execute_psql
from helpers import get_landscape_command, migrate_service_conf
import settings_files

TEST_SNAP_REVISION = "78"


@pytest.fixture(autouse=True)
def reset_install_source():
    settings_files.set_active_install_source("deb")
    yield
    settings_files.set_active_install_source("deb")


@pytest.fixture(autouse=True)
def pin_snap_revision(monkeypatch):
    monkeypatch.setattr("charm.get_snap_revision", lambda _: TEST_SNAP_REVISION)


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


def test_snap_service_conf_migration_failure_raises():
    error = subprocess.CalledProcessError(1, ["snap"], stderr="migration failed")
    with (
        patch("helpers.subprocess.run", side_effect=error),
        pytest.raises(subprocess.CalledProcessError) as raised,
    ):
        migrate_service_conf("snap")

    assert raised.value is error


def test_install_snap_installs_component_and_host_packages_without_ppa():
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
            TEST_SNAP_REVISION,
        ]
    )
    mocks["apt"].add_package.assert_any_call(
        list(SNAP_HOST_APT_PACKAGES), update_cache=True
    )
    landscape_snap.ensure.assert_called_once_with(
        mocks["snap"].SnapState.Latest,
        revision=TEST_SNAP_REVISION,
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
        TEST_SNAP_REVISION,
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
        revision=TEST_SNAP_REVISION,
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


def test_start_snap_services_enables_core_leader_and_optional_daemons(snap_charm):
    charm = snap_charm
    charm.unit.is_leader = Mock(return_value=True)
    charm.charm_config = charm.charm_config.model_copy(
        update={"enable_hostagent_messenger": True}
    )
    charm._stored.enable_ubuntu_installer_attach = True
    landscape_snap = MagicMock()
    landscape_snap.services = {service: {} for service in SNAP_TIMER_SERVICES}

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


def test_start_snap_services_skips_unavailable_optional_timer(snap_charm):
    charm = snap_charm
    charm.unit.is_leader = Mock(return_value=True)
    landscape_snap = MagicMock()
    landscape_snap.services = {
        service: {} for service in SNAP_TIMER_SERVICES if service != "hash-id-databases"
    }

    with patch("charm.snap.SnapCache", return_value={LANDSCAPE_SNAP: landscape_snap}):
        charm._start_snap_services()

    started = set(landscape_snap.start.call_args.args[0])
    assert "hash-id-databases" not in started
    assert set(SNAP_TIMER_SERVICES) - {"hash-id-databases"} <= started


def test_start_snap_services_disables_leader_services_on_follower(snap_charm):
    charm = snap_charm
    charm.unit.is_leader = Mock(return_value=False)
    landscape_snap = MagicMock()
    landscape_snap.services = {"package-search": {}}

    with patch("charm.snap.SnapCache", return_value={LANDSCAPE_SNAP: landscape_snap}):
        charm._start_snap_services()

    leader_daemons = {
        SNAP_DAEMON_NAMES[service]
        for service in LEADER_SERVICES
        if SNAP_DAEMON_NAMES.get(service) in landscape_snap.services
    }
    assert set(landscape_snap.start.call_args.args[0]) == set(SNAP_CORE_SERVICES)
    assert set(landscape_snap.stop.call_args.args[0]) == {
        *SNAP_TIMER_SERVICES,
        *leader_daemons,
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


def test_check_account_exists_is_staged_in_snap_data(tmp_path, monkeypatch, snap_charm):
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
    with patch("charm.check_call") as connect:
        charm._configure_outbox_config()

    connect.assert_called_once_with(
        [
            "snap",
            "connect",
            "landscape-outbox:landscape-conf",
            "landscape-server:landscape-conf",
        ]
    )


def test_outbox_connection_failure_raises(snap_charm):
    charm = snap_charm
    with (
        patch("charm.check_call") as connect,
        pytest.raises(subprocess.CalledProcessError),
    ):
        connect.side_effect = subprocess.CalledProcessError(1, ["snap", "connect"])
        charm._configure_outbox_config()


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


def test_deb_cron_files_are_disabled_and_restored(deb_charm):
    charm = deb_charm
    with (
        patch("charm.os.path.exists", return_value=True),
        patch("charm.os.replace") as replace,
    ):
        charm._disable_deb_cron_jobs()
        charm._restore_deb_cron_jobs()

    assert replace.call_args_list[0].args == (
        DEB_CRON_FILES[0],
        f"{DEB_CRON_FILES[0]}.deb",
    )
    assert replace.call_args_list[1].args == (
        DEB_CRON_FILES[1],
        f"{DEB_CRON_FILES[1]}.deb",
    )
    assert replace.call_args_list[2].args == (
        f"{DEB_CRON_FILES[0]}.deb",
        DEB_CRON_FILES[0],
    )
    assert replace.call_args_list[3].args == (
        f"{DEB_CRON_FILES[1]}.deb",
        DEB_CRON_FILES[1],
    )


def test_deb_to_snap_migration_copies_state_and_marks_success(deb_charm):
    charm = deb_charm
    charm._stored.running = True
    charm.unit.is_leader = Mock(return_value=True)

    with (
        patch("charm.check_call") as check_call,
        patch.object(charm, "_backup_deb_config") as backup_config,
        patch.object(charm, "_disable_deb_cron_jobs") as disable_cron,
        patch.object(charm, "_install_snap") as install_snap,
        patch.object(charm, "_copy_migration_path") as copy_path,
        patch("charm.migrate_service_conf") as migrate_conf,
        patch.object(charm, "_configure_outbox_config") as configure_outbox,
    ):
        assert charm._migrate_deb_to_snap()

    backup_config.assert_called_once_with()
    disable_cron.assert_called_once_with()
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
    configure_outbox.assert_called_once_with()
    assert charm._stored.install_source == "snap"
    assert not charm._stored.running


@pytest.mark.parametrize("was_running", [True, False])
def test_failed_deb_to_snap_migration_restores_deb(deb_charm, was_running):
    charm = deb_charm
    charm._stored.running = was_running
    landscape_snap = Mock()

    with (
        patch("charm.check_call") as check_call,
        patch.object(charm, "_backup_deb_config"),
        patch.object(charm, "_restore_deb_config_backup") as restore_config,
        patch.object(charm, "_restore_deb_cron_jobs") as restore_cron,
        patch.object(
            charm, "_install_snap", side_effect=RuntimeError("install failed")
        ),
        patch("charm.snap.SnapCache", return_value={LANDSCAPE_SNAP: landscape_snap}),
    ):
        assert not charm._migrate_deb_to_snap()

    restore_config.assert_called_once_with()
    restore_cron.assert_called_once_with()
    if was_running:
        check_call.assert_any_call(["/usr/bin/lsctl", "start"], env=ANY)
    else:
        assert all(
            call.args[0] != ["/usr/bin/lsctl", "start"]
            for call in check_call.call_args_list
        )
    landscape_snap.stop.assert_called_once_with()
    assert charm._stored.install_source == "deb"
    assert charm._stored.running is was_running
    assert isinstance(charm.unit.status, BlockedStatus)
    assert "deb services restored" in charm.unit.status.message


def test_rollback_restores_running_state_when_service_start_fails(deb_charm):
    charm = deb_charm
    charm._stored.running = False

    with (
        patch.object(charm, "_restore_deb_config_backup"),
        patch.object(charm, "_restore_deb_cron_jobs"),
        patch("charm.snap.SnapCache", return_value={LANDSCAPE_SNAP: Mock()}),
        patch(
            "charm.check_call",
            side_effect=subprocess.CalledProcessError(1, ["lsctl", "start"]),
        ),
    ):
        charm._restore_deb_after_failed_migration(True)

    assert charm._stored.running


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
