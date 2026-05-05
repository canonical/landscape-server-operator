from subprocess import CalledProcessError
from unittest import mock
from unittest.mock import call, Mock, patch

from charms.data_platform_libs.v0.data_interfaces import DatabaseCreatedEvent
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus
from ops.testing import Context, Relation, State, StoredState
import pytest
from scenario.errors import UncaughtCharmError

from charm import (
    LandscapeServerCharm,
    SCHEMA_SCRIPT,
)
from database import (
    DatabaseConnectionContext,
    execute_psql,
    fetch_postgres_relation_data,
    get_postgres_owner_role_from_version,
    grant_role,
    PgHbaNotReadyError,
    PostgresRoles,
)


class TestFetchPostgresRelationData:
    def test_returns_connection_details(self):
        db_manager = mock.Mock()
        db_manager.fetch_relation_data.return_value = {
            1: {
                "endpoints": "1.2.3.4:5432",
                "username": "landscape",
                "password": "secret",
                "version": "14.8",
            }
        }
        with mock.patch("database.logger"):
            result = fetch_postgres_relation_data(db_manager)

        db_manager.fetch_relation_data.assert_called_once_with()
        assert result == DatabaseConnectionContext(
            host="1.2.3.4",
            port="5432",
            username="landscape",
            password="secret",
            version="14.8",
        )

    def test_skips_empty_entries(self):
        db_manager = mock.Mock()
        db_manager.fetch_relation_data.return_value = {
            1: {},
            2: {
                "endpoints": "5.6.7.8:6543",
                "username": "reader",
                "password": "hunter2",
                "version": "13.3",
            },
        }
        with mock.patch("database.logger"):
            result = fetch_postgres_relation_data(db_manager)

        assert result == DatabaseConnectionContext(
            host="5.6.7.8",
            port="6543",
            username="reader",
            password="hunter2",
            version="13.3",
        )

    def test_returns_empty_context_when_no_data(self):
        db_manager = mock.Mock()
        db_manager.fetch_relation_data.return_value = {}
        with mock.patch("database.logger"):
            result = fetch_postgres_relation_data(db_manager)

        assert result == DatabaseConnectionContext()


