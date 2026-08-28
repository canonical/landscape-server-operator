# © 2026 Canonical Ltd.

module "landscape_server" {
  source      = "../../../charm"
  model_uuid  = var.model_uuid
  config      = var.landscape_server.config
  app_name    = var.landscape_server.app_name
  channel     = var.landscape_server.channel
  constraints = var.landscape_server.constraints
  revision    = var.landscape_server.revision
  base        = var.landscape_server.base
  charm_name  = var.landscape_server.charm_name
  units       = var.landscape_server.units
}

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
  # machines is not supported by the external haproxy module (haproxy-rev331)

  count = var.haproxy != null && var.haproxy_route_offer_url == null ? 1 : 0
}

module "postgresql" {
  source      = "git::https://github.com/canonical/postgresql-operator.git//terraform?ref=v16/1.305.0"
  juju_model  = var.model_uuid
  config      = var.postgresql.config
  app_name    = var.postgresql.app_name
  channel     = var.postgresql.channel
  constraints = var.postgresql.constraints
  revision    = var.postgresql.revision
  base        = var.postgresql.base
  units       = var.postgresql.units
  # machines is not supported by the external postgresql module (v16/1.165.0)

  count = var.postgresql != null ? 1 : 0
}

# TODO: Replace with internal charm module if/when it's created
resource "juju_application" "rabbitmq_server" {
  name        = var.rabbitmq_server.app_name
  model_uuid  = var.model_uuid
  units       = var.rabbitmq_server.machines == null ? var.rabbitmq_server.units : null
  machines    = var.rabbitmq_server.machines
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

locals {
  has_modern_amqp_relations = try(module.landscape_server.requires.inbound_amqp, null) != null && try(module.landscape_server.requires.outbound_amqp, null) != null
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

resource "juju_integration" "landscape_server_haproxy" {
  model_uuid = var.model_uuid

  application {
    name     = module.landscape_server.app_name
    endpoint = module.landscape_server.provides.website
  }

  application {
    name     = module.haproxy[0].app_name
    endpoint = module.haproxy[0].requires.reverseproxy
  }

  depends_on = [module.landscape_server, module.haproxy]

  count = var.haproxy != null && var.haproxy_route_offer_url == null && !local.has_haproxy_route ? 1 : 0
}

resource "juju_integration" "landscape_server_appserver_haproxy_route_in_model" {
  model_uuid = var.model_uuid

  application {
    name     = module.landscape_server.app_name
    endpoint = module.landscape_server.requires.appserver_haproxy_route
  }

  application {
    name     = module.haproxy[0].app_name
    endpoint = module.haproxy[0].provides.haproxy_route
  }

  depends_on = [module.landscape_server, module.haproxy]

  count = var.haproxy != null && var.haproxy_route_offer_url == null && local.has_haproxy_route ? 1 : 0
}

resource "juju_integration" "landscape_server_pingserver_haproxy_route_in_model" {
  model_uuid = var.model_uuid

  application {
    name     = module.landscape_server.app_name
    endpoint = module.landscape_server.requires.pingserver_haproxy_route
  }

  application {
    name     = module.haproxy[0].app_name
    endpoint = module.haproxy[0].provides.haproxy_route
  }

  depends_on = [module.landscape_server, module.haproxy]

  count = var.haproxy != null && var.haproxy_route_offer_url == null && local.has_haproxy_route ? 1 : 0
}

resource "juju_integration" "landscape_server_message_server_haproxy_route_in_model" {
  model_uuid = var.model_uuid

  application {
    name     = module.landscape_server.app_name
    endpoint = module.landscape_server.requires.message_server_haproxy_route
  }

  application {
    name     = module.haproxy[0].app_name
    endpoint = module.haproxy[0].provides.haproxy_route
  }

  depends_on = [module.landscape_server, module.haproxy]

  count = var.haproxy != null && var.haproxy_route_offer_url == null && local.has_haproxy_route ? 1 : 0
}

resource "juju_integration" "landscape_server_api_haproxy_route_in_model" {
  model_uuid = var.model_uuid

  application {
    name     = module.landscape_server.app_name
    endpoint = module.landscape_server.requires.api_haproxy_route
  }

  application {
    name     = module.haproxy[0].app_name
    endpoint = module.haproxy[0].provides.haproxy_route
  }

  depends_on = [module.landscape_server, module.haproxy]

  count = var.haproxy != null && var.haproxy_route_offer_url == null && local.has_haproxy_route ? 1 : 0
}

resource "juju_integration" "landscape_server_package_upload_haproxy_route_in_model" {
  model_uuid = var.model_uuid

  application {
    name     = module.landscape_server.app_name
    endpoint = module.landscape_server.requires.package_upload_haproxy_route
  }

  application {
    name     = module.haproxy[0].app_name
    endpoint = module.haproxy[0].provides.haproxy_route
  }

  depends_on = [module.landscape_server, module.haproxy]

  count = var.haproxy != null && var.haproxy_route_offer_url == null && local.has_haproxy_route ? 1 : 0
}

resource "juju_integration" "landscape_server_repository_haproxy_route_in_model" {
  model_uuid = var.model_uuid

  application {
    name     = module.landscape_server.app_name
    endpoint = module.landscape_server.requires.repository_haproxy_route
  }

  application {
    name     = module.haproxy[0].app_name
    endpoint = module.haproxy[0].provides.haproxy_route
  }

  depends_on = [module.landscape_server, module.haproxy]

  count = var.haproxy != null && var.haproxy_route_offer_url == null && local.has_haproxy_route ? 1 : 0
}

resource "juju_integration" "landscape_server_hostagent_messenger_haproxy_route_in_model" {
  model_uuid = var.model_uuid

  application {
    name     = module.landscape_server.app_name
    endpoint = module.landscape_server.requires.hostagent_messenger_haproxy_route
  }

  application {
    name     = module.haproxy[0].app_name
    endpoint = "haproxy-route-tcp"
  }

  depends_on = [module.landscape_server, module.haproxy]

  count = var.haproxy != null && var.haproxy_route_tcp_offer_url == null && local.has_haproxy_route && local.enable_hostagent_messenger ? 1 : 0
}

resource "juju_integration" "landscape_server_ubuntu_installer_attach_haproxy_route_in_model" {
  model_uuid = var.model_uuid

  application {
    name     = module.landscape_server.app_name
    endpoint = module.landscape_server.requires.ubuntu_installer_attach_haproxy_route
  }

  application {
    name     = module.haproxy[0].app_name
    endpoint = "haproxy-route-tcp"
  }

  depends_on = [module.landscape_server, module.haproxy]

  count = var.haproxy != null && var.haproxy_route_tcp_offer_url == null && local.has_haproxy_route && local.enable_ubuntu_installer ? 1 : 0
}

resource "juju_integration" "landscape_server_appserver_haproxy_route_lbaas" {
  model_uuid = var.model_uuid

  application {
    name     = module.landscape_server.app_name
    endpoint = module.landscape_server.requires.appserver_haproxy_route
  }

  application {
    offer_url = var.haproxy_route_offer_url
  }

  depends_on = [
    module.landscape_server,
    juju_integration.landscape_server_pingserver_haproxy_route_lbaas,
    juju_integration.landscape_server_message_server_haproxy_route_lbaas,
    juju_integration.landscape_server_api_haproxy_route_lbaas,
    juju_integration.landscape_server_package_upload_haproxy_route_lbaas,
    juju_integration.landscape_server_repository_haproxy_route_lbaas,
    juju_integration.landscape_server_hostagent_messenger_haproxy_route_lbaas,
    juju_integration.landscape_server_ubuntu_installer_attach_haproxy_route_lbaas,
  ]

  count = var.haproxy_route_offer_url != null && local.has_haproxy_route ? 1 : 0
}

resource "juju_integration" "landscape_server_pingserver_haproxy_route_lbaas" {
  model_uuid = var.model_uuid

  application {
    name     = module.landscape_server.app_name
    endpoint = module.landscape_server.requires.pingserver_haproxy_route
  }

  application {
    offer_url = var.haproxy_route_offer_url
  }

  depends_on = [module.landscape_server]

  count = var.haproxy_route_offer_url != null && local.has_haproxy_route ? 1 : 0
}

resource "juju_integration" "landscape_server_message_server_haproxy_route_lbaas" {
  model_uuid = var.model_uuid

  application {
    name     = module.landscape_server.app_name
    endpoint = module.landscape_server.requires.message_server_haproxy_route
  }

  application {
    offer_url = var.haproxy_route_offer_url
  }

  depends_on = [module.landscape_server]

  count = var.haproxy_route_offer_url != null && local.has_haproxy_route ? 1 : 0
}

resource "juju_integration" "landscape_server_api_haproxy_route_lbaas" {
  model_uuid = var.model_uuid

  application {
    name     = module.landscape_server.app_name
    endpoint = module.landscape_server.requires.api_haproxy_route
  }

  application {
    offer_url = var.haproxy_route_offer_url
  }

  depends_on = [module.landscape_server]

  count = var.haproxy_route_offer_url != null && local.has_haproxy_route ? 1 : 0
}

resource "juju_integration" "landscape_server_package_upload_haproxy_route_lbaas" {
  model_uuid = var.model_uuid

  application {
    name     = module.landscape_server.app_name
    endpoint = module.landscape_server.requires.package_upload_haproxy_route
  }

  application {
    offer_url = var.haproxy_route_offer_url
  }

  depends_on = [module.landscape_server]

  count = var.haproxy_route_offer_url != null && local.has_haproxy_route ? 1 : 0
}

resource "juju_integration" "landscape_server_repository_haproxy_route_lbaas" {
  model_uuid = var.model_uuid

  application {
    name     = module.landscape_server.app_name
    endpoint = module.landscape_server.requires.repository_haproxy_route
  }

  application {
    offer_url = var.haproxy_route_offer_url
  }

  depends_on = [module.landscape_server]

  count = var.haproxy_route_offer_url != null && local.has_haproxy_route ? 1 : 0
}

resource "juju_integration" "landscape_server_hostagent_messenger_haproxy_route_lbaas" {
  model_uuid = var.model_uuid

  application {
    name     = module.landscape_server.app_name
    endpoint = module.landscape_server.requires.hostagent_messenger_haproxy_route
  }

  application {
    offer_url = var.haproxy_route_tcp_offer_url
  }

  depends_on = [module.landscape_server]

  count = var.haproxy_route_tcp_offer_url != null && local.has_haproxy_route && local.enable_hostagent_messenger ? 1 : 0
}

resource "juju_integration" "landscape_server_ubuntu_installer_attach_haproxy_route_lbaas" {
  model_uuid = var.model_uuid

  application {
    name     = module.landscape_server.app_name
    endpoint = module.landscape_server.requires.ubuntu_installer_attach_haproxy_route
  }

  application {
    offer_url = var.haproxy_route_tcp_offer_url
  }

  depends_on = [module.landscape_server]

  count = var.haproxy_route_tcp_offer_url != null && local.has_haproxy_route && local.enable_ubuntu_installer ? 1 : 0
}

locals {
  has_modern_pg_interface    = can(module.landscape_server.requires.database)
  has_haproxy_route          = coalesce(module.landscape_server.has_modern_haproxy_interface, false)
  enable_hostagent_messenger = try(var.landscape_server.config["enable_hostagent_messenger"], "false") == "true"
  enable_ubuntu_installer    = try(var.landscape_server.config["enable_ubuntu_installer_attach"], "false") == "true"

  # deploy the certificates app if haproxy or task-handler is present
  deploy_tls_certificates = var.tls_certificates != null && ((var.haproxy != null && var.haproxy_route_offer_url == null && local.has_haproxy_route) || var.landscape_task_handler != null)
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

resource "juju_application" "tls_certificates" {
  name        = var.tls_certificates.app_name
  model_uuid  = var.model_uuid
  units       = var.tls_certificates.machines == null ? 1 : null
  machines    = var.tls_certificates.machines
  constraints = var.tls_certificates.constraints

  charm {
    name     = var.tls_certificates.charm_name
    revision = var.tls_certificates.revision
    channel  = var.tls_certificates.channel
    base     = var.tls_certificates.base
  }

  count = local.deploy_tls_certificates ? 1 : 0
}

resource "juju_integration" "haproxy_certificates" {
  model_uuid = var.model_uuid

  application {
    name     = module.haproxy[0].app_name
    endpoint = module.haproxy[0].requires.certificates
  }

  application {
    name = juju_application.tls_certificates[0].name
  }

  depends_on = [module.haproxy, juju_application.tls_certificates]

  count = var.tls_certificates != null && var.haproxy != null && var.haproxy_route_offer_url == null && local.has_haproxy_route ? 1 : 0
}

resource "juju_integration" "haproxy_receive_ca_certs" {
  model_uuid = var.model_uuid

  application {
    name     = module.haproxy[0].app_name
    endpoint = module.haproxy[0].requires.receive_ca_certs
  }

  application {
    name = juju_application.tls_certificates[0].name
  }

  depends_on = [module.haproxy, juju_application.tls_certificates]

  count = var.tls_certificates != null && var.haproxy != null && var.haproxy_route_offer_url == null && local.has_haproxy_route ? 1 : 0
}

resource "juju_application" "pgbouncer_debarchive" {
  name       = "${var.pgbouncer.app_name}-debarchive"
  model_uuid = var.model_uuid
  config     = var.pgbouncer.config

  charm {
    name     = "pgbouncer"
    revision = var.pgbouncer.revision
    channel  = var.pgbouncer.channel
    base     = var.pgbouncer.base
  }

  lifecycle {
    # It's a subordinate
    ignore_changes = [units]
  }

  count = var.pgbouncer != null && var.landscape_debarchive != null && local.has_modern_pg_interface ? 1 : 0
}

resource "juju_application" "pgbouncer_server" {
  name       = "${var.pgbouncer.app_name}-server"
  model_uuid = var.model_uuid
  config     = var.pgbouncer.config

  charm {
    name     = "pgbouncer"
    revision = var.pgbouncer.revision
    channel  = var.pgbouncer.channel
    base     = var.pgbouncer.base
  }

  lifecycle {
    # It's a subordinate
    ignore_changes = [units]
  }

  count = var.pgbouncer != null && local.has_modern_pg_interface ? 1 : 0
}

resource "juju_integration" "landscape_debarchive_pgbouncer" {
  model_uuid = var.model_uuid

  application {
    name     = juju_application.landscape_debarchive[0].name
    endpoint = "database"
  }

  application {
    name     = juju_application.pgbouncer_debarchive[0].name
    endpoint = "database"
  }

  depends_on = [juju_application.landscape_debarchive, juju_application.pgbouncer_debarchive]

  count = var.pgbouncer != null && var.landscape_debarchive != null && local.has_modern_pg_interface ? 1 : 0
}

resource "juju_integration" "landscape_server_pgbouncer" {
  model_uuid = var.model_uuid

  application {
    name     = module.landscape_server.app_name
    endpoint = module.landscape_server.requires.database
  }

  application {
    name     = juju_application.pgbouncer_server[0].name
    endpoint = "database"
  }

  depends_on = [module.landscape_server, juju_application.pgbouncer_server]

  count = var.pgbouncer != null && local.has_modern_pg_interface ? 1 : 0
}

resource "juju_integration" "pgbouncer_debarchive_postgresql" {
  model_uuid = var.model_uuid

  application {
    name     = juju_application.pgbouncer_debarchive[0].name
    endpoint = "backend-database"
  }

  application {
    name     = module.postgresql[0].application_name
    endpoint = module.postgresql[0].provides.database
  }

  depends_on = [juju_application.pgbouncer_debarchive, module.postgresql]

  count = var.pgbouncer != null && var.landscape_debarchive != null && var.postgresql != null && local.has_modern_pg_interface ? 1 : 0
}

resource "juju_integration" "pgbouncer_server_postgresql" {
  model_uuid = var.model_uuid

  application {
    name     = juju_application.pgbouncer_server[0].name
    endpoint = "backend-database"
  }

  application {
    name     = module.postgresql[0].application_name
    endpoint = module.postgresql[0].provides.database
  }

  depends_on = [juju_application.pgbouncer_server, module.postgresql]

  count = var.pgbouncer != null && var.postgresql != null && local.has_modern_pg_interface ? 1 : 0
}

resource "juju_application" "landscape_debarchive" {
  name        = var.landscape_debarchive.app_name
  model_uuid  = var.model_uuid
  units       = var.landscape_debarchive.machines == null ? var.landscape_debarchive.units : null
  machines    = var.landscape_debarchive.machines
  constraints = var.landscape_debarchive.constraints
  config      = var.landscape_debarchive.config

  expose {}

  charm {
    name     = var.landscape_debarchive.charm_name
    revision = var.landscape_debarchive.revision
    channel  = var.landscape_debarchive.channel
    base     = var.landscape_debarchive.base
  }

  count = var.landscape_debarchive != null ? 1 : 0
}

resource "juju_integration" "landscape_debarchive_landscape_server" {
  model_uuid = var.model_uuid

  application {
    name     = juju_application.landscape_debarchive[0].name
    endpoint = "landscape-server"
  }

  application {
    name     = module.landscape_server.app_name
    endpoint = module.landscape_server.provides.debarchive
  }

  depends_on = [juju_application.landscape_debarchive, module.landscape_server]

  count = var.landscape_debarchive != null ? 1 : 0
}

resource "juju_integration" "landscape_debarchive_postgresql" {
  model_uuid = var.model_uuid

  application {
    name     = juju_application.landscape_debarchive[0].name
    endpoint = "database"
  }

  application {
    name     = module.postgresql[0].application_name
    endpoint = module.postgresql[0].provides.database
  }

  depends_on = [juju_application.landscape_debarchive, module.postgresql]

  count = var.landscape_debarchive != null && var.postgresql != null ? 1 : 0
}

resource "juju_integration" "landscape_debarchive_haproxy_route_in_model" {
  model_uuid = var.model_uuid

  application {
    name     = juju_application.landscape_debarchive[0].name
    endpoint = "debarchive-haproxy-route"
  }

  application {
    name     = module.haproxy[0].app_name
    endpoint = module.haproxy[0].provides.haproxy_route
  }

  depends_on = [juju_application.landscape_debarchive, module.haproxy]

  count = var.landscape_debarchive != null && var.haproxy != null && var.haproxy_route_offer_url == null && local.has_haproxy_route ? 1 : 0
}

resource "juju_integration" "landscape_debarchive_haproxy_route_lbaas" {
  model_uuid = var.model_uuid

  application {
    name     = juju_application.landscape_debarchive[0].name
    endpoint = "debarchive-haproxy-route"
  }

  application {
    offer_url = var.haproxy_route_offer_url
  }

  depends_on = [juju_application.landscape_debarchive]

  count = var.landscape_debarchive != null && var.haproxy_route_offer_url != null && local.has_haproxy_route ? 1 : 0
}

resource "juju_application" "landscape_task_handler" {
  name        = var.landscape_task_handler.app_name
  model_uuid  = var.model_uuid
  units       = var.landscape_task_handler.machines == null ? var.landscape_task_handler.units : null
  machines    = var.landscape_task_handler.machines
  constraints = var.landscape_task_handler.constraints
  config      = var.landscape_task_handler.config

  expose {}

  charm {
    name     = var.landscape_task_handler.charm_name
    revision = var.landscape_task_handler.revision
    channel  = var.landscape_task_handler.channel
    base     = var.landscape_task_handler.base
  }

  count = var.landscape_task_handler != null ? 1 : 0
}

resource "juju_integration" "landscape_task_handler_landscape_server" {
  model_uuid = var.model_uuid

  application {
    name     = juju_application.landscape_task_handler[0].name
    endpoint = "landscape-server"
  }

  application {
    name     = module.landscape_server.app_name
    endpoint = module.landscape_server.provides.task_handler
  }

  depends_on = [juju_application.landscape_task_handler, module.landscape_server]

  count = var.landscape_task_handler != null ? 1 : 0
}

resource "juju_integration" "landscape_task_handler_postgresql" {
  model_uuid = var.model_uuid

  application {
    name     = juju_application.landscape_task_handler[0].name
    endpoint = "task-db"
  }

  application {
    name     = module.postgresql[0].application_name
    endpoint = module.postgresql[0].provides.database
  }

  depends_on = [juju_application.landscape_task_handler, module.postgresql]

  count = var.landscape_task_handler != null && var.postgresql != null ? 1 : 0
}

resource "juju_integration" "landscape_task_handler_certificates" {
  model_uuid = var.model_uuid

  application {
    name     = juju_application.landscape_task_handler[0].name
    endpoint = "certificates"
  }

  application {
    name = juju_application.tls_certificates[0].name
  }

  depends_on = [juju_application.landscape_task_handler, juju_application.tls_certificates]

  count = var.landscape_task_handler != null && var.tls_certificates != null ? 1 : 0
}

resource "juju_integration" "landscape_task_handler_grpc_haproxy_route_in_model" {
  model_uuid = var.model_uuid

  application {
    name     = juju_application.landscape_task_handler[0].name
    endpoint = "grpc-haproxy-route"
  }

  application {
    name     = module.haproxy[0].app_name
    endpoint = "haproxy-route-tcp"
  }

  depends_on = [juju_application.landscape_task_handler, module.haproxy]

  count = var.landscape_task_handler != null && var.haproxy != null && var.haproxy_route_tcp_offer_url == null ? 1 : 0
}

resource "juju_integration" "landscape_task_handler_grpc_haproxy_route_lbaas" {
  model_uuid = var.model_uuid

  application {
    name     = juju_application.landscape_task_handler[0].name
    endpoint = "grpc-haproxy-route"
  }

  application {
    offer_url = var.haproxy_route_tcp_offer_url
  }

  depends_on = [juju_application.landscape_task_handler]

  count = var.landscape_task_handler != null && var.haproxy_route_tcp_offer_url != null ? 1 : 0
}
