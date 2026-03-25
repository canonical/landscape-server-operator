import time

import jubilant
import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry


def get_session(
    retries: int = 10,
    backoff_factor: float = 0.3,
    status_forcelist: tuple[int, ...] = (503,),
) -> requests.Session:
    """
    Create a session that includes retries for 503 statuses.

    This is useful for load balancing tests because the Landscape unit
    can report "ready" in Juju even if Landscape server is not yet ready to serve
    requests.

    Copied from https://urllib3.readthedocs.io/en/stable/reference/urllib3.util.html

    `retries`:
        Total number of retries to allow. Takes precedence over other counts.
        Set to None to remove this constraint and fall back on other counts.
        Set to 0 to fail on the first retry.

    `backoff_factor`:
        A backoff factor to apply between attempts after the second try (most errors
        are resolved immediately by a second try without a delay). urllib3 will sleep
        for: {backoff factor} * (2 ** ({number of previous retries})) seconds.

    `status_forcelist`:
        A set of integer HTTP status codes that we should force a retry on. A retry is
        initiated if the request method is in allowed_methods and the response status
        code is in status_forcelist. By default, this is disabled with None.

    """

    session = requests.Session()
    strategy = Retry(
        total=retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
        allowed_methods={"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"},
        raise_on_status=False,
    )

    adapter = HTTPAdapter(max_retries=strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def has_legacy_pg(juju: jubilant.Juju) -> bool:
    """
    Checks if PostgreSQL is in the current model
    and it's related using the `db-admin` endpoint
    (i.e., it's using the legacy PG interface).
    """
    pg = juju.status().apps.get("postgresql")
    if not pg:
        return False

    return "db-admin" in pg.relations


def has_modern_pg(juju: jubilant.Juju) -> bool:
    """
    Checks if PostgreSQL is in the current model
    and it's related using the `database` endpoint
    (i.e., it's using the modern PG interface).
    """
    pg = juju.status().apps.get("postgresql")
    if not pg:
        return False

    return "database" in pg.relations


def supports_legacy_pg(juju: jubilant.Juju) -> bool:
    """
    Checks if PostgreSQL is in the current model
    and it supports the legacy PG interface
    (i.e., the channel is 14/x or latest/x).
    """
    pg = juju.status().apps.get("postgresql")
    if not pg:
        return False

    return "14" in pg.charm_channel or "latest" in pg.charm_channel


def restore_db_relations(juju: jubilant.Juju, expected: set[str]) -> None:
    """
    Restores the relation between Landscape Server and PostgreSQL
    that may have been altered when testing the legacy/modern interfaces.
    """
    relations = set(juju.status().apps["landscape-server"].relations)

    # Used to have modern, needs it back
    if "database" in expected and "database" not in relations:
        # Will error if both are integrated at the same time
        if "db" in relations:
            juju.remove_relation(
                "landscape-server:db", "postgresql:db-admin", force=True
            )
            juju.wait(lambda status: not has_legacy_pg(juju), timeout=120)

        juju.integrate("landscape-server:database", "postgresql:database")

    elif "database" not in expected and "database" in relations:
        juju.remove_relation(
            "landscape-server:database", "postgresql:database", force=True
        )
        juju.wait(lambda status: not has_modern_pg(juju), timeout=120)

    # Refresh after they might have changed
    relations = set(juju.status().apps["landscape-server"].relations)

    # Supports for legacy was dropped in PG 16+
    if supports_legacy_pg(juju):
        # Used to have legacy, needs it back
        if "db" in expected and "db" not in relations:
            # Will error if both are integrated at the same time
            if "database" in relations:
                juju.remove_relation(
                    "landscape-server:database", "postgresql:database", force=True
                )
                juju.wait(lambda status: not has_modern_pg(juju), timeout=120)

            juju.integrate("landscape-server:db", "postgresql:db-admin")

        elif "db" not in expected and "db" in relations:
            juju.remove_relation(
                "landscape-server:db", "postgresql:db-admin", force=True
            )
            juju.wait(lambda status: not has_legacy_pg(juju), timeout=120)

    juju.wait(jubilant.all_active, timeout=300)


def wait_for_service(
    juju: jubilant.Juju,
    unit: str,
    service: str,
    timeout: int = 60,
    check_interval: float = 5.0,
) -> None:
    """
    Poll until a systemd service is active on the given unit.

    Juju reporting active does not guarantee all systemd services have finished
    starting, so this retries until `timeout` seconds have elapsed.
    """
    deadline = time.monotonic() + timeout
    last_exc: jubilant.CLIError | None = None
    while time.monotonic() < deadline:
        try:
            juju.ssh(unit, f"systemctl is-active {service}.service")
            return
        except jubilant.CLIError as e:
            last_exc = e
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            time.sleep(min(check_interval, remaining))
    raise AssertionError(
        f"Service '{service}' never became active on '{unit}'"
    ) from last_exc


def has_pgbouncer(juju: jubilant.Juju) -> bool:
    """
    Checks if PgBouncer is in the current model and is related to landscape-server
    via the `database` endpoint.
    """
    pgbouncer = juju.status().apps.get("pgbouncer")
    if not pgbouncer:
        return False

    return "database" in pgbouncer.relations


def has_haproxy_route_provider(juju: jubilant.Juju, app: str) -> bool:
    """
    Check if an app in the given model
    has an `haproxy-route` relation established.
    """
    status = juju.status()
    return any(
        rel.interface == "haproxy-route"
        for rels in status.apps[app].relations.values()
        for rel in rels
    )


def has_tls_certs_provider(juju: jubilant.Juju, app: str = "landscape-server") -> bool:
    """
    Check if an app in the given model
    has a `tls-certificates` relation established.
    """
    status = juju.status()
    return any(
        rel.interface == "tls-certificates"
        for rels in status.apps[app].relations.values()
        for rel in rels
    )
