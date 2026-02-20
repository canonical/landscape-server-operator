# © 2025 Canonical Ltd.

mock_provider "juju" {}

variables {
  model = "test-landscape"
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

run "test_internal_haproxy_true" {
  command = plan

  variables {
    landscape_server = {
      revision = 216
    }
    http_ingress                    = {}
    hostagent_messenger_ingress     = {}
    ubuntu_installer_attach_ingress = {}
    lb_certs                        = {}
  }

  override_module {
    target = module.landscape_server
    outputs = {
      app_name = "landscape-server"
      requires = {
        load_balancer_certificates      = "load-balancer-certificates"
        http_ingress                    = "http-ingress"
        hostagent_messenger_ingress     = "hostagent-messenger-ingress"
        ubuntu_installer_attach_ingress = "ubuntu-installer-attach-ingress"
        inbound_amqp                    = "inbound-amqp"
        outbound_amqp                   = "outbound-amqp"
        database                        = "database"
        db                              = "db"
        application_dashboard           = "application-dashboard"
      }
    }
  }

  assert {
    condition     = local.has_internal_haproxy == true
    error_message = "has_internal_haproxy should be true when load_balancer_certificates exists"
  }

  assert {
    condition     = length(module.haproxy) == 0
    error_message = "Legacy HAProxy module should not be deployed with internal haproxy"
  }

  assert {
    condition     = length(juju_application.http_ingress) == 1
    error_message = "HTTP ingress configurator should be deployed"
  }

  assert {
    condition     = length(juju_application.hostagent_messenger_ingress) == 1
    error_message = "Hostagent messenger ingress configurator should be deployed"
  }

  assert {
    condition     = length(juju_application.ubuntu_installer_attach_ingress) == 1
    error_message = "Ubuntu installer attach ingress configurator should be deployed"
  }

  assert {
    condition     = length(juju_integration.landscape_server_haproxy) == 0
    error_message = "Legacy HAProxy integration should not be created with internal haproxy"
  }

  assert {
    condition     = length(juju_integration.landscape_server_http_ingress) == 1
    error_message = "HTTP ingress integration should be created"
  }

  assert {
    condition     = length(juju_integration.landscape_server_hostagent_messenger_ingress) == 1
    error_message = "Hostagent messenger ingress integration should be created"
  }

  assert {
    condition     = length(juju_integration.landscape_server_ubuntu_installer_attach_ingress) == 1
    error_message = "Ubuntu installer attach ingress integration should be created"
  }
}

run "test_internal_haproxy_false" {
  command = plan

  variables {
    landscape_server = {
      revision = 215
    }
  }

  override_module {
    target = module.landscape_server
    outputs = {
      app_name = "landscape-server"
      requires = {
        website               = "website"
        inbound_amqp          = "inbound-amqp"
        outbound_amqp         = "outbound-amqp"
        database              = "database"
        db                    = "db"
        application_dashboard = "application-dashboard"
      }
    }
  }

  assert {
    condition     = local.has_internal_haproxy == false
    error_message = "has_internal_haproxy should be false when load_balancer_certificates doesn't exist"
  }

  assert {
    condition     = length(module.haproxy) == 1
    error_message = "Legacy HAProxy module should be deployed without internal haproxy"
  }

  assert {
    condition     = length(juju_application.http_ingress) == 0
    error_message = "Ingress configurators should not be deployed without internal haproxy"
  }

  assert {
    condition     = length(juju_integration.landscape_server_haproxy) == 1
    error_message = "Legacy HAProxy integration should be created without internal haproxy"
  }

  assert {
    condition     = length(juju_integration.landscape_server_http_ingress) == 0
    error_message = "Ingress integrations should not be created without internal haproxy"
  }
}

run "test_tls_certificates_integration" {
  command = plan

  variables {
    landscape_server = {
      revision = 216
    }
    lb_certs = {}
  }

  override_module {
    target = module.landscape_server
    outputs = {
      app_name = "landscape-server"
      requires = {
        load_balancer_certificates      = "load-balancer-certificates"
        http_ingress                    = "http-ingress"
        hostagent_messenger_ingress     = "hostagent-messenger-ingress"
        ubuntu_installer_attach_ingress = "ubuntu-installer-attach-ingress"
        inbound_amqp                    = "inbound-amqp"
        outbound_amqp                   = "outbound-amqp"
        database                        = "database"
        db                              = "db"
        application_dashboard           = "application-dashboard"
      }
    }
  }

  assert {
    condition     = length(juju_application.lb_certs) == 1
    error_message = "lb_certs application should be deployed"
  }

  assert {
    condition     = length(juju_integration.landscape_server_tls_certificates) == 1
    error_message = "TLS certificates integration should be created when lb_certs is specified"
  }
}

run "test_tls_certificates_integration_skipped" {
  command = plan

  variables {
    landscape_server = {
      revision = 216
    }
    lb_certs = null
  }

  override_module {
    target = module.landscape_server
    outputs = {
      app_name = "landscape-server"
      requires = {
        load_balancer_certificates      = "load-balancer-certificates"
        http_ingress                    = "http-ingress"
        hostagent_messenger_ingress     = "hostagent-messenger-ingress"
        ubuntu_installer_attach_ingress = "ubuntu-installer-attach-ingress"
        inbound_amqp                    = "inbound-amqp"
        outbound_amqp                   = "outbound-amqp"
        database                        = "database"
        db                              = "db"
        application_dashboard           = "application-dashboard"
      }
    }
  }

  assert {
    condition     = length(juju_application.lb_certs) == 0
    error_message = "lb_certs application should not be deployed when set to null"
  }

  assert {
    condition     = length(juju_integration.landscape_server_tls_certificates) == 0
    error_message = "TLS certificates integration should not be created when lb_certs is null"
  }
}
