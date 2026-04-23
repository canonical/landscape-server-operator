"""
Integration test fixtures.
"""

import os
import pathlib
import tempfile

import jubilant
import pytest

BUNDLE_NAME = "bundle.yaml"
"""
The name of the bundle used for integration testing.
"""
WAIT_TIMEOUT_SECONDS = 60 * 20  # Landscape takes a long time to deploy.
USE_HOST_JUJU_MODEL = os.getenv("LANDSCAPE_CHARM_USE_HOST_JUJU_MODEL", False)
"""
If `True`, return a reference the current Juju model on the host instead of a temporary
model.
"""

USE_HOST_LBAAS_MODEL = os.getenv("LANDSCAPE_CHARM_USE_HOST_LBAAS_MODEL", False)
"""
If `True`, use existing LBaaS model instead of creating a temporary one.
The model name should be set in `LBAAS_MODEL_NAME` environment variable.
"""

LBAAS_MODEL_NAME = os.getenv("LBAAS_MODEL_NAME", "lbaas")
"""
Name of the LBaaS model to use when `USE_HOST_LBAAS_MODEL` is `True`.
"""


@pytest.fixture(scope="module")
def host_juju():
    """
    Get a reference to the current Landscape server Juju model on the host.

    This runs a light check to ensure the current model is in fact a Landscape server
    bundle.

    This fixture is useful when experimenting with new tests to avoid needing to
    re-deploy the bundle in between attempts.
    """
    yield _host_juju()


def _host_juju():
    juju = jubilant.Juju()
    expected_applications = {
        "landscape-server",
        "postgresql",
        "rabbitmq-server",
    }
    model_applications = juju.status().apps

    for app in expected_applications:
        assert app in model_applications

    return juju


@pytest.fixture(scope="module")
def juju():
    """
    Create a temporary Juju model.
    """

    if USE_HOST_JUJU_MODEL:
        yield _host_juju()
    else:
        with jubilant.temp_model() as juju:
            yield juju


@pytest.fixture(scope="module")
def bundle(juju: jubilant.Juju) -> None:
    """
    Create a Landscape bundle, using a local landscape-server charm.

    The landscape-server charm must be packed out-of-band; this fixture will not pack
    the charm itself.
    """
    if not USE_HOST_JUJU_MODEL:
        juju.deploy(charm=bundle_path())
        juju.wait(
            jubilant.all_active,
            timeout=WAIT_TIMEOUT_SECONDS,
            successes=5,  # Landscape can take a while to come up, fully active.
            delay=5.0,
        )


def bundle_path() -> pathlib.Path:
    """
    Return the path to the landscape-server integration test bundle, with the
    local charm path rewritten to an absolute path.

    Juju copies the bundle YAML into its own snap temp directory before parsing,
    so relative charm paths are resolved from there rather than from the original
    bundle location. Writing an absolute path avoids this.
    """
    src = pathlib.Path(__file__).parent / BUNDLE_NAME
    assert src.exists(), f"{src} not found."

    content = src.read_text()
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("charm:"):
            charm_val = stripped[len("charm:") :].strip().strip('"').strip("'")
            if charm_val and not charm_val.startswith(("ch:", "local:")):
                abs_path = (src.parent / charm_val).resolve()
                content = content.replace(charm_val, str(abs_path))

    tmp = pathlib.Path(tempfile.mkstemp(suffix=".yaml")[1])
    tmp.write_text(content)
    return tmp


@pytest.fixture(scope="module")
def lbaas(juju: jubilant.Juju, bundle: None):
    """
    Provide a reference to the HAProxy model for tests that need it.

    Environment variables:
    - LANDSCAPE_CHARM_USE_HOST_JUJU_MODEL: Yield local model directly when haproxy
        is co-deployed.
    - LANDSCAPE_CHARM_USE_HOST_LBAAS_MODEL: Use an existing separate lbaas model.
    - LBAAS_MODEL_NAME: Name of the lbaas model (default: "lbaas").

    Yields None when no separate lbaas model is configured; tests that require a
    distinct lbaas model skip themselves via their own `lbaas is None` guards.
    """
    haproxy_in_local_model = "haproxy" in juju.status().apps
    if USE_HOST_JUJU_MODEL and not USE_HOST_LBAAS_MODEL and haproxy_in_local_model:
        yield juju
        return

    if USE_HOST_LBAAS_MODEL:
        lbaas_model = LBAAS_MODEL_NAME
        lbaas_juju = jubilant.Juju(model=lbaas_model)
        try:
            lbaas_status = lbaas_juju.status()
            assert "haproxy" in lbaas_status.apps, "haproxy not found in lbaas model"
        except Exception as e:
            pytest.fail(
                f"Failed to connect to existing lbaas model '{lbaas_model}': {e}"
            )
        yield lbaas_juju
    else:
        yield None
