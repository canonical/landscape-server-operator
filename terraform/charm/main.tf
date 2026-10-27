# © 2025 Canonical Ltd.

locals {
  charm_revision = var.revision != null ? var.revision : data.juju_charm.landscape_server[0].revision
}

# Resolve unpinned channels during planning so relation counts match the charm
# revision that will actually be deployed, rather than assuming every feature.
data "juju_charm" "landscape_server" {
  count = var.revision == null ? 1 : 0

  charm        = var.charm_name
  channel      = var.channel
  base         = var.base
  architecture = try(regex("(?:^|\\s)arch=(\\S+)", var.constraints)[0], "amd64")
}

resource "juju_application" "landscape_server" {
  name       = var.app_name
  model_uuid = var.model_uuid

  charm {
    name     = var.charm_name
    channel  = var.channel
    revision = local.charm_revision
    base     = var.base
  }

  expose {}

  config      = var.config
  constraints = var.constraints
  units       = var.machines == null ? var.units : null
  machines    = var.machines
  trust       = true
}