class TestDatabaseRelation:
    """
    Tests for the modern `postgres_client` interface.
    """

    @staticmethod
    def _state(
        *,
        relation: Relation,
        leader: bool,
        config: dict | None = None,
        ready: dict | None = None,
    ) -> State:
        ready_map = ready or {
            "db": False,
            "inbound-amqp": False,
            "outbound-amqp": False,
            "haproxy": False,
        }
        stored = StoredState(
            owner_path="LandscapeServerCharm",
            content={"ready": ready_map},
        )
        return State(
            relations=[relation],
            leader=leader,
            config=config or {},
            stored_states=[stored],
        )

    def test_database_relation_changed_not_leader(self):
        ctx = Context(LandscapeServerCharm)
        relation = Relation(
            "database",
            remote_app_name="postgresql",
        )
        state_in = self._state(relation=relation, leader=False)

        with (
            patch("charm.update_db_conf") as update_db_conf,
            patch("charm.fetch_postgres_relation_data") as fetch_mock,
        ):
            fetch_mock.return_value = DatabaseConnectionContext(
                host="1.2.3.4",
                port="5432",
                username="landscape",
                password="secret",
                version="14.8",
            )

            with ctx(ctx.on.start(), state_in) as manager:
                manager.charm.database = Mock()
                with patch.object(
                    manager.charm, "_update_ready_status"
                ) as update_ready:
                    manager.charm._database_relation_changed(
                        mock.create_autospec(DatabaseCreatedEvent)
                    )
                    status = manager.charm.unit.status
                    ready = dict(manager.charm._stored.ready)

        assert isinstance(status, ActiveStatus)
        assert ready["db"] is True
        update_db_conf.assert_called_once()
        update_ready.assert_called_once_with(restart_services=True)

    def test_database_relation_missing_fields(self):
        ctx = Context(LandscapeServerCharm)
        relation = Relation("database", remote_app_name="postgresql")

        state_in = self._state(relation=relation, leader=True)

        with (
            patch("charm.fetch_postgres_relation_data") as fetch_mock,
            patch("charm.update_db_conf") as update_db_conf,
            patch(
                "charm.LandscapeServerCharm._migrate_schema_bootstrap",
                return_value=True,
            ),
            patch(
                "charm.LandscapeServerCharm._update_wsl_distributions",
                return_value=True,
            ),
            patch(
                "charm.get_postgres_roles",
                return_value=PostgresRoles(
                    relation="relation-9",
                    application="landscape-app",
                    owner="postgres",
                    superuser=None,
                ),
            ),
            patch("charm.grant_role") as grant_role_mock,
        ):
            fetch_mock.return_value = DatabaseConnectionContext(
                host="1.2.3.4",
                port=None,
                username=None,
                password="secret",
                version="14.8",
            )

            with ctx(ctx.on.start(), state_in) as manager:
                manager.charm.database = Mock()
                with patch.object(
                    manager.charm, "_update_ready_status"
                ) as update_ready:
                    manager.charm._database_relation_changed(
                        mock.create_autospec(DatabaseCreatedEvent)
                    )
                    status = manager.charm.unit.status
                    ready = dict(manager.charm._stored.ready)

        assert isinstance(status, ActiveStatus)
        assert ready["db"] is False
        update_db_conf.assert_not_called()
        grant_role_mock.assert_not_called()
        update_ready.assert_called_once_with()

    def test_database_relation_uses_relation_credentials(self):
        ctx = Context(LandscapeServerCharm)
        relation = Relation("database", remote_app_name="postgresql")

        state_in = self._state(relation=relation, leader=True)

        with (
            patch("charm.fetch_postgres_relation_data") as fetch_mock,
            patch("charm.update_db_conf") as update_db_conf,
            patch(
                "charm.LandscapeServerCharm._migrate_schema_bootstrap",
                return_value=True,
            ) as migrate_mock,
            patch(
                "charm.LandscapeServerCharm._update_wsl_distributions",
                return_value=True,
            ),
            patch(
                "charm.get_postgres_roles",
                return_value=PostgresRoles(
                    relation="landscape",
                    application="landscape-app",
                    owner="postgres",
                    superuser=None,
                ),
            ),
            patch("charm.grant_role") as grant_role_mock,
        ):
            fetch_mock.return_value = DatabaseConnectionContext(
                host="1.2.3.4",
                port="5432",
                username="landscape",
                password="secret",
                version="14.8",
            )

            with ctx(ctx.on.start(), state_in) as manager:
                manager.charm.database = Mock()
                with patch.object(
                    manager.charm, "_update_ready_status"
                ) as update_ready:
                    manager.charm._database_relation_changed(
                        mock.create_autospec(DatabaseCreatedEvent)
                    )
                    status = manager.charm.unit.status
                    ready = dict(manager.charm._stored.ready)

        update_db_conf.assert_called_once_with(
            host="1.2.3.4",
            port="5432",
            user="landscape",
            password="secret",
            schema_password=None,
        )
        migrate_mock.assert_called_once_with("postgres")
        grant_role_mock.assert_not_called()
        update_ready.assert_called_once_with(restart_services=True)
        assert isinstance(status, ActiveStatus)
        assert ready["db"] is True

    def test_database_relation_manual_overrides(self):
        ctx = Context(LandscapeServerCharm)
        relation = Relation("database", remote_app_name="postgresql")

        state_in = self._state(
            relation=relation,
            leader=True,
            config={
                "db_host": "override-host",
                "db_port": "6000",
                "db_schema_user": "schemauser",
                "db_landscape_password": "landscape-pass",
            },
        )

        with (
            patch("charm.fetch_postgres_relation_data") as fetch_mock,
            patch("charm.update_db_conf") as update_db_conf,
            patch(
                "charm.LandscapeServerCharm._migrate_schema_bootstrap",
                return_value=True,
            ) as migrate_mock,
            patch(
                "charm.LandscapeServerCharm._update_wsl_distributions",
                return_value=True,
            ),
            patch(
                "charm.get_postgres_roles",
                return_value=PostgresRoles(
                    relation="schemauser",
                    application="landscape-app",
                    owner="postgres",
                    superuser=None,
                ),
            ),
            patch("charm.grant_role") as grant_role_mock,
        ):
            fetch_mock.return_value = DatabaseConnectionContext(
                host="1.2.3.4",
                port="5432",
                username="landscape",
                password="secret",
                version="14.8",
            )

            with ctx(ctx.on.start(), state_in) as manager:
                manager.charm.database = Mock()
                with patch.object(
                    manager.charm, "_update_ready_status"
                ) as update_ready:
                    manager.charm._database_relation_changed(
                        mock.create_autospec(DatabaseCreatedEvent)
                    )
                    status = manager.charm.unit.status
                    ready = dict(manager.charm._stored.ready)

        assert isinstance(status, ActiveStatus)
        assert ready["db"] is True
        update_db_conf.assert_called_once_with(
            host="override-host",
            port="6000",
            user="schemauser",
            password="landscape-pass",
            schema_password=None,
        )
        migrate_mock.assert_called_once_with("postgres")
        grant_role_mock.assert_not_called()
        update_ready.assert_called_once_with(restart_services=True)

    def test_database_relation_pg16_grants_roles(self):
        ctx = Context(LandscapeServerCharm)
        relation = Relation("database", remote_app_name="postgresql")

        fetch_context = DatabaseConnectionContext(
            host="1.2.3.4",
            port="5432",
            username="relation-9",
            password="secret",
            version="16.9",
        )

        with (
            patch("charm.update_db_conf") as update_db_conf,
            patch(
                "charm.LandscapeServerCharm._migrate_schema_bootstrap",
                return_value=True,
            ) as migrate_mock,
            patch(
                "charm.LandscapeServerCharm._update_wsl_distributions",
                return_value=True,
            ),
            patch(
                "charm.get_postgres_roles",
                return_value=PostgresRoles(
                    relation="relation-9",
                    application="landscape-app",
                    owner="charmed_dba",
                    superuser="landscape-maintenance",
                ),
            ),
            patch("charm.grant_role") as grant_role_mock,
            patch("charm.fetch_postgres_relation_data", return_value=fetch_context),
        ):
            state_in = self._state(relation=relation, leader=True)

            with ctx(ctx.on.start(), state_in) as manager:
                manager.charm.database = Mock()
                manager.charm._database_relation_changed(
                    mock.create_autospec(DatabaseCreatedEvent)
                )

        migrate_mock.assert_called_once_with("charmed_dba")
        grant_role_mock.assert_has_calls(
            [
                call(
                    host="1.2.3.4",
                    port="5432",
                    relation_user="relation-9",
                    relation_password="secret",
                    role="charmed_dml",
                    user="landscape-app",
                ),
                call(
                    host="1.2.3.4",
                    port="5432",
                    relation_user="relation-9",
                    relation_password="secret",
                    role="charmed_dba",
                    user="landscape-maintenance",
                ),
            ]
        )
        assert grant_role_mock.call_count == 2
        update_db_conf.assert_called_once_with(
            host="1.2.3.4",
            port="5432",
            user="relation-9",
            password="secret",
            schema_password=None,
        )

    def test_database_relation_schema_password_override(self):
        ctx = Context(LandscapeServerCharm)
        relation = Relation("database", remote_app_name="postgresql")

        config = {
            "db_schema_password": "override-schema-pass",
        }
        state_in = self._state(relation=relation, leader=True, config=config)

        with (
            patch("charm.fetch_postgres_relation_data") as fetch_mock,
            patch("charm.update_db_conf") as update_db_conf,
            patch(
                "charm.LandscapeServerCharm._migrate_schema_bootstrap",
                return_value=True,
            ),
            patch(
                "charm.LandscapeServerCharm._update_wsl_distributions",
                return_value=True,
            ),
            patch(
                "charm.get_postgres_roles",
                return_value=PostgresRoles(
                    relation="landscape",
                    application="landscape-app",
                    owner="postgres",
                    superuser=None,
                ),
            ),
            patch("charm.grant_role") as grant_role_mock,
        ):
            fetch_mock.return_value = DatabaseConnectionContext(
                host="1.2.3.4",
                port="5432",
                username="landscape",
                password="secret",
                version="14.8",
            )

            with ctx(ctx.on.start(), state_in) as manager:
                manager.charm.database = Mock()
                with patch.object(manager.charm, "_update_ready_status"):
                    manager.charm._database_relation_changed(
                        mock.create_autospec(DatabaseCreatedEvent)
                    )

        update_db_conf.assert_called_once_with(
            host="1.2.3.4",
            port="5432",
            user="landscape",
            password="secret",
            schema_password="override-schema-pass",
        )
        grant_role_mock.assert_not_called()

    def test_database_relation_partial_overrides(self):
        ctx = Context(LandscapeServerCharm)
        relation = Relation("database", remote_app_name="postgresql")

        config = {
            "db_host": "override-host",
        }
        state_in = self._state(relation=relation, leader=True, config=config)

        with (
            patch("charm.fetch_postgres_relation_data") as fetch_mock,
            patch("charm.update_db_conf") as update_db_conf,
            patch(
                "charm.LandscapeServerCharm._migrate_schema_bootstrap",
                return_value=True,
            ),
            patch(
                "charm.LandscapeServerCharm._update_wsl_distributions",
                return_value=True,
            ),
            patch(
                "charm.get_postgres_roles",
                return_value=PostgresRoles(
                    relation="landscape",
                    application="landscape-app",
                    owner="postgres",
                    superuser=None,
                ),
            ),
            patch("charm.grant_role") as grant_role_mock,
        ):
            fetch_mock.return_value = DatabaseConnectionContext(
                host="1.2.3.4",
                port="5432",
                username="landscape",
                password="secret",
                version="14.8",
            )

            with ctx(ctx.on.start(), state_in) as manager:
                manager.charm.database = Mock()
                with patch.object(manager.charm, "_update_ready_status"):
                    manager.charm._database_relation_changed(
                        mock.create_autospec(DatabaseCreatedEvent)
                    )

        update_db_conf.assert_called_once_with(
            host="override-host",
            port="5432",
            user="landscape",
            password="secret",
            schema_password=None,
        )
        grant_role_mock.assert_not_called()

    @patch(
        "charm.get_postgres_roles",
        return_value=PostgresRoles(
            relation="landscape",
            application="landscape",
            owner="postgres",
            superuser=None,
        ),
    )
    @patch("charm.fetch_postgres_relation_data")
    @patch("charm.update_db_conf")
    @patch("charm.LandscapeServerCharm._migrate_schema_bootstrap", return_value=False)
    def test_database_relation_migrate_failure(
        self, _, update_db_conf, fetch_mock, get_roles_mock
    ):
        ctx = Context(LandscapeServerCharm)
        relation = Relation("database", remote_app_name="postgresql")
        fetch_mock.return_value = DatabaseConnectionContext(
            host="1.2.3.4",
            port="5432",
            username="landscape",
            password="secret",
            version="14.8",
        )

        state_in = self._state(relation=relation, leader=True)

        with ctx(ctx.on.start(), state_in) as manager:
            manager.charm.database = Mock()
            with patch.object(manager.charm, "_update_ready_status") as update_ready:
                manager.charm._database_relation_changed(
                    mock.create_autospec(DatabaseCreatedEvent)
                )
                status = manager.charm.unit.status
                ready = dict(manager.charm._stored.ready)

        update_db_conf.assert_called_once()
        update_ready.assert_not_called()
        assert isinstance(status, MaintenanceStatus)
        assert ready["db"] is False

    def test_database_relation_update_wsl_failure(self):
        ctx = Context(LandscapeServerCharm)
        relation = Relation("database", remote_app_name="postgresql")

        state_in = self._state(relation=relation, leader=True)

        with (
            patch("charm.fetch_postgres_relation_data") as fetch_mock,
            patch("charm.update_db_conf") as update_db_conf,
            patch(
                "charm.LandscapeServerCharm._migrate_schema_bootstrap",
                return_value=True,
            ),
            patch(
                "charm.LandscapeServerCharm._update_wsl_distributions",
                return_value=False,
            ),
            patch(
                "charm.get_postgres_roles",
                return_value=PostgresRoles(
                    relation="relation-9",
                    application="landscape",
                    owner="postgres",
                    superuser=None,
                ),
            ),
            patch("charm.grant_role") as grant_role_mock,
        ):
            fetch_mock.return_value = DatabaseConnectionContext(
                host="1.2.3.4",
                port="5432",
                username="relation-9",
                password="secret",
                version="14.8",
            )

            with ctx(ctx.on.start(), state_in) as manager:
                manager.charm.database = Mock()
                with patch.object(
                    manager.charm, "_update_ready_status"
                ) as update_ready:
                    manager.charm._database_relation_changed(
                        mock.create_autospec(DatabaseCreatedEvent)
                    )
                    status = manager.charm.unit.status
                    ready = dict(manager.charm._stored.ready)

        update_db_conf.assert_called_once()
        grant_role_mock.assert_not_called()
        update_ready.assert_not_called()
        assert isinstance(status, MaintenanceStatus)
        assert ready["db"] is False


