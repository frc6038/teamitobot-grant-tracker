"""
Production cutover şema doğrulamasının (scripts/verify_and_stamp_baseline.py)
gerçek PostgreSQL'e karşı davranışını doğrulayan testler.

Şemalar burada ORM (database.py/Base.metadata) veya alembic upgrade
kullanılarak DEĞİL, bağımsız ham SQL DDL ile kuruluyor; böylece
karşılaştırma fonksiyonu gerçekten kolon/type/nullable/constraint
farklarını yakalıyor mu diye test edilebiliyor (dairesel doğrulama değil).
"""

import os
import sys
import uuid
from pathlib import Path

from sqlalchemy import create_engine, inspect, text

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT / "scripts"))

from verify_and_stamp_baseline import (  # noqa: E402
    EXPECTED_SCHEMA,
    describe_actual_schema,
    diff_schema,
)

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

INDEPENDENT_LEGACY_DDL = """
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    chat_id BIGINT NOT NULL,
    username VARCHAR(255),
    is_active BOOLEAN,
    is_subscribed BOOLEAN,
    total_scrapes INTEGER NOT NULL,
    created_at TIMESTAMP
);
CREATE UNIQUE INDEX ix_users_chat_id ON users (chat_id);

CREATE TABLE grants (
    id SERIAL PRIMARY KEY,
    text VARCHAR(1000),
    title VARCHAR(1000),
    start_date DATE,
    end_date DATE,
    url VARCHAR(2000),
    detected_at TIMESTAMP
);
CREATE INDEX ix_grants_detected_at ON grants (detected_at);

CREATE TABLE stats (
    id SERIAL PRIMARY KEY,
    total_scrapes INTEGER,
    total_notifications INTEGER,
    total_users INTEGER,
    started_at TIMESTAMP,
    last_scrape_at TIMESTAMP
);

CREATE TABLE notifications (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users (id),
    grant_id INTEGER NOT NULL REFERENCES grants (id),
    sent_at TIMESTAMP,
    CONSTRAINT uq_notification_user_grant UNIQUE (user_id, grant_id)
);
"""


def _maintenance_url(test_database_url):
    return test_database_url.rsplit("/", 1)[0] + "/postgres"


def _create_scratch_database():
    name = f"itobot_schema_{uuid.uuid4().hex[:12]}"
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


def _apply_ddl(database_url, ddl):
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(text(ddl))
    finally:
        engine.dispose()


def _assert_main_refuses_and_does_not_stamp(
    scratch_url, monkeypatch, capsys, expected_stderr_substring
):
    """main()'i gerçek CLI yolundan çalıştırıp exit=1, beklenen redacted
    hata mesajı ve alembic_version tablosunun HİÇ yazılmadığını doğrular."""

    import verify_and_stamp_baseline

    monkeypatch.setenv("DATABASE_URL", scratch_url)
    exit_code = verify_and_stamp_baseline.main()
    assert exit_code == 1
    stderr = capsys.readouterr().err
    assert expected_stderr_substring in stderr

    engine = create_engine(scratch_url)
    try:
        with engine.connect() as connection:
            version_table = connection.execute(
                text("SELECT to_regclass('public.alembic_version')")
            ).scalar()
    finally:
        engine.dispose()
    assert version_table is None


def test_expected_schema_matches_real_baseline_migration(pg_engine):
    """EXPECTED_SCHEMA sözleşmesi, gerçek alembic upgrade head sonucuyla
    (ORM'den değil, migration dosyasından üretilen şemayla) hâlâ eşleşiyor
    mu diye kontrol eder; migration değişip sözleşme unutulursa burada
    kırılır."""

    from alembic.config import Config

    from alembic import command

    scratch_url = _create_scratch_database()
    try:
        os.environ["_ALEMBIC_DATABASE_URL"] = scratch_url
        alembic_cfg = Config(str(REPOSITORY_ROOT / "alembic.ini"))
        alembic_cfg.set_main_option("script_location", str(REPOSITORY_ROOT / "alembic"))
        command.upgrade(alembic_cfg, "head")

        engine = create_engine(scratch_url)
        try:
            inspector = inspect(engine)
            actual = describe_actual_schema(inspector, EXPECTED_SCHEMA.keys())
        finally:
            engine.dispose()

        assert diff_schema(EXPECTED_SCHEMA, actual) == []
    finally:
        _drop_scratch_database(scratch_url)


