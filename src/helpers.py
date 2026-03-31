import logging
import os
import subprocess
import sys

logger = logging.getLogger("landscape-charm")

MIGRATE_SERVICE_CONF_SCRIPT = "/opt/canonical/landscape/migrate-service-conf"


def get_modified_env_vars():
    """
    Because the python path gets munged by the juju env, this grabs the current
    env vars and returns a copy with the juju env removed from the python paths
    """
    env_vars = os.environ.copy()
    logger.info("Fixing python paths")
    new_paths = [
        path
        for path in sys.path
        if "juju" not in path
        # Exclude the charm's own stdlib paths (e.g. /usr/lib/python3.14) so that
        # subprocesses running under the landscape venv's Python (3.12) don't pick up
        # C extensions compiled for a different Python version, causing
        # SRE module mismatches.
        and f"/usr/lib/python{sys.version_info.major}.{sys.version_info.minor}"
        not in path
    ]
    env_vars["PYTHONPATH"] = ":".join(new_paths) + ":/opt/canonical/landscape"
    return env_vars


def migrate_service_conf() -> None:
    if os.path.isfile(MIGRATE_SERVICE_CONF_SCRIPT):
        try:
            migrate_result = subprocess.run(
                [MIGRATE_SERVICE_CONF_SCRIPT],
                capture_output=True,
                text=True,
                check=True,
                timeout=60,
                env=get_modified_env_vars(),
            )
        except subprocess.CalledProcessError as e:
            logger.error(
                "Migrating service.conf failed with return code %s", e.returncode
            )
            logger.error("Failed to migrate service.conf: %s", e.stderr)
        except subprocess.TimeoutExpired:
            logger.error("migrate-service-conf timed out")
        else:
            logger.info("Migrated service.conf: %s", migrate_result)
