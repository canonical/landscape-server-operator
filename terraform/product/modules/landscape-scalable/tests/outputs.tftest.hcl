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

run "validate_output_structure" {
  command = apply

  variables {
    landscape_server = {
      revision = 150
    }
  }

  override_module {
    target = module.landscape_server
    outputs = {
      app_name                     = "landscape-server"
      has_modern_haproxy_interface = false
      provides = {
        website = "website"
      }
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
      requires = {
        reverseproxy     = "reverseproxy"
        certificates     = "certificates"
        receive_ca_certs = "receive-ca-certs"
      }
    }
  }

  assert {
    condition     = output.applications != null
    error_message = "Applications output should exist"
  }

  assert {
    condition     = can(output.applications.landscape_server)
    error_message = "Applications output should include landscape_server"
  }

  assert {
    condition     = can(output.applications.haproxy)
    error_message = "Applications output should include haproxy key (may be null)"
  }

  assert {
    condition     = can(output.applications.postgresql)
    error_message = "Applications output should include postgresql"
  }

  assert {
    condition     = can(output.applications.rabbitmq_server)
    error_message = "Applications output should include rabbitmq_server"
  }

  assert {
    condition     = can(output.applications.pgbouncer)
    error_message = "Applications output should include pgbouncer key (may be null)"
  }

  assert {
    condition     = can(output.applications.landscape_debarchive)
    error_message = "Applications output should include landscape_debarchive key (may be null)"
  }

  assert {
    condition     = can(output.applications.landscape_task_handler)
    error_message = "Applications output should include landscape_task_handler key (may be null)"
  }
}

run "validate_has_modern_amqp_relations_output" {
  command = plan

  assert {
    condition     = output.has_modern_amqp_relations != null
    error_message = "has_modern_amqp_relations output should exist"
  }

  assert {
    condition     = output.has_modern_amqp_relations == local.has_modern_amqp_relations
    error_message = "has_modern_amqp_relations output should match the local value"
  }
}


run "validate_optional_outputs" {
  command = plan

  assert {
    condition     = can(output.registration_key) || output.registration_key == null
    error_message = "registration_key output should be accessible (nullable)"
  }

  assert {
    condition     = can(output.admin_email) || output.admin_email == null
    error_message = "admin_email output should be accessible (nullable)"
  }

  assert {
    condition     = can(output.admin_password) || output.admin_password == null
    error_message = "admin_password output should be accessible (nullable)"
  }
}

run "validate_outputs_with_config" {
  command = plan

  variables {
    landscape_server = {
      revision = 150
      config = {
        registration_key = "test-key-12345"
        admin_email      = "admin@example.com"
        admin_password   = "secure-password"
      }
    }
  }

  assert {
    condition     = output.registration_key == "test-key-12345"
    error_message = "registration_key output should match configured value"
  }

  assert {
    condition     = output.admin_email == "admin@example.com"
    error_message = "admin_email output should match configured value"
  }

  assert {
    condition     = output.admin_password == "secure-password"
    error_message = "admin_password output should match configured value"
  }
}
