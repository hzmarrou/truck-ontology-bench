"""Dataclasses representing a parsed Markdown ontology.

The model is deliberately domain-neutral. It carries just enough to
drive a Fabric-ready ontology config: class names, field names, types,
primary keys, foreign-key references, and human-readable descriptions.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


_MARKDOWN_TYPE_TO_FABRIC = {
    # Canonical forms
    "string": "String",
    "int": "BigInt",
    "integer": "BigInt",
    "bigint": "BigInt",
    "long": "BigInt",
    "float": "Double",
    "double": "Double",
    "decimal": "Double",
    "numeric": "Double",
    "boolean": "Boolean",
    "bool": "Boolean",
    "date": "DateTime",
    "datetime": "DateTime",
    "timestamp": "DateTime",
    "uuid": "String",
    # Arrays — stored as string (JSON array) in Lakehouse
    "string[]": "String",
    "int[]": "String",
}


@dataclass
class Field:
    """A single attribute of an entity as declared in the Markdown spec."""

    name: str
    raw_type: str
    description: str = ""
    is_primary_key: bool = False
    references_entity: str | None = None  # e.g. "Terminal" when raw_type mentions FK -> Terminal

    @property
    def fabric_value_type(self) -> str:
        """Map the Markdown-declared type to a Fabric ontology ``valueType``."""
        core = self.raw_type.lower().split()[0].strip()
        # strip trailing (PK) / (FK) etc.
        core = core.rstrip(" ,;")
        return _MARKDOWN_TYPE_TO_FABRIC.get(core, "String")


@dataclass
class ParsedEntity:
    """An entity class declared in the Markdown ontology."""

    name: str
    description: str = ""
    fields: list[Field] = field(default_factory=list)

    @property
    def primary_key(self) -> list[str]:
        return [f.name for f in self.fields if f.is_primary_key]

    def field_by_name(self, name: str) -> Field | None:
        return next((f for f in self.fields if f.name == name), None)


@dataclass
class ParsedOntology:
    """Complete parsed Markdown ontology."""

    title: str
    source_path: str
    entities: list[ParsedEntity] = field(default_factory=list)

    def entity_by_name(self, name: str) -> ParsedEntity | None:
        return next((e for e in self.entities if e.name == name), None)

    def foreign_keys(self) -> list[tuple[ParsedEntity, Field, ParsedEntity]]:
        """Return (source_entity, fk_field, target_entity) triples for every FK."""
        out: list[tuple[ParsedEntity, Field, ParsedEntity]] = []
        for e in self.entities:
            for f in e.fields:
                if f.references_entity:
                    target = self.entity_by_name(f.references_entity)
                    if target:
                        out.append((e, f, target))
        return out

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    @property
    def summary(self) -> str:
        lines = [
            f"Ontology: {self.title}",
            f"Source:   {self.source_path}",
            f"Entities: {len(self.entities)}",
            "",
        ]
        for e in self.entities:
            pk = ",".join(e.primary_key) or "(no PK)"
            fks = sum(1 for f in e.fields if f.references_entity)
            lines.append(f"  {e.name:25s} fields={len(e.fields):3d}  PK={pk}  FKs={fks}")
        return "\n".join(lines)
