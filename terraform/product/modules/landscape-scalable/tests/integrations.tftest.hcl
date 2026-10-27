# © 2025 Canonical Ltd.

mock_provider "juju" {
  mock_data "juju_charm" {
    defaults = {
      revision = 625
    }
  }
}

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

  variables {
    landscape_server = {
      channel = "24.04/stable"
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

  variables {
    landscape_server = {
      channel = "24.04/stable"
    }
  }

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

  variables {
    landscape_server = {
      revision = 278
    }
    # Explicit null: terraform ~1.10 (CI) coerces null-defaulted object
    # variables to their defaults instead of preserving null
    pgbouncer = null
  }

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
      revision = 278
      config = {
        enable_hostagent_messenger     = "true"
        enable_ubuntu_installer_attach = "true"
      }
    }
    haproxy_route_offer_url     = "admin/lbaas.haproxy-route"
    haproxy_route_tcp_offer_url = "admin/lbaas.haproxy-route-tcp"
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
    error_message = "hostagent-messenger haproxy-route-tcp integration should be created before HTTPS support"
  }

  assert {
    condition     = length(juju_integration.landscape_server_hostagent_messenger_haproxy_route_https_lbaas) == 0
    error_message = "hostagent-messenger haproxy-route integration should not be created before HTTPS support"
  }

  assert {
    condition     = length(juju_integration.landscape_server_ubuntu_installer_attach_haproxy_route_tcp_lbaas) == 1
    error_message = "ubuntu-installer-attach haproxy-route-tcp integration should be created before HTTPS support"
  }

  assert {
    condition     = length(juju_integration.landscape_server_ubuntu_installer_attach_haproxy_route_lbaas) == 0
    error_message = "ubuntu-installer-attach haproxy-route integration should not be created before HTTPS support"
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
    landscape_server = {
      revision = 278
    }
    pgbouncer = {}
  }


  assert {
    condition     = length(juju_application.pgbouncer_server) == 1
    error_message = "PgBouncer application should be deployed when pgbouncer is set"
  }

  assert {
    condition     = length(juju_integration.landscape_server_pgbouncer) == 1
    error_message = "landscape-server → pgbouncer integration should be created"
  }

  assert {
    condition     = length(juju_integration.pgbouncer_server_postgresql) == 1
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
    landscape_server = {
      revision = 278
    }
    pgbouncer = null
  }


  assert {
    condition     = length(juju_application.pgbouncer_server) == 0
    error_message = "PgBouncer application should not be deployed when pgbouncer is null"
  }

  assert {
    condition     = length(juju_integration.landscape_server_pgbouncer) == 0
    error_message = "landscape-server → pgbouncer integration should not be created when pgbouncer is null"
  }

  assert {
    condition     = length(juju_integration.pgbouncer_server_postgresql) == 0
    error_message = "pgbouncer → postgresql integration should not be created when pgbouncer is null"
  }

  assert {
    condition     = length(juju_integration.landscape_server_postgresql_modern) == 1
    error_message = "Direct landscape-server → postgresql integration should be created when pgbouncer is null"
  }
}

run "test_legacy_haproxy_reverseproxy_created" {
  command = plan

  variables {
    haproxy = {}
  }



  assert {
    condition     = length(juju_integration.landscape_server_haproxy) == 1
    error_message = "Legacy reverseproxy integration should be created for legacy charm"
  }

  assert {
    condition     = length(juju_integration.landscape_server_appserver_haproxy_route_in_model) == 0
    error_message = "Modern haproxy-route integrations should not be created for legacy charm"
  }

  assert {
    condition     = length(juju_integration.landscape_server_pingserver_haproxy_route_in_model) == 0
    error_message = "Modern haproxy-route integrations should not be created for legacy charm"
  }
}

run "test_modern_haproxy_reverseproxy_not_created" {
  command = plan

  variables {
    landscape_server = {
      revision = 278
    }
    haproxy = {}
  }



  assert {
    condition     = length(juju_integration.landscape_server_haproxy) == 0
    error_message = "Legacy reverseproxy integration should not be created for modern charm"
  }

  assert {
    condition     = length(juju_integration.landscape_server_appserver_haproxy_route_in_model) == 1
    error_message = "Modern haproxy-route integration should be created for modern charm"
  }
}

