# © 2026 Canonical Ltd.

resource "juju_machine" "landscape_server" {
  count      = var.landscape_server.units
  model_uuid = var.model_uuid
  base       = var.landscape_server.base
  name       = "landscape-server-${count.index}"

  lifecycle {
    create_before_destroy = true
  }
}

module "landscape_server" {
  source      = "../../../charm"
  model_uuid  = var.model_uuid
  config      = var.landscape_server.config
  app_name    = var.landscape_server.app_name
  channel     = var.landscape_server.channel
  constraints = var.landscape_server.constraints
  revision    = var.landscape_server.revision
  base        = var.landscape_server.base
  machines    = toset([for m in juju_machine.landscape_server : m.machine_id])

  depends_on = [juju_machine.landscape_server]
}

# Legacy external HAProxy (pre-26.04 only)
# For 26.04+ with internal HAProxy, external LB would be in a separate model (LBaaS)
module "haproxy" {
  source      = "git::https://github.com/canonical/haproxy-operator.git//terraform/charm/haproxy?ref=haproxy-rev331"
  model_uuid  = var.model_uuid
  config      = var.haproxy.config
  app_name    = var.haproxy.app_name
  channel     = var.haproxy.channel
  constraints = var.haproxy.constraints
  revision    = var.haproxy.revision
  base        = var.haproxy.base
  units       = var.haproxy.units

  count = var.haproxy != null && !local.has_internal_haproxy ? 1 : 0
}

resource "juju_application" "http_ingress" {
  name        = var.http_ingress.app_name
  model_uuid  = var.model_uuid
  machines    = toset([for m in juju_machine.landscape_server : m.machine_id])
  constraints = var.http_ingress.constraints
  config      = var.http_ingress.config

  charm {
    name     = "ingress-configurator"
    revision = var.http_ingress.revision
    channel  = var.http_ingress.channel
    base     = var.http_ingress.base
  }

  depends_on = [juju_machine.landscape_server]

  count = var.http_ingress != null && local.has_internal_haproxy ? 1 : 0
}

resource "juju_application" "hostagent_messenger_ingress" {
  name        = var.hostagent_messenger_ingress.app_name
  model_uuid  = var.model_uuid
  machines    = toset([for m in juju_machine.landscape_server : m.machine_id])
  constraints = var.hostagent_messenger_ingress.constraints
  config      = var.hostagent_messenger_ingress.config

  charm {
    name     = "ingress-configurator"
    revision = var.hostagent_messenger_ingress.revision
    channel  = var.hostagent_messenger_ingress.channel
    base     = var.hostagent_messenger_ingress.base
  }

  depends_on = [juju_machine.landscape_server]

  count = var.hostagent_messenger_ingress != null && local.has_internal_haproxy ? 1 : 0
}

resource "juju_application" "ubuntu_installer_attach_ingress" {
  name        = var.ubuntu_installer_attach_ingress.app_name
  model_uuid  = var.model_uuid
  machines    = toset([for m in juju_machine.landscape_server : m.machine_id])
  constraints = var.ubuntu_installer_attach_ingress.constraints
  config      = var.ubuntu_installer_attach_ingress.config

  charm {
    name     = "ingress-configurator"
    revision = var.ubuntu_installer_attach_ingress.revision
    channel  = var.ubuntu_installer_attach_ingress.channel
    base     = var.ubuntu_installer_attach_ingress.base
  }

  depends_on = [juju_machine.landscape_server]

  count = var.ubuntu_installer_attach_ingress != null && local.has_internal_haproxy ? 1 : 0
}

module "postgresql" {
  source      = "git::https://github.com/canonical/postgresql-operator.git//terraform?ref=v16/1.165.0"
  juju_model  = var.model_uuid
  config      = var.postgresql.config
  app_name    = var.postgresql.app_name
  channel     = var.postgresql.channel
  constraints = var.postgresql.constraints
  revision    = var.postgresql.revision
  base        = var.postgresql.base
  units       = var.postgresql.units

