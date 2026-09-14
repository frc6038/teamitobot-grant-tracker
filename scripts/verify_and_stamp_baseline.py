"""Production cutover: doğrula ve baseline'a stamp'le.

`DATABASE_URL=<production-url> alembic stamp head` çıplak haliyle riskli:
production şeması ile baseline migration'ın (9ffc96b8fba3) beklediği şema
arasında kolon/type/nullable/constraint/index farkı varsa fark edilmeden
yanlış revizyon işaretlenmiş olur. Bu script önce gerçek şemayı
EXPECTED_SCHEMA sözleşmesiyle karşılaştırır, eşleşmiyorsa hiçbir şey
yazmadan durur; eşleşiyorsa `alembic stamp head` çalıştırır.

EXPECTED_SCHEMA, database.py'deki ORM modellerinden DEĞİL, doğrudan
alembic/versions/9ffc96b8fba3_*.py migration dosyasından elle çıkarılmıştır
(bkz. tests/postgres/test_schema_contract.py, sözleşmeyi ORM'den bağımsız
olarak gerçek bir migration çalıştırmasına karşı doğrular).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import Inspector

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

EXPECTED_SCHEMA = {
    "users": {
        "columns": {
            "id": {"type": "INTEGER", "nullable": False, "autoincrement": True},
            "chat_id": {"type": "BIGINT", "nullable": False, "autoincrement": False},
            "username": {
                "type": "VARCHAR(255)",
                "nullable": True,
                "autoincrement": False,
            },
            "is_active": {"type": "BOOLEAN", "nullable": True, "autoincrement": False},
            "is_subscribed": {
                "type": "BOOLEAN",
                "nullable": True,
                "autoincrement": False,
            },
            "total_scrapes": {
                "type": "INTEGER",
                "nullable": False,
                "autoincrement": False,
            },
            "created_at": {
                "type": "TIMESTAMP",
                "nullable": True,
                "autoincrement": False,
            },
        },
        "primary_key": ("id",),
        "unique_constraints": frozenset(),
        "foreign_keys": frozenset(),
        "indexes": frozenset(
            {("ix_users_chat_id", ("chat_id",), True, "btree", None, ())}
        ),
    },
    "grants": {
        "columns": {
            "id": {"type": "INTEGER", "nullable": False, "autoincrement": True},
            "text": {"type": "VARCHAR(1000)", "nullable": True, "autoincrement": False},
            "title": {
                "type": "VARCHAR(1000)",
                "nullable": True,
                "autoincrement": False,
            },
            "start_date": {"type": "DATE", "nullable": True, "autoincrement": False},
            "end_date": {"type": "DATE", "nullable": True, "autoincrement": False},
            "url": {"type": "VARCHAR(2000)", "nullable": True, "autoincrement": False},
            "detected_at": {
                "type": "TIMESTAMP",
                "nullable": True,
                "autoincrement": False,
            },
        },
        "primary_key": ("id",),
        "unique_constraints": frozenset(),
        "foreign_keys": frozenset(),
        "indexes": frozenset(
            {("ix_grants_detected_at", ("detected_at",), False, "btree", None, ())}
        ),
    },
    "notifications": {
        "columns": {
            "id": {"type": "INTEGER", "nullable": False, "autoincrement": True},
            "user_id": {"type": "INTEGER", "nullable": False, "autoincrement": False},
            "grant_id": {"type": "INTEGER", "nullable": False, "autoincrement": False},
            "sent_at": {"type": "TIMESTAMP", "nullable": True, "autoincrement": False},
        },
        "primary_key": ("id",),
        "unique_constraints": frozenset({("grant_id", "user_id")}),
        "foreign_keys": frozenset(
            {
                ("grant_id", "grants", "id"),
                ("user_id", "users", "id"),
            }
        ),
        "indexes": frozenset(),
    },
    "stats": {
        "columns": {
            "id": {"type": "INTEGER", "nullable": False, "autoincrement": True},
            "total_scrapes": {
                "type": "INTEGER",
                "nullable": True,
                "autoincrement": False,
            },
            "total_notifications": {
                "type": "INTEGER",
                "nullable": True,
                "autoincrement": False,
            },
            "total_users": {
                "type": "INTEGER",
                "nullable": True,
                "autoincrement": False,
            },
            "started_at": {
                "type": "TIMESTAMP",
                "nullable": True,
                "autoincrement": False,
            },
            "last_scrape_at": {
                "type": "TIMESTAMP",
                "nullable": True,
                "autoincrement": False,
            },
        },
        "primary_key": ("id",),
        "unique_constraints": frozenset(),
        "foreign_keys": frozenset(),
        "indexes": frozenset(),
    },
}


def describe_actual_schema(inspector: Inspector, table_names) -> dict:
    """Verilen tablolar için gerçek veritabanı şemasını EXPECTED_SCHEMA ile
    aynı şekilde tanımlar."""

    schema = {}
    for table_name in table_names:
        columns = {
            col["name"]: {
                "type": str(col["type"]),
                "nullable": col["nullable"],
                "autoincrement": bool(col.get("autoincrement")),
            }
            for col in inspector.get_columns(table_name)
        }
        primary_key = tuple(
            inspector.get_pk_constraint(table_name)["constrained_columns"] or []
        )
        unique_constraints = frozenset(
            tuple(sorted(unique["column_names"]))
            for unique in inspector.get_unique_constraints(table_name)
        )
        foreign_keys = frozenset(
            (
                fk["constrained_columns"][0],
                fk["referred_table"],
                fk["referred_columns"][0],
            )
            for fk in inspector.get_foreign_keys(table_name)
        )
        # Bir unique constraint'in arkasındaki otomatik index'i ayrı bir
        # index gibi saymamak için dışarıda bırakıyoruz; hem unique hem
        # non-unique index'ler (ör. ix_grants_detected_at) dahil. Ad,
        # access method (btree/hash/gin/...) ve partial predicate de dahil
        # ediliyor; aksi halde aynı isimde ama farklı davranışlı bir index
        # (ör. WHERE predicate'li veya hash tabanlı) fark edilmeden geçer.
        indexes = frozenset(
            (
                index["name"],
                tuple(index["column_names"]),
                index["unique"],
                index.get("dialect_options", {}).get("postgresql_using", "btree"),
                index.get("dialect_options", {}).get("postgresql_where"),
                tuple(index.get("include_columns") or ()),
            )
            for index in inspector.get_indexes(table_name)
            if not index.get("duplicates_constraint")
        )

        schema[table_name] = {
            "columns": columns,
            "primary_key": primary_key,
            "unique_constraints": unique_constraints,
            "foreign_keys": foreign_keys,
            "indexes": indexes,
        }
    return schema


def diff_schema(expected: dict, actual: dict) -> list[str]:
    """İki şema tanımını karşılaştırır, insan tarafından okunabilir fark
    listesi döner (production verisi/URL'i içermez). Boş liste = eşleşiyor."""

    mismatches = []

    for table_name, expected_table in expected.items():
        if table_name not in actual:
            mismatches.append(f"tablo eksik: {table_name}")
            continue

        actual_table = actual[table_name]

        for column_name, expected_column in expected_table["columns"].items():
            actual_column = actual_table["columns"].get(column_name)
            if actual_column is None:
                mismatches.append(f"{table_name}.{column_name}: kolon eksik")
                continue
            if actual_column["type"] != expected_column["type"]:
                mismatches.append(
                    f"{table_name}.{column_name}: type beklenen="
                    f"{expected_column['type']} gerçek={actual_column['type']}"
                )
            if actual_column["nullable"] != expected_column["nullable"]:
                mismatches.append(
                    f"{table_name}.{column_name}: nullable beklenen="
                    f"{expected_column['nullable']} gerçek={actual_column['nullable']}"
                )
            if actual_column["autoincrement"] != expected_column["autoincrement"]:
                mismatches.append(
                    f"{table_name}.{column_name}: autoincrement beklenen="
                    f"{expected_column['autoincrement']} "
                    f"gerçek={actual_column['autoincrement']}"
                )

        extra_columns = set(actual_table["columns"]) - set(expected_table["columns"])
        for column_name in sorted(extra_columns):
            mismatches.append(f"{table_name}.{column_name}: beklenmeyen ekstra kolon")

        if actual_table["primary_key"] != expected_table["primary_key"]:
            mismatches.append(
                f"{table_name}: primary key beklenen={expected_table['primary_key']} "
                f"gerçek={actual_table['primary_key']}"
            )
        if actual_table["unique_constraints"] != expected_table["unique_constraints"]:
            mismatches.append(
                f"{table_name}: unique constraint uyuşmuyor "
                f"(beklenen={sorted(expected_table['unique_constraints'])}, "
                f"gerçek={sorted(actual_table['unique_constraints'])})"
            )
        if actual_table["foreign_keys"] != expected_table["foreign_keys"]:
            mismatches.append(
                f"{table_name}: foreign key uyuşmuyor "
                f"(beklenen={sorted(expected_table['foreign_keys'])}, "
                f"gerçek={sorted(actual_table['foreign_keys'])})"
            )
        if actual_table["indexes"] != expected_table["indexes"]:
            mismatches.append(
                f"{table_name}: index uyuşmuyor "
                f"(beklenen={sorted(expected_table['indexes'])}, "
                f"gerçek={sorted(actual_table['indexes'])})"
            )

    for table_name in set(actual) - set(expected):
        mismatches.append(f"beklenmeyen ekstra tablo: {table_name}")

    return mismatches


def main() -> int:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("DATABASE_URL tanımlı değil.", file=sys.stderr)
        return 1

    sys.path.insert(0, str(REPOSITORY_ROOT))
    os.environ.setdefault("TELEGRAM_BOT_TOKEN", "schema-verify-tooling-placeholder")

    engine = create_engine(database_url)
    try:
        inspector = inspect(engine)
        # Sadece beklenen tabloları değil, public schema'daki TÜM tabloları
        # inceliyoruz; aksi halde diff_schema()'nın "beklenmeyen ekstra
        # tablo" kontrolü hiçbir zaman tetiklenmez (alembic_version hariç,
        # o baseline'ın parçası değil, stamp'in kendisi tarafından yazılır).
        # Eksik bir beklenen tabloyu inspect etmeye çalışıp NoSuchTableError
        # patlatmamak için sadece gerçekten var olan tabloları describe
        # ediyoruz; diff_schema() eksik tabloyu zaten kendisi yakalıyor.
        table_names = set(inspector.get_table_names()) - {"alembic_version"}
        actual = describe_actual_schema(inspector, table_names)
    finally:
        engine.dispose()

    mismatches = diff_schema(EXPECTED_SCHEMA, actual)
    if mismatches:
        print("❌ Şema baseline ile eşleşmiyor, stamp uygulanmadı:", file=sys.stderr)
        for mismatch in mismatches:
            print(f"  - {mismatch}", file=sys.stderr)
        return 1

    print("✅ Şema baseline ile eşleşiyor, 'alembic stamp head' uygulanıyor...")

    from alembic.config import Config

    from alembic import command

    os.environ["_ALEMBIC_DATABASE_URL"] = database_url
    alembic_cfg = Config(str(REPOSITORY_ROOT / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(REPOSITORY_ROOT / "alembic"))
    command.stamp(alembic_cfg, "head")

    print("✅ Stamp tamamlandı.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
