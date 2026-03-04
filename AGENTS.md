# AGENTS.md

## Project overview

This is a [Juju charm](https://documentation.ubuntu.com/juju/3.6/) that deploys and manages [Landscape Server](https://ubuntu.com/landscape). The charm is written in Python using the [Ops framework](https://documentation.ubuntu.com/ops/latest/).

Key source files:
- `src/charm.py` — main charm logic
- `src/config.py` — charm configuration dataclass
- `src/database.py` — PostgreSQL relation helpers
- `src/settings_files.py` — Landscape service config file management
- `src/haproxy.py` — HAProxy integration
- `lib/charms/` — vendored charm libraries (do not edit manually)

## Setup

Dependencies are managed with [Poetry](https://python-poetry.org/).

```sh
sudo apt install -y pipx
pipx install poetry
poetry install --with dev
```

## Common commands

| Task                                       | Command                                                                                                                                   |
| ------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------- |
| Unit tests                                 | `make test`                                                                                                                               |
| Unit tests (single)                        | `poetry run pytest tests/unit/test_charm.py::TestCharm::test_install`                                                                     |
| Coverage                                   | `make coverage`                                                                                                                           |
| Integration tests (against existing model) | `LANDSCAPE_CHARM_USE_HOST_JUJU_MODEL=1 make integration-test`                                                                             |
| Integration tests (deploy fresh model)     | `make integration-test`                                                                                                                   |
| LBaaS integration tests                    | `make lbaas && LANDSCAPE_CHARM_USE_HOST_JUJU_MODEL=1 LANDSCAPE_CHARM_USE_HOST_LBAAS_MODEL=1 LBAAS_MODEL_NAME=lbaas make integration-test` |
| Lint                                       | `make lint`                                                                                                                               |
| Format                                     | `make fmt`                                                                                                                                |
| Build charm                                | `make build`                                                                                                                              |
| Deploy bundle locally                      | `make deploy`                                                                                                                             |
| Terraform tests                            | `make terraform-test-all`                                                                                                                 |
| Terraform lint/fix                         | `make terraform-fix-all`                                                                                                                  |

Always run `make lint` and `make test` before finishing a task.

## PR guidelines

- Keep PRs focused on a single concern
- Run `make lint`, `make test`, and `LANDSCAPE_CHARM_USE_HOST_JUJU_MODEL=1 make integration-test` before pushing
- Follow [conventional commit format](https://www.conventionalcommits.org/en/v1.0.0/) (`feat:`, `fix:`, `chore:`, etc.)
