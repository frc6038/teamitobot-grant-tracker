"""
database.py'deki init_db() migration gate'inin gerçek revizyon kontrolünü
doğrulayan testler (sadece alembic_version tablosunun varlığına değil)
"""

import os
import uuid

import pytest
from sqlalchemy import create_engine, text

from database import init_db

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")


def _maintenance_url(test_database_url):
    return test_database_url.rsplit("/", 1)[0] + "/postgres"


def _create_scratch_database():
    name = f"itobot_initdb_{uuid.uuid4().hex[:12]}"
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


def _init_db_against(database_url):
    """init_db()'yi verilen DATABASE_URL'e karşı, database.py'nin engine'ini
    o URL'e yeniden bağlayarak çalıştırır."""

    import database as database_module

    original_engine = database_module.engine
    database_module.engine = create_engine(database_url)
    try:
        init_db()
    finally:
        database_module.engine.dispose()
        database_module.engine = original_engine


def test_init_db_rejects_empty_database(pg_engine):
    scratch_url = _create_scratch_database()
    try:
        with pytest.raises(RuntimeError, match="beklenen Alembic revizyonunda değil"):
            _init_db_against(scratch_url)
    finally:
        _drop_scratch_database(scratch_url)


def test_init_db_rejects_stale_unknown_revision(pg_engine):
    scratch_url = _create_scratch_database()
    try:
        engine = create_engine(scratch_url)
        try:
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "CREATE TABLE alembic_version "
                        "(version_num VARCHAR(32) NOT NULL PRIMARY KEY)"
                    )
                )
                connection.execute(
                    text("INSERT INTO alembic_version VALUES ('deadbeef0000')")
                )
        finally:
            engine.dispose()

        with pytest.raises(RuntimeError, match="deadbeef0000"):
            _init_db_against(scratch_url)
    finally:
        _drop_scratch_database(scratch_url)


def test_init_db_accepts_correct_head(pg_engine):
    from alembic.config import Config

    from alembic import command

    scratch_url = _create_scratch_database()
    try:
        alembic_cfg = Config(os.path.join(REPO_ROOT, "alembic.ini"))
        alembic_cfg.set_main_option(
            "script_location", os.path.join(REPO_ROOT, "alembic")
        )
        os.environ["_ALEMBIC_DATABASE_URL"] = scratch_url
        command.upgrade(alembic_cfg, "head")

        _init_db_against(scratch_url)
    finally:
        _drop_scratch_database(scratch_url)


def test_init_db_error_never_contains_database_url(pg_engine):
    """Hata mesajı, migrate edilmemiş durumda bile URL/credential içermemeli."""

    scratch_url = _create_scratch_database()
    secret_marker = scratch_url.split("://", 1)[1].split("@")[0]
    try:
        with pytest.raises(RuntimeError) as excinfo:
            _init_db_against(scratch_url)

        assert secret_marker not in str(excinfo.value)
    finally:
        _drop_scratch_database(scratch_url)
