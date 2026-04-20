"""Utility: regenerate the Fabric comparison notebook.

Run:
    python scripts/_build_notebook.py

Rewrites ``notebooks/compare_agents_fabric.ipynb`` from the cell
definitions below.

Design: the notebook calls the two Data Agents through ``FabricOpenAI``
(OpenAI Assistants API surface) and scores answers deterministically via
a separator-normalized token match against each scenario's
``ontology_signals``. No Spark writes / Delta tables / evaluate_data_agent
involvement, so none of the SDK write-path bugs apply.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "notebooks" / "compare_agents_fabric.ipynb"

SCENARIOS_JSON = (REPO / "scenarios" / "truck_scenarios.json").read_text(encoding="utf-8")


def md(text: str) -> dict:
    return {
        "cell_type": "markdown",
        "id": str(uuid.uuid4()),
        "metadata": {},
        "source": text.splitlines(keepends=True),
    }


def code(text: str) -> dict:
    return {
        "cell_type": "code",
        "id": str(uuid.uuid4()),
        "metadata": {},
        "outputs": [],
        "execution_count": None,
        "source": text.splitlines(keepends=True),
    }


cells: list[dict] = []

cells.append(md("""# NakedAgent vs OntologyAgent — truck logistics benchmark

Side-by-side evaluation of two Fabric Data Agents on 18 long-haul trucking scenarios (sanity, multi-hop, graph, governed metrics, ambiguity, guardrails).

## Architecture — two different query engines

`scripts/05_setup_agents.py` wires the two agents so they each go through exactly one data surface:

| Agent | Data source | Query engine | What it "sees" |
|---|---|---|---|
| `NakedAgent` | Lakehouse Delta tables | Spark SQL | 11 raw tables with `_id` FK columns |
| `OntologyAgent` | Ontology (graph model) | GQL | 11 entity types + 19 typed relationships |

The ontology's graph model is populated by `scripts/04_refresh_and_validate.py`, which materializes nodes and edges from the Lakehouse tables via the bindings + contextualizations. Both agents see the *same underlying data*; they just traverse it through different engines.

## How the notebook works

For each scenario the notebook:

1. Sends the question to `NakedAgent` via `FabricOpenAI` and captures the final text reply
2. Does the same for `OntologyAgent`
3. Scores each answer with a deterministic token check — every `ontology_signals` token in the scenario must appear in the response (case + separator insensitive) for the answer to count as correct
4. Emits a side-by-side DataFrame and writes `Files/truck/_agent_comparison.json` to the attached lakehouse

Scoring is reproducible: the same agents + scenarios produce the same scorecard every time.

## Prerequisites

- **Default lakehouse must be attached** — left sidebar -> Lakehouses -> + Add -> star it.
- `NakedAgent` and `OntologyAgent` already provisioned in this workspace (`scripts/05_setup_agents.py`).
- **The graph model must be refreshed since the last lakehouse change.** `OntologyAgent` queries the graph, not the lakehouse directly — stale graph = stale answers. If you just loaded data, run `scripts/04_refresh_and_validate.py` first or click **Refresh now** on the graph model in the Fabric UI.
- The notebook is self-contained — if `Files/truck/agent-comparison-questions.json` is missing, an inline copy of the scenarios is used instead.
"""))

cells.append(md("""## 1. Install the SDK

`Jinja2==3.1.6` is pinned because the Fabric runtime ships a newer Jinja2 that breaks the Data Agent SDK's template rendering."""))
cells.append(code("%pip install -U fabric-data-agent-sdk pandas Jinja2==3.1.6"))

cells.append(md("## 2. Configure the run"))
cells.append(code("""NAKED_AGENT_NAME = "NakedAgent"
ONTOLOGY_AGENT_NAME = "OntologyAgent"
DATA_AGENT_STAGE = "sandbox"   # switch to "production" after publishing

OUTPUT_DIR = "/lakehouse/default/Files/truck"
OUTPUT_FILE = f"{OUTPUT_DIR}/_agent_comparison.json"

MAX_ANSWER_WAIT_SECONDS = 300
RETRIES_PER_QUESTION = 2
"""))

cells.append(md("""## 3. Load the 18-scenario benchmark

Prefers `Files/truck/agent-comparison-questions.json` on the attached lakehouse; falls back to an inline copy if the file is not present."""))
cells.append(code(f"""import json
from pathlib import Path

import pandas as pd

LAKEHOUSE_QUESTIONS_PATH = "/lakehouse/default/Files/truck/agent-comparison-questions.json"

# Raw JSON string so Python does not mis-parse true/false/null as identifiers.
INLINE_SCENARIOS_JSON = r\"\"\"{SCENARIOS_JSON}\"\"\"

def load_scenarios() -> list[dict]:
    path = Path(LAKEHOUSE_QUESTIONS_PATH)
    if path.exists():
        print(f"Loaded scenarios from lakehouse: {{path}}")
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    print("Lakehouse file not found; using inline fallback.")
    return json.loads(INLINE_SCENARIOS_JSON)

scenarios: list[dict] = load_scenarios()
print(f"Loaded {{len(scenarios)}} scenarios")
pd.DataFrame([
    {{"scenario_id": s["scenario_id"], "domain": s["domain"], "question": s["user_question"]}}
    for s in scenarios
])
"""))

