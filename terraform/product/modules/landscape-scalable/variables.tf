# © 2026 Canonical Ltd.

variable "model_uuid" {
  description = "UUID of the Juju model to deploy Landscape Server to."
  type        = string
}

variable "landscape_server" {
  description = "Configuration for the Landscape Server charm."
  type = object({
    app_name = optional(string, "landscape-server")
    channel  = optional(string, "25.10/edge")
    config = optional(map(string), {
      autoregistration               = "true"
      landscape_ppa                  = "ppa:landscape/self-hosted-beta"
      min_install                    = "true"
      root_url                       = "https://landscape.local/"
      enable_hostagent_messenger     = "true"
      enable_ubuntu_installer_attach = "true"
    })
    constraints = optional(string, "arch=amd64")
    resources   = optional(map(string), {})
    revision    = optional(number)
    base        = optional(string, "ubuntu@24.04")
    units       = optional(number, 1)
  })

  default = {}
}

variable "postgresql" {
  description = "Configuration for the PostgreSQL charm. Set to null to skip deployment."
  type = object({
    app_name = optional(string, "postgresql")
    channel  = optional(string, "16/stable")
    config = optional(map(string), {
      plugin_plpython3u_enable     = "true"
      plugin_ltree_enable          = "true"
      plugin_intarray_enable       = "true"
      plugin_debversion_enable     = "true"
      plugin_pg_trgm_enable        = "true"
      experimental_max_connections = "500"
    })
    constraints = optional(string, "arch=amd64")
    resources   = optional(map(string), {})
    revision    = optional(number)
    base        = optional(string, "ubuntu@24.04")
    units       = optional(number, 1)
  })

  default  = {}
  nullable = true

}

variable "haproxy" {
  description = "Configuration for the (legacy) HAProxy charm. Set to null to skip deployment."
  type = object({
    app_name = optional(string, "haproxy")
    channel  = optional(string, "latest/edge")
    config = optional(map(string), {
      default_timeouts            = "queue 60000, connect 5000, client 120000, server 120000"
      global_default_bind_options = "no-tlsv10"
      services                    = ""
      ssl_cert                    = "SELFSIGNED"
    })
    constraints = optional(string, "arch=amd64")
    resources   = optional(map(string), {})
    revision    = optional(number)
    base        = optional(string, "ubuntu@22.04")
    units       = optional(number, 1)
  })

  default  = null
  nullable = true
}

variable "http_ingress" {
  description = "Configuration for the HTTP ingress configurator charm. Set to null to skip deployment."
  type = object({
    app_name = optional(string, "http-ingress")
    channel  = optional(string, "latest/edge")
    config = optional(map(string), {
      paths                      = "/"
      hostname                   = "landscape.local"
      header-rewrite-expressions = "X-Forwarded-Proto:https"
      allow-http                 = "true"
    })
    constraints = optional(string, "arch=amd64")
    resources   = optional(map(string), {})
    revision    = optional(number)
    base        = optional(string, "ubuntu@24.04")
    units       = optional(number, 1)
  })

  default  = null
  nullable = true
}

variable "hostagent_messenger_ingress" {
  description = "Configuration for the hostagent messenger ingress configurator charm. Set to null to skip deployment."
  type = object({
    app_name = optional(string, "hostagent-messenger-ingress")
    channel  = optional(string, "latest/edge")
    config = optional(map(string), {
      external-grpc-port = "6554"
      hostname           = "landscape.local"
      backend-protocol   = "https"
    })
    constraints = optional(string, "arch=amd64")
    resources   = optional(map(string), {})
    revision    = optional(number)
    base        = optional(string, "ubuntu@24.04")
    units       = optional(number, 1)
  })

  default  = null
  nullable = true
}

variable "ubuntu_installer_attach_ingress" {
  description = "Configuration for the Ubuntu installer attach ingress configurator charm. Set to null to skip deployment."
  type = object({
    app_name = optional(string, "ubuntu-installer-attach-ingress")
    channel  = optional(string, "latest/edge")
    config = optional(map(string), {
      external-grpc-port = "50051"
      hostname           = "landscape.local"
      backend-protocol   = "https"
    })
    constraints = optional(string, "arch=amd64")
    resources   = optional(map(string), {})
    revision    = optional(number)
    base        = optional(string, "ubuntu@24.04")
    units       = optional(number, 1)
  })

  default  = null
  nullable = true
}

variable "rabbitmq_server" {
  description = "Configuration for the RabbitMQ charm. Set to null to skip deployment."
  type = object({
    app_name = optional(string, "rabbitmq-server")
    channel  = optional(string, "latest/edge")
    config = optional(map(string), {
      consumer-timeout = "259200000"
    })
    constraints = optional(string, "arch=amd64")
    resources   = optional(map(string), {})
    revision    = optional(number)
    base        = optional(string, "ubuntu@24.04")
    units       = optional(number, 1)
  })

  default  = {}
  nullable = true
}

variable "lb_certs" {
  description = "Configuration for the self-signed-certificates charm (for internal HAProxy TLS). Set to null to skip deployment."
  type = object({
    app_name    = optional(string, "lb-certs")
    channel     = optional(string, "1/stable")
    config      = optional(map(string), {})
    constraints = optional(string, "arch=amd64")
    resources   = optional(map(string), {})
    revision    = optional(number)
    base        = optional(string, "ubuntu@24.04")
    units       = optional(number, 1)
  })

  default  = {}
  nullable = true
}
