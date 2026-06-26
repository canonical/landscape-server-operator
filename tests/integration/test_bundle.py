"""
Integration tests for the Landscape scalable bundle, using Postgres, RabbitMQ,
and Landscape Server.

NOTE: These tests assume an IPv4 public address for the Landscape Server charm.
"""

import json
import re
import shlex
from urllib.parse import urlparse

import jubilant
import pytest

from charm import (
    DEFAULT_OUTBOX_SNAP_CHANNEL,
    DEFAULT_SERVICES,
    LANDSCAPE_OUTBOX_SNAP,
    LANDSCAPE_UBUNTU_INSTALLER_ATTACH,
    LEADER_SERVICES,
)
from tests.integration.conftest import USE_HOST_JUJU_MODEL
from tests.integration.helpers import (
    all_landscape_active,
    get_session,
    has_legacy_pg,
    has_modern_pg,
    has_pgbouncer,
    leader_unit_name,
    relation_app_data,
    supports_legacy_pg,
    wait_for_http_status,
    wait_for_service,
)

LIVE_MODEL_SKIP_REASON = "Potentially destructive test skipped on live model."


def _query_main_db(juju: jubilant.Juju, sql: str) -> str:
    """Execute a read-only SQL query against the configured main Landscape DB."""
    result = juju.run("landscape-server/leader", "get-service-conf")
    stores = json.loads(result.results["config"])["stores"]
    host, port = stores["host"].rsplit(":", 1)
    password, user, dbname = stores["password"], stores["user"], stores["main"]

    ssh_command = (
        f"PGPASSWORD={shlex.quote(password)} "
        "psql "
        f"-h {shlex.quote(host)} "
        f"-p {shlex.quote(port)} "
        f"-U {shlex.quote(user)} "
        f"-d {shlex.quote(dbname)} "
        f"-tAc {shlex.quote(sql)}"
    )

    return juju.exec(ssh_command, unit="landscape-server/leader").stdout


def _haproxy_ip(juju: jubilant.Juju, lbaas: jubilant.Juju) -> str:
    """Return the haproxy IP from the local model, lbaas model, or skip."""
    haproxy = juju.status().apps.get("haproxy")
    if haproxy:
        return list(haproxy.units.values())[0].public_address
    if lbaas is not None:
        lbaas_haproxy = lbaas.status().apps.get("haproxy")
        if lbaas_haproxy:
            return list(lbaas_haproxy.units.values())[0].public_address
    pytest.skip("No haproxy app found in local or lbaas model")


def test_debarchive_relation(juju: jubilant.Juju):
    """Landscape Server and debarchive publish and consume relation data."""
    juju.wait(all_landscape_active, timeout=300)
    status = juju.status()

    if "landscape-debarchive" not in status.apps:
        pytest.skip("landscape-debarchive not deployed")

    landscape_relations = status.apps["landscape-server"].relations
    debarchive_relations = status.apps["landscape-debarchive"].relations
    assert "debarchive" in landscape_relations
    assert "landscape-server" in debarchive_relations
    assert "database" in debarchive_relations

    leader_unit = leader_unit_name(juju, "landscape-server")
    data = relation_app_data(juju, leader_unit, "debarchive")
    expected_hostname = urlparse(
        juju.config("landscape-server").get("root_url", "https://landscape.local/")
    ).hostname

    assert data["hostname"] == expected_hostname
    assert data["secret-token-id"].startswith("secret://")

    token = juju.exec(
        "sudo snap get landscape-debarchive deb.archive.jwt.secret",
        unit="landscape-debarchive/leader",
    ).stdout.strip()
    assert token and token != "-"


@pytest.mark.skipif(
    USE_HOST_JUJU_MODEL,
    reason=LIVE_MODEL_SKIP_REASON,
)
def test_redirect_https_none_routes_not_redirected(
    juju: jubilant.Juju, lbaas: jubilant.Juju
):
    """
    When redirect_https=none, all routes are accessible over HTTP without redirect.
    """
    pytest.skip(
        "Setting redirect_https=none generates a haproxy redirect rule that "
        "exceeds haproxy's 64-word line limit, causing an invalid config. "
        "See https://github.com/canonical/haproxy-operator/issues/409"
    )
    host = _haproxy_ip(juju, lbaas)
    hostname = urlparse(
        juju.config("landscape-server").get("root_url", "https://landscape.local/")
    ).hostname

    original = juju.config("landscape-server").get("redirect_https")
    try:
        juju.config("landscape-server", values={"redirect_https": "none"})
        juju.wait(all_landscape_active, timeout=300)
        lbaas.wait(all_landscape_active, timeout=300)

        for route in ("ping", "api/about", "message-system", "upload"):
            url = f"http://{host}/{route}"
            wait_for_http_status(
                url,
                expected_status=200,
                timeout=120,
                verify=False,
                allow_redirects=False,
                headers={"Host": hostname},
            )
    finally:
        restore = original or "default"
        juju.config("landscape-server", values={"redirect_https": restore})
        juju.wait(all_landscape_active, timeout=300)
        lbaas.wait(all_landscape_active, timeout=300)


