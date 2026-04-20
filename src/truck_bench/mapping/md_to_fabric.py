"""Convert a ``ParsedOntology`` (from Markdown) into a Fabric-ready config.

The output has the same shape consumed by
``fabric_client.definition_builder.build_from_config``:

.. code:: python

    {
        "name": "Truck_Logistics",
        "description": "...",
        "tablePrefix": "trk",
        "entities": [
            {
                "name": "Terminal",
                "keyProperty": "terminal_id",
                "tableName": "trk_terminal",
                "seedFile": "terminals.jsonl",
                "properties": [{"name": "...", "valueType": "..."}, ...],
            },
            ...
        ],
        "relationships": [
            {"name": "truck_home_terminal", "source": "Truck", "target": "Terminal",
             "contextEntity": "Truck", "contextTable": "trk_truck",
             "sourceKeyColumns": "truck_id", "targetKeyColumns": "home_terminal_id"},
            ...
        ],
    }

Relationships are derived from the parsed FK references. For each
``(source_entity, fk_field, target_entity)`` triple the mapper emits a
relationship whose context table is the source table, wiring the source
PK to the FK column in the source and the target PK to the target side.
"""

from __future__ import annotations

import re

from ..markdown_parser.model import Field, ParsedEntity, ParsedOntology


def _snake(name: str) -> str:
    s = re.sub(r"(?<=[a-z0-9])([A-Z])", r"_\1", name)
    s = re.sub(r"(?<=[A-Z])([A-Z][a-z])", r"_\1", s)
    return s.lower()


def _pluralize(snake: str) -> str:
    """Produce the conventional plural for a seed filename.

    Most trucking entities in the seed set use simple plurals (``trucks.jsonl``,
    ``drivers.jsonl``, ``loads.jsonl``). A handful use compound names kept
    as-is (``maintenance_events.jsonl``, ``service_tickets.jsonl``,
    ``driver_hos_logs.jsonl``).
    """
    # Words that need their own plural rule
    irregular = {
        "maintenance_event": "maintenance_events",
        "service_ticket": "service_tickets",
        "driver_hos_log": "driver_hos_logs",
    }
    if snake in irregular:
        return irregular[snake]
    if snake.endswith("y"):
        return snake[:-1] + "ies"
    if snake.endswith("s") or snake.endswith("x"):
        return snake + "es"
    return snake + "s"


def _derive_relationship_name(source: ParsedEntity, fk_field: Field, target: ParsedEntity) -> str:
    """Produce a stable, human-readable relationship name.

    The FK column name is almost always of the form ``<role>_<target>_id``
    (``home_terminal_id``, ``origin_terminal_id``) or just ``<target>_id``
    (``driver_id``). We strip the trailing ``_id`` and prepend the source
    entity in snake_case so edges are unique even when two FKs point to
    the same target (e.g. ``route_origin_terminal`` vs
    ``route_destination_terminal``).
    """
    base = fk_field.name
    if base.endswith("_id"):
        base = base[:-3]
    return f"{_snake(source.name)}_{base}"


def build_ontology_config(
    parsed: ParsedOntology,
    *,
    display_name: str = "Truck_Logistics",
    description: str = "Long-haul trucking ontology (11 entities, ~20 relationships)",
    table_prefix: str = "trk",
    entity_table_overrides: dict[str, str] | None = None,
    entity_seed_overrides: dict[str, str] | None = None,
    skip_entities: set[str] | None = None,
) -> dict:
    """Produce the Fabric-ready ontology config dict."""
    table_overrides = entity_table_overrides or {}
    seed_overrides = entity_seed_overrides or {}
    skip = skip_entities or set()

    # -- Entities ---------------------------------------------------------
    entities: list[dict] = []
    for e in parsed.entities:
        if e.name in skip:
            continue
        if not e.primary_key:
            raise ValueError(
                f"Entity '{e.name}' has no primary key; cannot map to Fabric entity. "
                "Mark one field with '(PK)' in the Markdown spec."
            )
        snake = _snake(e.name)
        table_name = table_overrides.get(e.name, f"{table_prefix}_{snake}")
        seed_file = seed_overrides.get(e.name, f"{_pluralize(snake)}.jsonl")

        properties = [
            {"name": f.name, "valueType": f.fabric_value_type}
            for f in e.fields
        ]

        pk = e.primary_key
        entities.append({
            "name": e.name,
            "tableName": table_name,
            "seedFile": seed_file,
            "keyProperty": pk[0] if len(pk) == 1 else pk,
            "properties": properties,
        })

    # -- Relationships ----------------------------------------------------
    relationships: list[dict] = []
    seen_names: set[str] = set()

    entity_by_name = {e.name: e for e in parsed.entities if e.name not in skip}
    table_by_entity = {e["name"]: e["tableName"] for e in entities}

    for src_entity, fk_field, tgt_entity in parsed.foreign_keys():
        if src_entity.name in skip or tgt_entity.name in skip:
            continue
        if src_entity.name not in entity_by_name or tgt_entity.name not in entity_by_name:
            continue

        rel_name = _derive_relationship_name(src_entity, fk_field, tgt_entity)
        if rel_name in seen_names:
            continue
        seen_names.add(rel_name)

        src_pk = src_entity.primary_key[0]
        tgt_pk = tgt_entity.primary_key[0]

        relationships.append({
            "name": rel_name,
            "source": src_entity.name,
            "target": tgt_entity.name,
            "contextEntity": src_entity.name,
            "contextTable": table_by_entity[src_entity.name],
            "sourceKeyColumns": src_pk,
            "targetKeyColumns": fk_field.name,
        })

    return {
        "name": display_name,
        "description": description,
        "tablePrefix": table_prefix,
        "entities": entities,
        "relationships": relationships,
    }