  count = var.postgresql != null ? 1 : 0
}

# TODO: Replace with internal charm module if/when it's created
resource "juju_application" "rabbitmq_server" {
  name        = var.rabbitmq_server.app_name
  model_uuid  = var.model_uuid
  units       = var.rabbitmq_server.units
  constraints = var.rabbitmq_server.constraints
  config      = var.rabbitmq_server.config

  charm {
    name     = "rabbitmq-server"
    revision = var.rabbitmq_server.revision
    channel  = var.rabbitmq_server.channel
    base     = var.rabbitmq_server.base
  }

  count = var.rabbitmq_server != null ? 1 : 0
}

resource "juju_application" "lb_certs" {
  name        = var.lb_certs.app_name
  model_uuid  = var.model_uuid
  units       = var.lb_certs.units
  constraints = var.lb_certs.constraints
  config      = var.lb_certs.config

  charm {
    name     = "self-signed-certificates"
    revision = var.lb_certs.revision
    channel  = var.lb_certs.channel
    base     = var.lb_certs.base
  }

  count = var.lb_certs != null && local.has_internal_haproxy ? 1 : 0
}

locals {
  has_modern_amqp_relations = try(module.landscape_server.requires.inbound_amqp, null) != null && try(module.landscape_server.requires.outbound_amqp, null) != null
  has_internal_haproxy      = try(module.landscape_server.requires.load_balancer_certificates, null) != null
}

resource "juju_integration" "landscape_server_inbound_amqp" {
  model_uuid = var.model_uuid

  application {
    name     = module.landscape_server.app_name
    endpoint = module.landscape_server.requires.inbound_amqp
  }

  application {
    name = juju_application.rabbitmq_server[0].name
  }

  depends_on = [module.landscape_server, juju_application.rabbitmq_server]

  count = var.rabbitmq_server != null && local.has_modern_amqp_relations ? 1 : 0
}

resource "juju_integration" "landscape_server_outbound_amqp" {
  model_uuid = var.model_uuid

  application {
    name     = module.landscape_server.app_name
    endpoint = module.landscape_server.requires.outbound_amqp
  }

  application {
    name = juju_application.rabbitmq_server[0].name
  }

  depends_on = [module.landscape_server, juju_application.rabbitmq_server]

  count = var.rabbitmq_server != null && local.has_modern_amqp_relations ? 1 : 0
}

# TODO: update when RMQ charm module exists
resource "juju_integration" "landscape_server_rabbitmq_server" {
  model_uuid = var.model_uuid

  application {
    name = module.landscape_server.app_name
  }

  application {
    name = juju_application.rabbitmq_server[0].name
  }

  depends_on = [module.landscape_server, juju_application.rabbitmq_server]

  count = var.rabbitmq_server != null && !local.has_modern_amqp_relations ? 1 : 0
}

# Legacy HAProxy integration (pre-26.04 internal haproxy)
resource "juju_integration" "landscape_server_haproxy" {
  model_uuid = var.model_uuid

  application {
    name = module.landscape_server.app_name
  }

  application {
    name = module.haproxy[0].app_name
  }

  depends_on = [module.landscape_server, module.haproxy]

  count = var.haproxy != null && !local.has_internal_haproxy ? 1 : 0
}

resource "juju_integration" "landscape_server_tls_certificates" {
  model_uuid = var.model_uuid

  application {
    name     = module.landscape_server.app_name
    endpoint = module.landscape_server.requires.load_balancer_certificates
  }

  application {
    name     = juju_application.lb_certs[0].name
    endpoint = "certificates"
  }

  depends_on = [module.landscape_server, juju_application.lb_certs]

  count = var.lb_certs != null && local.has_internal_haproxy ? 1 : 0
}

