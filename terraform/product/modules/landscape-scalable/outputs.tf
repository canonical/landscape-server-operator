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
    postgresql       = var.postgresql != null && length(module.postgresql) > 0 ? module.postgresql[0] : null
    rabbitmq_server  = var.rabbitmq_server != null && length(juju_application.rabbitmq_server) > 0 ? juju_application.rabbitmq_server[0] : null
    lb_certs         = var.lb_certs != null && length(juju_application.lb_certs) > 0 ? juju_application.lb_certs[0] : null
  }
}

locals {
  haproxy_self_signed = var.haproxy != null && !local.has_internal_haproxy && (
    lookup(var.haproxy.config, "ssl_key", null) == null ||
    lookup(var.haproxy.config, "ssl_cert", null) == null ||
    lookup(var.haproxy.config, "ssl_cert", null) == "SELFSIGNED"
  )
}

output "haproxy_self_signed" {
  description = "Indicates whether legacy HAProxy is using a self-signed TLS certificate. Null for 26.04+ deployments with internal HAProxy or when haproxy is not deployed."
  value       = var.haproxy != null && !local.has_internal_haproxy ? local.haproxy_self_signed : null
}

output "has_modern_amqp_relations" {
  description = "Indicates whether the deployment uses the modern inbound/outbound AMQP endpoints."
  value       = local.has_modern_amqp_relations
}

output "has_modern_postgres_interface" {
  description = "Indicates whether the deployment supports the modern PostgreSQL charm interface."
  value       = local.has_modern_pg_interface
}

output "has_internal_haproxy" {
  description = "Indicates whether the deployment uses internal HAProxy (26.04 beta+) instead of the legacy external HAProxy charm."
  value       = local.has_internal_haproxy
}

output "ingress_configurators_deployed" {
  description = "Indicates whether ingress configurator charms are deployed for external load balancer integration."
  value       = local.has_internal_haproxy && var.http_ingress != null && var.hostagent_messenger_ingress != null && var.ubuntu_installer_attach_ingress != null && var.lb_certs != null
}
