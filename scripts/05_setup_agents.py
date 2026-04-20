"""05 - Provision NakedAgent + OntologyAgent in Fabric.

Inputs:
    outputs/_state.json
    outputs/ontology-config.json
    scenarios/truck_scenarios.json
Outputs:
    outputs/_agents.json
    outputs/agent-comparison-questions.json  (convenience copy)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from truck_bench.agents import upsert_naked_agent, upsert_ontology_agent  # noqa: E402
from truck_bench.agents.provision import lookup_lakehouse_display_name  # noqa: E402
from truck_bench.fabric_client import FabricConfig  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--state", default=REPO_ROOT / "outputs" / "_state.json", type=Path)
    parser.add_argument("--config", default=REPO_ROOT / "outputs" / "ontology-config.json", type=Path)
    parser.add_argument("--scenarios", default=REPO_ROOT / "scenarios" / "truck_scenarios.json", type=Path)
    parser.add_argument("--out", default=REPO_ROOT / "outputs" / "_agents.json", type=Path)
    parser.add_argument("--naked-name", default="NakedAgent")
    parser.add_argument("--ontology-name", default="OntologyAgent")
    args = parser.parse_args()

    config = FabricConfig.from_env()
    state = json.loads(args.state.read_text(encoding="utf-8"))
    cfg_dict = json.loads(args.config.read_text(encoding="utf-8"))

    lakehouse_name = lookup_lakehouse_display_name(config)
    print(f"Lakehouse: {lakehouse_name} ({config.lakehouse_id})")
    print(f"Ontology:  {state['ontologyName']} ({state['ontologyId']})")

    entity_tables = [e["tableName"] for e in cfg_dict["entities"]]

    print("\n[1] Provisioning NakedAgent...")
    naked = upsert_naked_agent(
        config=config,
        ontology_config=cfg_dict,
        selected_tables=entity_tables,
        lakehouse_display_name=lakehouse_name,
        name=args.naked_name,
    )

    print("\n[2] Provisioning OntologyAgent...")
    ontology_agent = upsert_ontology_agent(
        config=config,
        ontology_id=state["ontologyId"],
        ontology_name=state["ontologyName"],
        ontology_config=cfg_dict,
        selected_tables=entity_tables,
        lakehouse_display_name=lakehouse_name,
        name=args.ontology_name,
    )

    comp_path = REPO_ROOT / "outputs" / "agent-comparison-questions.json"
    comp_path.write_text(args.scenarios.read_text(encoding="utf-8"), encoding="utf-8")

    out = {
        "workspaceId": config.workspace_id,
        "ontologyId": state["ontologyId"],
        "ontologyName": state["ontologyName"],
        "lakehouseId": config.lakehouse_id,
        "lakehouseName": lakehouse_name,
        "agents": {"naked": naked, "ontology": ontology_agent},
        "scenariosFile": str(comp_path),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=2), encoding="utf-8")

    print("\nData agent setup complete.")
    print(f"  Naked agent:    {naked['displayName']} ({naked['id']})")
    print(f"  Ontology agent: {ontology_agent['displayName']} ({ontology_agent['id']})")
    print(f"  Written to:     {args.out}")
    print("\nNext: open notebooks/compare_agents_fabric.ipynb in Fabric and run all cells.")


if __name__ == "__main__":
    main()
