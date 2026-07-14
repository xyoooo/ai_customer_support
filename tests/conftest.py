import os
from collections.abc import Iterator

os.environ["SUPPORTPILOT_ENVIRONMENT"] = "test"
os.environ["SUPPORTPILOT_DATABASE_URL"] = (
    "postgresql+asyncpg://supportpilot_app:local_app_password@localhost:5432/supportpilot_test"
)
os.environ["SUPPORTPILOT_MIGRATION_DATABASE_URL"] = (
    "postgresql+psycopg://supportpilot_migrator:local_migrator_password"
    "@localhost:5432/supportpilot_test"
)
os.environ["SUPPORTPILOT_JWT_SECRET"] = "test-secret-with-at-least-thirty-two-characters"

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from apps.api.main import app

MIGRATION_URL = os.environ["SUPPORTPILOT_MIGRATION_DATABASE_URL"].replace(
    "postgresql+psycopg://", "postgresql://"
)


@pytest.fixture(scope="session")
def migrated_database() -> Iterator[None]:
    config = Config("alembic.ini")
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    yield


@pytest.fixture(autouse=True)
def clean_database(request: pytest.FixtureRequest) -> Iterator[None]:
    if request.node.get_closest_marker("integration") is None:
        yield
        return
    request.getfixturevalue("migrated_database")
    with psycopg.connect(MIGRATION_URL, autocommit=True) as connection:
        connection.execute(
            "TRUNCATE TABLE refresh_sessions, workspace_memberships, workspaces, users CASCADE"
        )
    yield
    with psycopg.connect(MIGRATION_URL, autocommit=True) as connection:
        connection.execute(
            "TRUNCATE TABLE refresh_sessions, workspace_memberships, workspaces, users CASCADE"
        )


@pytest.fixture(scope="session")
def client(migrated_database: None) -> Iterator[TestClient]:
    del migrated_database
    with TestClient(app) as test_client:
        yield test_client