@pytest.mark.skipif(
    USE_HOST_JUJU_MODEL,
    reason=LIVE_MODEL_SKIP_REASON,
)
def test_redirect_https_all_routes_redirect_to_https(
    juju: jubilant.Juju, lbaas: jubilant.Juju
):
    """
    When redirect_https=all, all HTTP routes including /ping, /repository, and
    /message-system are redirected to HTTPS.
    """
    host = _haproxy_ip(juju, lbaas)
    hostname = urlparse(
        juju.config("landscape-server").get("root_url", f"https://{host}/")
    ).hostname
    original = juju.config("landscape-server").get("redirect_https")
    try:
        juju.config("landscape-server", values={"redirect_https": "all"})
        juju.wait(all_landscape_active, timeout=300)
        lbaas.wait(all_landscape_active, timeout=300)

        for route in (
            "ping",
            "message-system",
            "repository",
            "api/about",
            "hashid-databases",
            "upload",
            "zzz-some-default-route",
        ):
            url = f"http://{host}/{route}"
            wait_for_http_status(
                url,
                expected_status=(301, 302),
                timeout=120,
                verify=False,
                allow_redirects=False,
                headers={"Host": hostname},
            )
    finally:
        restore = original or "default"
        juju.config("landscape-server", values={"redirect_https": restore})
        juju.wait(all_landscape_active, timeout=300)
        lbaas.wait(all_landscape_active, timeout=300)


@pytest.mark.skipif(
    USE_HOST_JUJU_MODEL,
    reason=LIVE_MODEL_SKIP_REASON,
)
def test_redirect_https_default_routes_redirect_to_https(
    juju: jubilant.Juju, lbaas: jubilant.Juju
):
    """
    When redirect_https=default, HTTP requests are redirected to HTTPS except for
    /ping and /repository which always allow plain HTTP.
    """
    host = _haproxy_ip(juju, lbaas)
    hostname = urlparse(
        juju.config("landscape-server").get("root_url", f"https://{host}/")
    ).hostname
    original = juju.config("landscape-server").get("redirect_https")
    try:
        juju.config("landscape-server", values={"redirect_https": "default"})
        juju.wait(all_landscape_active, timeout=600)
        lbaas.wait(all_landscape_active, timeout=300)

        for route in ("ping",):
            url = f"http://{host}/{route}"
            wait_for_http_status(
                url,
                expected_status=(200, 404, 503),
                timeout=120,
                verify=False,
                allow_redirects=False,
                headers={"Host": hostname},
            )

        for route in (
            "message-system",
            "api/about",
            "hashid-databases",
            "upload",
            "zzz-some-default-route",
        ):
            url = f"http://{host}/{route}"
            wait_for_http_status(
                url,
                expected_status=(301, 302),
                timeout=120,
                verify=False,
                allow_redirects=False,
                headers={"Host": hostname},
            )
    finally:
        restore = original or "default"
        juju.config("landscape-server", values={"redirect_https": restore})
        juju.wait(all_landscape_active, timeout=300)
        lbaas.wait(all_landscape_active, timeout=300)


@pytest.mark.skipif(
    USE_HOST_JUJU_MODEL,
    reason=LIVE_MODEL_SKIP_REASON,
)
def test_services_up_over_https(juju: jubilant.Juju, lbaas: jubilant.Juju):
    """
    Services are responding over HTTPS.
    """
    host = _haproxy_ip(juju, lbaas)

    original = juju.config("landscape-server").get("redirect_https")
    try:
        juju.config("landscape-server", values={"redirect_https": "default"})
        juju.wait(all_landscape_active, timeout=300)
        lbaas.wait(all_landscape_active, timeout=300)

        routes = ("ping", "api/about", "message-system", "")

        session = get_session()
        for route in routes:
            response = session.get(f"https://{host}/{route}", verify=False)
            assert response.status_code == 200, (
                f"Expected 200 status code for /{route} over HTTPS, "
                f"got {response.status_code}"
            )
    finally:
        restore = original or "default"
        juju.config("landscape-server", values={"redirect_https": restore})
        juju.wait(all_landscape_active, timeout=300)
        lbaas.wait(all_landscape_active, timeout=300)