# Ingress configurator integrations (optional, for LBaaS)
resource "juju_integration" "landscape_server_http_ingress" {
  model_uuid = var.model_uuid

  application {
    name     = module.landscape_server.app_name
    endpoint = module.landscape_server.requires.http_ingress
  }

  application {
    name     = juju_application.http_ingress[0].name
    endpoint = "ingress"
  }

  depends_on = [module.landscape_server, juju_application.http_ingress]

  count = var.http_ingress != null && local.has_internal_haproxy ? 1 : 0
}

resource "juju_integration" "landscape_server_hostagent_messenger_ingress" {
  model_uuid = var.model_uuid

  application {
    name     = module.landscape_server.app_name
    endpoint = module.landscape_server.requires.hostagent_messenger_ingress
  }

  application {
    name     = juju_application.hostagent_messenger_ingress[0].name
    endpoint = "ingress"
  }

  depends_on = [module.landscape_server, juju_application.hostagent_messenger_ingress]

  count = var.hostagent_messenger_ingress != null && local.has_internal_haproxy ? 1 : 0
}

resource "juju_integration" "landscape_server_ubuntu_installer_attach_ingress" {
  model_uuid = var.model_uuid

  application {
    name     = module.landscape_server.app_name
    endpoint = module.landscape_server.requires.ubuntu_installer_attach_ingress
  }

  application {
    name     = juju_application.ubuntu_installer_attach_ingress[0].name
    endpoint = "ingress"
  }

  depends_on = [module.landscape_server, juju_application.ubuntu_installer_attach_ingress]

  count = var.ubuntu_installer_attach_ingress != null && local.has_internal_haproxy ? 1 : 0
}

locals {
  has_modern_pg_interface = try(module.landscape_server.requires.database, null) != null
}


resource "juju_integration" "landscape_server_postgresql_legacy" {
  model_uuid = var.model_uuid

  application {
    name     = module.landscape_server.app_name
    endpoint = module.landscape_server.requires.db
  }

  application {
    name     = module.postgresql[0].application_name
    endpoint = "db-admin"
  }

  count = var.postgresql != null && !local.has_modern_pg_interface ? 1 : 0

  depends_on = [module.landscape_server, module.postgresql]

}

resource "juju_integration" "landscape_server_postgresql_modern" {
  model_uuid = var.model_uuid

  application {
    name     = module.landscape_server.app_name
    endpoint = module.landscape_server.requires.database
  }

  application {
    name     = module.postgresql[0].application_name
    endpoint = module.postgresql[0].provides.database
  }

  depends_on = [module.landscape_server, module.postgresql]

  count = var.postgresql != null && local.has_modern_pg_interface && var.pgbouncer == null ? 1 : 0

}

resource "juju_application" "pgbouncer" {
  name       = var.pgbouncer.app_name
  model_uuid = var.model_uuid
  units      = 0
  config     = var.pgbouncer.config

  charm {
    name     = "pgbouncer"
    revision = var.pgbouncer.revision
    channel  = var.pgbouncer.channel
    base     = var.pgbouncer.base
  }

  count = var.pgbouncer != null && local.has_modern_pg_interface ? 1 : 0
}

resource "juju_integration" "landscape_server_pgbouncer" {
  model_uuid = var.model_uuid

  application {
    name     = module.landscape_server.app_name
    endpoint = module.landscape_server.requires.database
  }

  application {
    name     = juju_application.pgbouncer[0].name
    endpoint = "database"
  }

  depends_on = [module.landscape_server, juju_application.pgbouncer]

  count = var.pgbouncer != null && local.has_modern_pg_interface ? 1 : 0
}

resource "juju_integration" "pgbouncer_postgresql" {
  model_uuid = var.model_uuid

  application {
    name     = juju_application.pgbouncer[0].name
    endpoint = "backend-database"
  }

  application {
    name     = module.postgresql[0].application_name
    endpoint = module.postgresql[0].provides.database
  }

  depends_on = [juju_application.pgbouncer, module.postgresql]

  count = var.pgbouncer != null && var.postgresql != null && local.has_modern_pg_interface ? 1 : 0
}
