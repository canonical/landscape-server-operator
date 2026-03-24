"""
Integration tests for the Landscape scalable bundle, using Postgres, RabbitMQ,
and Landscape Server.

NOTE: These tests assume an IPv4 public address for the Landscape Server charm.
"""

import json
import time
from urllib.parse import urlparse

import jubilant
import pytest
import requests

from charm import DEFAULT_SERVICES, LANDSCAPE_UBUNTU_INSTALLER_ATTACH, LEADER_SERVICES
import haproxy
from tests.integration.helpers import (
    get_session,
    has_legacy_pg,
    has_modern_pg,
    has_pgbouncer,
    has_tls_certs_provider,
    restore_db_relations,
    supports_legacy_pg,
    wait_for_service,
)


def test_metrics_forbidden(juju: jubilant.Juju, bundle: None):
    """
    Requests to `/metrics` are denied with a 403.

    This includes the older `<host>/metrics` endpoint, and any newer per-service
    endpoints that end with `/metrics`, like `<host>/api/metrics`.
    """
    host = (
        juju.status()
        .apps["landscape-server"]
        .units["landscape-server/0"]
        .public_address
    )

    assert requests.get(f"http://{host}/metrics").status_code == 403
    assert requests.get(f"https://{host}/metrics", verify=False).status_code == 403

    services = ("message-system", "api", "ping")

    for service in services:
        for scheme in ("http", "https"):
            url = f"{scheme}://{host}/{service}/metrics"
            assert requests.get(url, verify=False).status_code == 403


def test_redirect_https_all(juju: jubilant.Juju, bundle: None):
    """
    If `redirect_https=all`, then redirect all HTTP requests on all routes to HTTPS.
    """
    host = (
        juju.status()
        .apps["landscape-server"]
        .units["landscape-server/0"]
        .public_address
    )
    original = juju.config("landscape-server").get("redirect_https")
    try:
        juju.config("landscape-server", values={"redirect_https": "all"})
        juju.wait(jubilant.all_active, timeout=300)

        redirect_routes = (
            "about",
            "api/about",
            "attachment",
            "hashid-databases",
            "ping",
            "message-system",
            "repository",
            "upload",
            "zzz-some-default-route",
        )

        session = get_session()
        for route in redirect_routes:
            url = f"http://{host}/{route}"
            response = session.get(url, allow_redirects=False)
            assert response.is_redirect, f"Got {response} from {url}"
    finally:
        juju.config("landscape-server", values={"redirect_https": original})
        juju.wait(jubilant.all_active, timeout=300)


def test_redirect_https_none(juju: jubilant.Juju, bundle: None):
    """
    If `redirect_https=none`, then do not redirect any HTTP requests on any routes
    to HTTPS.
    """
    host = (
        juju.status()
        .apps["landscape-server"]
        .units["landscape-server/0"]
        .public_address
    )
    original = juju.config("landscape-server").get("redirect_https")
    try:
        juju.config("landscape-server", values={"redirect_https": "none"})
        juju.wait(jubilant.all_active, timeout=300)

        no_redirect_routes = (
            "about",
            "api/about",
            "attachment",
            "hashid-databases",
            "ping",
            "message-system",
            "repository",
            "upload",
            "zzz-some-default-route",
        )

        session = get_session()
        for route in no_redirect_routes:
            url = f"http://{host}/{route}"
            response = session.get(url, allow_redirects=False)
            assert not response.is_redirect, f"Got {response} from {url}"
    finally:
        juju.config("landscape-server", values={"redirect_https": original})
        juju.wait(jubilant.all_active, timeout=300)


def test_redirect_https_default(juju: jubilant.Juju, bundle: None):
    """
    If `redirect_https=default`, then redirect all HTTP requests except for those to the
    /repository and /ping routes to HTTPS.
    """
    host = (
        juju.status()
        .apps["landscape-server"]
        .units["landscape-server/0"]
        .public_address
    )
    original = juju.config("landscape-server").get("redirect_https")
    try:
        juju.config("landscape-server", values={"redirect_https": "default"})
        juju.wait(jubilant.all_active, timeout=300)

        no_redirect_routes = (
            "ping",
            "repository",
        )

        session = get_session()
        for route in no_redirect_routes:
            url = f"http://{host}/{route}"
            response = session.get(url, allow_redirects=False)
            assert not response.is_redirect, f"Got {response} from {url}"

        redirect_routes = (
            "about",
            "api/about",
            "attachment",
            "hashid-databases",
            "message-system",
            "upload",
            "zzz-some-default-route",
        )
        for route in redirect_routes:
            url = f"http://{host}/{route}"
            response = session.get(url, allow_redirects=False)
            assert response.is_redirect, f"Got {response} from {url}"
    finally:
        juju.config("landscape-server", values={"redirect_https": original})
        juju.wait(jubilant.all_active, timeout=300)