def test_independent_legacy_fixture_matches_expected_schema(pg_engine):
    """Bağımsız ham SQL fixture'ı, karşılaştırma fonksiyonunu geçmeli."""

    scratch_url = _create_scratch_database()
    try:
        _apply_ddl(scratch_url, INDEPENDENT_LEGACY_DDL)

        engine = create_engine(scratch_url)
        try:
            inspector = inspect(engine)
            actual = describe_actual_schema(inspector, EXPECTED_SCHEMA.keys())
        finally:
            engine.dispose()

        assert diff_schema(EXPECTED_SCHEMA, actual) == []
    finally:
        _drop_scratch_database(scratch_url)


def test_missing_column_is_rejected(pg_engine):
    scratch_url = _create_scratch_database()
    try:
        broken_ddl = INDEPENDENT_LEGACY_DDL.replace("    is_subscribed BOOLEAN,\n", "")
        _apply_ddl(scratch_url, broken_ddl)

        engine = create_engine(scratch_url)
        try:
            inspector = inspect(engine)
            actual = describe_actual_schema(inspector, EXPECTED_SCHEMA.keys())
        finally:
            engine.dispose()

        mismatches = diff_schema(EXPECTED_SCHEMA, actual)
        assert any(
            "users.is_subscribed" in m and "kolon eksik" in m for m in mismatches
        )
    finally:
        _drop_scratch_database(scratch_url)


def test_wrong_column_type_is_rejected(pg_engine):
    scratch_url = _create_scratch_database()
    try:
        broken_ddl = INDEPENDENT_LEGACY_DDL.replace(
            "    chat_id BIGINT NOT NULL,", "    chat_id INTEGER NOT NULL,"
        )
        _apply_ddl(scratch_url, broken_ddl)

        engine = create_engine(scratch_url)
        try:
            inspector = inspect(engine)
            actual = describe_actual_schema(inspector, EXPECTED_SCHEMA.keys())
        finally:
            engine.dispose()

        mismatches = diff_schema(EXPECTED_SCHEMA, actual)
        assert any("users.chat_id" in m and "type" in m for m in mismatches)
    finally:
        _drop_scratch_database(scratch_url)


def test_wrong_nullable_is_rejected(pg_engine):
    scratch_url = _create_scratch_database()
    try:
        broken_ddl = INDEPENDENT_LEGACY_DDL.replace(
            "    total_scrapes INTEGER NOT NULL,\n    created_at TIMESTAMP\n);\n"
            "CREATE UNIQUE INDEX ix_users_chat_id",
            "    total_scrapes INTEGER,\n    created_at TIMESTAMP\n);\n"
            "CREATE UNIQUE INDEX ix_users_chat_id",
        )
        _apply_ddl(scratch_url, broken_ddl)

        engine = create_engine(scratch_url)
        try:
            inspector = inspect(engine)
            actual = describe_actual_schema(inspector, EXPECTED_SCHEMA.keys())
        finally:
            engine.dispose()

        mismatches = diff_schema(EXPECTED_SCHEMA, actual)
        assert any("users.total_scrapes" in m and "nullable" in m for m in mismatches)
    finally:
        _drop_scratch_database(scratch_url)


def test_missing_unique_constraint_is_rejected(pg_engine):
    scratch_url = _create_scratch_database()
    try:
        broken_ddl = INDEPENDENT_LEGACY_DDL.replace(
            ",\n    CONSTRAINT uq_notification_user_grant UNIQUE (user_id, grant_id)",
            "",
        )
        _apply_ddl(scratch_url, broken_ddl)

        engine = create_engine(scratch_url)
        try:
            inspector = inspect(engine)
            actual = describe_actual_schema(inspector, EXPECTED_SCHEMA.keys())
        finally:
            engine.dispose()

        mismatches = diff_schema(EXPECTED_SCHEMA, actual)
        assert any(
            "notifications" in m and "unique constraint" in m for m in mismatches
        )
    finally:
        _drop_scratch_database(scratch_url)


