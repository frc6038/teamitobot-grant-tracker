"""Production şema envanteri yakala (sadece yapı, hiç satır verisi değil).

GRANT-09 review bulgusu: EXPECTED_SCHEMA sözleşmesi migration dosyasından
elle çıkarılmış, fakat gerçek production'ın deployed reality'siyle
karşılaştırıldığına dair bir kanıt/artifact repository'de yok. Bu script
production DATABASE_URL'ine erişimi olan biri tarafından ÇALIŞTIRILIP
çıktısı repository'ye commit edilmelidir; Claude/otomasyon bunu kendi
başına üretemez çünkü gerçek production'a erişimi yoktur.

Kullanım (production erişimi olan biri tarafından, bir kereye mahsus):

    DATABASE_URL=<production-url> ENVIRONMENT_ID=render-prod \
        python scripts/capture_schema_inventory.py > docs/production_schema_inventory.json

Çıktı sadece tablo/kolon/type/nullable/constraint/index YAPISINI içerir;
hiçbir satır verisi veya secret sorgulanmaz/yazılmaz.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect, text

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

from verify_and_stamp_baseline import describe_actual_schema  # noqa: E402


def _to_json_safe(schema: dict) -> dict:
    """frozenset/tuple içeren şema tanımını JSON'a yazılabilir hale getirir."""

    safe = {}
    for table_name, table in schema.items():
        safe[table_name] = {
            "columns": table["columns"],
            "primary_key": list(table["primary_key"]),
            "unique_constraints": sorted(list(c) for c in table["unique_constraints"]),
            "foreign_keys": sorted(list(fk) for fk in table["foreign_keys"]),
            "indexes": sorted(
                [name, list(columns), unique, using, where, list(include)]
                for name, columns, unique, using, where, include in table["indexes"]
            ),
        }
    return safe


def main() -> int:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("DATABASE_URL tanımlı değil.", file=sys.stderr)
        return 1

    environment_id = os.environ.get("ENVIRONMENT_ID")
    if not environment_id:
        print(
            "ENVIRONMENT_ID tanımlı değil (ör. 'render-prod'); bu envanterin "
            "hangi ortamdan alındığını izlenebilir kılmak için zorunludur.",
            file=sys.stderr,
        )
        return 1

    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            # Tam "SELECT version()" çıktısı patch/build/OS/derleyici detayı
            # sızdırır; sadece PostgreSQL major sürümünü tutuyoruz
            # (server_version_num formatı MMmmpp, ör. 160015 -> major 16).
            version_num = connection.execute(text("SHOW server_version_num")).scalar()
            postgres_major_version = int(version_num) // 10000
        inspector = inspect(engine)
        table_names = set(inspector.get_table_names()) - {"alembic_version"}
        schema = describe_actual_schema(inspector, table_names)
    finally:
        engine.dispose()

    safe_schema = _to_json_safe(schema)
    schema_json = json.dumps(safe_schema, sort_keys=True)
    checksum = hashlib.sha256(schema_json.encode()).hexdigest()

    inventory = {
        "captured_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "environment_id": environment_id,
        "postgres_major_version": postgres_major_version,
        "redaction_method": (
            "yalnız information_schema/pg_catalog üzerinden yapı introspection; "
            "hiçbir satır verisi veya secret sorgulanmadı/yazılmadı"
        ),
        "schema_checksum_sha256": checksum,
        "schema": safe_schema,
    }

    print(json.dumps(inventory, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
