# © 2025 Canonical Ltd.

mock_provider "juju" {}

run "modern_amqp_relations" {
  command = plan

  variables {
    model_uuid = uuid()
    channel    = "25.10/edge"
    revision   = 200
    base       = "ubuntu@24.04"
  }

  assert {
    condition     = output.requires.inbound_amqp == "inbound-amqp"
    error_message = "Modern revision should use inbound-amqp relation"
  }

  assert {
    condition     = output.requires.outbound_amqp == "outbound-amqp"
    error_message = "Modern revision should use outbound-amqp relation"
  }

  assert {
    condition     = !can(output.requires.amqp)
    error_message = "Modern revision should not have legacy amqp relation"
  }
}

run "legacy_amqp_relations_by_revision" {
  command = plan

  variables {
    model_uuid = uuid()
    channel    = "25.10/edge"
    revision   = 141
    base       = "ubuntu@22.04"
  }

  assert {
    condition     = output.requires.amqp == "amqp"
    error_message = "Revision 141 should use legacy amqp relation"
  }

  assert {
    condition     = !can(output.requires.inbound_amqp)
    error_message = "Legacy revision should not have inbound-amqp relation"
  }

  assert {
    condition     = !can(output.requires.outbound_amqp)
    error_message = "Legacy revision should not have outbound-amqp relation"
  }
}

run "modern_amqp_relations_null_revision" {
  command = plan

  variables {
    model_uuid = uuid()
    revision   = null
  }

  assert {
    condition     = !can(output.requires.amqp)
    error_message = "Null revision should not use legacy amqp relation"
  }

  assert {
    condition     = can(output.requires.inbound_amqp)
    error_message = "Null revision should have inbound-amqp relation"
  }

  assert {
    condition     = can(output.requires.outbound_amqp)
    error_message = "Null revision should have outbound-amqp relation"
  }
}

run "legacy_amqp_relations_by_channel" {
  command = plan

  variables {
    model_uuid = uuid()
    channel    = "latest/stable"
    revision   = 200
    base       = "ubuntu@22.04"
  }

  assert {
    condition     = output.requires.amqp == "amqp"
    error_message = "Legacy channel should use legacy amqp relation"
  }

  assert {
    condition     = !can(output.requires.inbound_amqp)
    error_message = "Legacy channel should not have inbound-amqp relation"
  }

  assert {
    condition     = !can(output.requires.outbound_amqp)
    error_message = "Legacy channel should not have outbound-amqp relation"
  }
}

run "provides_relations" {
  command = plan

  variables {
    model_uuid = uuid()
    channel    = "25.10/edge"
    revision   = 200
    base       = "ubuntu@24.04"
  }

  assert {
    condition     = output.provides.cos_agent == "cos-agent"
    error_message = "Should provide cos-agent relation"
  }

  assert {
    condition     = output.provides.data == "data"
    error_message = "Should provide data relation"
  }

  assert {
    condition     = output.provides.hosted == "hosted"
    error_message = "Should provide hosted relation"
  }

  assert {
    condition     = output.provides.nrpe_external_master == "nrpe-external-master"
    error_message = "Should provide nrpe-external-master relation"
  }

  assert {
    condition     = output.provides.website == "website"
    error_message = "Should provide website relation"
  }
}

run "application_dashboard_required" {
  command = plan

  variables {
    model_uuid = uuid()
    channel    = "latest/stable"
    revision   = 100
    base       = "ubuntu@22.04"
  }

  assert {
    condition     = output.requires.application_dashboard == "application-dashboard"
    error_message = "Should always require application-dashboard relation"
  }
}

run "amqp_threshold_edge_case" {
  command = plan

  variables {
    model_uuid = uuid()
    channel    = "25.10/edge"
    revision   = 142
    base       = "ubuntu@24.04"
  }

  assert {
    condition     = output.requires.inbound_amqp == "inbound-amqp"
    error_message = "Revision 142 should use modern amqp relations"
  }

  assert {
    condition     = output.requires.outbound_amqp == "outbound-amqp"
    error_message = "Revision 142 should use modern amqp relations"
  }
}

run "modern_postgres_relations" {
  command = plan

  variables {
    model_uuid = uuid()
    channel    = "25.10/edge"
    revision   = 213
    base       = "ubuntu@24.04"
  }

  assert {
    condition     = output.requires.database == "database"
    error_message = "Modern revision should have database relation"
  }

  assert {
    condition     = output.requires.db == "db"
    error_message = "Modern revision should have db relation"
  }
}

run "legacy_postgres_relations" {
  command = plan

  variables {
    model_uuid = uuid()
    channel    = "25.10/edge"
    revision   = 212
    base       = "ubuntu@24.04"
  }

  assert {
    condition     = output.requires.db == "db"
    error_message = "Legacy revision should have db relation"
  }

  assert {
    condition     = !can(output.requires.database)
    error_message = "Legacy revision should not have database relation"
  }
}

run "modern_postgres_relations_null_revision" {
  command = plan

  variables {
    model_uuid = uuid()
    revision   = null
  }

  assert {
    condition     = output.requires.database == "database"
    error_message = "Null revision should have database relation"
  }

  assert {
    condition     = output.requires.db == "db"
    error_message = "Null revision should have db relation"
  }
}

run "internal_haproxy_relations" {
  command = plan

  variables {
    model_uuid = uuid()
    channel    = "26.04/beta"
    revision   = 216
    base       = "ubuntu@24.04"
  }

  assert {
    condition     = output.requires.load_balancer_certificates == "load-balancer-certificates"
    error_message = "Rev 216+ should have load-balancer-certificates relation"
  }

  assert {
    condition     = output.requires.http_ingress == "http-ingress"
    error_message = "Rev 216+ should have http-ingress relation"
  }

  assert {
    condition     = output.requires.hostagent_messenger_ingress == "hostagent-messenger-ingress"
    error_message = "Rev 216+ should have hostagent-messenger-ingress relation"
  }

  assert {
    condition     = output.requires.ubuntu_installer_attach_ingress == "ubuntu-installer-attach-ingress"
    error_message = "Rev 216+ should have ubuntu-installer-attach-ingress relation"
  }

  assert {
    condition     = !can(output.requires.website)
    error_message = "Rev 216+ should not have legacy website relation"
  }
}

run "legacy_haproxy_relations" {
  command = plan

  variables {
    model_uuid = uuid()
    channel    = "25.10/edge"
    revision   = 215
    base       = "ubuntu@24.04"
  }

  assert {
    condition     = output.requires.website == "website"
    error_message = "Pre-216 should have legacy website relation"
  }

  assert {
    condition     = !can(output.requires.load_balancer_certificates)
    error_message = "Pre-216 should not have load-balancer-certificates relation"
  }

  assert {
    condition     = !can(output.requires.http_ingress)
    error_message = "Pre-216 should not have ingress relations"
  }
}

run "internal_haproxy_null_revision" {
  command = plan

  variables {
    model_uuid = uuid()
    revision   = null
  }

  assert {
    condition     = can(output.requires.load_balancer_certificates)
    error_message = "Null revision should have internal haproxy relations"
  }

  assert {
    condition     = !can(output.requires.website)
    error_message = "Null revision should not have legacy website relation"
  }
}