def test_modern_database_relation(
    juju: jubilant.Juju, lbaas: jubilant.Juju, saved_db_relations: set[str]
):
    """
    Test the modern `database` interface.
    """
    initial_relations = saved_db_relations

    if "db" in initial_relations:
        juju.remove_relation("landscape-server:db", "postgresql:db-admin", force=True)
        juju.wait(lambda status: not has_legacy_pg(juju), timeout=120)

        juju.integrate("landscape-server:database", "postgresql:database")

    elif "database" not in initial_relations:
        juju.integrate("landscape-server:database", "postgresql:database")
        juju.wait(lambda status: has_modern_pg(juju), timeout=120)

    relations = set(juju.status().apps["landscape-server"].relations)

    assert "database" in relations


def test_bootstrap_account_created_with_modern_database(
    juju: jubilant.Juju, bundle: None
):
    """
    When admin_email/name/password are configured, the bootstrap-account script
    must succeed even though Patroni regenerates pg_hba.conf asynchronously after
    the landscape role is created by landscape-schema --bootstrap.
    """
    if not has_modern_pg(juju):
        pytest.skip("Modern database relation not active")

    config = juju.config("landscape-server")
    if not all(config.get(k) for k in ("admin_email", "admin_name", "admin_password")):
        pytest.skip(
            "admin_email, admin_name, and admin_password must all be configured"
        )
    if not config.get("root_url"):
        pytest.skip("root_url must be configured for bootstrap-account")
    admin_email = config["admin_email"]

    juju.wait(all_landscape_active, timeout=300)

    result = _query_main_db(juju, "SELECT email FROM person;")
    assert admin_email in result, (
        f"Admin {admin_email} not found in person table after bootstrap. "
    )


def test_demo_data_created_when_config_enabled(juju: jubilant.Juju, bundle: None):
    """
    Non-mutative check: only validate demo data if the option is already enabled.
    """
    if not has_modern_pg(juju):
        pytest.skip("Modern database relation not active")

    if not juju.config("landscape-server").get("demo_data"):
        pytest.skip("demo_data is not enabled in model config")

    juju.wait(all_landscape_active, timeout=300)

    result = _query_main_db(juju, "SELECT COUNT(*) FROM computer;")
    assert int(result.strip()) > 0, "Expected demo computers when demo_data is enabled"


def test_demo_data_registration_key_matches_config(juju: jubilant.Juju, bundle: None):
    """
    Non-mutative check: only validate registration key parity when already set.
    """
    if not has_modern_pg(juju):
        pytest.skip("Modern database relation not active")

    config = juju.config("landscape-server")
    if not config.get("demo_data"):
        pytest.skip("demo_data is not enabled in model config")

    registration_key = config.get("registration_key")
    if not registration_key:
        pytest.skip("registration_key is not set in model config")

    juju.wait(all_landscape_active, timeout=300)

    result = _query_main_db(juju, "SELECT registration_key FROM account LIMIT 1;")
    assert result.strip() == registration_key, (
        "Expected account.registration_key to match configured registration_key"
    )


def test_legacy_db_relation(
    juju: jubilant.Juju, lbaas: jubilant.Juju, saved_db_relations: set[str]
):
    """
    Test the legacy `db` interface.
    """
    if not supports_legacy_pg(juju):
        pytest.skip("Legacy pgsql relation not available on this PostgreSQL charm")

    initial_relations = saved_db_relations

    if "database" in initial_relations:
        juju.remove_relation(
            "landscape-server:database", "postgresql:database", force=True
        )
        juju.wait(lambda status: not has_modern_pg(juju), timeout=120)
        juju.integrate("landscape-server:db", "postgresql:db-admin")

    elif "db" not in initial_relations:
        juju.integrate("landscape-server:db", "postgresql:db-admin")
        juju.wait(lambda status: has_legacy_pg(juju), timeout=120)

    relations = set(juju.status().apps["landscape-server"].relations)

    assert "db" in relations


def test_pgbouncer_relation(juju: jubilant.Juju, bundle: None):
    """
    If PgBouncer is deployed, landscape-server connects to it via the `database`
    endpoint rather than directly to PostgreSQL.
    """
    if not has_pgbouncer(juju):
        pytest.skip("PgBouncer not present in this model, skipping...")

    pg_relations = set(juju.status().apps["pgbouncer"].relations)
    assert "database" in pg_relations, "pgbouncer should have a `database` relation"
    assert "backend-database" in pg_relations, (
        "pgbouncer should have a `backend-database` relation to PostgreSQL"
    )

    ls_relations = set(juju.status().apps["landscape-server"].relations)
    assert "database" in ls_relations, (
        "landscape-server should be related via the `database` endpoint"
    )


def test_get_service_conf_action(juju: jubilant.Juju, bundle: None):
    """
    The get-service-conf action returns a JSON-serialisable dict with the
    expected top-level sections from service.conf.
    """
    juju.wait(all_landscape_active, timeout=300)

    result = juju.run("landscape-server/leader", "get-service-conf")
    assert result.status == "completed"

    config = json.loads(result.results["config"])
    assert "stores" in config, (
        f"Expected 'stores' section in service.conf, got: {list(config)}"
    )