def test_missing_foreign_key_is_rejected(pg_engine):
    scratch_url = _create_scratch_database()
    try:
        broken_ddl = INDEPENDENT_LEGACY_DDL.replace(
            "user_id INTEGER NOT NULL REFERENCES users (id),",
            "user_id INTEGER NOT NULL,",
        )
        _apply_ddl(scratch_url, broken_ddl)

        engine = create_engine(scratch_url)
        try:
            inspector = inspect(engine)
            actual = describe_actual_schema(inspector, EXPECTED_SCHEMA.keys())
        finally:
            engine.dispose()

        mismatches = diff_schema(EXPECTED_SCHEMA, actual)
        assert any("notifications" in m and "foreign key" in m for m in mismatches)
    finally:
        _drop_scratch_database(scratch_url)


def test_missing_non_unique_index_is_rejected(pg_engine, monkeypatch, capsys):
    scratch_url = _create_scratch_database()
    try:
        broken_ddl = INDEPENDENT_LEGACY_DDL.replace(
            "CREATE INDEX ix_grants_detected_at ON grants (detected_at);\n", ""
        )
        _apply_ddl(scratch_url, broken_ddl)
        _assert_main_refuses_and_does_not_stamp(
            scratch_url, monkeypatch, capsys, "grants: index uyuşmuyor"
        )
    finally:
        _drop_scratch_database(scratch_url)


def test_wrong_index_columns_is_rejected(pg_engine, monkeypatch, capsys):
    scratch_url = _create_scratch_database()
    try:
        broken_ddl = INDEPENDENT_LEGACY_DDL.replace(
            "CREATE INDEX ix_grants_detected_at ON grants (detected_at);",
            "CREATE INDEX ix_grants_detected_at ON grants (title);",
        )
        _apply_ddl(scratch_url, broken_ddl)
        _assert_main_refuses_and_does_not_stamp(
            scratch_url, monkeypatch, capsys, "grants: index uyuşmuyor"
        )
    finally:
        _drop_scratch_database(scratch_url)


def test_renamed_index_is_rejected(pg_engine, monkeypatch, capsys):
    """Aynı kolonu/uniqueness'ı kapsayan ama farklı isimli bir index eskiden
    'eşleşiyor' sayılıyordu (sadece column_names+unique karşılaştırılıyordu);
    artık index adı da sözleşmenin parçası."""

    scratch_url = _create_scratch_database()
    try:
        broken_ddl = INDEPENDENT_LEGACY_DDL.replace(
            "CREATE INDEX ix_grants_detected_at ON grants (detected_at);",
            "CREATE INDEX ix_grants_other_name ON grants (detected_at);",
        )
        _apply_ddl(scratch_url, broken_ddl)
        _assert_main_refuses_and_does_not_stamp(
            scratch_url, monkeypatch, capsys, "grants: index uyuşmuyor"
        )
    finally:
        _drop_scratch_database(scratch_url)


def test_partial_index_predicate_is_rejected(pg_engine, monkeypatch, capsys):
    """WHERE predicate'li bir partial index, aynı isim/kolon/uniqueness'a
    sahip olsa bile tam index'ten farklı coverage sağlar; eskiden bu fark
    hiç yakalanmıyordu."""

    scratch_url = _create_scratch_database()
    try:
        broken_ddl = INDEPENDENT_LEGACY_DDL.replace(
            "CREATE INDEX ix_grants_detected_at ON grants (detected_at);",
            "CREATE INDEX ix_grants_detected_at ON grants (detected_at) "
            "WHERE detected_at IS NOT NULL;",
        )
        _apply_ddl(scratch_url, broken_ddl)
        _assert_main_refuses_and_does_not_stamp(
            scratch_url, monkeypatch, capsys, "grants: index uyuşmuyor"
        )
    finally:
        _drop_scratch_database(scratch_url)


def test_hash_index_method_is_rejected(pg_engine, monkeypatch, capsys):
    """Hash tabanlı bir index, planner davranışı btree'den tamamen farklı
    olduğu halde eskiden aynı sayılıyordu; artık access method da
    karşılaştırılıyor."""

    scratch_url = _create_scratch_database()
    try:
        broken_ddl = INDEPENDENT_LEGACY_DDL.replace(
            "CREATE INDEX ix_grants_detected_at ON grants (detected_at);",
            "CREATE INDEX ix_grants_detected_at ON grants USING hash (detected_at);",
        )
        _apply_ddl(scratch_url, broken_ddl)
        _assert_main_refuses_and_does_not_stamp(
            scratch_url, monkeypatch, capsys, "grants: index uyuşmuyor"
        )
    finally:
        _drop_scratch_database(scratch_url)


