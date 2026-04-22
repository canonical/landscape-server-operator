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
  description = "Configuration for the HAProxy charm. Set to null to skip deployment."
  type = object({
    app_name    = optional(string, "haproxy")
    channel     = optional(string, "2.8/edge")
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

variable "haproxy_route_offer_url" {
  description = "Offer URL for the haproxy-route endpoint from a cross-model haproxy deployment (LBaaS). Set to null to skip."
  type        = string
  default     = null
  nullable    = true
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

variable "pgbouncer" {
  description = "Configuration for the PgBouncer charm. Set to null to skip deployment. PgBouncer is a subordinate charm and does not have its own units."
  type = object({
    app_name = optional(string, "pgbouncer")
    channel  = optional(string, "1/stable")
    config   = optional(map(string), {})
    revision = optional(number)
    base     = optional(string, "ubuntu@24.04")
  })

  default  = null
  nullable = true
}

variable "haproxy_self_signed_certs" {
  description = "Configuration for the self-signed-certificates charm used by HAProxy. Set to null to skip deployment."
  type = object({
    app_name    = optional(string, "self-signed-certificates")
    channel     = optional(string, "1/stable")
    constraints = optional(string, "arch=amd64")
    revision    = optional(number)
    base        = optional(string, "ubuntu@24.04")
  })

  default  = {}
  nullable = true
}