def test_landscape_schema_migrated(juju: jubilant.Juju, bundle: None):
    """
    The Landscape database schema is present after deployment.

    Reads the connection details from service.conf via the get-service-conf
    action on the leader unit and runs a query to confirm the `account` table
    (created by landscape-schema) exists. This works regardless of whether
    pgbouncer or direct PostgreSQL is in use, since the host/port/user/password/
    dbname come from whatever landscape-server is configured to connect to.
    """
    juju.wait(all_landscape_active, timeout=300)

    result = _query_main_db(
        juju,
        "SELECT COUNT(*) FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_name = 'account';",
    ).strip()

    assert result == "1", (
        "Expected the 'account' table to exist in the landscape database, "
        f"got: {result!r}"
    )


def test_all_services_up(juju: jubilant.Juju, lbaas: jubilant.Juju):
    """
    All expected Landscape systemd services are active on every unit.

    Uses `wait_for_service` rather than a one-shot check because Juju
    reporting active does not guarantee the services have finished starting.
    """
    juju.wait(all_landscape_active, timeout=300)

    status = juju.status()
    units = status.apps["landscape-server"].units
    config = juju.config("landscape-server")
    enable_ubuntu_installer = config.get("enable_ubuntu_installer_attach", False)

    for name, unit_status in units.items():
        for service in DEFAULT_SERVICES:
            wait_for_service(juju, name, service)

        if enable_ubuntu_installer:
            wait_for_service(juju, name, LANDSCAPE_UBUNTU_INSTALLER_ATTACH)

        if unit_status.leader:
            for service in LEADER_SERVICES:
                wait_for_service(juju, name, service)


@pytest.mark.skipif(
    USE_HOST_JUJU_MODEL,
    reason=LIVE_MODEL_SKIP_REASON,
)
def test_ubuntu_installer_attach_service(juju: jubilant.Juju, lbaas: jubilant.Juju):
    """
    NOTE: There is not an equivalent hostagent_messenger test because
    that service will run regardless of the config, unlike Ubuntu Installer
    Attach which will actually install/uninstall the package/service in addition
    to creating an HAProxy backend for it.
    """
    juju.wait(all_landscape_active, timeout=300)

    status = juju.status()
    units = status.apps["landscape-server"].units
    original = juju.config("landscape-server").get("enable_ubuntu_installer_attach")

    try:
        juju.config(
            "landscape-server", values={"enable_ubuntu_installer_attach": "true"}
        )
        juju.wait(all_landscape_active, timeout=300)
        for name in units.keys():
            wait_for_service(juju, name, LANDSCAPE_UBUNTU_INSTALLER_ATTACH)

    finally:
        restore_val = "true" if original else "false"
        juju.config(
            "landscape-server", values={"enable_ubuntu_installer_attach": restore_val}
        )
        juju.wait(all_landscape_active, timeout=300)


@pytest.mark.skipif(
    USE_HOST_JUJU_MODEL,
    reason=LIVE_MODEL_SKIP_REASON,
)
def test_ubuntu_installer_attach_toggle_no_maintenance(
    juju: jubilant.Juju, lbaas: jubilant.Juju
):
    """
    Toggling Ubuntu Installer Attach should return to active status and
    reflect the correct service state.
    """
    juju.wait(all_landscape_active, timeout=300)
    config = juju.config("landscape-server")
    original_installer = config.get("enable_ubuntu_installer_attach")

    try:
        juju.config(
            "landscape-server", values={"enable_ubuntu_installer_attach": "true"}
        )
        juju.wait(all_landscape_active, timeout=300)

        status = juju.status()
        assert status.apps["landscape-server"].app_status.current == "active"

        for name in status.apps["landscape-server"].units.keys():
            wait_for_service(juju, name, LANDSCAPE_UBUNTU_INSTALLER_ATTACH)

        juju.config(
            "landscape-server", values={"enable_ubuntu_installer_attach": "false"}
        )
        juju.wait(all_landscape_active, timeout=300)

        status = juju.status()
        assert status.apps["landscape-server"].app_status.current == "active"

        for name in status.apps["landscape-server"].units.keys():
            with pytest.raises(Exception):
                juju.exec(
                    f"systemctl is-active {LANDSCAPE_UBUNTU_INSTALLER_ATTACH}.service",
                    unit=name,
                )

    finally:
        restore_val = "true" if original_installer else "false"
        juju.config(
            "landscape-server", values={"enable_ubuntu_installer_attach": restore_val}
        )
        juju.wait(all_landscape_active, timeout=300)


def test_non_leader_unit_redirects_leader_only_services(
    juju: jubilant.Juju, lbaas: jubilant.Juju
):
    status = juju.status()
    units = status.apps["landscape-server"].units

    if len(units) <= 1:
        pytest.skip("Need more than 1 unit to have a non-leader!")

    juju.wait(all_landscape_active, timeout=300)

    host = _haproxy_ip(juju, lbaas)
    assert juju.wait(all_landscape_active, timeout=300) and (
        get_session().get(f"https://{host}/upload", verify=False).status_code == 200
    )


