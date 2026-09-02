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

run "debug" {
  command = plan

  variables {
    landscape_server = {
      revision = 278
    }
  }

  assert {
    condition     = var.postgresql != null
    error_message = "postgresql is null!"
  }

  assert {
    condition     = var.pgbouncer == null
    error_message = "pgbouncer is not null!"
  }

  assert {
    condition     = local.has_modern_pg_interface
    error_message = "has_modern_pg_interface is false!"
  }
}
