# © 2026 Canonical Ltd.

# The following outputs are meant to conform with Canonical's standards for
# charm modules in a Terraform ecosystem (CC008).

output "app_name" {
  description = "Name of the deployed application."
  value       = juju_application.landscape_server.name
}

output "provides" {
  description = " Map of integration endpoints this charm provides (`cos-agent`, `data`, `hosted`, `nrpe-external-master`, `website`)."
  value = {
    cos_agent            = "cos-agent"
    data                 = "data"
    hosted               = "hosted"
    nrpe_external_master = "nrpe-external-master"
    website              = "website"
  }
}

locals {
  # Needed since the relations changed to support the hostagent services
  legacy_amqp_rel_channels = ["latest/stable", "latest/beta", "24.04/edge"]
  amqp_rels_updated_rev    = 142
  has_modern_amqp_rels     = !contains(local.legacy_amqp_rel_channels, var.channel) && (var.revision != null ? var.revision >= local.amqp_rels_updated_rev : true)
  amqp_relations           = local.has_modern_amqp_rels ? { inbound_amqp = "inbound-amqp", outbound_amqp = "outbound-amqp" } : { amqp = "amqp" }

  # Add support for the modern Postgres charm interface and keep backwards compatibility
  postgres_rels_updated_rev     = 213
  has_modern_postgres_interface = var.revision != null ? var.revision >= local.postgres_rels_updated_rev : true
  db_relations                  = local.has_modern_postgres_interface ? { database = "database", db = "db" } : { db = "db" }

  # External HAProxy (pre-26.04): if revision is old enough, expose website endpoint
  in_model_haproxy_rev    = 278
  legacy_haproxy_channels = ["latest/stable", "latest/beta", "24.04/edge"]
  has_external_haproxy    = var.revision != null ? var.revision < local.in_model_haproxy_rev : contains(local.legacy_haproxy_channels, var.channel)
  haproxy_relations       = local.has_external_haproxy ? { website = "website" } : {}

  haproxy_route_relations = local.has_external_haproxy ? {} : {
    appserver_haproxy_route               = "appserver-haproxy-route"
    pingserver_haproxy_route              = "pingserver-haproxy-route"
    message_server_haproxy_route          = "message-server-haproxy-route"
    api_haproxy_route                     = "api-haproxy-route"
    package_upload_haproxy_route          = "package-upload-haproxy-route"
    repository_haproxy_route              = "repository-haproxy-route"
    hostagent_messenger_haproxy_route     = "hostagent-messenger-haproxy-route"
    ubuntu_installer_attach_haproxy_route = "ubuntu-installer-attach-haproxy-route"
  }
}

output "requires" {
  description = "Map of integration endpoints this charm requires."
  value = merge({
    application_dashboard = "application-dashboard",
  }, local.amqp_relations, local.db_relations, local.haproxy_relations, local.haproxy_route_relations)
}

output "has_haproxy_route_interface" {
  description = "Indicates whether the deployed revision uses haproxy-route relations (26.04+) rather than the legacy external HAProxy website endpoint."
  value       = !local.has_external_haproxy
}
