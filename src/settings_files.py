# Copyright 2025 Canonical Ltd

"""
Functions for manipulating Landscape Server service settings in the
filesystem.
"""

import base64
from base64 import b64decode, binascii
from collections import defaultdict
from configparser import ConfigParser
import os
import secrets
from string import ascii_letters, digits
from urllib.error import URLError
from urllib.request import urlopen

from charms.operator_libs_linux.v1.systemd import daemon_reload

from database import get_postgres_owner_role_from_version, PostgresRoles
from helpers import migrate_service_conf

CONFIGS_DIR = "/opt/canonical/landscape/configs"

DEFAULT_SETTINGS = "/etc/default/landscape-server"

LICENSE_FILE = "/etc/landscape/license.txt"
LICENSE_FILE_PROTOCOLS = (
    "file://",
    "http://",
    "https://",
)

SERVICE_CONF = "/etc/landscape/service.conf"

DEFAULT_POSTGRES_PORT = "5432"

AMQP_USERNAME = "landscape"
VHOSTS = {
    "inbound-amqp": "landscape",
    "outbound-amqp": "landscape-hostagent",
}


class LicenseFileReadException(Exception):
    pass


class SSLCertReadException(Exception):
    pass


class ServiceConfMissing(Exception):
    pass


class SecretTokenMissing(Exception):
    pass


_SERVICES_WITH_HARDCODED_DEPLOYMENT_MODE = [
    "landscape-api.service",
    "landscape-appserver.service",
    "landscape-async-frontend.service",
    "landscape-job-handler.service",
    "landscape-msgserver.service",
    "landscape-package-search.service",
    "landscape-package-upload.service",
    "landscape-pingserver.service",
]

_DEPLOYMENT_MODE_OVERRIDE_CONF = "deployment-mode.conf"


def write_deployment_mode_systemd_override(mode: str) -> None:
    """
    Writes a systemd drop-in per service to override LANDSCAPE_SYSTEM__DEPLOYMENT_MODE.

    Necessary because the package hardcodes 'standalone' in each unit file's
    Environment= directive.
    """
    for service in _SERVICES_WITH_HARDCODED_DEPLOYMENT_MODE:
        override_dir = f"/etc/systemd/system/{service}.d"
        os.makedirs(override_dir, exist_ok=True)
        with open(os.path.join(override_dir, _DEPLOYMENT_MODE_OVERRIDE_CONF), "w") as f:
            f.write("[Service]\n")
            f.write(f"Environment=LANDSCAPE_SYSTEM__DEPLOYMENT_MODE={mode}\n")
    daemon_reload()


def configure_for_deployment_mode(mode: str) -> None:
    """
    Creates filesystem symlinks so Landscape can locate config files for the given
    deployment mode.
    """
    if mode == "standalone":
        return

    sym_path = os.path.join(CONFIGS_DIR, mode)

    if os.path.exists(sym_path):
        return

    os.symlink(os.path.join(CONFIGS_DIR, "standalone"), sym_path)


def merge_service_conf(other: str) -> None:
    """
    Merges `other` into the Landscape Server configuration file,
    overwriting existing config.
    """
    config = ConfigParser()
    config.read(SERVICE_CONF)
    config.read_string(other)

    with open(SERVICE_CONF, "w") as config_fp:
        config.write(config_fp)


def prepend_default_settings(updates: dict) -> None:
    """
    Adds `updates` to the start of the Landscape Server default
    settings file.
    """
    with open(DEFAULT_SETTINGS, "r") as settings_fp:
        settings = settings_fp.read()

    with open(DEFAULT_SETTINGS, "w") as settings_fp:
        for k, v in updates.items():
            settings_fp.write(f'{k}="{v}"\n')

        settings_fp.write(settings)


def update_default_settings(updates: dict) -> None:
    """
    Updates the Landscape Server default settings file.

    This file is mainly used to determine which services should be
    running for this installation.
    """
    with open(DEFAULT_SETTINGS, "r") as settings_fp:
        new_lines = []

        for line in settings_fp:
            if "=" in line and line.split("=")[0] in updates:
                key = line.split("=")[0]
                new_line = f'{key}="{updates[key]}"\n'
            else:
                new_line = line

            new_lines.append(new_line)

    with open(DEFAULT_SETTINGS, "w") as settings_file:
        settings_file.write("".join(new_lines))


