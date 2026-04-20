"""03 - Create the ontology in Fabric, load tables from JSONL, push bindings.

Inputs:
    outputs/ontology-config.json        (from 02_build_mapping.py)
    input/data/seed/*.jsonl             (11 trucking seed files)
Outputs:
    outputs/_state.json                 (ontologyId, ontologyName, tables)

Behaviour:
    1. Delete any stale truck artifacts (ontology, graph model, auto-created lakehouse)
    2. Create the new Fabric ontology, push entity + relationship schema
    3. Open a Livy session and drop any pre-existing trk_* tables
    4. Create entity tables from the config, load JSONL seed data
    5. Add data bindings + contextualizations, push final definition
    6. Write outputs/_state.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from truck_bench.fabric_client import FabricConfig  # noqa: E402
from truck_bench.fabric_client.auth import get_headers  # noqa: E402
from truck_bench.fabric_client.definition_builder import (  # noqa: E402
    add_all_bindings,
    add_all_contextualizations,
    build_from_config,
    decode_definition,
    encode_definition,
)
from truck_bench.fabric_client.graph_api import GraphClient  # noqa: E402
from truck_bench.fabric_client.lakehouse_sync import (  # noqa: E402
    create_tables_from_config,
    load_jsonl_data,
)
from truck_bench.fabric_client.livy_api import LivyClient  # noqa: E402
from truck_bench.fabric_client.ontology_api import OntologyClient  # noqa: E402


# -- Helpers ----------------------------------------------------------------

def _list_workspace_items(config: FabricConfig) -> list[dict]:
    items: list[dict] = []
    url = f"{config.api_base}/workspaces/{config.workspace_id}/items"
    params: dict[str, str] = {}
    while url:
        r = requests.get(url, headers=get_headers(config), params=params)
        r.raise_for_status()
        body = r.json()
        items.extend(body.get("value", []))
        url = body.get("continuationUri")
        params = {}
    return items


def _cleanup_stale(
    config: FabricConfig,
    ontology_names: list[str],
    graph_names: list[str],
    lh_prefixes: list[str],
) -> None:
    """Delete ONLY artifacts this repo owns.

    Every artifact is matched by EXACT displayName (ontologies, graph
    models) or by EXACT name-prefix (auto-created lakehouses). No
    substring heuristics — a shared workspace may host other users'
    ontologies with overlapping names.
    """
    items = _list_workspace_items(config)
    headers = get_headers(config)
    deleted_names: set[str] = set()

    owned_ontologies = set(ontology_names)
    owned_graphs = set(graph_names)
    owned_lh_prefixes = tuple(lh_prefixes)

    ont_client = OntologyClient(config)
    for o in ont_client.list_ontologies():
        name = o["displayName"]
        if name in owned_ontologies:
            print(f"  deleting ontology {name} ({o['id']})")
            ont_client.delete_ontology(o["id"])
            deleted_names.add(name)

    gc = GraphClient(config)
    for g in gc.list_graph_models():
        name = g.get("displayName", "")
        if name in owned_graphs:
            print(f"  deleting graph model {name} ({g['id']})")
            try:
                gc.delete_graph_model(g["id"])
            except Exception as exc:  # noqa: BLE001
                print(f"    WARN: {exc}")

    for it in items:
        if it.get("type") != "Lakehouse":
            continue
        if it.get("id") == config.lakehouse_id:
            continue
        name = it.get("displayName", "")
        if any(name.startswith(prefix) for prefix in owned_lh_prefixes):
            print(f"  deleting auto-created lakehouse {name} ({it['id']})")
            try:
                r = requests.delete(
                    f"{config.api_base}/workspaces/{config.workspace_id}/lakehouses/{it['id']}",
                    headers=headers,
                )
                r.raise_for_status()
            except Exception as exc:  # noqa: BLE001
                print(f"    WARN: {exc}")

    if deleted_names:
        print(f"  waiting for {len(deleted_names)} ontology deletion(s) to propagate...")
        deadline = time.time() + 120
        while time.time() < deadline:
            remaining = {o["displayName"] for o in ont_client.list_ontologies()} & deleted_names
            if not remaining:
                print("    deletions propagated.")
                return
            time.sleep(5)
        print(f"    WARN: still seeing {sorted(remaining)} after 120s; continuing anyway.")


def _create_ontology_with_id(
    ont: OntologyClient,
    name: str,
    description: str,
    *,
    conflict_retries: int = 12,
    conflict_backoff: int = 10,
) -> str:
    """Fabric's displayName reservation lags deletion; retry on 409."""
    for attempt in range(1, conflict_retries + 1):
        try:
            result = ont.create_ontology(name, description=description)
        except requests.exceptions.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else None
            if status == 409 and attempt < conflict_retries:
                print(f"  create returned 409 (attempt {attempt}); waiting {conflict_backoff}s before retry...")
                time.sleep(conflict_backoff)
                continue
            raise

        ontology_id = result.get("id")
        if ontology_id:
            return ontology_id
        time.sleep(3)
        for o in ont.list_ontologies():
            if o["displayName"] == name:
                return o["id"]
        raise RuntimeError(f"Could not resolve newly created ontology '{name}'")

    raise RuntimeError(
        f"Could not create ontology '{name}' after {conflict_retries} attempts; "
        f"Fabric kept returning 409 Conflict."
    )