def test_services_up_over_https(juju: jubilant.Juju, bundle: None):
    """
    Services are responding over HTTPS.
    """
    host = (
        juju.status()
        .apps["landscape-server"]
        .units["landscape-server/0"]
        .public_address
    )

    original = juju.config("landscape-server").get("redirect_https")
    try:
        juju.config("landscape-server", values={"redirect_https": "all"})
        juju.wait(jubilant.all_active, timeout=300)

        routes = ("ping", "api/about", "message-system", "")

        session = get_session()
        for route in routes:
            response = session.get(f"https://{host}/{route}", verify=False)
            assert response.status_code == 200, (
                f"Expected 200 status code for /{route} over HTTPS, "
                f"got {response.status_code}"
            )
    finally:
        juju.config("landscape-server", values={"redirect_https": original})
        juju.wait(jubilant.all_active, timeout=300)


def test_modern_database_relation(juju: jubilant.Juju, bundle: None):
    """
    Test the modern `database` interface.
    """
    status = juju.status()
    initial_relations = set(status.apps["landscape-server"].relations)

    if "db" in initial_relations:
        juju.remove_relation("landscape-server:db", "postgresql:db-admin", force=True)
        juju.wait(lambda status: not has_legacy_pg(juju), timeout=120)

        juju.integrate("landscape-server:database", "postgresql:database")

    elif "database" not in initial_relations:
        juju.integrate("landscape-server:database", "postgresql:database")
        juju.wait(lambda status: has_modern_pg(juju), timeout=120)

    relations = set(juju.status().apps["landscape-server"].relations)

    assert "database" in relations

    restore_db_relations(juju, initial_relations)


def test_legacy_db_relation(juju: jubilant.Juju, bundle: None):
    """
    Test the legacy `db` interface.
    """
    if not supports_legacy_pg(juju):
        pytest.skip("Legacy pgsql relation not available on this PostgreSQL charm")

    status = juju.status()
    initial_relations = set(status.apps["landscape-server"].relations)

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

    restore_db_relations(juju, initial_relations)


def test_pgbouncer_relation(juju: jubilant.Juju, bundle: None):
    """
    If PgBouncer is deployed, landscape-server connects to it via the `database`
    endpoint rather than directly to PostgreSQL.
    """
    if not has_pgbouncer(juju):
        pytest.skip("PgBouncer not present in this model, skipping...")

    pg_relations = set(juju.status().apps["pgbouncer"].relations)
    assert "database" in pg_relations, "pgbouncer should have a `database` relation"
    assert (
        "backend-database" in pg_relations
    ), "pgbouncer should have a `backend-database` relation to PostgreSQL"

    ls_relations = set(juju.status().apps["landscape-server"].relations)
    assert (
        "database" in ls_relations
    ), "landscape-server should be related via the `database` endpoint"


def test_get_service_conf_action(juju: jubilant.Juju, bundle: None):
    """
    The get-service-conf action returns a JSON-serialisable dict with the
    expected top-level sections from service.conf.
    """
    juju.wait(jubilant.all_active, timeout=300)

    result = juju.run("landscape-server/leader", "get-service-conf")
    assert result.status == "completed"

    config = json.loads(result.results["config"])
    assert (
        "stores" in config
    ), f"Expected 'stores' section in service.conf, got: {list(config)}"


def test_landscape_schema_migrated(juju: jubilant.Juju, bundle: None):
    """
    The Landscape database schema is present after deployment.

    Reads the connection details from service.conf via the get-service-conf
    action on the leader unit and runs a query to confirm the `account` table
    (created by landscape-schema) exists. This works regardless of whether
    pgbouncer or direct PostgreSQL is in use, since the host/port/user/password/
    dbname come from whatever landscape-server is configured to connect to.
    """
    juju.wait(jubilant.all_active, timeout=300)

    result = juju.run("landscape-server/leader", "get-service-conf")
    stores = json.loads(result.results["config"])["stores"]
    host, port = stores["host"].split(":")
    password, user, dbname = stores["password"], stores["user"], stores["main"]

    result = juju.ssh(
        "landscape-server/leader",
        f"PGPASSWORD={password} psql -h {host} -p {port} -U {user} -d {dbname}"
        ' -tAc "SELECT COUNT(*) FROM information_schema.tables'
        " WHERE table_schema = 'public' AND table_name = 'account';\"",
    ).strip()

    assert result == "1", (
        "Expected the 'account' table to exist in the landscape database, "
        f"got: {result!r}"
    )


