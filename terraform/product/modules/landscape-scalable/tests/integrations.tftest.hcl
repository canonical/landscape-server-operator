# © 2025 Canonical Ltd.

mock_provider "juju" {}

variables {
  model_uuid = uuid()
  landscape_server = {
    revision = 150
  }
  haproxy         = {}
  postgresql      = {}
  rabbitmq_server = {}
}

run "test_local_has_modern_amqp_relations_true" {
  command = plan

  override_module {
    target = module.landscape_server
    outputs = {
      app_name = "landscape-server"
      requires = {
        inbound_amqp  = "inbound-amqp"
        outbound_amqp = "outbound-amqp"
        database      = "database"
        db            = "db"
      }
    }
  }

  assert {
    condition     = local.has_modern_amqp_relations == true
    error_message = "has_modern_amqp_relations should be true when both inbound_amqp and outbound_amqp exist"
  }

  assert {
    condition     = can(module.landscape_server.requires.inbound_amqp) && can(module.landscape_server.requires.outbound_amqp)
    error_message = "Both inbound_amqp and outbound_amqp should be accessible via can()"
  }
}

run "test_local_has_modern_amqp_relations_false" {
  command = plan

  override_module {
    target = module.landscape_server
    outputs = {
      app_name = "landscape-server"
      requires = {
        database = "database"
        db       = "db"
      }
    }
  }

  assert {
    condition     = local.has_modern_amqp_relations == false
    error_message = "`has_modern_amqp_relations` should be false when inbound_amqp or outbound_amqp don't exist"
  }

  assert {
    condition     = !can(module.landscape_server.requires.inbound_amqp) && !can(module.landscape_server.requires.outbound_amqp)
    error_message = "Neither inbound_amqp nor outbound_amqp should be accessible when has_modern_amqp_relations is false"
  }
}


run "test_modern_amqp_interfaces" {
  command = plan

  assert {
    condition = (
      local.has_modern_amqp_relations == true ?
      (
        length(juju_integration.landscape_server_inbound_amqp) == 1 &&
        length(juju_integration.landscape_server_outbound_amqp) == 1
      ) : true
    )
    error_message = "When has_modern_amqp_relations is true, both modern AMQP relations should be created"
  }

  assert {
    condition = (
      local.has_modern_amqp_relations == true ?
      length(juju_integration.landscape_server_rabbitmq_server) == 0 : true
    )
    error_message = "When has_modern_amqp_relations is true, legacy relation should not be created"
  }
}

run "test_legacy_amqp_interface" {
  command = plan

  assert {
    condition = (
      local.has_modern_amqp_relations == false ?
      length(juju_integration.landscape_server_rabbitmq_server) == 1 : true
    )
    error_message = "When has_modern_amqp_relations is false, legacy relation should be created"
  }

  assert {
    condition = (
      local.has_modern_amqp_relations == false ?
      (
        length(juju_integration.landscape_server_inbound_amqp) == 0 &&
        length(juju_integration.landscape_server_outbound_amqp) == 0
      ) : true
    )
    error_message = "When has_modern_amqp_relations is false, modern AMQP relations should not be created"
  }
}


run "validate_all_modules_created" {
  command = plan

  variables {
    landscape_server = {
      revision = 150
    }
  }

  override_module {
    target = module.landscape_server
    outputs = {
      app_name = "landscape-server"
      requires = {
        website               = "website"
        amqp                  = "amqp"
        db                    = "db"
        application_dashboard = "application-dashboard"
      }
    }
  }

  assert {
    condition     = module.landscape_server != null
    error_message = "Landscape server module should be created"
  }

  assert {
    condition     = length(module.haproxy) == 1
    error_message = "HAProxy module should be created for legacy deployments"
  }

  assert {
    condition     = module.postgresql != null
    error_message = "PostgreSQL module should be created"
  }

  assert {
    condition     = juju_application.rabbitmq_server != null
    error_message = "RabbitMQ application should be created"
  }
}

run "validate_all_integrations_created" {
  command = plan

  variables {
    landscape_server = {
      revision = 150
    }
  }

  override_module {
    target = module.landscape_server
    outputs = {
      app_name = "landscape-server"
      requires = {
        website               = "website"
        amqp                  = "amqp"
        db                    = "db"
        application_dashboard = "application-dashboard"
      }
    }
  }

  override_module {
    target = module.haproxy
    outputs = {
      app_name = "haproxy"
    }
  }

  assert {
    condition     = length(juju_integration.landscape_server_haproxy) == 1
    error_message = "Landscape-HAProxy integration should be created for legacy deployments"
  }

  assert {
    condition = (
      length(juju_integration.landscape_server_postgresql_legacy) > 0 ||
      length(juju_integration.landscape_server_postgresql_modern) > 0
    )
    error_message = "At least one Postgres integration pattern should be created (legacy or modern)"
  }

  assert {
    condition = (
      length(juju_integration.landscape_server_rabbitmq_server) > 0 ||
      (
        length(juju_integration.landscape_server_inbound_amqp) > 0 &&
        length(juju_integration.landscape_server_outbound_amqp) > 0
      )
    )
    error_message = "At least one AMQP integration pattern should be created (legacy single or modern combo)"
  }
}

run "test_modern_postgres_interfaces" {
  command = plan

  assert {
    condition = (
      local.has_modern_pg_interface == true ?
      length(juju_integration.landscape_server_postgresql_modern) == 1 : true
    )
    error_message = "When has_modern_pg_interface is true, modern Postgres integration should be created"
  }

  assert {
    condition = (
      local.has_modern_pg_interface == true ?
      length(juju_integration.landscape_server_postgresql_legacy) == 0 : true
    )
    error_message = "When has_modern_pg_interface is true, legacy Postgres integration should not be created"
  }
}

