"""06 - Score the NakedAgent vs OntologyAgent comparison.

Inputs:
    outputs/_agent_comparison.json    (produced by the Fabric notebook)
    scenarios/truck_scenarios.json
    outputs/ontology-config.json
Outputs:
    outputs/scorecard.md
    outputs/scorecard.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from truck_bench.scoring import (  # noqa: E402
    AgentResponse,
    generate_scorecard,
    golden_answers_from_scenarios,
    load_scenarios,
    score_all,
)


_POSITIVE = {"yes", "true", "1"}
_NEGATIVE = {"no", "false", "0"}


def _verdict_of(row: dict, suffix: str) -> str:
    for col in (f"evaluation_judgement_{suffix}",
                f"evaluation_result_{suffix}",
                f"evaluation_status_{suffix}"):
        raw = row.get(col)
        if raw is None:
            continue
        if isinstance(raw, bool):
            return "yes" if raw else "no"
        s = str(raw).strip().lower()
        if not s:
            continue
        if s in _POSITIVE:
            return "yes"
        if s in _NEGATIVE:
            return "no"
        if s == "unclear":
            return "unclear"
    return ""


def _build_response(sid: str, agent_type: str, row: dict) -> AgentResponse:
    ans = row.get(f"actual_answer_{agent_type}", "") or ""
    resp = AgentResponse(
        scenario_id=sid,
        agent_type=agent_type,
        answer=ans,
        reasoning=ans,
        sql_or_gql=ans,
        error=None,
    )
    resp.reasoning = f"__critic_verdict__={_verdict_of(row, agent_type)}\n{ans}"
    return resp


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--comparison", default=REPO_ROOT / "outputs" / "_agent_comparison.json", type=Path)
    parser.add_argument("--scenarios", default=REPO_ROOT / "scenarios" / "truck_scenarios.json", type=Path)
    parser.add_argument("--md-out", default=REPO_ROOT / "outputs" / "scorecard.md", type=Path)
    parser.add_argument("--json-out", default=REPO_ROOT / "outputs" / "scorecard.json", type=Path)
    args = parser.parse_args()

    scenarios = load_scenarios(args.scenarios)
    by_question = {s.user_question: s for s in scenarios}
    golden_answers = golden_answers_from_scenarios(scenarios)

    comparison = json.loads(args.comparison.read_text(encoding="utf-8"))
    per_question = comparison.get("perQuestion", [])

    naked_responses: list[AgentResponse] = []
    ontology_responses: list[AgentResponse] = []

    for row in per_question:
        scenario = by_question.get(row.get("question", ""))
        if not scenario:
            continue
        naked_responses.append(_build_response(scenario.scenario_id, "naked", row))
        ontology_responses.append(_build_response(scenario.scenario_id, "ontology", row))

    naked_scores = score_all(naked_responses, golden_answers)
    onto_scores = score_all(ontology_responses, golden_answers)

    md = generate_scorecard(naked_scores, onto_scores, scenarios)
    args.md_out.parent.mkdir(parents=True, exist_ok=True)
    args.md_out.write_text(md, encoding="utf-8")

    def _dump(results):
        return [
            {k: getattr(r, k) for k in ("scenario_id", "agent_type", "metric_correct",
                                          "tables_correct", "relationships_correct",
                                          "ambiguity_detected", "guardrail_respected",
                                          "signals_correct", "total_score", "max_score",
                                          "notes")}
            for r in results
        ]

    args.json_out.write_text(json.dumps({
        "naked": _dump(naked_scores),
        "ontology": _dump(onto_scores),
    }, indent=2), encoding="utf-8")

    print(md)
    print()
    print(f"Wrote {args.md_out}")
    print(f"Wrote {args.json_out}")


if __name__ == "__main__":
    main()