def test_appserver_haproxy_route_enabled(juju: jubilant.Juju, lbaas: jubilant.Juju):
    """
    Verify that appserver-haproxy-route is present and publishes correct data.
    """
    juju.wait(all_landscape_active, timeout=300)
    status = juju.status()
    app_status = status.apps["landscape-server"]

    if "appserver-haproxy-route" not in app_status.relations:
        pytest.skip("appserver-haproxy-route relation not present in bundle")

    leader_unit_name = None
    for name, unit_status in app_status.units.items():
        if unit_status.leader:
            leader_unit_name = name
            break

    if not leader_unit_name:
        pytest.fail("No leader unit found for landscape-server")

    def get_relation_data(endpoint):
        ids_stdout = juju.cli(
            "exec", "--unit", leader_unit_name, "--", f"relation-ids {endpoint}"
        )
        ids = ids_stdout.strip().splitlines()
        if not ids:
            pytest.fail(f"No relation IDs found for endpoint {endpoint}")
        rel_id = ids[0]
        data_stdout = juju.cli(
            "exec",
            "--unit",
            leader_unit_name,
            "--",
            f"relation-get --format=json -r {rel_id} --app - {leader_unit_name}",
        )
        data = json.loads(data_stdout)

        return {k: v.strip('"') if isinstance(v, str) else v for k, v in data.items()}

    appserver_data = get_relation_data("appserver-haproxy-route")

    assert appserver_data.get("service", "").startswith("landscape-appserver-")


@pytest.mark.skipif(
    USE_HOST_JUJU_MODEL,
    reason=LIVE_MODEL_SKIP_REASON,
)
def test_grpc_haproxy_route_config_enabled(juju: jubilant.Juju, lbaas: jubilant.Juju):
    """
    Verify that when haproxy-route configs are enabled, the charm creates the
    relations and publishes the correct data to the relation databags.
    """
    status = juju.status()
    app_status = status.apps["landscape-server"]
    if (
        "hostagent-messenger-haproxy-route" not in app_status.relations
        or "ubuntu-installer-attach-haproxy-route" not in app_status.relations
    ):
        pytest.skip("gRPC haproxy-route not integrated, skipping...")

    juju.wait(all_landscape_active, timeout=300)
    config = juju.config("landscape-server")
    original_hostagent = config.get("enable_hostagent_messenger")
    original_installer = config.get("enable_ubuntu_installer_attach")

    try:
        juju.config(
            "landscape-server",
            values={
                "enable_hostagent_messenger": "true",
                "enable_ubuntu_installer_attach": "true",
            },
        )
        juju.wait(all_landscape_active, timeout=300)
        status = juju.status()
        app_status = status.apps["landscape-server"]
        assert "hostagent-messenger-haproxy-route" in app_status.relations
        assert "ubuntu-installer-attach-haproxy-route" in app_status.relations

        leader_unit_name = None
        for name, unit_status in app_status.units.items():
            if unit_status.leader:
                leader_unit_name = name
                break

        if not leader_unit_name:
            pytest.fail("No leader unit found for landscape-server")

        def get_relation_data(endpoint):
            ids_stdout = juju.cli(
                "exec", "--unit", leader_unit_name, "--", f"relation-ids {endpoint}"
            )
            ids = ids_stdout.strip().splitlines()
            if not ids:
                pytest.fail(f"No relation IDs found for endpoint {endpoint}")
            rel_id = ids[0]
            data_stdout = juju.cli(
                "exec",
                "--unit",
                leader_unit_name,
                "--",
                f"relation-get --format=json -r {rel_id} --app - {leader_unit_name}",
            )
            data = json.loads(data_stdout)

            return {
                k: v.strip('"') if isinstance(v, str) else v for k, v in data.items()
            }

        hostagent_data = get_relation_data("hostagent-messenger-haproxy-route")

        assert hostagent_data.get("external_grpc_port") == "6554", (
            "Expected external_grpc_port 6554, "
        )
        f"got {hostagent_data.get('external_grpc_port')}"
        assert hostagent_data.get("service", "").startswith(
            "landscape-hostagent-messenger-"
        )

        installer_data = get_relation_data("ubuntu-installer-attach-haproxy-route")

        assert installer_data.get("external_grpc_port") == "50051", (
            "Expected external_grpc_port 50051, "
        )
        f"got {installer_data.get('external_grpc_port')}"
        assert installer_data.get("service", "").startswith(
            "landscape-ubuntu-installer-attach-"
        )
    finally:
        juju.config(
            "landscape-server",
            values={
                "enable_hostagent_messenger": "true" if original_hostagent else "false",
                "enable_ubuntu_installer_attach": (
                    "true" if original_installer else "false"
                ),
            },
        )
        juju.wait(all_landscape_active, timeout=300)