def test_all_services_up(juju: jubilant.Juju, bundle: None):
    """
    All expected Landscape systemd services are active on every unit.

    Uses `wait_for_service` rather than a one-shot check because Juju
    reporting active does not guarantee the services have finished starting.
    """
    juju.wait(jubilant.all_active, timeout=300)

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


def test_ubuntu_installer_attach_service(juju: jubilant.Juju, bundle: None):
    """
    NOTE: There is not an equivalent hostagent_messenger test because
    that service will run regardless of the config, unlike Ubuntu Installer
    Attach which will actually install/uninstall the package/service in addition
    to creating an HAProxy backend for it.
    """
    juju.wait(jubilant.all_active, timeout=300)

    status = juju.status()
    units = status.apps["landscape-server"].units
    original = juju.config("landscape-server").get("enable_ubuntu_installer_attach")

    try:
        juju.config(
            "landscape-server", values={"enable_ubuntu_installer_attach": "true"}
        )
        juju.wait(jubilant.all_active, timeout=300)
        for name in units.keys():
            wait_for_service(juju, name, LANDSCAPE_UBUNTU_INSTALLER_ATTACH)

    finally:
        restore_val = "true" if original else "false"
        juju.config(
            "landscape-server", values={"enable_ubuntu_installer_attach": restore_val}
        )
        juju.wait(jubilant.all_active, timeout=300)


def test_ubuntu_installer_attach_toggle_no_maintenance(
    juju: jubilant.Juju, bundle: None
):
    """
    Toggling Ubuntu Installer Attach should return to active status and
    reflect the correct service state.
    """
    juju.wait(jubilant.all_active, timeout=300)
    config = juju.config("landscape-server")
    original_installer = config.get("enable_ubuntu_installer_attach")

    try:
        juju.config(
            "landscape-server", values={"enable_ubuntu_installer_attach": "true"}
        )
        juju.wait(jubilant.all_active, timeout=300)

        status = juju.status()
        assert status.apps["landscape-server"].app_status.current == "active"

        for name in status.apps["landscape-server"].units.keys():
            wait_for_service(juju, name, LANDSCAPE_UBUNTU_INSTALLER_ATTACH)

        juju.config(
            "landscape-server", values={"enable_ubuntu_installer_attach": "false"}
        )
        juju.wait(jubilant.all_active, timeout=300)

        status = juju.status()
        assert status.apps["landscape-server"].app_status.current == "active"

        for name in status.apps["landscape-server"].units.keys():
            with pytest.raises(Exception):
                juju.ssh(
                    name,
                    f"systemctl is-active {LANDSCAPE_UBUNTU_INSTALLER_ATTACH}.service",
                )

    finally:
        restore_val = "true" if original_installer else "false"
        juju.config(
            "landscape-server", values={"enable_ubuntu_installer_attach": restore_val}
        )
        juju.wait(jubilant.all_active, timeout=300)


def test_non_leader_unit_redirects_leader_only_services(
    juju: jubilant.Juju, bundle: None
):
    status = juju.status()
    units = status.apps["landscape-server"].units

    if len(units) <= 1:
        pytest.skip("Need more than 1 unit to have a non-leader!")

    juju.wait(jubilant.all_active, timeout=300)

    for name, unit_status in units.items():
        if not unit_status.leader:
            host = juju.status().apps["landscape-server"].units[name].public_address

            assert juju.wait(jubilant.all_active, timeout=300) and (
                get_session().get(f"https://{host}/upload", verify=False).status_code
                == 200
            )


