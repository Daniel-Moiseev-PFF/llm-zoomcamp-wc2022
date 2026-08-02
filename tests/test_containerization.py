"""The compose file is the reproducibility contract, so it gets asserted.

Reads the YAML and the Dockerfile only — nothing here starts a container.
"""

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
COMPOSE_PATH = ROOT / "docker-compose.yml"
DOCKERFILE_PATH = ROOT / "Dockerfile"

# Every service that runs our Python and therefore needs the database.
PYTHON_SERVICES = {
    "app",
    "seed",
    "ingest-football",
    "ingest-prose",
    "eval-retrieval",
    "eval-answers",
}
GATED = {"ingest-football", "ingest-prose", "eval-retrieval", "eval-answers"}


@pytest.fixture(scope="module")
def compose():
    return yaml.safe_load(COMPOSE_PATH.read_text())


@pytest.fixture(scope="module")
def services(compose):
    return compose["services"]


def test_every_python_service_shares_one_image(services):
    for name in PYTHON_SERVICES:
        assert services[name]["build"] == ".", name


def test_python_services_reach_postgres_by_service_name(services):
    # The localhost default in postgres_credentials() is right on the host and
    # wrong in a container.
    for name in PYTHON_SERVICES:
        assert services[name]["environment"]["POSTGRES_HOST"] == "postgres", name


def test_python_services_wait_for_a_healthy_database(services):
    for name in PYTHON_SERVICES:
        assert services[name]["depends_on"]["postgres"] == {
            "condition": "service_healthy"
        }, name


def test_credentials_come_from_the_env_file_not_the_compose_file(services):
    for name in PYTHON_SERVICES:
        assert services[name]["env_file"] == ".env", name
        assert "POSTGRES_PASSWORD" not in services[name]["environment"], name


def test_postgres_credentials_are_interpolated_never_literal(services):
    for key in ("POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB"):
        assert services["postgres"]["environment"][key].startswith("${")


def test_only_the_app_and_the_seeder_run_by_default(services):
    for name in GATED:
        assert services[name].get("profiles"), name
    for name in ("app", "seed", "postgres", "grafana"):
        assert not services[name].get("profiles"), name


def test_the_knowledge_base_restores_before_anything_reads_it(services):
    mounts = [m for m in services["postgres"]["volumes"] if "initdb" in m]
    targets = sorted(m.split(":")[1] for m in mounts)
    assert len(targets) == 2
    assert targets[0].endswith("00-extensions.sql")  # sorts first, runs first
    assert targets[1].endswith("10-kb.sql.gz")
    assert all(m.endswith(":ro") for m in mounts)


def test_the_seeder_is_idempotent(services):
    # A plain `up` twice must not stack 300 fabricated rows.
    command = " ".join(services["seed"]["command"])
    assert "--purge" in command


def test_published_ports_can_be_moved(services):
    # A reviewer with their own Postgres on 5432 would otherwise fail on the
    # very first `up` with an opaque bind error.
    published = [
        port for name in ("postgres", "grafana", "app") for port in services[name]["ports"]
    ]
    assert published
    for port in published:
        assert port.startswith("${"), port


def test_containers_dial_postgres_on_its_internal_port(services):
    # POSTGRES_PORT in .env moves the published port. If it leaked into the
    # containers they would dial a port that is not open inside the network.
    for name in PYTHON_SERVICES:
        assert services[name]["environment"]["POSTGRES_PORT"] == "5432", name


def test_no_service_hardcodes_a_container_name(services):
    # Container names are global to the daemon, so a hardcoded one stops the
    # stack running alongside a second copy of itself — which is exactly what
    # verifying the fresh-clone path requires.
    for name, service in services.items():
        assert "container_name" not in service, name


def test_the_image_installs_from_the_lockfile():
    # --frozen fails rather than re-resolving when uv.lock and pyproject
    # disagree; that is what makes the build reproducible.
    dockerfile = DOCKERFILE_PATH.read_text()
    assert dockerfile.count("FROM ") >= 2  # builder + runtime
    assert "uv sync --frozen" in dockerfile
    assert "--no-dev" in dockerfile


def test_the_uv_image_is_pinned():
    # A floating :latest tag would defeat the point of --frozen.
    assert "astral-sh/uv:latest" not in DOCKERFILE_PATH.read_text()
