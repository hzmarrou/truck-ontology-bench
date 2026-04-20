"""Unit tests for the Markdown-to-Fabric mapping."""

from __future__ import annotations

from pathlib import Path

import pytest

from truck_bench.mapping import build_ontology_config
from truck_bench.markdown_parser import parse_markdown


ROOT = Path(__file__).resolve().parents[1]
MD_PATH = ROOT / "input" / "schema" / "ontology.md"


@pytest.fixture(scope="module")
def config() -> dict:
    return build_ontology_config(parse_markdown(MD_PATH))


def test_produces_eleven_entities(config: dict) -> None:
    assert len(config["entities"]) == 11


def test_every_entity_has_table_and_seed_and_key(config: dict) -> None:
    for e in config["entities"]:
        assert e["tableName"].startswith("trk_")
        assert e["seedFile"].endswith(".jsonl")
        assert e["keyProperty"]
        assert e["properties"]


def test_nineteen_relationships(config: dict) -> None:
    assert len(config["relationships"]) == 19


def test_relationship_names_are_unique(config: dict) -> None:
    names = [r["name"] for r in config["relationships"]]
    assert len(names) == len(set(names)), "duplicate relationship names"


def test_route_has_two_terminal_relationships(config: dict) -> None:
    route_rels = [r for r in config["relationships"]
                  if r["source"] == "Route" and r["target"] == "Terminal"]
    names = {r["name"] for r in route_rels}
    assert names == {"route_origin_terminal", "route_destination_terminal"}


def test_trip_has_five_outgoing_relationships(config: dict) -> None:
    trip_rels = [r for r in config["relationships"] if r["source"] == "Trip"]
    targets = {r["target"] for r in trip_rels}
    assert targets == {"Driver", "Truck", "Trailer", "Load", "Route"}


def test_relationship_context_and_keys(config: dict) -> None:
    # trip_driver relationship: context table is trk_trip, source key is trip_id,
    # target key is driver_id (the FK column on Trip).
    rel = next(r for r in config["relationships"] if r["name"] == "trip_driver")
    assert rel["contextTable"] == "trk_trip"
    assert rel["sourceKeyColumns"] == "trip_id"
    assert rel["targetKeyColumns"] == "driver_id"


def test_table_prefix_override() -> None:
    parsed = parse_markdown(MD_PATH)
    cfg = build_ontology_config(parsed, table_prefix="fleet")
    assert all(e["tableName"].startswith("fleet_") for e in cfg["entities"])


def test_skip_entities() -> None:
    parsed = parse_markdown(MD_PATH)
    cfg = build_ontology_config(parsed, skip_entities={"ServiceTicket"})
    names = {e["name"] for e in cfg["entities"]}
    assert "ServiceTicket" not in names
    # And no relationship should reference a skipped entity
    for r in cfg["relationships"]:
        assert r["source"] != "ServiceTicket"
        assert r["target"] != "ServiceTicket"
