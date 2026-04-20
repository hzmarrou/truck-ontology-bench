"""Create Lakehouse tables and load seed data via the Livy API.

Supports both CSV and JSONL seed files. The trucking benchmark ships
JSONL natively (one object per line); the loader auto-detects by file
extension or accepts an explicit ``filename_resolver``.
"""

from __future__ import annotations

import csv as csv_mod
import json
import re
from pathlib import Path

from .livy_api import LivyClient


_ONTOLOGY_TYPE_TO_SPARK = {
    "String": "STRING",
    "DateTime": "TIMESTAMP",
    "Date": "DATE",
    "BigInt": "BIGINT",
    "Int": "INT",
    "Double": "DOUBLE",
    "Boolean": "BOOLEAN",
    "Object": "STRING",
}


def _spark_type(ontology_type: str) -> str:
    return _ONTOLOGY_TYPE_TO_SPARK.get(ontology_type, "STRING")


def entity_name_to_table(name: str) -> str:
    """Convert a PascalCase entity name to a snake_case table name."""
    s = re.sub(r"(?<=[a-z0-9])([A-Z])", r"_\1", name)
    s = re.sub(r"(?<=[A-Z])([A-Z][a-z])", r"_\1", s)
    return s.lower().replace(" ", "_")


def create_tables_from_config(
    livy: LivyClient,
    entities_config: list[dict],
    entity_map: dict,
    *,
    if_not_exists: bool = True,
) -> None:
    """Create a Delta table per entity, named per ``entity_map[name]["table"]``."""
    for entity_cfg in entities_config:
        name = entity_cfg["name"]
        table = entity_map[name]["table"]
        cols = ", ".join(
            f"{p['name']} {_spark_type(p['valueType'])}"
            for p in entity_cfg["properties"]
        )
        qualifier = "IF NOT EXISTS " if if_not_exists else ""
        print(f"  Creating table {qualifier.lower()}{table}...")
        livy.sql(f"CREATE TABLE {qualifier}{table} ({cols}) USING DELTA")


def _format_value(value, value_type: str) -> str:
    """Render a Python value as a Spark-SQL literal per its ontology type."""
    if value is None or value == "":
        return "NULL"
    if value_type in ("BigInt", "Int", "Double"):
        return str(value)
    if value_type == "Boolean":
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value).lower()
    if value_type == "DateTime":
        return f"TIMESTAMP '{value}'"
    if value_type == "Date":
        return f"DATE '{value}'"
    # String + everything else — escape single quotes
    s = str(value).replace("'", "''")
    return f"'{s}'"


def _insert_rows(
    livy: LivyClient,
    table: str,
    rows: list[dict],
    entity_cfg: dict,
    batch_size: int = 200,
) -> None:
    entity_cols = [p["name"] for p in entity_cfg["properties"]]
    type_map = {p["name"]: p["valueType"] for p in entity_cfg["properties"]}
    if not rows:
        return

    # Intersect entity columns with row keys so we tolerate extra seed fields
    present_cols = set().union(*(row.keys() for row in rows))
    columns = [c for c in entity_cols if c in present_cols]
    if not columns:
        print(f"  SKIP {table} - no overlapping columns between seed and entity")
        return
    col_list = ", ".join(columns)

    value_rows: list[str] = []
    for row in rows:
        values: list[str] = []
        for col in columns:
            values.append(_format_value(row.get(col), type_map.get(col, "String")))
        value_rows.append("(" + ", ".join(values) + ")")

    print(f"  Loading {len(rows)} rows into {table}...")
    for i in range(0, len(value_rows), batch_size):
        batch = value_rows[i:i + batch_size]
        livy.sql(f"INSERT INTO {table} ({col_list}) VALUES {', '.join(batch)}")


def load_csv_data(
    livy: LivyClient,
    csv_dir: str | Path,
    entities_config: list[dict],
    entity_map: dict,
    *,
    batch_size: int = 200,
    filename_resolver=None,
) -> None:
    """Load per-entity CSVs into their Lakehouse tables via INSERT statements."""
    csv_dir = Path(csv_dir)
    resolver = filename_resolver or (lambda name: f"{name}.csv")

    for entity_cfg in entities_config:
        name = entity_cfg["name"]
        table = entity_map[name]["table"]
        csv_path = csv_dir / (entity_cfg.get("csvFile") or resolver(name))
        if not csv_path.exists():
            print(f"  SKIP {name} - seed file missing: {csv_path}")
            continue
        with open(csv_path, newline="", encoding="utf-8") as f:
            rows = list(csv_mod.DictReader(f))
        _insert_rows(livy, table, rows, entity_cfg, batch_size=batch_size)


def load_jsonl_data(
    livy: LivyClient,
    jsonl_dir: str | Path,
    entities_config: list[dict],
    entity_map: dict,
    *,
    batch_size: int = 200,
    filename_resolver=None,
) -> None:
    """Load per-entity JSONL files into their Lakehouse tables.

    One JSON object per line. Like ``load_csv_data`` the loader tolerates
    extra fields in the seed data that the entity does not model.
    """
    jsonl_dir = Path(jsonl_dir)
    resolver = filename_resolver or (lambda name: f"{name}.jsonl")

    for entity_cfg in entities_config:
        name = entity_cfg["name"]
        table = entity_map[name]["table"]
        jsonl_path = jsonl_dir / (entity_cfg.get("seedFile") or resolver(name))
        if not jsonl_path.exists():
            print(f"  SKIP {name} - seed file missing: {jsonl_path}")
            continue
        rows: list[dict] = []
        with open(jsonl_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rows.append(json.loads(line))
        _insert_rows(livy, table, rows, entity_cfg, batch_size=batch_size)


def drop_tables(livy: LivyClient, tables: list[str]) -> None:
    for t in tables:
        try:
            livy.sql(f"DROP TABLE IF EXISTS {t}")
            print(f"  dropped {t}")
        except Exception as e:  # noqa: BLE001
            print(f"  WARN: could not drop {t}: {e}")