run "test_legacy_haproxy_skipped_when_null" {
  command = plan

  variables {
    haproxy = null
  }


  assert {
    condition     = length(juju_integration.landscape_server_haproxy) == 0
    error_message = "No haproxy integration should be created when haproxy is null"
  }
}

run "test_other_landscape_charms_created" {
  command = plan

  variables {
    landscape_server = {
      # rev 447: first revision with both the debarchive (added at 357) and
      # task-handler (added at 447) relations
      revision = 447
    }
    landscape_debarchive   = {}
    landscape_task_handler = {}
    haproxy                = {}
  }



  assert {
    condition     = length(juju_application.landscape_debarchive) == 1
    error_message = "landscape-debarchive application should be deployed when set"
  }

  assert {
    condition     = length(juju_application.landscape_task_handler) == 1
    error_message = "landscape-task-handler application should be deployed when set"
  }

  assert {
    condition     = length(juju_integration.landscape_debarchive_landscape_server) == 1
    error_message = "debarchive → landscape-server integration should be created"
  }

  assert {
    condition     = length(juju_integration.landscape_debarchive_postgresql) == 1
    error_message = "debarchive → postgresql integration should be created"
  }

  assert {
    condition     = length(juju_integration.landscape_debarchive_haproxy_route_in_model) == 1
    error_message = "debarchive → haproxy route (in-model) should be created"
  }

  assert {
    condition     = length(juju_integration.landscape_task_handler_landscape_server) == 1
    error_message = "task-handler → landscape-server integration should be created"
  }

  assert {
    condition     = length(juju_integration.landscape_task_handler_postgresql) == 1
    error_message = "task-handler → postgresql task-db integration should be created"
  }

  assert {
    condition     = length(juju_integration.landscape_task_handler_certificates) == 1
    error_message = "task-handler → tls-certificates integration should be created"
  }

  assert {
    condition     = length(juju_integration.landscape_task_handler_grpc_haproxy_route_in_model) == 1
    error_message = "task-handler → haproxy grpc route (in-model) should be created"
  }

  assert {
    condition     = length(juju_application.tls_certificates) == 1
    error_message = "tls-certificates should be deployed to satisfy task-handler certs"
  }
}

run "test_debarchive_created_task_handler_skipped_between_thresholds" {
  command = plan

  variables {
    landscape_server = {
      # rev 400: debarchive relation exists (added at 357) but the
      # task-handler relation does not yet (added at 447)
      revision = 400
    }
    landscape_debarchive   = {}
    landscape_task_handler = {}
    haproxy                = {}
  }

  assert {
    condition     = length(juju_application.landscape_debarchive) == 1
    error_message = "landscape-debarchive should be deployed once its relation exists, independent of task-handler"
  }

  assert {
    condition     = length(juju_application.landscape_task_handler) == 0
    error_message = "landscape-task-handler should not be deployed before its relation exists, even if debarchive's does"
  }

  assert {
    condition     = length(juju_integration.landscape_debarchive_landscape_server) == 1
    error_message = "debarchive → landscape-server integration should be created"
  }

  assert {
    condition     = length(juju_integration.landscape_task_handler_landscape_server) == 0
    error_message = "task-handler → landscape-server integration should not be created"
  }

  assert {
    condition     = length(juju_integration.landscape_task_handler_certificates) == 0
    error_message = "task-handler → tls-certificates integration should not be created since task-handler is not deployed"
  }
}

