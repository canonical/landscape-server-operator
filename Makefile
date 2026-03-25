include terraform/charm/Makefile
include terraform/product/Makefile

DIR_NAME := $(notdir $(shell pwd))
LBAAS_DIR ?= ./bundle-examples/lbaas
LBAAS_BUNDLE_PATH ?= $(LBAAS_DIR)/lbaas.bundle.yaml
BUNDLE_PATH ?= ./bundle-examples/bundle.yaml
PLATFORM ?= ubuntu@24.04:amd64
MODEL_NAME ?= $(DIR_NAME)-build
LBAAS_MODEL_NAME ?= lbaas
CLEAN_PLATFORM := $(subst :,-,$(PLATFORM))
SKIP_BUILD ?= false
SKIP_CLEAN ?= false
SKIP_ADD_MODEL ?= false

# Python testing and linting
.PHONY: test
test:
	uv run pytest --tb native tests/unit

.PHONY: integration-test
integration-test:
	uv run --group integration pytest -v --tb native tests/integration

.PHONY: coverage
coverage:
	uv run coverage run --branch --source=src -m pytest -v --tb native tests/unit
	uv run coverage report -m

.PHONY: check
check:
	uv run ruff check src tests
	uv run ruff format --check src tests

.PHONY: lint
lint:
	uv run ruff check --fix src tests
	uv run ruff format src tests

# Charm building and deployment
.PHONY: build
build:
	uv run ccc pack --platform $(PLATFORM)


.PHONY: add-model
add-model:
	@if [  "$(SKIP_ADD_MODEL)" != "true" ]; then juju add-model $(MODEL_NAME); else echo "skipping add-model..."; fi

.PHONY: deploy
deploy:
	@if [ "$(SKIP_CLEAN)" != "true" ]; then $(MAKE) clean; else echo "skipping clean..."; fi
	@if [ "$(SKIP_BUILD)" != "true" ]; then $(MAKE) build; else echo "skipping build..."; fi
	$(MAKE) add-model
	juju deploy -m $(MODEL_NAME) $(BUNDLE_PATH)

.PHONY: deploy-lbaas
deploy-lbaas:
	@if [ "$(SKIP_CLEAN)" != "true" ]; then $(MAKE) clean; else echo "skipping clean..."; fi
	@if [ "$(SKIP_BUILD)" != "true" ]; then $(MAKE) build; else echo "skipping build..."; fi
	$(MAKE) add-model
	juju deploy -m $(MODEL_NAME) $(LBAAS_BUNDLE_PATH)

.PHONY: check-jq
check-jq:
	@command -v jq >/dev/null 2>&1 || { echo "Error: jq is not installed. See https://jqlang.org/download/"; exit 1; }

.PHONY: check-terraform
check-terraform:
	@command -v terraform >/dev/null 2>&1 || { echo "Error: terraform is not installed. See https://developer.hashicorp.com/terraform/install"; exit 1; }

.PHONY: install-terraform
install-terraform:
	@if command -v terraform >/dev/null 2>&1; then \
		echo "Terraform is already installed, skipping install..."; \
	else \
		echo "Installing Terraform..."; \
		snap install terraform --classic; \
	fi

.PHONY: clean-lbaas
clean-lbaas:
	-juju destroy-model --no-prompt $(LBAAS_MODEL_NAME) \
		--force --no-wait --destroy-storage
	-cd $(LBAAS_DIR) && \
		rm -rf *.tfstate

.PHONY: lbaas
lbaas: clean-lbaas install-terraform deploy-lbaas
	cd $(LBAAS_DIR) && \
	terraform init -backend=false && \
	terraform apply -auto-approve \
		-var model_name=$(MODEL_NAME) \
		-var lbaas_model_name=$(LBAAS_MODEL_NAME)

.PHONY: clean
clean:
	-rm -f landscape-server_$(CLEAN_PLATFORM).charm
	-juju destroy-model --no-prompt $(MODEL_NAME) \
		--force --no-wait --destroy-storage
	-cd terraform/product/modules/landscape-scalable && \
		rm -rf terraform.tfstate*

.PHONY: terraform-check-all
terraform-check-all: check-terraform
	cd terraform/charm && $(MAKE) check-charm-module
	cd terraform/product && $(MAKE) check-product-modules

.PHONY: terraform-fix-all
terraform-fix-all: check-terraform
	cd terraform/charm && $(MAKE) fix-charm-module
	cd terraform/product && $(MAKE) fix-product-modules

.PHONY: terraform-test-all
terraform-test-all: check-terraform
	cd terraform/charm && $(MAKE) test-charm-module
	cd terraform/product && $(MAKE) test-product-modules

# Variables: MODEL_NAME (default: <dir>-build), SKIP_CLEAN (default: false), SKIP_ADD_MODEL (default: false)
.PHONY: deploy-landscape-scalable
deploy-landscape-scalable: check-terraform check-jq
	@if [ "$(SKIP_CLEAN)" != "true" ]; then $(MAKE) clean; else echo "skipping clean..."; fi
	$(MAKE) add-model
	cd terraform/product/modules/landscape-scalable && \
	terraform init -backend=false && \
	terraform apply -auto-approve \
		-var model_uuid=$$(juju show-model $(MODEL_NAME) --format=json | jq -r '.["$(MODEL_NAME)"]["model-uuid"]')