cells.append(md("""## 4. Agent wrapper

`ask_agent(name, question)` creates a short-lived thread, posts the question, waits for the run to complete, and returns the agent's final text reply. The constructor tries the current SDK signature first and falls back to a keyword-less form so the notebook works on both old and new SDK versions. Retries cover transient network errors but skip deterministic `TypeError` / `ImportError` failures."""))
cells.append(code("""import time
from fabric.dataagent.client import FabricOpenAI


def _make_client(agent_name: str) -> "FabricOpenAI":
    try:
        return FabricOpenAI(artifact_name=agent_name, data_agent_stage=DATA_AGENT_STAGE)
    except TypeError:
        return FabricOpenAI(artifact_name=agent_name)


def _call_once(agent_name: str, question: str, max_wait: int) -> str:
    client = _make_client(agent_name)
    assistant = client.beta.assistants.create(model="not-used")
    thread = client.beta.threads.create()
    client.beta.threads.messages.create(
        thread_id=thread.id, role="user", content=question
    )
    run = client.beta.threads.runs.create_and_poll(
        thread_id=thread.id, assistant_id=assistant.id
    )
    if run.status != "completed":
        return f"<run {run.status}>"

    # Return only the LATEST assistant message. The Fabric SDK does not always
    # hand back a pristine thread for each threads.create() call; picking by
    # max(created_at) keeps us robust against thread reuse.
    msgs = client.beta.threads.messages.list(thread_id=thread.id)
    assistant_msgs = [m for m in msgs.data if m.role == "assistant"]
    if not assistant_msgs:
        return "<empty>"
    latest = max(assistant_msgs, key=lambda m: getattr(m, "created_at", 0))
    pieces = [c.text.value for c in latest.content if c.type == "text"]
    return "\\n".join(pieces).strip() or "<empty>"


_NON_RETRYABLE = (TypeError, ImportError, AttributeError)


def ask_agent(agent_name: str, question: str,
              max_wait: int = MAX_ANSWER_WAIT_SECONDS,
              retries: int = RETRIES_PER_QUESTION) -> str:
    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            return _call_once(agent_name, question, max_wait)
        except _NON_RETRYABLE as exc:
            return f"<error: {exc}>"
        except Exception as exc:
            last_exc = exc
            if attempt < retries:
                time.sleep(5 * attempt)
    return f"<error: {last_exc}>"
"""))

cells.append(md("""## 5. Scoring helper

An answer is marked correct when every token in the scenario's `ontology_signals` list appears in the answer as a case-insensitive substring, after folding `_` / `-` / `/` / whitespace to a single space. An empty signal list evaluates to `False` (used by ambiguity scenarios where the expected response is prose, not a set of tokens)."""))
cells.append(code("""import re


def _normalize(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"[_\\-/]+", " ", s)
    s = re.sub(r"\\s+", " ", s)
    return s.strip()


def score_answer(answer: str, signals: list[str]) -> dict:
    if not signals:
        return {"correct": False, "matched": [], "missing": [], "signal_count": 0}
    answer_norm = _normalize(answer)
    matched: list[str] = []
    missing: list[str] = []
    for s in signals:
        if _normalize(s) in answer_norm:
            matched.append(s)
        else:
            missing.append(s)
    return {
        "correct": len(missing) == 0,
        "matched": matched,
        "missing": missing,
        "signal_count": len(signals),
    }
"""))

cells.append(md("""## 6. Run the benchmark

Sends all 18 questions to each agent and scores the answers. Expect ~3 minutes per agent on F16 capacity. A failure past the retry budget is recorded in `actual_answer_<agent>` and treated as incorrect; the loop never aborts early."""))
cells.append(code("""from datetime import datetime

per_question: list[dict] = []
for i, scenario in enumerate(scenarios, 1):
    qid = scenario["scenario_id"]
    question = scenario["user_question"]
    signals = scenario.get("ontology_signals", [])
    print(f"[{i}/{len(scenarios)}] {qid} — {question[:70]}")

    naked_answer = ask_agent(NAKED_AGENT_NAME, question)
    ontology_answer = ask_agent(ONTOLOGY_AGENT_NAME, question)

    naked_score = score_answer(naked_answer, signals)
    ontology_score = score_answer(ontology_answer, signals)

    per_question.append({
        "scenario_id": qid,
        "domain": scenario.get("domain", ""),
        "question": question,
        "expected_answer": scenario.get("gold_label", ""),
        "ontology_signals": signals,

        "actual_answer_naked": naked_answer,
        "evaluation_judgement_naked": naked_score["correct"],
        "matched_signals_naked": naked_score["matched"],
        "missing_signals_naked": naked_score["missing"],

        "actual_answer_ontology": ontology_answer,
        "evaluation_judgement_ontology": ontology_score["correct"],
        "matched_signals_ontology": ontology_score["matched"],
        "missing_signals_ontology": ontology_score["missing"],
    })

df_results = pd.DataFrame(per_question)
print(f"\\nCompleted {len(df_results)} scenarios.")
print(
    f"NakedAgent correct:    {int(df_results['evaluation_judgement_naked'].sum())}/{len(df_results)}"
)
print(
    f"OntologyAgent correct: {int(df_results['evaluation_judgement_ontology'].sum())}/{len(df_results)}"
)
"""))