run "test_other_landscape_charms_skipped_for_legacy_revision" {
  command = plan

  variables {
    landscape_server = {
      revision = 216
    }
    landscape_debarchive   = {}
    landscape_task_handler = {}
    haproxy                = {}
  }

  assert {
    condition     = length(juju_application.landscape_debarchive) == 0
    error_message = "landscape-debarchive should not be deployed when landscape-server revision predates the debarchive relation"
  }

  assert {
    condition     = length(juju_application.landscape_task_handler) == 0
    error_message = "landscape-task-handler should not be deployed when landscape-server revision predates the task-handler relation"
  }

  assert {
    condition     = length(juju_integration.landscape_debarchive_landscape_server) == 0
    error_message = "debarchive → landscape-server integration should not be created for legacy revisions"
  }

  assert {
    condition     = length(juju_integration.landscape_task_handler_landscape_server) == 0
    error_message = "task-handler → landscape-server integration should not be created for legacy revisions"
  }
}

run "test_other_landscape_charms_skipped" {
  command = plan

  variables {
    landscape_debarchive   = null
    landscape_task_handler = null
  }

  assert {
    condition     = length(juju_application.landscape_debarchive) == 0
    error_message = "landscape-debarchive should not be deployed when null"
  }

  assert {
    condition     = length(juju_application.landscape_task_handler) == 0
    error_message = "landscape-task-handler should not be deployed when null"
  }

  assert {
    condition     = length(juju_integration.landscape_debarchive_postgresql) == 0
    error_message = "debarchive postgresql integration should not be created when null"
  }

  assert {
    condition     = length(juju_integration.landscape_task_handler_certificates) == 0
    error_message = "task-handler certificates integration should not be created when null"
  }
}

run "test_installer_attach_https_cross_model" {
  command = plan

  variables {
    landscape_server = {
      channel = "26.10/stable"
      config = {
        enable_ubuntu_installer_attach = "true"
      }
    }
    haproxy_route_offer_url     = "admin/lbaas.haproxy-route"
    haproxy_route_tcp_offer_url = "admin/lbaas.haproxy-route-tcp"
  }

  assert {
    condition     = length(juju_integration.landscape_server_ubuntu_installer_attach_haproxy_route_lbaas) == 1
    error_message = "ubuntu-installer-attach haproxy-route integration should be created"
  }

  assert {
    condition     = length(juju_integration.landscape_server_ubuntu_installer_attach_haproxy_route_tcp_lbaas) == 0
    error_message = "ubuntu-installer-attach haproxy-route-tcp integration should not be created"
  }

  assert {
    condition     = length(juju_application.tls_certificates) == 1 && length(juju_integration.landscape_server_grpc_certificates) == 1
    error_message = "A certificate provider should be deployed and related to landscape-server"
  }

  assert {
    condition     = length(juju_offer.tls_certificates_send_ca_cert) == 1
    error_message = "The CA should be offered so the cross-model haproxy can trust the gRPC backends"
  }
}

run "test_installer_attach_without_certificate_provider_has_no_route" {
  command = plan

  variables {
    landscape_server = {
      channel = "26.10/stable"
      config = {
        enable_ubuntu_installer_attach = "true"
      }
    }
    tls_certificates            = null
    haproxy_route_offer_url     = "admin/lbaas.haproxy-route"
    haproxy_route_tcp_offer_url = "admin/lbaas.haproxy-route-tcp"
  }

  assert {
    condition     = length(juju_integration.landscape_server_ubuntu_installer_attach_haproxy_route_lbaas) == 0
    error_message = "ubuntu-installer-attach HTTPS route needs a certificate provider"
  }

  assert {
    condition     = length(juju_integration.landscape_server_ubuntu_installer_attach_haproxy_route_tcp_lbaas) == 0
    error_message = "ubuntu-installer-attach modern charm must not use haproxy-route-tcp"
  }

  assert {
    condition     = length(juju_offer.tls_certificates_send_ca_cert) == 0
    error_message = "The CA should not be offered without a certificate provider"
  }
}

