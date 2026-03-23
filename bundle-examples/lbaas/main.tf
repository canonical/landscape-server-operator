data "juju_model" "landscape_model" {
  name = var.model_name
}

resource "terraform_data" "wait_for_landscape" {
  provisioner "local-exec" {
    command = <<-EOT
      juju wait-for model $MODEL_NAME --timeout 3600s --query='forEach(units, unit => unit.workload-status == "active")'
      EOT
    environment = {
      MODEL_NAME = var.model_name
    }
  }
}

locals {
  ssh_key_files   = fileset(pathexpand("~/.ssh"), "*.pub")
  ssh_key_path    = length(local.ssh_key_files) > 0 ? pathexpand("~/.ssh/${sort(local.ssh_key_files)[0]}") : null
  ssh_key_content = local.ssh_key_path != null ? trimspace(file(local.ssh_key_path)) : null
}

resource "terraform_data" "check_ssh_key" {
  lifecycle {
    precondition {
      condition     = local.ssh_key_path != null
      error_message = "No SSH public key found in ~/.ssh/. Please generate one with: ssh-keygen -t ed25519"
    }
  }
}

resource "juju_model" "lbaas_model" {
  name = var.lbaas_model_name
}

resource "juju_ssh_key" "lbaas_ssh_key" {
  model   = juju_model.lbaas_model.name
  payload = local.ssh_key_content
}


resource "juju_application" "haproxy" {
  model = juju_model.lbaas_model.name
  name  = "haproxy"

  charm {
    name    = "haproxy"
    channel = "2.8/edge"
  }

  units = 1
}

resource "juju_application" "self_signed_certificates" {
  model = juju_model.lbaas_model.name
  name  = "self-signed-certificates"

  charm {
    name    = "self-signed-certificates"
    channel = "1/stable"
  }

  units = 1
}

resource "juju_integration" "haproxy_certs" {
  model = juju_model.lbaas_model.name

  application {
    name     = juju_application.haproxy.name
    endpoint = "certificates"
  }

  application {
    name     = juju_application.self_signed_certificates.name
    endpoint = "certificates"
  }
}

resource "juju_integration" "haproxy_receive_ca_certs" {
  model = juju_model.lbaas_model.name

  application {
    name     = juju_application.haproxy.name
    endpoint = "receive-ca-certs"
  }

  application {
    name     = juju_application.self_signed_certificates.name
    endpoint = "send-ca-cert"
  }
}

resource "juju_offer" "haproxy_route" {
  model            = juju_model.lbaas_model.name
  application_name = juju_application.haproxy.name
  endpoint         = "haproxy-route"
}

data "juju_offer" "haproxy_route" {
  url = juju_offer.haproxy_route.url
}

resource "juju_integration" "pingserver_haproxy_route" {
  model = data.juju_model.landscape_model.name

  application {
    offer_url = data.juju_offer.haproxy_route.url
  }

  application {
    name     = "landscape-server"
    endpoint = "pingserver-haproxy-route"
  }
}

resource "juju_integration" "message_server_haproxy_route" {
  model = data.juju_model.landscape_model.name

  application {
    offer_url = data.juju_offer.haproxy_route.url
  }

  application {
    name     = "landscape-server"
    endpoint = "message-server-haproxy-route"
  }
}

resource "juju_integration" "api_haproxy_route" {
  model = data.juju_model.landscape_model.name

  application {
    offer_url = data.juju_offer.haproxy_route.url
  }

  application {
    name     = "landscape-server"
    endpoint = "api-haproxy-route"
  }
}

resource "juju_integration" "package_upload_haproxy_route" {
  model = data.juju_model.landscape_model.name

  application {
    offer_url = data.juju_offer.haproxy_route.url
  }

  application {
    name     = "landscape-server"
    endpoint = "package-upload-haproxy-route"
  }
}

resource "juju_integration" "repository_haproxy_route" {
  model = data.juju_model.landscape_model.name

  application {
    offer_url = data.juju_offer.haproxy_route.url
  }

  application {
    name     = "landscape-server"
    endpoint = "repository-haproxy-route"
  }
}

resource "juju_integration" "hostagent_messenger_haproxy_route" {
  model = data.juju_model.landscape_model.name

  application {
    offer_url = data.juju_offer.haproxy_route.url
  }

  application {
    name     = "landscape-server"
    endpoint = "hostagent-messenger-haproxy-route"
  }
}

resource "juju_integration" "ubuntu_installer_attach_haproxy_route" {
  model = data.juju_model.landscape_model.name

  application {
    offer_url = data.juju_offer.haproxy_route.url
  }

  application {
    name     = "landscape-server"
    endpoint = "ubuntu-installer-attach-haproxy-route"
  }
}

resource "juju_integration" "appserver_haproxy_route" {
  model = data.juju_model.landscape_model.name

  application {
    offer_url = data.juju_offer.haproxy_route.url
  }

  application {
    name     = "landscape-server"
    endpoint = "appserver-haproxy-route"
  }

  depends_on = [
    juju_integration.pingserver_haproxy_route,
    juju_integration.message_server_haproxy_route,
    juju_integration.api_haproxy_route,
    juju_integration.package_upload_haproxy_route,
    juju_integration.repository_haproxy_route,
    juju_integration.hostagent_messenger_haproxy_route,
    juju_integration.ubuntu_installer_attach_haproxy_route,
  ]
}

resource "terraform_data" "wait_for_lbaas" {
  provisioner "local-exec" {
    command = <<-EOT
      juju wait-for model $MODEL_NAME --timeout 3600s --query='forEach(units, unit => unit.workload-status == "active")'
      EOT
    environment = {
      MODEL_NAME = var.lbaas_model_name
    }
  }

  depends_on = [juju_offer.haproxy_route, juju_integration.haproxy_certs, juju_integration.haproxy_receive_ca_certs]
}