def test_get_certificates_action_without_tls_relation(
    juju: jubilant.Juju, bundle: None
):
    status = juju.status()
    juju.wait(jubilant.all_active, timeout=300)

    has_tls_cert_relation = has_tls_certs_provider(juju)
    original_cert_provider = None

    if has_tls_cert_relation:
        cert_provider = None
        for app_name, app_status in status.apps.items():
            if app_name == "landscape-server":
                continue
            for rels in app_status.relations.values():
                if any(rel.interface == "tls-certificates" for rel in rels):
                    cert_provider = app_name
                    break

            if cert_provider:
                break  # We're allowed to have one

        assert cert_provider is not None
        original_cert_provider = cert_provider

        juju.remove_relation(
            "landscape-server:load-balancer-certificates",
            f"{cert_provider}:certificates",
            force=True,
        )
        juju.wait(lambda status: not has_tls_certs_provider(juju), timeout=120)

    with pytest.raises(jubilant.TaskError) as e:
        juju.run("landscape-server/0", "get-certificates")

    assert "No assigned TLS certificate found for this unit" in e.value.task.message
    assert e.value.task.status == "failed"

    if original_cert_provider:
        juju.integrate(
            "landscape-server:load-balancer-certificates",
            f"{original_cert_provider}:certificates",
        )
        juju.wait(lambda status: has_tls_certs_provider(juju), timeout=120)


def test_get_certificates_action_with_tls_relation(juju: jubilant.Juju, bundle: None):
    juju.wait(jubilant.all_active, timeout=300)

    if not has_tls_certs_provider(juju):
        pytest.skip("No TLS certificate relation found in bundle")

    juju.wait(jubilant.all_active, timeout=300)

    status = juju.status()
    leader_unit = None
    for unit_name, unit_status in status.apps["landscape-server"].units.items():
        if unit_status.leader:
            leader_unit = unit_name
            break

    assert leader_unit is not None

    max_attempts = 12
    result = None
    for attempt in range(max_attempts):
        try:
            result = juju.run(leader_unit, "get-certificates")
            if result.status == "completed":
                break
        except Exception:
            if attempt < max_attempts - 1:
                time.sleep(5)
                status = juju.status()
                for unit_name, unit_status in status.apps[
                    "landscape-server"
                ].units.items():
                    if unit_status.leader:
                        leader_unit = unit_name
                        break
            else:
                raise

    assert result is not None
    assert result.status == "completed"
    assert "certificate" in result.results
    assert "ca" in result.results
    assert "chain" in result.results


def test_get_certificates_action_on_non_leader_unit(juju: jubilant.Juju, bundle: None):
    status = juju.status()
    juju.wait(jubilant.all_active, timeout=300)

    if not has_tls_certs_provider(juju):
        pytest.skip("No TLS certificate relation found in bundle")

    status = juju.status()
    non_leader_units = [
        unit_name
        for unit_name, unit_status in status.apps["landscape-server"].units.items()
        if not unit_status.leader
    ]

    if not non_leader_units:
        pytest.skip("No non-leader units found")

    juju.wait(jubilant.all_active, timeout=300)

    result = juju.run(non_leader_units[0], "get-certificates")

    assert result.status == "completed"
    assert "certificate" in result.results
    assert "ca" in result.results
    assert "chain" in result.results


def test_http_ingress_enabled(juju: jubilant.Juju, bundle: None):
    """
    Verify that http-ingress is present and publishes correct data.
    """
    juju.wait(jubilant.all_active, timeout=300)
    status = juju.status()
    app_status = status.apps["landscape-server"]

    if "http-ingress" not in app_status.relations:
        pytest.skip("http-ingress relation not present in bundle")

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

    http_data = get_relation_data("http-ingress")

    assert (
        http_data.get("port") == "80"
    ), f"Expected port 80, got {http_data.get('port')}"
    assert http_data.get("name") == "landscape-server"


def test_grpc_ingress_config_enabled(juju: jubilant.Juju, bundle: None):
    """
    Verify that when ingress configs are enabled, the charm creates the ingress
    relations and publishes the correct data to the relation databags.
    """
    status = juju.status()
    app_status = status.apps["landscape-server"]
    if (
        "hostagent-messenger-ingress" not in app_status.relations
        or "ubuntu-installer-attach-ingress" not in app_status.relations
    ):
        pytest.skip("gRPC ingress not integrated, skipping...")

    juju.wait(jubilant.all_active, timeout=300)
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
        juju.wait(jubilant.all_active, timeout=300)
        status = juju.status()
        app_status = status.apps["landscape-server"]
        assert "hostagent-messenger-ingress" in app_status.relations
        assert "ubuntu-installer-attach-ingress" in app_status.relations

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

        hostagent_data = get_relation_data("hostagent-messenger-ingress")

        assert (
            hostagent_data.get("port") == "6554"
        ), f"Expected port 6554, got {hostagent_data.get('port')}"
        assert hostagent_data.get("name") == "landscape-server"

        installer_data = get_relation_data("ubuntu-installer-attach-ingress")

        assert (
            installer_data.get("port") == "50051"
        ), f"Expected port 50051, got {installer_data.get('port')}"
        assert installer_data.get("name") == "landscape-server"

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
        juju.wait(jubilant.all_active, timeout=300)