run "test_hostagent_messenger_https_cross_model" {
  command = plan

  variables {
    landscape_server = {
      channel = "26.10/stable"
      config = {
        enable_hostagent_messenger = "true"
      }
    }
    haproxy_route_offer_url     = "admin/lbaas.haproxy-route"
    haproxy_route_tcp_offer_url = "admin/lbaas.haproxy-route-tcp"
  }

  assert {
    condition     = length(juju_integration.landscape_server_hostagent_messenger_haproxy_route_https_lbaas) == 1
    error_message = "hostagent-messenger haproxy-route integration should be created"
  }

  assert {
    condition     = length(juju_integration.landscape_server_hostagent_messenger_haproxy_route_lbaas) == 0
    error_message = "hostagent-messenger haproxy-route-tcp integration should not be created"
  }

  assert {
    condition     = length(juju_application.tls_certificates) == 1 && length(juju_integration.landscape_server_grpc_certificates) == 1
    error_message = "A certificate provider should be deployed and related to landscape-server"
  }

  assert {
    condition     = length(juju_offer.tls_certificates_send_ca_cert) == 1
    error_message = "The CA should be offered so the cross-model haproxy can trust the gRPC backends"
  }
}

run "test_hostagent_messenger_without_certificate_provider" {
  command = plan

  variables {
    landscape_server = {
      channel = "26.10/stable"
      config = {
        enable_hostagent_messenger = "true"
      }
    }
    tls_certificates            = null
    haproxy_route_offer_url     = "admin/lbaas.haproxy-route"
    haproxy_route_tcp_offer_url = "admin/lbaas.haproxy-route-tcp"
  }

  assert {
    condition     = length(juju_integration.landscape_server_hostagent_messenger_haproxy_route_https_lbaas) == 0
    error_message = "hostagent-messenger HTTPS route needs a certificate provider"
  }

  assert {
    condition     = length(juju_integration.landscape_server_hostagent_messenger_haproxy_route_lbaas) == 0
    error_message = "hostagent-messenger must not use haproxy-route-tcp on charms with HTTPS support"
  }

  assert {
    condition     = length(juju_offer.tls_certificates_send_ca_cert) == 0
    error_message = "The CA should not be offered without a certificate provider"
  }
}

run "test_hostagent_messenger_before_rev_599_uses_tcp" {
  command = plan

  variables {
    landscape_server = {
      channel  = "26.04/stable"
      revision = 598
      config = {
        enable_hostagent_messenger     = "true"
        enable_ubuntu_installer_attach = "true"
      }
    }
    haproxy_route_offer_url     = "admin/lbaas.haproxy-route"
    haproxy_route_tcp_offer_url = "admin/lbaas.haproxy-route-tcp"
  }

  assert {
    condition     = length(juju_integration.landscape_server_hostagent_messenger_haproxy_route_https_lbaas) == 0 && length(juju_integration.landscape_server_hostagent_messenger_haproxy_route_lbaas) == 1
    error_message = "Revisions before 599 route hostagent-messenger over haproxy-route-tcp"
  }

  assert {
    condition     = length(juju_integration.landscape_server_ubuntu_installer_attach_haproxy_route_lbaas) == 1 && length(juju_integration.landscape_server_ubuntu_installer_attach_haproxy_route_tcp_lbaas) == 0
    error_message = "Revisions from 595 route ubuntu-installer-attach over HTTPS"
  }
}

run "test_grpc_routes_on_26_04_from_rev_599_use_https" {
  command = plan

  variables {
    landscape_server = {
      channel  = "26.04/stable"
      revision = 599
      config = {
        enable_hostagent_messenger     = "true"
        enable_ubuntu_installer_attach = "true"
      }
    }
    haproxy_route_offer_url     = "admin/lbaas.haproxy-route"
    haproxy_route_tcp_offer_url = "admin/lbaas.haproxy-route-tcp"
  }

  assert {
    condition     = length(juju_integration.landscape_server_hostagent_messenger_haproxy_route_https_lbaas) == 1 && length(juju_integration.landscape_server_hostagent_messenger_haproxy_route_lbaas) == 0
    error_message = "Revisions from 599 route hostagent-messenger over HTTPS, including on 26.04"
  }

  assert {
    condition     = length(juju_integration.landscape_server_ubuntu_installer_attach_haproxy_route_lbaas) == 1 && length(juju_integration.landscape_server_ubuntu_installer_attach_haproxy_route_tcp_lbaas) == 0
    error_message = "Revisions from 595 route ubuntu-installer-attach over HTTPS, including on 26.04"
  }

  assert {
    condition     = length(juju_integration.landscape_server_grpc_certificates) == 1
    error_message = "landscape-server should relate to the certificate provider"
  }
}