def update_service_conf(updates: dict) -> None:
    """
    Updates the Landscape Server configuration file.

    `updates` is a mapping of {section => {key => value}}, to be applied
        to the config file.
    """
    if not os.path.isfile(SERVICE_CONF):
        # Landscape server will not overwrite this file on install, so we
        # cannot get the default values if we create it here
        raise ServiceConfMissing("Landscape server install failed!")

    config = ConfigParser()
    config.read(SERVICE_CONF)

    for section, data in updates.items():
        for key, value in data.items():
            if not config.has_section(section):
                config.add_section(section)

            config[section][key] = value

    with open(SERVICE_CONF, "w") as config_fp:
        config.write(config_fp)

    migrate_service_conf()


def generate_secret_token():
    alphanumerics = ascii_letters + digits
    return "".join(secrets.choice(alphanumerics) for _ in range(172))


def generate_cookie_encryption_key():
    # NOTE: This is similar to Fernet key generation, but we avoid
    # bringing extra modules this way.
    return base64.urlsafe_b64encode(os.urandom(32)).decode("utf-8")


def write_license_file(license_file: str, uid: int, gid: int) -> None:
    """
    Reads or decodes `license_file` to LICENSE_FILE and sets it up
    ownership for `uid` and `gid`.

    raises LicenseFileReadException if the location `license_file`
    cannot be read
    """

    if any((license_file.startswith(proto) for proto in LICENSE_FILE_PROTOCOLS)):
        try:
            license_file_data = urlopen(license_file).read()
        except URLError:
            raise LicenseFileReadException(
                f"Unable to read license file at {license_file}"
            )
    else:
        # Assume b64-encoded
        try:
            license_file_data = b64decode(license_file.encode())
        except binascii.Error:
            raise LicenseFileReadException("Unable to read b64-encoded license file")

    with open(LICENSE_FILE, "wb") as license_fp:
        license_fp.write(license_file_data)

    os.chmod(LICENSE_FILE, 0o640)
    os.chown(LICENSE_FILE, uid, gid)


def update_db_conf(
    host=None,
    password=None,
    schema_password=None,
    port=DEFAULT_POSTGRES_PORT,
    user=None,
):
    """Postgres specific settings override"""
    to_update = defaultdict(dict)
    if host:  # Note that host is required if port is changed
        to_update["stores"]["host"] = "{}:{}".format(host, port)
    if password:
        to_update["stores"]["password"] = password
        to_update["schema"]["store_password"] = password
    if schema_password:  # Overrides password
        to_update["schema"]["store_password"] = schema_password
    if user:
        to_update["schema"]["store_user"] = user
    if to_update:
        update_service_conf(to_update)


def get_postgres_roles(postgresql_version: str) -> PostgresRoles:
    """
    Gets the PostgreSQL role names for Landscape based on the
    version and the values written in `service.conf`.
    """
    config = ConfigParser()
    config.read(SERVICE_CONF)

    owner = get_postgres_owner_role_from_version(postgresql_version)

    # Relation role. Note this is granted the `SUPERUSER` role upon joining.
    relation = config.get("schema", "store_user", fallback=None)

    # Application role, is granted `charmed_dml` in Charmed Postgres 16+.
    application = config.get("stores", "user", fallback="landscape")

    # If provided in the config, this role will be escalated to `SUPERUSER`, aka
    # given the `charmed_dba` role in Charmed Postgres 16+.
    superuser = config.get("schema", "store_superuser", fallback=None)

    return PostgresRoles(
        owner=owner, relation=relation, application=application, superuser=superuser
    )


def read_service_conf() -> dict:
    """
    Returns the parsed contents of SERVICE_CONF as a plain dict of
    {section: {key: value}}, suitable for serialisation to JSON.
    """
    config = ConfigParser()
    config.read(SERVICE_CONF)
    return {section: dict(config[section]) for section in config.sections()}