# -- Main -------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", default=REPO_ROOT / "outputs" / "ontology-config.json", type=Path)
    parser.add_argument("--seed-dir", default=REPO_ROOT / "input" / "data" / "seed", type=Path)
    parser.add_argument("--state-out", default=REPO_ROOT / "outputs" / "_state.json", type=Path)
    parser.add_argument("--cleanup-names", nargs="*",
                        default=["Truck_Logistics", "truck_ontology"],
                        help="Ontology displayNames to delete. Exact match only.")
    parser.add_argument("--cleanup-graph-names", nargs="*",
                        default=["Truck_Logistics", "truck_ontology", "truck_graph"],
                        help="Graph-model displayNames to delete. Exact match only.")
    parser.add_argument("--cleanup-lh-prefixes", nargs="*",
                        default=["Truck_Logistics_lh_", "truck_ontology_lh_"],
                        help="Auto-created lakehouse name prefixes to delete.")
    args = parser.parse_args()

    config = FabricConfig.from_env()
    cfg_dict = json.loads(args.config.read_text(encoding="utf-8"))

    print("=" * 60)
    print(f"  SETUP: {cfg_dict['name']}")
    print(f"  workspace={config.workspace_id}  lakehouse={config.lakehouse_id}")
    print("=" * 60)

    # 1. Cleanup — exact-match lists only.
    print("\n[1] Cleaning up stale truck artifacts...")
    _cleanup_stale(
        config,
        ontology_names=args.cleanup_names,
        graph_names=args.cleanup_graph_names,
        lh_prefixes=args.cleanup_lh_prefixes,
    )

    # 2. Build initial schema parts
    print("\n[2] Building initial definition...")
    parts, entity_map, relationship_map = build_from_config(cfg_dict)
    print(f"    {len(entity_map)} entities, {len(relationship_map)} relationships")

    # 3. Create ontology + push schema
    print("\n[3] Creating ontology...")
    ont = OntologyClient(config)
    ontology_id = _create_ontology_with_id(ont, cfg_dict["name"], cfg_dict.get("description", ""))
    print(f"    ontologyId: {ontology_id}")

    print("\n[4] Pushing entity + relationship schema...")
    ont.update_definition(ontology_id, encode_definition(parts))

    # 5. Livy: tables + JSONL loads
    entity_tables = sorted({info["table"] for info in entity_map.values()})

    print(f"\n[5] Opening Livy session...")
    with LivyClient(config) as livy:
        print("\n[5a] Dropping any pre-existing truck tables...")
        for t in entity_tables:
            livy.sql(f"DROP TABLE IF EXISTS {t}")

        print("\n[5b] Creating entity tables...")
        create_tables_from_config(livy, cfg_dict["entities"], entity_map, if_not_exists=False)

        print("\n[5c] Loading JSONL seed data...")
        load_jsonl_data(livy, args.seed_dir, cfg_dict["entities"], entity_map)

    # 6. Re-fetch, add bindings + contextualizations, push final definition
    print("\n[6] Re-fetching definition...")
    raw = ont.get_definition(ontology_id)
    parts = decode_definition(raw)
    print(f"    got {len(parts)} parts")

    print("\n[7] Building data bindings...")
    parts = add_all_bindings(parts, entity_map, cfg_dict["entities"],
                             config.workspace_id, config.lakehouse_id)

    print("\n[8] Building contextualizations...")
    parts = add_all_contextualizations(parts, relationship_map, entity_map,
                                       config.workspace_id, config.lakehouse_id)

    print("\n[9] Pushing final definition (bindings + contextualizations)...")
    ont.update_definition(ontology_id, encode_definition(parts))

    # 10. State
    state = {
        "ontologyId": ontology_id,
        "ontologyName": cfg_dict["name"],
        "workspaceId": config.workspace_id,
        "lakehouseId": config.lakehouse_id,
        "tables": entity_tables,
    }
    args.state_out.parent.mkdir(parents=True, exist_ok=True)
    args.state_out.write_text(json.dumps(state, indent=2), encoding="utf-8")

    print("\n" + "=" * 60)
    print(f"  Setup complete. State -> {args.state_out}")
    print(f"  Next: python scripts/04_refresh_and_validate.py")
    print("=" * 60)


if __name__ == "__main__":
    main()