class TestDatabaseHelpers:
    def test_get_postgres_owner_role_pg16(self):
        assert get_postgres_owner_role_from_version("16.1") == "charmed_dba"

    def test_get_postgres_owner_role_falls_back(self):
        with patch("database.logger") as logger:
            result = get_postgres_owner_role_from_version("garbage")

        assert result == "postgres"
        logger.warning.assert_called_once()

    @patch("database.get_modified_env_vars", return_value={"PATH": "/usr/bin"})
    @patch("database.check_call")
    def test_execute_psql_calls_check_call(self, check_call_mock, get_env):
        execute_psql(
            host="db.internal",
            port="5432",
            relation_user="relation-user",
            relation_password="hunter2",
            sql="SELECT 1",
            database="landscape",
        )

        check_call_mock.assert_called_once_with(
            [
                "psql",
                "-h",
                "db.internal",
                "-p",
                "5432",
                "-U",
                "relation-user",
                "-d",
                "landscape",
                "-c",
                "SELECT 1",
            ],
            env={"PATH": "/usr/bin", "PGPASSWORD": "hunter2"},
        )
        get_env.assert_called_once_with()

    @patch("database.get_modified_env_vars", return_value={})
    @patch("database.check_call", side_effect=CalledProcessError(1, "psql"))
    def test_execute_psql_raises_on_error(self, check_call_mock, _):
        with patch("database.logger") as logger, pytest.raises(CalledProcessError):
            execute_psql(
                host="db.internal",
                port="5432",
                relation_user="relation-user",
                relation_password="hunter2",
                sql="SELECT 1",
            )

        logger.error.assert_called_once()
        check_call_mock.assert_called_once()

    @patch("database.get_modified_env_vars", return_value={})
    @patch("database.check_call")
    def test_execute_psql_uses_default_database(self, check_call_mock, _):
        execute_psql(
            host="db.internal",
            port="5432",
            relation_user="relation-user",
            relation_password="hunter2",
            sql="SELECT 1",
        )

        args = check_call_mock.call_args.args[0]
        assert "-d" in args
        idx = args.index("-d")
        assert args[idx + 1] == "postgres"

    @patch("database.execute_psql")
    def test_grant_role_calls_execute(self, execute_psql_mock):
        grant_role(
            host="db.internal",
            port="5432",
            relation_user="relation-user",
            relation_password="hunter2",
            user="landscape",
            role="charmed_dba",
        )

        execute_psql_mock.assert_called_once_with(
            host="db.internal",
            port="5432",
            relation_user="relation-user",
            relation_password="hunter2",
            sql="GRANT charmed_dba TO landscape;",
        )

    @patch(
        "database.execute_psql",
        side_effect=CalledProcessError(
            1, ["psql", "-c", "GRANT charmed_dba TO landscape;"]
        ),
    )
    def test_grant_role_raises_on_error(self, execute_psql_mock):
        with patch("database.logger") as logger, pytest.raises(CalledProcessError):
            grant_role(
                host="db.internal",
                port="5432",
                relation_user="relation-user",
                relation_password="hunter2",
                user="landscape",
                role="charmed_dba",
            )

        execute_psql_mock.assert_called_once()
        logger.error.assert_called_once()


