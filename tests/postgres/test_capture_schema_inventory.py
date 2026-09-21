"""
scripts/capture_schema_inventory.py'nin gerçek PostgreSQL'e karşı davranışını
doğrulayan testler.
"""

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

from sqlalchemy import create_engine, text

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")


def _maintenance_url(test_database_url):
    return test_database_url.rsplit("/", 1)[0] + "/postgres"


def _create_scratch_database():
    name = f"itobot_inventory_{uuid.uuid4().hex[:12]}"
    engine = create_engine(
        _maintenance_url(TEST_DATABASE_URL), isolation_level="AUTOCOMMIT"
    )
    try:
        with engine.connect() as connection:
            connection.execute(text(f'CREATE DATABASE "{name}"'))
    finally:
        engine.dispose()
    return TEST_DATABASE_URL.rsplit("/", 1)[0] + f"/{name}"


def _drop_scratch_database(database_url):
    name = database_url.rsplit("/", 1)[1]
    engine = create_engine(
        _maintenance_url(TEST_DATABASE_URL), isolation_level="AUTOCOMMIT"
    )
    try:
        with engine.connect() as connection:
            connection.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :name AND pid <> pg_backend_pid()"
                ),
                {"name": name},
            )
            connection.execute(text(f'DROP DATABASE IF EXISTS "{name}"'))
    finally:
        engine.dispose()


def test_capture_requires_environment_id(pg_engine):
    scratch_url = _create_scratch_database()
    try:
        env = {**os.environ, "DATABASE_URL": scratch_url}
        env.pop("ENVIRONMENT_ID", None)
        result = subprocess.run(
            [sys.executable, "scripts/capture_schema_inventory.py"],
            cwd=REPOSITORY_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 1
        assert "ENVIRONMENT_ID" in result.stderr
    finally:
        _drop_scratch_database(scratch_url)


def test_capture_produces_checksummed_structure_only_inventory(pg_engine):
    from alembic.config import Config

    from alembic import command

    scratch_url = _create_scratch_database()
    try:
        os.environ["_ALEMBIC_DATABASE_URL"] = scratch_url
        alembic_cfg = Config(str(REPOSITORY_ROOT / "alembic.ini"))
        alembic_cfg.set_main_option("script_location", str(REPOSITORY_ROOT / "alembic"))
        command.upgrade(alembic_cfg, "head")

        env = {
            **os.environ,
            "DATABASE_URL": scratch_url,
            "ENVIRONMENT_ID": "pytest-scratch",
        }
        result = subprocess.run(
            [sys.executable, "scripts/capture_schema_inventory.py"],
            cwd=REPOSITORY_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0

        inventory = json.loads(result.stdout)
        assert inventory["environment_id"] == "pytest-scratch"
        assert inventory["postgres_major_version"] == 16
        assert len(inventory["schema_checksum_sha256"]) == 64
        assert set(inventory["schema"]) == {"users", "grants", "notifications", "stats"}

        # Satır verisi/secret asla çıktıda olmamalı; şema tanımı dışında
        # hiçbir şey (bağlantı bilgisi, tam sürüm string'i dahil) yazılmamalı.
        assert scratch_url not in result.stdout
        assert "compiled by" not in result.stdout
    finally:
        _drop_scratch_database(scratch_url)
