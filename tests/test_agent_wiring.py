"""Unit tests for R01 — agent wiring must use canonical tableName."""

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


def _naked_selected_tables(cfg: dict) -> list[str]:
    """Exact logic from scripts/05_setup_agents.py so this test is a
    true regression guard against drift."""
    return [e["tableName"] for e in cfg["entities"]]


def test_naked_selection_matches_canonical_table_names(config: dict) -> None:
    selected = set(_naked_selected_tables(config))
    canonical = {e["tableName"] for e in config["entities"]}
    assert selected == canonical


def test_all_entities_have_table_name(config: dict) -> None:
    for entity in config["entities"]:
        assert entity.get("tableName"), f"{entity['name']} missing tableName"


def test_expected_truck_tables_present(config: dict) -> None:
    selected = set(_naked_selected_tables(config))
    for required in ("trk_truck", "trk_driver_hos_log",
                     "trk_maintenance_event", "trk_service_ticket"):
        assert required in selected, f"NakedAgent would not see {required}"