def test_lbaas_http_routes(juju: jubilant.Juju, lbaas: jubilant.Juju):
    """Test HTTP traffic for routes through external HAProxy."""
    if lbaas is None:
        pytest.skip("LBaaS model not available")

    config = juju.config("landscape-server")
    root_url = config.get("root_url", "https://landscape.local/")
    hostname = urlparse(root_url).hostname

    status = lbaas.status()
    if "haproxy" not in status.apps:
        pytest.skip("HAProxy not found in lbaas model")
    haproxy_unit = list(status.apps["haproxy"].units.values())[0]
    haproxy_ip = haproxy_unit.public_address

    session = get_session()

    routes = (
        "ping",
        # NOTE: Requires configuration
        # in order to return 200
        # "repository",
    )

    for route in routes:
        response = session.get(
            f"http://{haproxy_ip}/{route}",
            verify=False,
            timeout=10,
            headers={"Host": hostname},
            allow_redirects=False,
        )
        assert response.status_code == 200, (
            f"Expected status code 200 for HTTP /{route}, got {response.status_code}"
        )


def test_lbaas_https_all_routes(juju: jubilant.Juju, lbaas: jubilant.Juju):
    """Test HTTPS traffic for all routes through external HAProxy."""
    if lbaas is None:
        pytest.skip("LBaaS model not available")

    config = juju.config("landscape-server")
    root_url = config.get("root_url", "https://landscape.local/")
    hostname = urlparse(root_url).hostname

    status = lbaas.status()
    if "haproxy" not in status.apps:
        pytest.skip("HAProxy not found in lbaas model")
    haproxy_unit = list(status.apps["haproxy"].units.values())[0]
    haproxy_ip = haproxy_unit.public_address

    session = get_session()

    routes = (
        "api/about",
        "ping",
    )

    for route in routes:
        response = session.get(
            f"https://{haproxy_ip}/{route}",
            verify=False,
            timeout=10,
            headers={"Host": hostname},
        )
        assert response.status_code == 200, (
            f"Expected status code 200 for HTTPS /{route}, got {response.status_code}"
        )


@pytest.mark.skipif(
    USE_HOST_JUJU_MODEL,
    reason=LIVE_MODEL_SKIP_REASON,
)
def test_lbaas_grpc_hostagent_messenger(juju: jubilant.Juju, lbaas: jubilant.Juju):
    if lbaas is None:
        pytest.skip("LBaaS model not available")

    # NOTE: We do an inline import to avoid making `grpcio`
    # a build dependency.
    import grpc

    config = juju.config("landscape-server")
    root_url = config.get("root_url", "https://landscape.local/")
    hostname = urlparse(root_url).hostname

    lbaas_status = lbaas.status()
    if "haproxy" not in lbaas_status.apps:
        pytest.skip("HAProxy not found in lbaas model")
    haproxy_unit = list(lbaas_status.apps["haproxy"].units.values())[0]
    haproxy_ip = haproxy_unit.public_address

    main_status = juju.status()
    app_status = main_status.apps["landscape-server"]

    if "hostagent-messenger-haproxy-route" not in app_status.relations:
        pytest.skip("hostagent-messenger-haproxy-route not configured")

    haproxy_app = lbaas_status.apps["haproxy"]
    if "receive-ca-certs" not in haproxy_app.relations:
        pytest.skip("HAProxy missing receive-ca-certs relation, skipping...")

    original_hostagent = config.get("enable_hostagent_messenger")
    try:
        juju.config("landscape-server", values={"enable_hostagent_messenger": "true"})
        juju.wait(all_landscape_active, timeout=300)

        haproxy_unit_name = list(lbaas_status.apps["haproxy"].units.keys())[0]
        cert_result = lbaas.run(
            haproxy_unit_name, "get-certificate", {"hostname": hostname}
        )
        cert_pem = cert_result.results["certificate"].encode()

        credentials = grpc.ssl_channel_credentials(root_certificates=cert_pem)
        with grpc.secure_channel(
            f"{haproxy_ip}:6554",
            credentials,
            options=[("grpc.ssl_target_name_override", hostname)],
        ) as channel:
            grpc.channel_ready_future(channel).result(timeout=5)
    finally:
        juju.config(
            "landscape-server",
            values={
                "enable_hostagent_messenger": "true" if original_hostagent else "false"
            },
        )
        juju.wait(all_landscape_active, timeout=300)


