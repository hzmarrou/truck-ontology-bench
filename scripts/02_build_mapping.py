"""02 - Build a Fabric-ready ontology config from the parsed Markdown.

Inputs:
    input/schema/ontology.md
Outputs:
    outputs/ontology-config.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from truck_bench.markdown_parser import parse_markdown  # noqa: E402
from truck_bench.mapping import build_ontology_config  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--md", default=REPO_ROOT / "input" / "schema" / "ontology.md", type=Path)
    parser.add_argument("--name", default="Truck_Logistics")
    parser.add_argument("--description", default="Long-haul trucking ontology benchmark")
    parser.add_argument("--table-prefix", default="trk")
    parser.add_argument("--out", default=REPO_ROOT / "outputs" / "ontology-config.json", type=Path)
    parser.add_argument("--strict", action="store_true",
                        help="Fail if any FK can't be mapped to an entity "
                             "pair or a relationship name collides. "
                             "Recommended for CI / review runs.")
    args = parser.parse_args()

    print(f"Parsing {args.md} ...")
    parsed = parse_markdown(args.md)

    cfg = build_ontology_config(
        parsed,
        display_name=args.name,
        description=args.description,
        table_prefix=args.table_prefix,
        strict=args.strict,
    )

    report = cfg.pop("_mapping_report", {})

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(cfg, indent=2), encoding="utf-8")

    print(f"\nOntology: {cfg['name']}  ({len(cfg['entities'])} entities, "
          f"{len(cfg['relationships'])} relationships)")
    for e in cfg["entities"]:
        print(f"  entity: {e['name']:20s} table={e['tableName']:22s} seed={e['seedFile']:28s} "
              f"properties={len(e['properties'])}  key={e['keyProperty']}")
    print()
    for r in cfg["relationships"]:
        print(f"  rel:    {r['name']:45s} {r['source']:15s} -> {r['target']:15s} ctx={r['contextTable']}")

    if report:
        skipped = (
            len(report.get("unmapped_relationships", []))
            + len(report.get("duplicate_relationships", []))
        )
        if skipped:
            print(f"\nMapping report ({skipped} skipped; rerun with --strict to fail):")
            for r in report.get("unmapped_relationships", []):
                print(f"  - unmapped: {r['source']}.{r['fk']} -> {r['target']}  ({r['reason']})")
            for r in report.get("duplicate_relationships", []):
                print(f"  - duplicate: {r['name']} ({r['source']} -> {r['target']} via {r['fk']})")

    print(f"\nWrote {args.out}")


if __name__ == "__main__":
    main()
