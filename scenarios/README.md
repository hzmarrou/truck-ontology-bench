# scenarios/

The 18 benchmark questions the two Data Agents answer. Each scenario
pairs a natural-language `user_question` with the gold signals the
scorer uses to decide whether the answer is correct along up to seven
independent dimensions.

The single file here, `truck_scenarios.json`, is both the notebook's
input (it runs each `user_question` against each agent) and the
scorer's source of truth (it reads every scenario back when grading).

## What's in a scenario

| Column | Role |
|---|---|
| `scenario_id` | Join key between notebook rows and scenarios; must be unique. |
| `domain` | One of `sanity`, `multi_hop`, `graph`, `governed_metric`, `ambiguity`, `guardrail`. |
| `user_question` | The prompt sent to the agent. |
| `required_scope_tables`, `required_relationships` | Must appear in the answer. |
| `gold_label`, `ontology_signals` | Lexical must-mention tokens. |
| `gold_numeric_value` + tolerance | Numeric check for governed-metric scenarios. |
| `ambiguity_expected`, `action_policy` | Behavioural checks. |

**Full field reference** lives in
[`../docs/04-schema-reference.md#scenario-schema`](../docs/04-schema-reference.md#scenario-schema).

## Running the benchmark against these scenarios

The notebook at `../notebooks/compare_agents_fabric.ipynb` reads this
file (or its lakehouse copy) and writes per-question results to
`Files/truck/_agent_comparison.json` on the attached Lakehouse. The
local scorer at `../scripts/06_score.py` verifies the hash-locked
payload and produces the scorecard.

## Adding a new scenario

1. Append a JSON object. Pick the next free `scenario_id` (Q19 today).
2. Keep `ontology_signals` small (2–4 specific tokens). A long list
   punishes correct answers that paraphrase.
3. For governed-metric questions, compute `gold_numeric_value` by
   hand once, document the computation in
   `gold_numeric_description`, and set a realistic
   `gold_numeric_tolerance_pct` (1.0 for ratios, 0.5 for absolute
   counts).
4. Rerun `python scripts/_build_notebook.py` if you want the inline
   fallback in the notebook to match, then re-upload the notebook.
5. Run the notebook + `scripts/06_score.py`; the hash-lock will
   accept the new payload automatically.