@pytest.mark.skipif(
    USE_HOST_JUJU_MODEL,
    reason=LIVE_MODEL_SKIP_REASON,
)
def test_lbaas_grpc_ubuntu_installer_attach(juju: jubilant.Juju, lbaas: jubilant.Juju):
    if lbaas is None:
        pytest.skip("LBaaS model not available")

    # NOTE: We do an inline import to avoid making `grpcio`
    # a build dependency.
    import grpc

    config = juju.config("landscape-server")
    root_url = config.get("root_url", "https://landscape.local/")
    hostname = urlparse(root_url).hostname

    lbaas_status = lbaas.status()
    if "haproxy" not in lbaas_status.apps:
        pytest.skip("HAProxy not found in lbaas model")
    haproxy_unit = list(lbaas_status.apps["haproxy"].units.values())[0]
    haproxy_ip = haproxy_unit.public_address

    main_status = juju.status()
    app_status = main_status.apps["landscape-server"]

    if "ubuntu-installer-attach-haproxy-route" not in app_status.relations:
        pytest.skip("ubuntu-installer-attach-haproxy-route not configured")

    haproxy_app = lbaas_status.apps["haproxy"]
    if "receive-ca-certs" not in haproxy_app.relations:
        pytest.skip("HAProxy missing receive-ca-certs relation, skipping...")

    original_installer = config.get("enable_ubuntu_installer_attach")
    try:
        juju.config(
            "landscape-server", values={"enable_ubuntu_installer_attach": "true"}
        )
        juju.wait(all_landscape_active, timeout=300)

        haproxy_unit_name = list(lbaas_status.apps["haproxy"].units.keys())[0]
        cert_result = lbaas.run(
            haproxy_unit_name, "get-certificate", {"hostname": hostname}
        )
        cert_pem = cert_result.results["certificate"].encode()

        credentials = grpc.ssl_channel_credentials(root_certificates=cert_pem)
        with grpc.secure_channel(
            f"{haproxy_ip}:50051",
            credentials,
            options=[("grpc.ssl_target_name_override", hostname)],
        ) as channel:
            grpc.channel_ready_future(channel).result(timeout=5)
    finally:
        juju.config(
            "landscape-server",
            values={
                "enable_ubuntu_installer_attach": (
                    "true" if original_installer else "false"
                )
            },
        )
        juju.wait(all_landscape_active, timeout=300)


@pytest.mark.skipif(
    USE_HOST_JUJU_MODEL,
    reason=LIVE_MODEL_SKIP_REASON,
)
def test_upgrade_action_updates_ppa(juju: jubilant.Juju, bundle: None):
    """
    The upgrade action must add the PPA from the `landscape_ppa` config to apt
    sources before upgrading, so switching PPAs (ex. upgrade from self-hosted-24.04 to
    self-hosted-beta) works correctly.
    """
    unit_name = next(iter(juju.status().apps["landscape-server"].units))
    series = juju.exec("lsb_release -cs", unit=unit_name).stdout.strip()
    if series == "resolute":
        pytest.skip()

    juju.wait(all_landscape_active, timeout=300)

    landscape_ppas_config = juju.config("landscape-server").get(
        "landscape_ppa", "ppa:landscape/self-hosted-beta"
    )
    landscape_ppas = [p.strip() for p in landscape_ppas_config.split(",")]
    landscape_ppa = landscape_ppas[0]
    ppa_slug = landscape_ppa.removeprefix("ppa:")
    old_ppa = "ppa:landscape/self-hosted-24.04"

    if landscape_ppa == old_ppa:
        pytest.skip(
            "landscape_ppa is already self-hosted-24.04; nothing to swap, skipping."
        )

    unit_name = next(iter(juju.status().apps["landscape-server"].units))

    try:
        juju.exec(
            f"sudo add-apt-repository -y {old_ppa} && "
            f"sudo add-apt-repository -y --remove {landscape_ppa}",
            unit=unit_name,
        )
        try:
            juju.exec(
                f"grep -r '{ppa_slug}' /etc/apt/sources.list.d/",
                unit=unit_name,
            )
            pytest.fail(f"Expected '{ppa_slug}' to be absent before upgrade")
        except Exception:
            pass

        juju.run(unit_name, "pause")
        juju.run(unit_name, "upgrade")

        juju.exec(
            f"grep -r '{ppa_slug}' /etc/apt/sources.list.d/",
            unit=unit_name,
        )
    finally:
        for ppa in landscape_ppas:
            juju.exec(
                f"sudo add-apt-repository -y {ppa}",
                unit=unit_name,
            )
        juju.run(unit_name, "pause")
        juju.run(unit_name, "upgrade")
        juju.run(unit_name, "resume")


