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

| Name | Version |
|------|---------|
| <a name="requirement_terraform"></a> [terraform](#requirement\_terraform) | >= 1.10 |
| <a name="requirement_juju"></a> [juju](#requirement\_juju) | ~> 1.0 |

## Providers

| Name | Version |
|------|---------|
| <a name="provider_juju"></a> [juju](#provider\_juju) | ~> 1.0 |

## Modules

| Name | Source | Version |
|------|--------|---------|
| <a name="module_haproxy"></a> [haproxy](#module\_haproxy) | git::https://github.com/canonical/haproxy-operator.git//terraform/charm/haproxy | haproxy-rev331 |
| <a name="module_landscape_server"></a> [landscape\_server](#module\_landscape\_server) | ../../../charm | n/a |
| <a name="module_postgresql"></a> [postgresql](#module\_postgresql) | git::https://github.com/canonical/postgresql-operator.git//terraform | v16/1.165.0 |

## Resources

| Name | Type |
|------|------|
| [juju_application.haproxy_self_signed_certs](https://registry.terraform.io/providers/juju/juju/latest/docs/resources/application) | resource |
| [juju_application.pgbouncer](https://registry.terraform.io/providers/juju/juju/latest/docs/resources/application) | resource |
| [juju_application.rabbitmq_server](https://registry.terraform.io/providers/juju/juju/latest/docs/resources/application) | resource |
| [juju_integration.haproxy_certificates](https://registry.terraform.io/providers/juju/juju/latest/docs/resources/integration) | resource |
| [juju_integration.haproxy_receive_ca_certs](https://registry.terraform.io/providers/juju/juju/latest/docs/resources/integration) | resource |
| [juju_integration.landscape_server_api_haproxy_route_in_model](https://registry.terraform.io/providers/juju/juju/latest/docs/resources/integration) | resource |
| [juju_integration.landscape_server_api_haproxy_route_lbaas](https://registry.terraform.io/providers/juju/juju/latest/docs/resources/integration) | resource |
| [juju_integration.landscape_server_appserver_haproxy_route_in_model](https://registry.terraform.io/providers/juju/juju/latest/docs/resources/integration) | resource |
| [juju_integration.landscape_server_appserver_haproxy_route_lbaas](https://registry.terraform.io/providers/juju/juju/latest/docs/resources/integration) | resource |
| [juju_integration.landscape_server_haproxy](https://registry.terraform.io/providers/juju/juju/latest/docs/resources/integration) | resource |
| [juju_integration.landscape_server_hostagent_messenger_haproxy_route_in_model](https://registry.terraform.io/providers/juju/juju/latest/docs/resources/integration) | resource |
| [juju_integration.landscape_server_hostagent_messenger_haproxy_route_lbaas](https://registry.terraform.io/providers/juju/juju/latest/docs/resources/integration) | resource |
| [juju_integration.landscape_server_inbound_amqp](https://registry.terraform.io/providers/juju/juju/latest/docs/resources/integration) | resource |
| [juju_integration.landscape_server_message_server_haproxy_route_in_model](https://registry.terraform.io/providers/juju/juju/latest/docs/resources/integration) | resource |
| [juju_integration.landscape_server_message_server_haproxy_route_lbaas](https://registry.terraform.io/providers/juju/juju/latest/docs/resources/integration) | resource |
| [juju_integration.landscape_server_outbound_amqp](https://registry.terraform.io/providers/juju/juju/latest/docs/resources/integration) | resource |
| [juju_integration.landscape_server_package_upload_haproxy_route_in_model](https://registry.terraform.io/providers/juju/juju/latest/docs/resources/integration) | resource |
| [juju_integration.landscape_server_package_upload_haproxy_route_lbaas](https://registry.terraform.io/providers/juju/juju/latest/docs/resources/integration) | resource |
| [juju_integration.landscape_server_pgbouncer](https://registry.terraform.io/providers/juju/juju/latest/docs/resources/integration) | resource |
| [juju_integration.landscape_server_pingserver_haproxy_route_in_model](https://registry.terraform.io/providers/juju/juju/latest/docs/resources/integration) | resource |
| [juju_integration.landscape_server_pingserver_haproxy_route_lbaas](https://registry.terraform.io/providers/juju/juju/latest/docs/resources/integration) | resource |
| [juju_integration.landscape_server_postgresql_legacy](https://registry.terraform.io/providers/juju/juju/latest/docs/resources/integration) | resource |
| [juju_integration.landscape_server_postgresql_modern](https://registry.terraform.io/providers/juju/juju/latest/docs/resources/integration) | resource |
| [juju_integration.landscape_server_rabbitmq_server](https://registry.terraform.io/providers/juju/juju/latest/docs/resources/integration) | resource |
| [juju_integration.landscape_server_repository_haproxy_route_in_model](https://registry.terraform.io/providers/juju/juju/latest/docs/resources/integration) | resource |
| [juju_integration.landscape_server_repository_haproxy_route_lbaas](https://registry.terraform.io/providers/juju/juju/latest/docs/resources/integration) | resource |
| [juju_integration.landscape_server_ubuntu_installer_attach_haproxy_route_in_model](https://registry.terraform.io/providers/juju/juju/latest/docs/resources/integration) | resource |
| [juju_integration.landscape_server_ubuntu_installer_attach_haproxy_route_lbaas](https://registry.terraform.io/providers/juju/juju/latest/docs/resources/integration) | resource |
| [juju_integration.pgbouncer_postgresql](https://registry.terraform.io/providers/juju/juju/latest/docs/resources/integration) | resource |
| [juju_machine.landscape_server](https://registry.terraform.io/providers/juju/juju/latest/docs/resources/machine) | resource |

## Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|:--------:|
| <a name="input_haproxy"></a> [haproxy](#input\_haproxy) | Configuration for the HAProxy charm. Set to null to skip deployment. | <pre>object({<br/>    app_name    = optional(string, "haproxy")<br/>    channel     = optional(string, "2.8/edge")<br/>    config      = optional(map(string), {})<br/>    constraints = optional(string, "arch=amd64")<br/>    resources   = optional(map(string), {})<br/>    revision    = optional(number)<br/>    base        = optional(string, "ubuntu@24.04")<br/>    units       = optional(number, 1)<br/>  })</pre> | `{}` | no |
| <a name="input_haproxy_route_offer_url"></a> [haproxy\_route\_offer\_url](#input\_haproxy\_route\_offer\_url) | Offer URL for the haproxy-route endpoint from a cross-model haproxy deployment (LBaaS). Set to null to skip. | `string` | `null` | no |
| <a name="input_haproxy_self_signed_certs"></a> [haproxy\_self\_signed\_certs](#input\_haproxy\_self\_signed\_certs) | Configuration for the self-signed-certificates charm used by HAProxy. Set to null to skip deployment. | <pre>object({<br/>    app_name    = optional(string, "self-signed-certificates")<br/>    channel     = optional(string, "1/stable")<br/>    constraints = optional(string, "arch=amd64")<br/>    revision    = optional(number)<br/>    base        = optional(string, "ubuntu@24.04")<br/>  })</pre> | `{}` | no |
| <a name="input_landscape_server"></a> [landscape\_server](#input\_landscape\_server) | Configuration for the Landscape Server charm. | <pre>object({<br/>    app_name = optional(string, "landscape-server")<br/>    channel  = optional(string, "25.10/edge")<br/>    config = optional(map(string), {<br/>      autoregistration               = "true"<br/>      landscape_ppa                  = "ppa:landscape/self-hosted-beta"<br/>      min_install                    = "true"<br/>      root_url                       = "https://landscape.local/"<br/>      enable_hostagent_messenger     = "true"<br/>      enable_ubuntu_installer_attach = "true"<br/>    })<br/>    constraints = optional(string, "arch=amd64")<br/>    resources   = optional(map(string), {})<br/>    revision    = optional(number)<br/>    base        = optional(string, "ubuntu@24.04")<br/>    units       = optional(number, 1)<br/>  })</pre> | `{}` | no |
| <a name="input_model_uuid"></a> [model\_uuid](#input\_model\_uuid) | UUID of the Juju model to deploy Landscape Server to. | `string` | n/a | yes |
| <a name="input_pgbouncer"></a> [pgbouncer](#input\_pgbouncer) | Configuration for the PgBouncer charm. Set to null to skip deployment. PgBouncer is a subordinate charm and does not have its own units. | <pre>object({<br/>    app_name = optional(string, "pgbouncer")<br/>    channel  = optional(string, "1/stable")<br/>    config   = optional(map(string), {})<br/>    revision = optional(number)<br/>    base     = optional(string, "ubuntu@24.04")<br/>  })</pre> | `null` | no |
| <a name="input_postgresql"></a> [postgresql](#input\_postgresql) | Configuration for the PostgreSQL charm. Set to null to skip deployment. | <pre>object({<br/>    app_name = optional(string, "postgresql")<br/>    channel  = optional(string, "16/stable")<br/>    config = optional(map(string), {<br/>      plugin_plpython3u_enable     = "true"<br/>      plugin_ltree_enable          = "true"<br/>      plugin_intarray_enable       = "true"<br/>      plugin_debversion_enable     = "true"<br/>      plugin_pg_trgm_enable        = "true"<br/>      experimental_max_connections = "500"<br/>    })<br/>    constraints = optional(string, "arch=amd64")<br/>    resources   = optional(map(string), {})<br/>    revision    = optional(number)<br/>    base        = optional(string, "ubuntu@24.04")<br/>    units       = optional(number, 1)<br/>  })</pre> | `{}` | no |
| <a name="input_rabbitmq_server"></a> [rabbitmq\_server](#input\_rabbitmq\_server) | Configuration for the RabbitMQ charm. Set to null to skip deployment. | <pre>object({<br/>    app_name = optional(string, "rabbitmq-server")<br/>    channel  = optional(string, "latest/edge")<br/>    config = optional(map(string), {<br/>      consumer-timeout = "259200000"<br/>    })<br/>    constraints = optional(string, "arch=amd64")<br/>    resources   = optional(map(string), {})<br/>    revision    = optional(number)<br/>    base        = optional(string, "ubuntu@24.04")<br/>    units       = optional(number, 1)<br/>  })</pre> | `{}` | no |

## Outputs

| Name | Description |
|------|-------------|
| <a name="output_admin_email"></a> [admin\_email](#output\_admin\_email) | Administrator email from the Landscape Server config. |
| <a name="output_admin_password"></a> [admin\_password](#output\_admin\_password) | Administrator password from the Landscape Server config (sensitive). |
| <a name="output_applications"></a> [applications](#output\_applications) | The charms included in the module. |
| <a name="output_haproxy_self_signed"></a> [haproxy\_self\_signed](#output\_haproxy\_self\_signed) | Indicates whether HAProxy is using self-signed TLS certificates. True when self-signed-certificates is deployed alongside haproxy, null when haproxy is not deployed. |
| <a name="output_has_haproxy_route_interface"></a> [has\_haproxy\_route\_interface](#output\_has\_haproxy\_route\_interface) | Indicates whether the deployment uses the modern haproxy-route relation/interface instead of the legacy website interface. |
| <a name="output_has_modern_amqp_relations"></a> [has\_modern\_amqp\_relations](#output\_has\_modern\_amqp\_relations) | Indicates whether the deployment uses the modern inbound/outbound AMQP endpoints. |
| <a name="output_has_modern_postgres_interface"></a> [has\_modern\_postgres\_interface](#output\_has\_modern\_postgres\_interface) | Indicates whether the deployment supports the modern PostgreSQL charm interface. |
| <a name="output_registration_key"></a> [registration\_key](#output\_registration\_key) | Registration key from the Landscape Server config. |
<!-- END_TF_DOCS -->
