# © 2026 Canonical Ltd.

# The following outputs are meant to conform with Canonical's standards for
# charm modules in a Terraform ecosystem (CC008).

output "app_name" {
  description = "Name of the deployed application."
  value       = juju_application.landscape_server.name
}

locals {
  # The debarchive relation was added in rev 357 (first release after PR #150,
  # merged 2026-06-09), well before the task-handler relation below
  legacy_debarchive_channel_tracks = ["latest", "24.04"]
  legacy_debarchive_channel        = anytrue([for l in local.legacy_debarchive_channel_tracks : startswith(var.channel, l)])
  debarchive_updated_rev           = 357
  has_debarchive_relation          = !local.legacy_debarchive_channel && (var.revision != null ? var.revision >= local.debarchive_updated_rev : true)

  # The task-handler relation was added later, in rev 447 (first release
  # after PR #168, merged 2026-07-17)
  legacy_task_handler_channel_tracks = ["latest", "24.04"]
  legacy_task_handler_channel        = anytrue([for l in local.legacy_task_handler_channel_tracks : startswith(var.channel, l)])
  task_handler_updated_rev           = 447
  has_task_handler_relation          = !local.legacy_task_handler_channel && (var.revision != null ? var.revision >= local.task_handler_updated_rev : true)

  companion_relations = merge(
    local.has_debarchive_relation ? { debarchive = "debarchive" } : {},
    local.has_task_handler_relation ? { task_handler = "task-handler" } : {},
  )
}

output "provides" {
  description = "Map of integration endpoints this charm provides."
  value = merge({
    cos_agent            = "cos-agent"
    data                 = "data"
    hosted               = "hosted"
    nrpe_external_master = "nrpe-external-master"
    website              = "website"
  }, local.companion_relations)
}

output "has_debarchive_relation" {
  description = "Indicates whether the deployed revision provides the debarchive relation (added in rev 357)."
  value       = local.has_debarchive_relation
}

output "has_task_handler_relation" {
  description = "Indicates whether the deployed revision provides the task-handler relation (added in rev 447)."
  value       = local.has_task_handler_relation
}

locals {
  # Needed since the relations changed to support the hostagent services
  legacy_amqp_channel_tracks = ["latest", "24.04"]
  legacy_amqp_channel        = anytrue([for l in local.legacy_amqp_channel_tracks : startswith(var.channel, l)])
  amqp_rels_updated_rev      = 142
  has_modern_amqp_rels       = !local.legacy_amqp_channel && (var.revision != null ? var.revision >= local.amqp_rels_updated_rev : true)
  amqp_relations             = local.has_modern_amqp_rels ? { inbound_amqp = "inbound-amqp", outbound_amqp = "outbound-amqp" } : { amqp = "amqp" }

  # Add support for the modern Postgres charm interface and keep backwards compatibility
  postgres_rels_updated_rev      = 213
  legacy_postgres_channel_tracks = ["latest", "24.04"]
  legacy_postgres_channel        = anytrue([for l in local.legacy_postgres_channel_tracks : startswith(var.channel, l)])
  has_modern_postgres_interface  = !local.legacy_postgres_channel && (var.revision != null ? var.revision >= local.postgres_rels_updated_rev : true)
  db_relations                   = local.has_modern_postgres_interface ? { database = "database", db = "db" } : { db = "db" }

  # Legacy HAProxy (pre-26.04): if revision is old enough, expose website endpoint
  haproxy_updated_rev           = 278
  legacy_haproxy_channel_tracks = ["latest", "24.04"]
  legacy_haproxy_channel        = anytrue([for l in local.legacy_haproxy_channel_tracks : startswith(var.channel, l)])
  has_modern_haproxy_interface  = !local.legacy_haproxy_channel && (var.revision != null ? var.revision >= local.haproxy_updated_rev : true)
  haproxy_relations = local.has_modern_haproxy_interface ? {
    appserver_haproxy_route               = "appserver-haproxy-route"
    pingserver_haproxy_route              = "pingserver-haproxy-route"
    message_server_haproxy_route          = "message-server-haproxy-route"
    api_haproxy_route                     = "api-haproxy-route"
    package_upload_haproxy_route          = "package-upload-haproxy-route"
    repository_haproxy_route              = "repository-haproxy-route"
    hostagent_messenger_haproxy_route     = "hostagent-messenger-haproxy-route"
    ubuntu_installer_attach_haproxy_route = "ubuntu-installer-attach-haproxy-route"
  } : { website = "website" }

}

output "requires" {
  description = "Map of integration endpoints this charm requires."
  value = merge({
    application_dashboard = "application-dashboard",
    smtp                  = "smtp",
  }, local.amqp_relations, local.db_relations, local.haproxy_relations)
}

output "has_modern_haproxy_interface" {
  description = "Indicates whether the deployed revision uses haproxy-route relations (26.04+) rather than the legacy external HAProxy website endpoint."
  value       = local.has_modern_haproxy_interface
}