def test_outbox_snap_installed(juju: jubilant.Juju):
    """
    The landscape-outbox snap is installed and running on every unit and tracks
    the channel specified in the configuration.

    The landscape-outbox snap refreshes to the specified channel when the
    `outbox_snap_channel` config is changed.
    """

    # Default deployment should work out-of-the-box
    juju.wait(all_landscape_active, timeout=300)
    status = juju.status()
    units = status.apps["landscape-server"].units

    channel = juju.config("landscape-server")["outbox_snap_channel"]

    for unit in units:
        snap_list = juju.exec(
            f"snap list {LANDSCAPE_OUTBOX_SNAP}",
            unit=unit,
        ).stdout
        assert LANDSCAPE_OUTBOX_SNAP in snap_list
        assert str(channel) in snap_list

        snap_services = juju.exec(
            f"snap services {LANDSCAPE_OUTBOX_SNAP}",
            unit=unit,
        ).stdout
        assert re.search(r"\bactive\b", snap_services)

    # Refreshing to an invalid channel should fail
    fake_channel = "recent/stable"
    juju.config("landscape-server", values={"outbox_snap_channel": f"{fake_channel}"})
    juju.wait(jubilant.any_maintenance, timeout=60)
    app = juju.status().apps["landscape-server"]

    assert app.is_maintenance
    assert "Failed to refresh landscape-outbox snap" in app.app_status.message

    # Best-effort restore for other tests
    # TODO better context management for config-related tests
    juju.config(
        "landscape-server", values={"outbox_snap_channel": DEFAULT_OUTBOX_SNAP_CHANNEL}
    )
    juju.wait(all_landscape_active, timeout=300)


@pytest.mark.skipif(
    USE_HOST_JUJU_MODEL,
    reason=LIVE_MODEL_SKIP_REASON,
)
def test_action_pause_stops_services(juju: jubilant.Juju, bundle: None):
    """
    The pause action stops all Landscape systemd services on every unit.
    """
    juju.wait(all_landscape_active, timeout=300)

    status = juju.status()
    units = list(status.apps["landscape-server"].units)

    try:
        for unit in units:
            juju.run(unit, "pause")

        for unit in units:
            result = juju.exec(
                "systemctl is-active landscape-server.target || true",
                unit=unit,
            ).stdout
            assert "inactive" in result or "failed" in result, (
                f"Expected landscape-server.target to be inactive after pause on {unit}"
            )
    finally:
        for unit in units:
            juju.run(unit, "resume")
        juju.wait(all_landscape_active, timeout=300)


@pytest.mark.skipif(
    USE_HOST_JUJU_MODEL,
    reason=LIVE_MODEL_SKIP_REASON,
)
def test_action_resume_starts_services(juju: jubilant.Juju, bundle: None):
    """
    The resume action starts all Landscape systemd services after a pause.
    """
    juju.wait(all_landscape_active, timeout=300)

    status = juju.status()
    units = list(status.apps["landscape-server"].units)

    try:
        for unit in units:
            juju.run(unit, "pause")

        for unit in units:
            juju.run(unit, "resume")

        for unit in units:
            for service in DEFAULT_SERVICES:
                wait_for_service(juju, unit, service)
    finally:
        juju.wait(all_landscape_active, timeout=300)


@pytest.mark.skipif(
    USE_HOST_JUJU_MODEL,
    reason=LIVE_MODEL_SKIP_REASON,
)
def test_action_migrate_schema_fails_while_running(juju: jubilant.Juju, bundle: None):
    """
    Running migrate-schema while Landscape is running (not paused) must fail.
    """
    juju.wait(all_landscape_active, timeout=300)

    unit = leader_unit_name(juju, "landscape-server")

    with pytest.raises(Exception):
        juju.run(unit, "migrate-schema")


@pytest.mark.skipif(
    USE_HOST_JUJU_MODEL,
    reason=LIVE_MODEL_SKIP_REASON,
)
def test_action_migrate_schema_while_paused(juju: jubilant.Juju, bundle: None):
    """
    migrate-schema succeeds on the leader unit when Landscape is paused.
    """
    juju.wait(all_landscape_active, timeout=300)

    unit = leader_unit_name(juju, "landscape-server")

    try:
        juju.run(unit, "pause")
        result = juju.run(unit, "migrate-schema")
        assert result.status == "completed", (
            f"Expected migrate-schema to complete, got: {result.status}"
        )
    finally:
        juju.run(unit, "resume")
        juju.wait(all_landscape_active, timeout=300)


@pytest.mark.skipif(
    USE_HOST_JUJU_MODEL,
    reason=LIVE_MODEL_SKIP_REASON,
)
def test_action_migrate_schema_allow_connections(juju: jubilant.Juju, bundle: None):
    """
    migrate-schema with allow-connections=true succeeds while Landscape is running,
    allowing schema migration via PgBouncer without a full pause.
    """
    juju.wait(all_landscape_active, timeout=300)

    unit = leader_unit_name(juju, "landscape-server")

    result = juju.run(unit, "migrate-schema", {"allow-connections": True})
    assert result.status == "completed", (
        f"Expected migrate-schema --allow-connections to complete, got: {result.status}"
    )