def test_lbaas_http_all_routes(juju: jubilant.Juju, lbaas: jubilant.Juju):
    """Test HTTP traffic for all routes through external HAProxy."""
    config = juju.config("landscape-server")
    root_url = config.get("root_url", "https://landscape.local/")
    hostname = urlparse(root_url).hostname

    status = lbaas.status()
    haproxy_unit = list(status.apps["haproxy"].units.values())[0]
    haproxy_ip = haproxy_unit.public_address

    session = get_session()

    routes = (
        "about",
        "api/about",
        "ping",
        "message-system",
        "upload",
    )

    for route in routes:
        response = session.get(
            f"http://{haproxy_ip}/{route}",
            timeout=10,
            headers={"Host": hostname},
            allow_redirects=True,
        )
        assert (
            response.status_code == 200
        ), f"Expected status code 200 for HTTP /{route}, got {response.status_code}"


def test_lbaas_https_all_routes(juju: jubilant.Juju, lbaas: jubilant.Juju):
    """Test HTTPS traffic for all routes through external HAProxy."""
    config = juju.config("landscape-server")
    root_url = config.get("root_url", "https://landscape.local/")
    hostname = urlparse(root_url).hostname

    status = lbaas.status()
    haproxy_unit = list(status.apps["haproxy"].units.values())[0]
    haproxy_ip = haproxy_unit.public_address

    session = get_session()

    routes = (
        "about",
        "api/about",
        "ping",
        "message-system",
        "upload",
    )

    for route in routes:
        url = f"https://{haproxy_ip}/{route}"
        response = session.get(
            url,
            verify=False,
            timeout=10,
            headers={"Host": hostname},
            allow_redirects=True,
        )
        assert (
            response.status_code == 200
        ), f"Expected status code 200 for HTTPS /{route}, got {response.status_code}"


def test_lbaas_metrics_acl_all_endpoints(juju: jubilant.Juju, lbaas: jubilant.Juju):
    config = juju.config("landscape-server")
    root_url = config.get("root_url", "https://landscape.local/")
    hostname = urlparse(root_url).hostname

    status = lbaas.status()
    haproxy_unit = list(status.apps["haproxy"].units.values())[0]
    haproxy_ip = haproxy_unit.public_address

    session = get_session()

    response = session.get(
        f"http://{haproxy_ip}/metrics", timeout=10, headers={"Host": hostname}
    )
    assert (
        response.status_code == 403
    ), f"Expected 403 for HTTP /metrics, got {response.status_code}"

    response = session.get(
        f"https://{haproxy_ip}/metrics",
        verify=False,
        timeout=10,
        headers={"Host": hostname},
    )
    assert (
        response.status_code == 403
    ), f"Expected 403 for HTTPS /metrics, got {response.status_code}"

    services = ("message-system", "api", "ping")

    for service in services:
        response = session.get(
            f"http://{haproxy_ip}/{service}/metrics",
            timeout=10,
            headers={"Host": hostname},
        )
        assert response.status_code == 403, (
            f"Expected 403 for HTTP /{service}/metrics, " f"got {response.status_code}"
        )

        response = session.get(
            f"https://{haproxy_ip}/{service}/metrics",
            verify=False,
            timeout=10,
            headers={"Host": hostname},
        )
        assert response.status_code == 403, (
            f"Expected 403 for HTTPS /{service}/metrics, " f"got {response.status_code}"
        )


def test_lbaas_grpc_hostagent_messenger(juju: jubilant.Juju, lbaas: jubilant.Juju):
    # NOTE: We do an inline import to avoid making `grpcio`
    # a build dependency.
    import grpc

    config = juju.config("landscape-server")
    root_url = config.get("root_url", "https://landscape.local/")
    hostname = urlparse(root_url).hostname

    lbaas_status = lbaas.status()
    haproxy_unit = list(lbaas_status.apps["haproxy"].units.values())[0]
    haproxy_ip = haproxy_unit.public_address

    main_status = juju.status()
    app_status = main_status.apps["landscape-server"]

    if "hostagent-messenger-ingress" not in app_status.relations:
        pytest.skip("hostagent-messenger-ingress not configured")

    haproxy_app = lbaas_status.apps["haproxy"]
    if "receive-ca-certs" not in haproxy_app.relations:
        pytest.skip("HAProxy missing receive-ca-certs relation, skipping...")

    original_hostagent = config.get("enable_hostagent_messenger")
    try:
        juju.config("landscape-server", values={"enable_hostagent_messenger": "true"})
        juju.wait(jubilant.all_active, timeout=300)

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
        juju.wait(jubilant.all_active, timeout=300)