class TestBootstrapAccount:
    _ADMIN_CONFIG = {
        "admin_email": "admin@example.com",
        "admin_name": "Admin",
        "admin_password": "password123",
        "root_url": "https://landscape.local",
    }

    @staticmethod
    def _state(
        *, account_bootstrapped: bool = False, config: dict | None = None
    ) -> State:
        stored = StoredState(
            owner_path="LandscapeServerCharm",
            content={
                "ready": {
                    "db": False,
                    "inbound-amqp": False,
                    "outbound-amqp": False,
                    "load-balancer-certificates": False,
                },
                "account_bootstrapped": account_bootstrapped,
            },
        )
        return State(
            leader=True,
            config=config or TestBootstrapAccount._ADMIN_CONFIG,
            stored_states=[stored],
        )

    def test_pg_hba_error_raises(self):
        """pg_hba.conf race raises PgHbaNotReadyError so Juju retries the hook."""
        ctx = Context(LandscapeServerCharm)
        state_in = self._state()
        pg_hba = Mock(returncode=1, stdout="", stderr="no pg_hba.conf entry for host")

        with patch("charm.subprocess.run", return_value=pg_hba):
            with ctx(ctx.on.start(), state_in) as manager:
                with pytest.raises(PgHbaNotReadyError):
                    manager.charm._bootstrap_account()

    def test_pg_hba_error_does_not_mark_bootstrapped(self):
        ctx = Context(LandscapeServerCharm)
        state_in = self._state()
        pg_hba = Mock(returncode=1, stdout="", stderr="no pg_hba.conf entry for host")

        with patch("charm.subprocess.run", return_value=pg_hba):
            with ctx(ctx.on.start(), state_in) as manager:
                with pytest.raises(PgHbaNotReadyError):
                    manager.charm._bootstrap_account()
                assert manager.charm._stored.account_bootstrapped is False

    def test_success_marks_bootstrapped(self):
        ctx = Context(LandscapeServerCharm)
        state_in = self._state()

        with patch(
            "charm.subprocess.run",
            return_value=Mock(returncode=0, stdout="", stderr=""),
        ):
            with ctx(ctx.on.start(), state_in) as manager:
                manager.charm._bootstrap_account()
                assert manager.charm._stored.account_bootstrapped is True

    def test_duplicate_account_marks_bootstrapped(self):
        ctx = Context(LandscapeServerCharm)
        state_in = self._state()
        dup = Mock(returncode=1, stdout="", stderr="DuplicateAccountError")

        with patch("charm.subprocess.run", return_value=dup):
            with ctx(ctx.on.start(), state_in) as manager:
                manager.charm._bootstrap_account()
                assert manager.charm._stored.account_bootstrapped is True

    def test_generic_error_does_not_raise(self):
        """Non-pg_hba failures are logged and swallowed — no raise."""
        ctx = Context(LandscapeServerCharm)
        state_in = self._state()
        error = Mock(returncode=1, stdout="", stderr="some other error")

        with patch("charm.subprocess.run", return_value=error):
            with ctx(ctx.on.start(), state_in) as manager:
                manager.charm._bootstrap_account()

    def test_already_bootstrapped_skips_script(self):
        ctx = Context(LandscapeServerCharm)
        state_in = self._state(account_bootstrapped=True)

        with patch("charm.subprocess.run") as run_mock:
            with ctx(ctx.on.start(), state_in) as manager:
                manager.charm._bootstrap_account()
                run_mock.assert_not_called()

    def test_migrate_schema_bootstrap_propagates_pg_hba_raise(self):
        """_migrate_schema_bootstrap does not swallow PgHbaNotReadyError,
        so it propagates to the event handler and fails the hook."""
        ctx = Context(LandscapeServerCharm)
        state_in = self._state()

        with (
            patch("charm.check_call"),
            patch.object(
                LandscapeServerCharm,
                "_bootstrap_account",
                side_effect=PgHbaNotReadyError("no pg_hba.conf entry"),
            ),
        ):
            with ctx(ctx.on.start(), state_in) as manager:
                with pytest.raises(PgHbaNotReadyError):
                    manager.charm._migrate_schema_bootstrap()

    def test_migrate_schema_bootstrap_blocks_on_schema_failure(self):
        ctx = Context(LandscapeServerCharm)
        state_in = self._state()

        with patch(
            "charm.check_call", side_effect=CalledProcessError(1, SCHEMA_SCRIPT)
        ):
            with ctx(ctx.on.start(), state_in) as manager:
                result = manager.charm._migrate_schema_bootstrap()
                assert result is False
                assert isinstance(manager.charm.unit.status, BlockedStatus)

    def test_pg_hba_error_fails_database_hook(self):
        """pg_hba.conf race causes UncaughtCharmError so Juju retries the hook."""
        ctx = Context(LandscapeServerCharm)
        relation = Relation(
            "database",
            remote_app_name="postgresql",
            remote_app_data={
                "username": "landscape",
                "password": "secret",
                "endpoints": "1.2.3.4:5432",
                "version": "14.8",
                "database": "landscape",
            },
        )
        state_in = State(
            leader=True,
            relations=[relation],
            config=self._ADMIN_CONFIG,
            stored_states=[
                StoredState(
                    owner_path="LandscapeServerCharm",
                    content={
                        "ready": {
                            "db": False,
                            "inbound-amqp": False,
                            "outbound-amqp": False,
                            "load-balancer-certificates": False,
                        },
                        "account_bootstrapped": False,
                    },
                )
            ],
        )
        pg_hba = Mock(returncode=1, stdout="", stderr="no pg_hba.conf entry for host")

        with (
            patch(
                "charm.fetch_postgres_relation_data",
                return_value=DatabaseConnectionContext(
                    host="1.2.3.4",
                    port="5432",
                    username="landscape",
                    password="secret",
                    version="14.8",
                ),
            ),
            patch("charm.update_db_conf"),
            patch("charm.check_call"),
            patch(
                "charm.get_postgres_roles",
                return_value=PostgresRoles(
                    relation="landscape",
                    application="landscape-app",
                    owner="postgres",
                    superuser=None,
                ),
            ),
            patch("charm.grant_role"),
            patch("charm.subprocess.run", return_value=pg_hba),
            patch(
                "charm.LandscapeServerCharm._update_wsl_distributions",
                return_value=True,
            ),
            patch("charm.LandscapeServerCharm._update_ready_status"),
        ):
            with pytest.raises(UncaughtCharmError) as exc_info:
                ctx.run(ctx.on.relation_changed(relation), state_in)

        assert isinstance(exc_info.value.__cause__, PgHbaNotReadyError)
