"""01 - Parse the Markdown ontology into a neutral ParsedOntology JSON.

Inputs:
    input/schema/ontology.md
Outputs:
    outputs/parsed_ontology.json
    outputs/ontology_summary.txt
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from truck_bench.markdown_parser import parse_markdown  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--md", default=REPO_ROOT / "input" / "schema" / "ontology.md",
                        type=Path, help="Path to the Markdown ontology spec.")
    parser.add_argument("--out", default=REPO_ROOT / "outputs" / "parsed_ontology.json",
                        type=Path)
    parser.add_argument("--summary", default=REPO_ROOT / "outputs" / "ontology_summary.txt",
                        type=Path)
    args = parser.parse_args()

    print(f"Parsing {args.md} ...")
    ontology = parse_markdown(args.md)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    ontology.to_json(args.out)
    args.summary.write_text(ontology.summary, encoding="utf-8")

    print(ontology.summary)
    print()
    print(f"Wrote {args.out}")
    print(f"Wrote {args.summary}")


if __name__ == "__main__":
    main()