run "test_legacy_postgres_interface" {
  command = plan

  assert {
    condition = (
      local.has_modern_pg_interface == false ?
      length(juju_integration.landscape_server_postgresql_legacy) == 1 : true
    )
    error_message = "When has_modern_pg_interface is false, legacy Postgres integration should be created"
  }

  assert {
    condition = (
      local.has_modern_pg_interface == false ?
      length(juju_integration.landscape_server_postgresql_modern) == 0 : true
    )
    error_message = "When has_modern_pg_interface is false, modern Postgres integration should not be created"
  }
}

run "test_haproxy_route_integrations_created" {
  command = plan

  variables {
    landscape_server = {
      revision = 216
    }
    haproxy_route_offer_url = "admin/lbaas:haproxy-route"
  }

  override_module {
    target = module.landscape_server
    outputs = {
      app_name = "landscape-server"
      requires = {
        appserver_haproxy_route               = "appserver-haproxy-route"
        pingserver_haproxy_route              = "pingserver-haproxy-route"
        message_server_haproxy_route          = "message-server-haproxy-route"
        api_haproxy_route                     = "api-haproxy-route"
        package_upload_haproxy_route          = "package-upload-haproxy-route"
        hostagent_messenger_haproxy_route     = "hostagent-messenger-haproxy-route"
        ubuntu_installer_attach_haproxy_route = "ubuntu-installer-attach-haproxy-route"
        inbound_amqp                          = "inbound-amqp"
        outbound_amqp                         = "outbound-amqp"
        database                              = "database"
        db                                    = "db"
        application_dashboard                 = "application-dashboard"
      }
      has_haproxy_route_interface = true
    }
  }

  assert {
    condition     = length(juju_integration.landscape_server_appserver_haproxy_route_lbaas) == 1
    error_message = "appserver haproxy-route integration should be created"
  }

  assert {
    condition     = length(juju_integration.landscape_server_pingserver_haproxy_route_lbaas) == 1
    error_message = "pingserver haproxy-route integration should be created"
  }

  assert {
    condition     = length(juju_integration.landscape_server_message_server_haproxy_route_lbaas) == 1
    error_message = "message-server haproxy-route integration should be created"
  }

  assert {
    condition     = length(juju_integration.landscape_server_api_haproxy_route_lbaas) == 1
    error_message = "api haproxy-route integration should be created"
  }

  assert {
    condition     = length(juju_integration.landscape_server_package_upload_haproxy_route_lbaas) == 1
    error_message = "package-upload haproxy-route integration should be created"
  }

  assert {
    condition     = length(juju_integration.landscape_server_hostagent_messenger_haproxy_route_lbaas) == 1
    error_message = "hostagent-messenger haproxy-route integration should be created"
  }

  assert {
    condition     = length(juju_integration.landscape_server_ubuntu_installer_attach_haproxy_route_lbaas) == 1
    error_message = "ubuntu-installer-attach haproxy-route integration should be created"
  }

  assert {
    condition     = length(module.haproxy) == 0
    error_message = "Legacy HAProxy module should not be deployed when using haproxy-route"
  }
}

run "test_haproxy_route_integrations_skipped" {
  command = plan

  variables {
    landscape_server = {
      revision = 216
    }
    haproxy_route_offer_url = null
  }

  assert {
    condition     = length(juju_integration.landscape_server_appserver_haproxy_route_lbaas) == 0
    error_message = "haproxy-route integrations should not be created when offer_url is null"
  }
}

run "test_pgbouncer_integration" {
  command = plan

  variables {
    pgbouncer = {}
  }

  override_module {
    target = module.landscape_server
    outputs = {
      app_name = "landscape-server"
      requires = {
        inbound_amqp  = "inbound-amqp"
        outbound_amqp = "outbound-amqp"
        database      = "database"
        db            = "db"
      }
    }
  }

  assert {
    condition     = length(juju_application.pgbouncer) == 1
    error_message = "PgBouncer application should be deployed when pgbouncer is set"
  }

  assert {
    condition     = length(juju_integration.landscape_server_pgbouncer) == 1
    error_message = "landscape-server → pgbouncer integration should be created"
  }

  assert {
    condition     = length(juju_integration.pgbouncer_postgresql) == 1
    error_message = "pgbouncer → postgresql backend-database integration should be created"
  }

  assert {
    condition     = length(juju_integration.landscape_server_postgresql_modern) == 0
    error_message = "Direct landscape-server → postgresql integration should not be created when pgbouncer is deployed"
  }
}

run "test_pgbouncer_skipped" {
  command = plan

  variables {
    pgbouncer = null
  }

  override_module {
    target = module.landscape_server
    outputs = {
      app_name = "landscape-server"
      requires = {
        inbound_amqp  = "inbound-amqp"
        outbound_amqp = "outbound-amqp"
        database      = "database"
        db            = "db"
      }
    }
  }

  assert {
    condition     = length(juju_application.pgbouncer) == 0
    error_message = "PgBouncer application should not be deployed when pgbouncer is null"
  }

  assert {
    condition     = length(juju_integration.landscape_server_pgbouncer) == 0
    error_message = "landscape-server → pgbouncer integration should not be created when pgbouncer is null"
  }

  assert {
    condition     = length(juju_integration.pgbouncer_postgresql) == 0
    error_message = "pgbouncer → postgresql integration should not be created when pgbouncer is null"
  }

  assert {
    condition     = length(juju_integration.landscape_server_postgresql_modern) == 1
    error_message = "Direct landscape-server → postgresql integration should be created when pgbouncer is null"
  }
}