def test_missing_autoincrement_is_rejected(pg_engine, monkeypatch, capsys):
    """Baseline'da id kolonları sequence-backed (SERIAL); production'da düz
    INTEGER PRIMARY KEY olursa (sequence yok) verifier bunu yakalamalı,
    aksi halde ID otomatik üretilemeyen bir production DB stamp'lenir."""

    scratch_url = _create_scratch_database()
    try:
        broken_ddl = INDEPENDENT_LEGACY_DDL.replace(
            "id SERIAL PRIMARY KEY,\n    chat_id",
            "id INTEGER PRIMARY KEY,\n    chat_id",
        )
        _apply_ddl(scratch_url, broken_ddl)
        _assert_main_refuses_and_does_not_stamp(
            scratch_url, monkeypatch, capsys, "users.id: autoincrement"
        )
    finally:
        _drop_scratch_database(scratch_url)


def test_main_refuses_stamp_when_table_missing(pg_engine, monkeypatch, capsys):
    """main() gerçek CLI yolunda eksik bir tabloyu redacted bir hatayla
    reddetmeli; sadece diff_schema() birim testi değil, uçtan uca kanıt."""

    scratch_url = _create_scratch_database()
    try:
        stats_block = INDEPENDENT_LEGACY_DDL[
            INDEPENDENT_LEGACY_DDL.index(
                "CREATE TABLE stats"
            ) : INDEPENDENT_LEGACY_DDL.index("CREATE TABLE notifications")
        ]
        broken_ddl = INDEPENDENT_LEGACY_DDL.replace(stats_block, "")
        _apply_ddl(scratch_url, broken_ddl)
        _assert_main_refuses_and_does_not_stamp(
            scratch_url, monkeypatch, capsys, "tablo eksik: stats"
        )
    finally:
        _drop_scratch_database(scratch_url)


def test_main_refuses_stamp_when_unexpected_extra_table_exists(
    pg_engine, monkeypatch, capsys
):
    """main() artık sadece beklenen tabloları değil, public schema'daki TÜM
    tabloları inceliyor; production'da baseline'da olmayan bir tablo varsa
    bu da fark edilmeden geçmemeli."""

    scratch_url = _create_scratch_database()
    try:
        extra_table_ddl = (
            INDEPENDENT_LEGACY_DDL
            + "\nCREATE TABLE audit_log (\n    id SERIAL PRIMARY KEY\n);\n"
        )
        _apply_ddl(scratch_url, extra_table_ddl)
        _assert_main_refuses_and_does_not_stamp(
            scratch_url, monkeypatch, capsys, "beklenmeyen ekstra tablo: audit_log"
        )
    finally:
        _drop_scratch_database(scratch_url)


def test_main_refuses_stamp_on_schema_mismatch(pg_engine, monkeypatch, capsys):
    scratch_url = _create_scratch_database()
    try:
        broken_ddl = INDEPENDENT_LEGACY_DDL.replace("    is_subscribed BOOLEAN,\n", "")
        _apply_ddl(scratch_url, broken_ddl)
        _assert_main_refuses_and_does_not_stamp(
            scratch_url, monkeypatch, capsys, "eşleşmiyor"
        )
    finally:
        _drop_scratch_database(scratch_url)


def test_main_stamps_on_schema_match(pg_engine, monkeypatch):
    import verify_and_stamp_baseline

    scratch_url = _create_scratch_database()
    try:
        _apply_ddl(scratch_url, INDEPENDENT_LEGACY_DDL)

        monkeypatch.setenv("DATABASE_URL", scratch_url)
        exit_code = verify_and_stamp_baseline.main()
        assert exit_code == 0

        engine = create_engine(scratch_url)
        try:
            with engine.connect() as connection:
                version = connection.execute(
                    text("SELECT version_num FROM alembic_version")
                ).scalar()
        finally:
            engine.dispose()
        assert version == "9ffc96b8fba3"
    finally:
        _drop_scratch_database(scratch_url)
