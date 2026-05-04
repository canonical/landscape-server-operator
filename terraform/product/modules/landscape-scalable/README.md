# Landscape Scalable Product Module

This module requires a bootstrapped Juju cloud with a model created within it, the name of which can be provided as `model`.

For example, bootstrap a LXD cloud:

```sh
juju bootstrap lxd landscape-controller
```

Then, create a model named `landscape`:

```sh
juju add-model landscape
```

Then, get the UUID of the `landscape` model:

```sh
juju show-model landscape
```

Copy the value of `model-uuid`.

> [!TIP]
> If you have [`jq`](https://github.com/jqlang/jq) installed, you can use the following:
>
> ```sh
> juju show-model landscape --format=json | jq -r '.landscape["model-uuid"]'
> ```

Then, provide it when applying the plan as the `model_uuid` variable:

```sh
terraform init
terraform apply -var model_uuid=<model-uuid>
```

> [!TIP]
> Customize the module inputs with a `terraform.tfvars` file. An example is `terraform.tfvars.example`, which can be used after removing the `.example` extension.
>
> ```sh
> cp terraform.tfvars.example terraform.tfvars
> terraform init
> terraform apply
> ```

After deploying the module to the model, use the `juju status` command to monitor the lifecycle:

```sh
juju status -m landscape --relations --watch 2s
```

This module uses the [Landscape Server charm module](https://github.com/canonical/landscape-charm/tree/main/terraform).

<!-- BEGIN_TF_DOCS -->
## Requirements

| Name                                                                      | Version |
| ------------------------------------------------------------------------- | ------- |
| <a name="requirement_terraform"></a> [terraform](#requirement\_terraform) | >= 1.10 |
| <a name="requirement_juju"></a> [juju](#requirement\_juju)                | ~> 1.0  |

## Providers

| Name                                                 | Version |
| ---------------------------------------------------- | ------- |
| <a name="provider_juju"></a> [juju](#provider\_juju) | ~> 1.0  |

## Modules

| Name                                                                                   | Source                                                                          | Version        |
| -------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------- | -------------- |
| <a name="module_haproxy"></a> [haproxy](#module\_haproxy)                              | git::https://github.com/canonical/haproxy-operator.git//terraform/charm/haproxy | haproxy-rev331 |
| <a name="module_landscape_server"></a> [landscape\_server](#module\_landscape\_server) | ../../../charm                                                                  | n/a            |
| <a name="module_postgresql"></a> [postgresql](#module\_postgresql)                     | git::https://github.com/canonical/postgresql-operator.git//terraform            | v16/1.165.0    |

## Resources

| Name                                                                                                                                                     | Type     |
| -------------------------------------------------------------------------------------------------------------------------------------------------------- | -------- |
| [juju_application.hostagent_messenger_ingress](https://registry.terraform.io/providers/juju/juju/latest/docs/resources/application)                      | resource |
| [juju_application.http_ingress](https://registry.terraform.io/providers/juju/juju/latest/docs/resources/application)                                     | resource |
| [juju_application.lb_certs](https://registry.terraform.io/providers/juju/juju/latest/docs/resources/application)                                         | resource |
| [juju_application.rabbitmq_server](https://registry.terraform.io/providers/juju/juju/latest/docs/resources/application)                                  | resource |
| [juju_application.ubuntu_installer_attach_ingress](https://registry.terraform.io/providers/juju/juju/latest/docs/resources/application)                  | resource |
| [juju_integration.landscape_server_haproxy](https://registry.terraform.io/providers/juju/juju/latest/docs/resources/integration)                         | resource |
| [juju_integration.landscape_server_hostagent_messenger_ingress](https://registry.terraform.io/providers/juju/juju/latest/docs/resources/integration)     | resource |
| [juju_integration.landscape_server_http_ingress](https://registry.terraform.io/providers/juju/juju/latest/docs/resources/integration)                    | resource |
| [juju_integration.landscape_server_inbound_amqp](https://registry.terraform.io/providers/juju/juju/latest/docs/resources/integration)                    | resource |
| [juju_integration.landscape_server_outbound_amqp](https://registry.terraform.io/providers/juju/juju/latest/docs/resources/integration)                   | resource |
| [juju_integration.landscape_server_postgresql_legacy](https://registry.terraform.io/providers/juju/juju/latest/docs/resources/integration)               | resource |
| [juju_integration.landscape_server_postgresql_modern](https://registry.terraform.io/providers/juju/juju/latest/docs/resources/integration)               | resource |
| [juju_integration.landscape_server_rabbitmq_server](https://registry.terraform.io/providers/juju/juju/latest/docs/resources/integration)                 | resource |
| [juju_integration.landscape_server_tls_certificates](https://registry.terraform.io/providers/juju/juju/latest/docs/resources/integration)                | resource |
| [juju_integration.landscape_server_ubuntu_installer_attach_ingress](https://registry.terraform.io/providers/juju/juju/latest/docs/resources/integration) | resource |
| [juju_machine.landscape_server](https://registry.terraform.io/providers/juju/juju/latest/docs/resources/machine)                                         | resource |

## Inputs

| Name                                                                                                                                  | Description                                                                                                      | Type                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              | Default | Required |
| ------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------- | :------: |
| <a name="input_haproxy"></a> [haproxy](#input\_haproxy)                                                                               | Configuration for the (legacy) HAProxy charm. Set to null to skip deployment.                                    | <pre>object({<br/>    app_name = optional(string, "haproxy")<br/>    channel  = optional(string, "latest/edge")<br/>    config = optional(map(string), {<br/>      default_timeouts            = "queue 60000, connect 5000, client 120000, server 120000"<br/>      global_default_bind_options = "no-tlsv10"<br/>      services                    = ""<br/>      ssl_cert                    = "SELFSIGNED"<br/>    })<br/>    constraints = optional(string, "arch=amd64")<br/>    resources   = optional(map(string), {})<br/>    revision    = optional(number)<br/>    base        = optional(string, "ubuntu@22.04")<br/>    units       = optional(number, 1)<br/>  })</pre>                                                                                                             | `null`  |    no    |
| <a name="input_hostagent_messenger_ingress"></a> [hostagent\_messenger\_ingress](#input\_hostagent\_messenger\_ingress)               | Configuration for the hostagent messenger ingress configurator charm. Set to null to skip deployment.            | <pre>object({<br/>    app_name = optional(string, "hostagent-messenger-ingress")<br/>    channel  = optional(string, "latest/edge")<br/>    config = optional(map(string), {<br/>      external-grpc-port = "6554"<br/>      hostname           = "landscape.local"<br/>      backend-protocol   = "https"<br/>    })<br/>    constraints = optional(string, "arch=amd64")<br/>    resources   = optional(map(string), {})<br/>    revision    = optional(number)<br/>    base        = optional(string, "ubuntu@24.04")<br/>    units       = optional(number, 1)<br/>  })</pre>                                                                                                                                                                                                                 | `null`  |    no    |
| <a name="input_http_ingress"></a> [http\_ingress](#input\_http\_ingress)                                                              | Configuration for the HTTP ingress configurator charm. Set to null to skip deployment.                           | <pre>object({<br/>    app_name = optional(string, "http-ingress")<br/>    channel  = optional(string, "latest/edge")<br/>    config = optional(map(string), {<br/>      paths                      = "/"<br/>      hostname                   = "landscape.local"<br/>      header-rewrite-expressions = "X-Forwarded-Proto:https"<br/>      allow-http                 = "true"<br/>    })<br/>    constraints = optional(string, "arch=amd64")<br/>    resources   = optional(map(string), {})<br/>    revision    = optional(number)<br/>    base        = optional(string, "ubuntu@24.04")<br/>    units       = optional(number, 1)<br/>  })</pre>                                                                                                                                           | `null`  |    no    |
| <a name="input_landscape_server"></a> [landscape\_server](#input\_landscape\_server)                                                  | Configuration for the Landscape Server charm.                                                                    | <pre>object({<br/>    app_name = optional(string, "landscape-server")<br/>    channel  = optional(string, "25.10/edge")<br/>    config = optional(map(string), {<br/>      autoregistration               = "true"<br/>      landscape_ppa                  = "ppa:landscape/self-hosted-beta"<br/>      min_install                    = "true"<br/>      root_url                       = "https://landscape.local/"<br/>      enable_hostagent_messenger     = "true"<br/>      enable_ubuntu_installer_attach = "true"<br/>    })<br/>    constraints = optional(string, "arch=amd64")<br/>    resources   = optional(map(string), {})<br/>    revision    = optional(number)<br/>    base        = optional(string, "ubuntu@24.04")<br/>    units       = optional(number, 1)<br/>  })</pre> | `{}`    |    no    |
| <a name="input_lb_certs"></a> [lb\_certs](#input\_lb\_certs)                                                                          | Configuration for the self-signed-certificates charm (for internal HAProxy TLS). Set to null to skip deployment. | <pre>object({<br/>    app_name    = optional(string, "lb-certs")<br/>    channel     = optional(string, "1/stable")<br/>    config      = optional(map(string), {})<br/>    constraints = optional(string, "arch=amd64")<br/>    resources   = optional(map(string), {})<br/>    revision    = optional(number)<br/>    base        = optional(string, "ubuntu@24.04")<br/>    units       = optional(number, 1)<br/>  })</pre>                                                                                                                                                                                                                                                                                                                                                                   | `{}`    |    no    |
| <a name="input_model_uuid"></a> [model\_uuid](#input\_model\_uuid)                                                                    | UUID of the Juju model to deploy Landscape Server to.                                                            | `string`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          | n/a     |   yes    |
| <a name="input_postgresql"></a> [postgresql](#input\_postgresql)                                                                      | Configuration for the PostgreSQL charm. Set to null to skip deployment.                                          | <pre>object({<br/>    app_name = optional(string, "postgresql")<br/>    channel  = optional(string, "16/stable")<br/>    config = optional(map(string), {<br/>      plugin_plpython3u_enable     = "true"<br/>      plugin_ltree_enable          = "true"<br/>      plugin_intarray_enable       = "true"<br/>      plugin_debversion_enable     = "true"<br/>      plugin_pg_trgm_enable        = "true"<br/>      experimental_max_connections = "500"<br/>    })<br/>    constraints = optional(string, "arch=amd64")<br/>    resources   = optional(map(string), {})<br/>    revision    = optional(number)<br/>    base        = optional(string, "ubuntu@24.04")<br/>    units       = optional(number, 1)<br/>  })</pre>                                                                   | `{}`    |    no    |
| <a name="input_rabbitmq_server"></a> [rabbitmq\_server](#input\_rabbitmq\_server)                                                     | Configuration for the RabbitMQ charm. Set to null to skip deployment.                                            | <pre>object({<br/>    app_name = optional(string, "rabbitmq-server")<br/>    channel  = optional(string, "latest/edge")<br/>    config = optional(map(string), {<br/>      consumer-timeout = "259200000"<br/>    })<br/>    constraints = optional(string, "arch=amd64")<br/>    resources   = optional(map(string), {})<br/>    revision    = optional(number)<br/>    base        = optional(string, "ubuntu@24.04")<br/>    units       = optional(number, 1)<br/>  })</pre>                                                                                                                                                                                                                                                                                                                  | `{}`    |    no    |
| <a name="input_ubuntu_installer_attach_ingress"></a> [ubuntu\_installer\_attach\_ingress](#input\_ubuntu\_installer\_attach\_ingress) | Configuration for the Ubuntu installer attach ingress configurator charm. Set to null to skip deployment.        | <pre>object({<br/>    app_name = optional(string, "ubuntu-installer-attach-ingress")<br/>    channel  = optional(string, "latest/edge")<br/>    config = optional(map(string), {<br/>      external-grpc-port = "50051"<br/>      hostname           = "landscape.local"<br/>      backend-protocol   = "https"<br/>    })<br/>    constraints = optional(string, "arch=amd64")<br/>    resources   = optional(map(string), {})<br/>    revision    = optional(number)<br/>    base        = optional(string, "ubuntu@24.04")<br/>    units       = optional(number, 1)<br/>  })</pre>                                                                                                                                                                                                            | `null`  |    no    |

## Outputs

| Name                                                                                                                               | Description                                                                                                                                                 |
| ---------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| <a name="output_admin_email"></a> [admin\_email](#output\_admin\_email)                                                            | Administrator email from the Landscape Server config.                                                                                                       |
| <a name="output_admin_password"></a> [admin\_password](#output\_admin\_password)                                                   | Administrator password from the Landscape Server config (sensitive).                                                                                        |
| <a name="output_applications"></a> [applications](#output\_applications)                                                           | The charms included in the module.                                                                                                                          |
| <a name="output_haproxy_self_signed"></a> [haproxy\_self\_signed](#output\_haproxy\_self\_signed)                                  | Indicates whether the external HAProxy charm is using a self-signed TLS certificate. Null when haproxy is not deployed.                                     |
| <a name="output_has_haproxy_route_interface"></a> [has\_haproxy\_route\_interface](#output\_has\_haproxy\_route\_interface)        | Indicates whether the deployment uses haproxy-route relations (26.04+) rather than the legacy external HAProxy website endpoint.                            |
| <a name="output_has_modern_amqp_relations"></a> [has\_modern\_amqp\_relations](#output\_has\_modern\_amqp\_relations)              | Indicates whether the deployment uses the modern inbound/outbound AMQP endpoints.                                                                           |
| <a name="output_has_modern_postgres_interface"></a> [has\_modern\_postgres\_interface](#output\_has\_modern\_postgres\_interface)  | Indicates whether the deployment supports the modern PostgreSQL charm interface.                                                                            |
| <a name="output_registration_key"></a> [registration\_key](#output\_registration\_key)                                             | Registration key from the Landscape Server config.                                                                                                          |
<!-- END_TF_DOCS -->