def test_lbaas_grpc_ubuntu_installer_attach(juju: jubilant.Juju, lbaas: jubilant.Juju):
    # NOTE: We do an inline import to avoid making `grpcio`
    # a build dependency.
    import grpc

    config = juju.config("landscape-server")
    root_url = config.get("root_url", "https://landscape.local/")
    hostname = urlparse(root_url).hostname

    lbaas_status = lbaas.status()
    haproxy_unit = list(lbaas_status.apps["haproxy"].units.values())[0]
    haproxy_ip = haproxy_unit.public_address

    main_status = juju.status()
    app_status = main_status.apps["landscape-server"]

    if "ubuntu-installer-attach-ingress" not in app_status.relations:
        pytest.skip("ubuntu-installer-attach-ingress not configured")

    haproxy_app = lbaas_status.apps["haproxy"]
    if "receive-ca-certs" not in haproxy_app.relations:
        pytest.skip("HAProxy missing receive-ca-certs relation, skipping...")

    original_installer = config.get("enable_ubuntu_installer_attach")
    try:
        juju.config(
            "landscape-server", values={"enable_ubuntu_installer_attach": "true"}
        )
        juju.wait(jubilant.all_active, timeout=300)

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
        juju.wait(jubilant.all_active, timeout=300)


def test_haproxy_installed_and_configured(juju: jubilant.Juju, bundle: None):
    juju.wait(jubilant.all_active, timeout=300)

    status = juju.status()
    units = status.apps["landscape-server"].units

    for unit_name in units.keys():
        try:
            juju.ssh(unit_name, f"dpkg -l | grep -q {haproxy.HAPROXY_APT_PACKAGE_NAME}")
        except Exception as e:
            pytest.fail(f"HAProxy not installed on {unit_name}: {e}")

        try:
            juju.ssh(
                unit_name,
                f"sudo {haproxy.HAPROXY_EXECUTABLE} -c -f "
                f"{haproxy.HAPROXY_RENDERED_CONFIG_PATH}",
            )
        except Exception as e:
            pytest.fail(f"HAProxy config validation failed on {unit_name}: {e}")

        for error_file in haproxy.ERROR_FILES["files"].values():
            try:
                juju.ssh(
                    unit_name, f"test -f {haproxy.ERROR_FILES['location']}/{error_file}"
                )
            except Exception:
                pytest.fail(f"Error file missing on {unit_name}: {error_file}")

        wait_for_service(juju, unit_name, haproxy.HAPROXY_SERVICE)


def test_upgrade_action_updates_ppa(juju: jubilant.Juju, bundle: None):
    """
    The upgrade action must add the PPA from the `landscape_ppa` config to apt
    sources before upgrading, so switching PPAs (ex. upgrade from self-hosted-24.04 to
    self-hosted-beta) works correctly.
    """
    juju.wait(jubilant.all_active, timeout=300)

    landscape_ppa = juju.config("landscape-server").get(
        "landscape_ppa", "ppa:landscape/self-hosted-beta"
    )
    ppa_slug = landscape_ppa.removeprefix("ppa:")
    old_ppa = "ppa:landscape/self-hosted-24.04"

    if landscape_ppa == old_ppa:
        pytest.skip(
            "landscape_ppa is already self-hosted-24.04; nothing to swap, skipping."
        )

    unit_name = "landscape-server/0"

    try:
        juju.ssh(
            unit_name,
            f"sudo add-apt-repository -y {old_ppa} && "
            f"sudo add-apt-repository -y --remove {landscape_ppa}",
        )
        try:
            juju.ssh(unit_name, f"grep -r '{ppa_slug}' /etc/apt/sources.list.d/")
            pytest.fail(f"Expected '{ppa_slug}' to be absent before upgrade")
        except Exception:
            pass

        juju.run(unit_name, "pause")
        juju.run(unit_name, "upgrade")

        juju.ssh(unit_name, f"grep -r '{ppa_slug}' /etc/apt/sources.list.d/")
    finally:
        juju.ssh(unit_name, f"sudo add-apt-repository -y {landscape_ppa}")
        juju.run(unit_name, "resume")
        juju.wait(jubilant.all_active, timeout=300)
