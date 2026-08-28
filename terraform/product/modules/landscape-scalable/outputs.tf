# © 2025 Canonical Ltd.

output "registration_key" {
  description = "Registration key from the Landscape Server config."
  value       = lookup(var.landscape_server.config, "registration_key", null)
}

output "admin_email" {
  description = "Administrator email from the Landscape Server config."
  value       = lookup(var.landscape_server.config, "admin_email", null)
}

output "admin_password" {
  description = "Administrator password from the Landscape Server config (sensitive)."
  value       = lookup(var.landscape_server.config, "admin_password", null)
  sensitive   = true
}

output "applications" {
  description = "The charms included in the module."
  value = {
    landscape_server = module.landscape_server
    haproxy          = var.haproxy != null && length(module.haproxy) > 0 ? module.haproxy[0] : null
    tls_certificates = var.tls_certificates != null && length(juju_application.tls_certificates) > 0 ? juju_application.tls_certificates[0] : null
    postgresql       = var.postgresql != null && length(module.postgresql) > 0 ? module.postgresql[0] : null
    rabbitmq_server  = var.rabbitmq_server != null && length(juju_application.rabbitmq_server) > 0 ? juju_application.rabbitmq_server[0] : null
    pgbouncer        = var.pgbouncer != null && length(juju_application.pgbouncer) > 0 ? juju_application.pgbouncer[0] : null
  }
}

output "has_modern_amqp_relations" {
  description = "Indicates whether the deployment uses the modern inbound/outbound AMQP endpoints."
  value       = local.has_modern_amqp_relations
}

output "has_modern_postgres_interface" {
  description = "Indicates whether the deployment supports the modern PostgreSQL charm interface."
  value       = local.has_modern_pg_interface
}

output "has_modern_haproxy_interface" {
  description = "Indicates whether the deployment uses the modern haproxy-route relation/interface instead of the legacy website interface."
  value       = module.landscape_server.has_modern_haproxy_interface
}
