# © 2026 Canonical Ltd.

resource "juju_machine" "landscape_server" {
  count      = var.landscape_server.units
  model_uuid = var.model_uuid
  base       = var.landscape_server.base
  name       = "landscape-server-${count.index}"

  lifecycle {
    ignore_changes = [constraints]
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

  count = var.haproxy != null && var.haproxy_route_offer_url == null ? 1 : 0
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
    name = module.landscape_server.app_name
  }

  application {
    name     = module.haproxy[0].app_name
    endpoint = "haproxy-route"
  }

  depends_on = [module.landscape_server, module.haproxy]

  count = var.haproxy != null && var.haproxy_route_offer_url == null && !local.has_haproxy_route ? 1 : 0
}

resource "juju_integration" "landscape_server_appserver_haproxy_route_in_model" {
  model_uuid = var.model_uuid

  application {
    name     = module.landscape_server.app_name
    endpoint = "appserver-haproxy-route"
  }

  application {
    name     = module.haproxy[0].app_name
    endpoint = "haproxy-route"
  }

  depends_on = [module.landscape_server, module.haproxy]

  count = var.haproxy != null && var.haproxy_route_offer_url == null && local.has_haproxy_route ? 1 : 0
}

resource "juju_integration" "landscape_server_pingserver_haproxy_route_in_model" {
  model_uuid = var.model_uuid

  application {
    name     = module.landscape_server.app_name
    endpoint = "pingserver-haproxy-route"
  }

  application {
    name     = module.haproxy[0].app_name
    endpoint = "haproxy-route"
  }

  depends_on = [module.landscape_server, module.haproxy]

  count = var.haproxy != null && var.haproxy_route_offer_url == null && local.has_haproxy_route ? 1 : 0
}

resource "juju_integration" "landscape_server_message_server_haproxy_route_in_model" {
  model_uuid = var.model_uuid

  application {
    name     = module.landscape_server.app_name
    endpoint = "message-server-haproxy-route"
  }

  application {
    name     = module.haproxy[0].app_name
    endpoint = "haproxy-route"
  }

  depends_on = [module.landscape_server, module.haproxy]

  count = var.haproxy != null && var.haproxy_route_offer_url == null && local.has_haproxy_route ? 1 : 0
}

resource "juju_integration" "landscape_server_api_haproxy_route_in_model" {
  model_uuid = var.model_uuid

  application {
    name     = module.landscape_server.app_name
    endpoint = "api-haproxy-route"
  }

  application {
    name     = module.haproxy[0].app_name
    endpoint = "haproxy-route"
  }

  depends_on = [module.landscape_server, module.haproxy]

  count = var.haproxy != null && var.haproxy_route_offer_url == null && local.has_haproxy_route ? 1 : 0
}

resource "juju_integration" "landscape_server_package_upload_haproxy_route_in_model" {
  model_uuid = var.model_uuid

  application {
    name     = module.landscape_server.app_name
    endpoint = "package-upload-haproxy-route"
  }

  application {
    name     = module.haproxy[0].app_name
    endpoint = "haproxy-route"
  }

  depends_on = [module.landscape_server, module.haproxy]

  count = var.haproxy != null && var.haproxy_route_offer_url == null && local.has_haproxy_route ? 1 : 0
}

resource "juju_integration" "landscape_server_repository_haproxy_route_in_model" {
  model_uuid = var.model_uuid

  application {
    name     = module.landscape_server.app_name
    endpoint = "repository-haproxy-route"
  }

  application {
    name     = module.haproxy[0].app_name
    endpoint = "haproxy-route"
  }

  depends_on = [module.landscape_server, module.haproxy]

  count = var.haproxy != null && var.haproxy_route_offer_url == null && local.has_haproxy_route ? 1 : 0
}

resource "juju_integration" "landscape_server_hostagent_messenger_haproxy_route_in_model" {
  model_uuid = var.model_uuid

  application {
    name     = module.landscape_server.app_name
    endpoint = "hostagent-messenger-haproxy-route"
  }

  application {
    name     = module.haproxy[0].app_name
    endpoint = "haproxy-route"
  }

  depends_on = [module.landscape_server, module.haproxy]

  count = var.haproxy != null && var.haproxy_route_offer_url == null && local.has_haproxy_route && local.enable_hostagent_messenger ? 1 : 0
}

