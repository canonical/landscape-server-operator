"""
Configuration for the Landscape charm.
"""

from collections import Counter
from enum import Enum
from pathlib import Path
import re
from typing import Any

from pydantic import BaseModel, field_validator, model_validator
import yaml


class RedirectHTTPS(str, Enum):
    """
    Keywords to specify which HTTP routes should be redirected to HTTPS.
    """

    ALL = "all"
    NONE = "none"
    DEFAULT = "default"


class LandscapeCharmConfiguration(BaseModel):
    """
    `landscape-server` charm configuration.
    """

    landscape_ppa: str
    landscape_ppa_key: str

    @property
    def landscape_ppas(self) -> list[str]:
        return [p.strip() for p in self.landscape_ppa.split(",") if p.strip()]

    worker_counts: int
    license_file: str | None = None
    openid_provider_url: str | None = None
    openid_logout_url: str | None = None
    oidc_issuer: str | None = None
    oidc_client_id: str | None = None
    oidc_client_secret: str | None = None
    oidc_logout_url: str | None = None
    root_url: str | None = None
    system_email: str | None = None
    admin_email: str | None = None
    admin_name: str | None = None
    admin_password: str | None = None
    registration_key: str | None = None
    smtp_relay_host: str
    http_proxy: str | None = None
    https_proxy: str | None = None
    no_proxy: str | None = None
    site_name: str
    nagios_context: str | None = None
    nagios_servicegroups: str | None = None
    db_host: str | None = None
    db_landscape_password: str | None = None
    db_port: str | None = None
    db_schema_user: str | None = None
    db_schema_password: str | None = None
    deployment_mode: str
    additional_service_config: str | None = None
    secret_token: str | None = None
    cookie_encryption_key: str | None = None
    min_install: bool
    prometheus_scrape_interval: str
    autoregistration: bool
    redirect_https: RedirectHTTPS
    enable_hostagent_messenger: bool
    enable_ubuntu_installer_attach: bool
    max_global_haproxy_connections: int
    appserver_base_port: int
    pingserver_base_port: int
    message_server_base_port: int
    api_base_port: int
    package_upload_base_port: int
    hostagent_server_base_port: int
    ubuntu_installer_attach_base_port: int

    @field_validator("deployment_mode")
    @classmethod
    def deployment_mode_safe_chars(cls, v):
        if not re.fullmatch(r"[A-Za-z0-9_-]+", v):
            raise ValueError(
                f"deployment_mode {v!r} contains invalid characters. "
                "Only letters, numbers, hyphens, and underscores are allowed."
            )

        return v

    @model_validator(mode="after")
    def openid_oidc_exclusive(self):
        OPENID_CONFIGS = (
            "openid_provider_url",
            "openid_logout_url",
        )
        OIDC_CONFIGS = (
            "oidc_issuer",
            "oidc_client_id",
            "oidc_client_secret",
            "oidc_logout_url",
        )

        openid = self.model_dump(include=set(OPENID_CONFIGS))
        oidc = self.model_dump(include=set(OIDC_CONFIGS))

        if any(openid.values()) and any(oidc.values()):
            raise ValueError(
                "OpenID and OIDC configurations are mutually exclusive. "
                f"Received OpenID configuration: {openid} and "
                f"OIDC configuration: {oidc}."
            )
        return self

    @model_validator(mode="after")
    def openid_minimum_fields(self):
        """
        If using either `openid_provider_url` or `openid_logout_url`, must provide both.
        """
        required_configs = ("openid_provider_url", "openid_logout_url")
        fields = self.model_dump(include=set(required_configs))

        if any(fields.values()) and not all(fields.values()):
            raise ValueError(
                f"When using OpenID, must provide all of {required_configs}. "
                f"Got {fields}."
            )
        return self

    @model_validator(mode="after")
    def oidc_minimum_fields(self):
        """
        If providing any of `oidc_issuer`, `oidc_client_id`, or `oidc_client_secret`,
        must provide all three.
        """
        required_configs = ("oidc_issuer", "oidc_client_id", "oidc_client_secret")
        fields = self.model_dump(include=set(required_configs))

        if any(fields.values()) and not all(fields.values()):
            raise ValueError(
                f"When using OIDC, must provide all of {required_configs}. "
                f"Got {fields}."
            )
        return self

    @model_validator(mode="after")
    def haproxy_backend_port_validation(self):
        base_ports_with_workers = (
            "appserver_base_port",
            "pingserver_base_port",
            "message_server_base_port",
            "api_base_port",
        )
        base_ports_without_workers = (
            "package_upload_base_port",
            "hostagent_server_base_port",
            "ubuntu_installer_attach_base_port",
        )
        worker_counts = self.worker_counts
        ports_used = []
        for service in base_ports_with_workers:
            val = getattr(self, service)
            ports_used += list(range(val, val + worker_counts))
        ports_used += [getattr(self, service) for service in base_ports_without_workers]
        overused_ports = [
            port for port, count in Counter(ports_used).items() if count > 1
        ]
        if overused_ports:
            raise ValueError(
                "Configured service base ports and worker counts lead to overuse of "
                f"the following ports: {', '.join(map(str, overused_ports))}"
            )

        return self


def get_config_defaults() -> dict[str, Any]:
    """
    Get the `config.yaml`-defined configuration defaults for the charm.
    """
    config_file = Path(__file__).parent.parent / "config.yaml"
    assert config_file.exists(), f"Could not find config.yaml at {config_file}"

    with open(config_file) as f:
        raw = yaml.safe_load(f)

    configs = raw["options"]
    return {key: configs[key]["default"] for key in configs}


DEFAULT_CONFIGURATION = LandscapeCharmConfiguration.model_validate(
    get_config_defaults()
)
"""
A `LandscapeCharmConfiguration` populated with the defaults, for use as a fallback
when the charm is deployed with invalid configuration.
"""