run "test_unpinned_26_04_grpc_routes_in_model_use_tcp" {
  command = plan

  variables {
    landscape_server = {
      channel = "26.04/stable"
      config = {
        enable_hostagent_messenger     = "true"
        enable_ubuntu_installer_attach = "true"
      }
    }
  }

  override_data {
    target = module.landscape_server.data.juju_charm.landscape_server[0]
    values = {
      revision = 529
    }
  }

  assert {
    condition = (
      length(juju_integration.landscape_server_grpc_certificates) == 0 &&
      length(juju_integration.landscape_server_hostagent_messenger_haproxy_route_https_in_model) == 0 &&
      length(juju_integration.landscape_server_ubuntu_installer_attach_haproxy_route_in_model) == 0
    )
    error_message = "Unpinned 26.04/stable at revision 529 must not create Landscape certificates or gRPC HTTPS integrations"
  }

  assert {
    condition = (
      length(juju_integration.landscape_server_hostagent_messenger_haproxy_route_in_model) == 1 &&
      length(juju_integration.landscape_server_ubuntu_installer_attach_haproxy_route_tcp_in_model) == 1 &&
      length(juju_integration.landscape_server_appserver_haproxy_route_in_model) == 1
    )
    error_message = "Unpinned 26.04/stable must retain TCP gRPC routes and the existing appserver HTTP route"
  }
}

run "test_unpinned_26_04_grpc_routes_cross_model_use_tcp" {
  command = plan

  variables {
    landscape_server = {
      channel = "26.04/stable"
      config = {
        enable_hostagent_messenger     = "true"
        enable_ubuntu_installer_attach = "true"
      }
    }
    haproxy_route_offer_url     = "admin/lbaas.haproxy-route"
    haproxy_route_tcp_offer_url = "admin/lbaas.haproxy-route-tcp"
  }

  override_data {
    target = module.landscape_server.data.juju_charm.landscape_server[0]
    values = {
      revision = 529
    }
  }

  assert {
    condition = (
      length(juju_integration.landscape_server_grpc_certificates) == 0 &&
      length(juju_integration.landscape_server_hostagent_messenger_haproxy_route_https_lbaas) == 0 &&
      length(juju_integration.landscape_server_ubuntu_installer_attach_haproxy_route_lbaas) == 0 &&
      length(juju_offer.tls_certificates_send_ca_cert) == 0
    )
    error_message = "Unpinned 26.04/stable must not create gRPC HTTPS integrations or offer a gRPC CA"
  }

  assert {
    condition = (
      length(juju_integration.landscape_server_hostagent_messenger_haproxy_route_lbaas) == 1 &&
      length(juju_integration.landscape_server_ubuntu_installer_attach_haproxy_route_tcp_lbaas) == 1 &&
      length(juju_integration.landscape_server_appserver_haproxy_route_lbaas) == 1
    )
    error_message = "Unpinned 26.04/stable must use the cross-model TCP offer for gRPC and keep the appserver HTTP route"
  }
}

run "test_grpc_routes_in_model_do_not_offer_ca" {
  command = plan

  variables {
    landscape_server = {
      channel = "26.10/stable"
      config = {
        enable_hostagent_messenger     = "true"
        enable_ubuntu_installer_attach = "true"
      }
    }
  }

  assert {
    condition     = length(juju_integration.landscape_server_grpc_certificates) == 1 && length(juju_integration.haproxy_receive_ca_certs) == 1
    error_message = "The in-model haproxy should receive the CA that issues the gRPC backends' certificates"
  }

  assert {
    condition     = length(juju_offer.tls_certificates_send_ca_cert) == 0
    error_message = "The CA should not be offered when haproxy is in the same model"
  }
}