resource "juju_integration" "landscape_server_ubuntu_installer_attach_haproxy_route_in_model" {
  model_uuid = var.model_uuid

  application {
    name     = module.landscape_server.app_name
    endpoint = "ubuntu-installer-attach-haproxy-route"
  }

  application {
    name     = module.haproxy[0].app_name
    endpoint = "haproxy-route"
  }

  depends_on = [module.landscape_server, module.haproxy]

  count = var.haproxy != null && var.haproxy_route_offer_url == null && local.has_haproxy_route && local.enable_ubuntu_installer ? 1 : 0
}

resource "juju_integration" "landscape_server_appserver_haproxy_route_lbaas" {
  model_uuid = var.model_uuid

  application {
    name     = module.landscape_server.app_name
    endpoint = "appserver-haproxy-route"
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
    endpoint = "pingserver-haproxy-route"
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
    endpoint = "message-server-haproxy-route"
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
    endpoint = "api-haproxy-route"
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
    endpoint = "package-upload-haproxy-route"
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
    endpoint = "repository-haproxy-route"
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
    endpoint = "hostagent-messenger-haproxy-route"
  }

  application {
    offer_url = var.haproxy_route_offer_url
  }

  depends_on = [module.landscape_server]

  count = var.haproxy_route_offer_url != null && local.has_haproxy_route && local.enable_hostagent_messenger ? 1 : 0
}

resource "juju_integration" "landscape_server_ubuntu_installer_attach_haproxy_route_lbaas" {
  model_uuid = var.model_uuid

  application {
    name     = module.landscape_server.app_name
    endpoint = "ubuntu-installer-attach-haproxy-route"
  }

  application {
    offer_url = var.haproxy_route_offer_url
  }

  depends_on = [module.landscape_server]

  count = var.haproxy_route_offer_url != null && local.has_haproxy_route && local.enable_ubuntu_installer ? 1 : 0
}

locals {
  has_modern_pg_interface    = can(module.landscape_server.requires.database)
  has_haproxy_route          = coalesce(module.landscape_server.has_haproxy_route_interface, false)
  enable_hostagent_messenger = try(var.landscape_server.config["enable_hostagent_messenger"], "false") == "true"
  enable_ubuntu_installer    = try(var.landscape_server.config["enable_ubuntu_installer_attach"], "false") == "true"
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

resource "juju_application" "haproxy_self_signed_certs" {
  name        = var.haproxy_self_signed_certs.app_name
  model_uuid  = var.model_uuid
  units       = 1
  constraints = var.haproxy_self_signed_certs.constraints

  charm {
    name     = "self-signed-certificates"
    revision = var.haproxy_self_signed_certs.revision
    channel  = var.haproxy_self_signed_certs.channel
    base     = var.haproxy_self_signed_certs.base
  }

  count = var.haproxy_self_signed_certs != null && var.haproxy != null && var.haproxy_route_offer_url == null ? 1 : 0
}

resource "juju_integration" "haproxy_certificates" {
  model_uuid = var.model_uuid

  application {
    name     = module.haproxy[0].app_name
    endpoint = "certificates"
  }

  application {
    name = juju_application.haproxy_self_signed_certs[0].name
  }

  depends_on = [module.haproxy, juju_application.haproxy_self_signed_certs]

  count = var.haproxy_self_signed_certs != null && var.haproxy != null && var.haproxy_route_offer_url == null ? 1 : 0
}

resource "juju_integration" "haproxy_receive_ca_certs" {
  model_uuid = var.model_uuid

  application {
    name     = module.haproxy[0].app_name
    endpoint = "receive-ca-certs"
  }

  application {
    name = juju_application.haproxy_self_signed_certs[0].name
  }

  depends_on = [module.haproxy, juju_application.haproxy_self_signed_certs]

  count = var.haproxy_self_signed_certs != null && var.haproxy != null && var.haproxy_route_offer_url == null ? 1 : 0
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
