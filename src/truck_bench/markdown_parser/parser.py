"""Parse an ontology specification written in Markdown tables.

Expected document shape (one section per entity):

    # Ontology Schema — <domain>

    ## Entity Definitions

    ---

    ### <EntityName>
    <optional one-line description>

    | Field | Type | Description |
    |---|---|---|
    | <name> | <type> | <description> |
    | ...    | ...    | ...            |

    ---

    ### <NextEntityName>
    ...

``Type`` may include annotations like ``UUID (PK)``, ``UUID (FK -> Terminal)``,
``string[]``. The parser extracts primary-key flags and FK target entities
from those annotations.

Anything outside `### ...` entity sections (headers, diagrams, prose) is
ignored.
"""

from __future__ import annotations

import re
from pathlib import Path

from .model import Field, ParsedEntity, ParsedOntology


_H1_TITLE_RE = re.compile(r"^\s*#\s+(.+?)\s*$")
_ENTITY_HEADER_RE = re.compile(r"^\s*###\s+([A-Z][A-Za-z0-9_]*)\s*$")
_TABLE_ROW_RE = re.compile(r"^\s*\|(.+)\|\s*$")
_SEPARATOR_ROW_RE = re.compile(r"^\s*\|[\s\-:|]+\|\s*$")
_FK_RE = re.compile(
    r"\(\s*FK\s*(?:→|->|-->|=>)\s*([A-Z][A-Za-z0-9_]*)\s*\)",
    re.IGNORECASE,
)
_PK_RE = re.compile(r"\(\s*PK\s*\)", re.IGNORECASE)


def _clean_cell(cell: str) -> str:
    return cell.strip()


def _parse_table(lines: list[str], start: int) -> tuple[list[dict], int]:
    """Parse a Markdown pipe-table starting at ``lines[start]``.

    Returns ``(rows, next_line_index)``. Headers are the first row; a
    separator row (``|---|---|``) is expected on the next line.
    """
    if start >= len(lines) or not _TABLE_ROW_RE.match(lines[start]):
        return [], start

    header_cells = [_clean_cell(c) for c in lines[start].strip().strip("|").split("|")]
    i = start + 1

    # Skip optional separator row
    if i < len(lines) and _SEPARATOR_ROW_RE.match(lines[i]):
        i += 1

    rows: list[dict] = []
    while i < len(lines) and _TABLE_ROW_RE.match(lines[i]):
        cells = [_clean_cell(c) for c in lines[i].strip().strip("|").split("|")]
        if len(cells) < len(header_cells):
            cells += [""] * (len(header_cells) - len(cells))
        rows.append(dict(zip(header_cells, cells[: len(header_cells)])))
        i += 1
    return rows, i


def _parse_field(row: dict) -> Field:
    name = row.get("Field", "").strip()
    raw_type = row.get("Type", "").strip()
    description = row.get("Description", "").strip()

    is_pk = bool(_PK_RE.search(raw_type))
    fk_match = _FK_RE.search(raw_type)
    references = fk_match.group(1) if fk_match else None

    # Strip (PK) / (FK → X) markers from raw_type so downstream mapping sees
    # a clean type. Everything inside parentheses after the first whitespace
    # is removed; the first token is kept as the core type.
    core_type = raw_type.split("(", 1)[0].strip()

    return Field(
        name=name,
        raw_type=core_type or raw_type,
        description=description,
        is_primary_key=is_pk,
        references_entity=references,
    )


def parse_markdown(path: Path) -> ParsedOntology:
    """Parse a Markdown ontology file and return a ``ParsedOntology``."""
    text = Path(path).read_text(encoding="utf-8")
    lines = text.splitlines()

    title = ""
    for line in lines[:20]:
        m = _H1_TITLE_RE.match(line)
        if m:
            title = m.group(1).strip()
            break

    entities: list[ParsedEntity] = []
    i = 0
    while i < len(lines):
        m = _ENTITY_HEADER_RE.match(lines[i])
        if not m:
            i += 1
            continue

        name = m.group(1)
        description_parts: list[str] = []
        i += 1
        # Collect description lines until the next `|` (table start) or the next entity header
        while i < len(lines) and not _TABLE_ROW_RE.match(lines[i]) and not _ENTITY_HEADER_RE.match(lines[i]):
            line = lines[i].strip()
            if line and not line.startswith("#") and not line.startswith("---"):
                description_parts.append(line)
            i += 1

        rows: list[dict] = []
        if i < len(lines) and _TABLE_ROW_RE.match(lines[i]):
            rows, i = _parse_table(lines, i)

        fields = [_parse_field(r) for r in rows if r.get("Field")]
        entity = ParsedEntity(
            name=name,
            description=" ".join(description_parts).strip(),
            fields=fields,
        )
        entities.append(entity)

    return ParsedOntology(title=title, source_path=str(path), entities=entities)