cells.append(md("## 7. Side-by-side view"))
cells.append(code("""display_cols = [
    "scenario_id", "domain", "question",
    "evaluation_judgement_naked",
    "evaluation_judgement_ontology",
    "actual_answer_naked",
    "actual_answer_ontology",
]
df_results[display_cols]
"""))

cells.append(md("## 8. Summary"))
cells.append(code("""def _summary(df: pd.DataFrame, suffix: str) -> dict:
    col = f"evaluation_judgement_{suffix}"
    correct = int(df[col].sum())
    total = len(df)
    return {
        "correctCount": correct,
        "totalQuestions": total,
        "accuracyPct": round(100 * correct / total, 1) if total else 0.0,
    }

naked_summary = _summary(df_results, "naked")
ontology_summary = _summary(df_results, "ontology")

pd.DataFrame({
    "NakedAgent": naked_summary,
    "OntologyAgent": ontology_summary,
})
"""))

cells.append(md("""## 9. Save the JSON report

Produces `Files/truck/_agent_comparison.json` on the attached lakehouse. Download it to your local `truck-ontology-bench/outputs/_agent_comparison.json` and run `python scripts/06_score.py` for the markdown scorecard."""))
cells.append(code("""import os

os.makedirs(OUTPUT_DIR, exist_ok=True)

report = {
    "runAtUtc": datetime.utcnow().isoformat() + "Z",
    "stage": DATA_AGENT_STAGE,
    "scoringMethod": "ontology_signals token match (all tokens must appear, case + separator insensitive)",
    "agents": {
        "naked": {"name": NAKED_AGENT_NAME, **naked_summary},
        "ontology": {"name": ONTOLOGY_AGENT_NAME, **ontology_summary},
    },
    "perQuestion": per_question,
}

with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    json.dump(report, f, indent=2, default=str)

print(f"Saved: {OUTPUT_FILE}")
print(f"Rows:  {len(report['perQuestion'])}")
print(f"Naked    {naked_summary['correctCount']}/{naked_summary['totalQuestions']} ({naked_summary['accuracyPct']}%)")
print(f"Ontology {ontology_summary['correctCount']}/{ontology_summary['totalQuestions']} ({ontology_summary['accuracyPct']}%)")
"""))

cells.append(md("""## 10. What to look for

Because `OntologyAgent` now speaks GQL against the graph and `NakedAgent` speaks SQL against Delta tables, they are two genuinely different query engines. Expect the deltas to reflect that:

**Where OntologyAgent should win**

- **Multi-hop traversals** — Q04 (trip dispatch roll-up), Q10 (Atlanta↔Chicago in both directions), Q11 (miles driven per driver). GQL expresses multi-hop edge traversal naturally; SQL has to chain joins and tends to drop a side.
- **Negation / anti-joins** — Q12 (trucks with no maintenance). Graph `MATCH NOT` patterns are clearer than SQL `LEFT JOIN ... IS NULL`.
- **Ambiguity & guardrails** — Q16 (active trucks), Q17 (late loads), Q18 (dispatch action). The ontology agent has richer semantic context to flag multiple valid definitions.

**Where NakedAgent may win or tie**

- **Sanity questions (Q01–Q03)** — single-table SQL aggregations are trivial. OntologyAgent should tie here; if it loses, the GQL group-by workaround in the instructions is worth checking.
- **Heavy aggregation / math-y metrics** (Q13 on-time rate, Q15 maintenance per 10k miles). GQL aggregations are a documented weak spot in Fabric ontology — this is why the agent instructions include the "Support group by in GQL" nudge from the Fabric tutorial.

**Operational reminders**

- If `OntologyAgent` returns counts that don't match `NakedAgent`'s, first check whether the graph was refreshed since the last lakehouse write. The graph is not live-bound; `scripts/04_refresh_and_validate.py` or **Refresh now** in the UI materialises changes.
- Both agents answer from the *same data*, so a gap that comes from knowing which table/column to use is a genuine ontology win; a gap that comes from the engine's query capability is a platform artifact, not a semantic win.
"""))


notebook = {
    "cells": cells,
    "metadata": {
        "kernelspec": {"display_name": "Synapse PySpark", "language": "Python", "name": "synapse_pyspark"},
        "language_info": {"name": "python"},
        "microsoft": {
            "language": "python",
            "language_group": "synapse_pyspark",
            "ms_spell_check": {"ms_spell_check_language": "en"},
        },
    },
    "nbformat": 4,
    "nbformat_minor": 5,
}

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(notebook, indent=2), encoding="utf-8", newline="\n")
print(f"Wrote {OUT}  ({len(cells)} cells)")
