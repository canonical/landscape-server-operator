# © 2025 Canonical Ltd.

run "setup_tests" {
  module {
    source = "./tests/setup"
  }
}

run "basic_deploy" {
  variables {
    model_uuid = run.setup_tests.model_uuid
    landscape_server = {
      channel = "latest/edge"
      # renovate: depName="landscape-server"
      revision = 143
    }
  }

  assert {
    condition     = output.applications.landscape_server.app_name == "landscape-server"
    error_message = "landscape-server app_name did not match expected"
  }
}
