"""Unit tests for the Markdown ontology parser."""

from __future__ import annotations

from pathlib import Path

import pytest

from truck_bench.markdown_parser import parse_markdown
from truck_bench.markdown_parser.model import Field, ParsedEntity, ParsedOntology


ROOT = Path(__file__).resolve().parents[1]
MD_PATH = ROOT / "input" / "schema" / "ontology.md"


@pytest.fixture(scope="module")
def ontology() -> ParsedOntology:
    assert MD_PATH.exists(), f"ontology fixture not found: {MD_PATH}"
    return parse_markdown(MD_PATH)


def test_title_captured(ontology: ParsedOntology) -> None:
    assert "Trucking" in ontology.title


def test_exactly_eleven_entities(ontology: ParsedOntology) -> None:
    names = [e.name for e in ontology.entities]
    expected = {
        "Terminal", "Truck", "Trailer", "Driver", "Customer",
        "Route", "Load", "Trip", "MaintenanceEvent", "ServiceTicket", "DriverHOSLog",
    }
    assert set(names) == expected
    assert len(names) == 11


def test_primary_keys_detected(ontology: ParsedOntology) -> None:
    assert ontology.entity_by_name("Terminal").primary_key == ["terminal_id"]
    assert ontology.entity_by_name("Trip").primary_key == ["trip_id"]
    assert ontology.entity_by_name("DriverHOSLog").primary_key == ["hos_log_id"]


def test_foreign_keys_parsed(ontology: ParsedOntology) -> None:
    trip = ontology.entity_by_name("Trip")
    fk_targets = {f.references_entity for f in trip.fields if f.references_entity}
    assert fk_targets == {"Driver", "Truck", "Trailer", "Load", "Route"}


def test_field_type_normalization() -> None:
    # Directly exercise the type mapper via a Field instance.
    f = Field(name="n", raw_type="int", description="")
    assert f.fabric_value_type == "BigInt"
    assert Field(name="x", raw_type="float", description="").fabric_value_type == "Double"
    assert Field(name="x", raw_type="string", description="").fabric_value_type == "String"
    assert Field(name="x", raw_type="boolean", description="").fabric_value_type == "Boolean"
    assert Field(name="x", raw_type="date", description="").fabric_value_type == "DateTime"
    assert Field(name="x", raw_type="string[]", description="").fabric_value_type == "String"


def test_foreign_keys_aggregate(ontology: ParsedOntology) -> None:
    fks = ontology.foreign_keys()
    # 19 FK columns across all entities (matches the Relationship Diagram in the MD)
    assert len(fks) == 19
    # Terminal and Customer are root referentials -> zero FKs leaving them
    for e in ontology.entities:
        if e.name in ("Terminal", "Customer"):
            assert not any(f.references_entity for f in e.fields)
