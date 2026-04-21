# 04 — Schema reference

Field-by-field reference for the three authored artifacts in this
repo:

* [`scenarios/truck_scenarios.json`](#scenario-schema) — the 18
  benchmark questions and their gold answers.
* [`input/schema/ontology.md`](#ontology-markdown-format) — the
  source-of-truth ontology spec.
* [`gql-queries/*.gql`](#gql-query-file-format) — competency queries
  run by `scripts/04_refresh_and_validate.py`.

## Scenario schema

Each element of `scenarios/truck_scenarios.json` is a JSON object with
the fields below. The dataclass in
`src/truck_bench/scoring/scenarios.py` tolerates extra keys — only the
fields listed here are read.

| Field | Type | Required | Description |
|---|---|---|---|
| `scenario_id` | string | ✓ | Unique identifier (e.g. `"Q01"`). Used as the join key between notebook rows and scenarios; duplicates fail hard. |
| `domain` | string | ✓ | One of `sanity`, `multi_hop`, `graph`, `governed_metric`, `ambiguity`, `guardrail`. Controls grouping in the scorecard. |
| `user_question` | string | ✓ | The plain-English question the agent is asked. |
| `required_scope_tables` | string[] |   | Lakehouse tables the scorer expects to see referenced in the answer or SQL. Contributes to the `tables_correct` dimension. |
| `gold_label` | string |   | The canonical metric name the scenario is about (e.g. `on_time_delivery_rate`). Empty for ambiguity / guardrail scenarios. |
| `explanation` | string |   | Human note about what the scenario is meant to catch. Not scored; shown to the critic. |
| `action_policy` | string |   | `recommend_only` (default) or `execute`. The scorer awards the `guardrail_respected` dimension when the agent refused to claim execution. |
| `ambiguity_expected` | boolean |   | When `true`, the scorer awards `ambiguity_detected` if the agent flagged the ambiguity. |
| `required_relationships` | string[] |   | Ontology relationship names the scorer expects to see. Contributes to `relationships_correct`. |
| `expected_join_hops` | integer |   | Informational; not scored today. Used by the scenario-audit script. |
| `naked_agent_trap` | string |   | Prose describing the specific wrong-path a naked-schema agent tends to take. Not scored; helps a reviewer understand the scenario's intent. |
| `ontology_signals` | string[] |   | Must-mention tokens. Every token must appear in the agent answer (case + separator insensitive) for the `signals_correct` dimension to pass. Empty list → dimension is N/A. |
| `gold_numeric_value` | number \| null |   | Deterministic numeric gold for governed-metric scenarios. When set, the `numeric_correct` dimension passes if the agent's answer contains any number within `gold_numeric_tolerance_pct` of this value. |
| `gold_numeric_tolerance_pct` | number |   | Tolerance as a percentage (e.g. `1.0` = ±1 %). Defaults to 1.0. |
| `gold_numeric_description` | string |   | Human note about what the gold number represents and how it was computed. |

### Adding a new scenario

1. Append a new object to `scenarios/truck_scenarios.json`.
2. Pick a unique `scenario_id` (Q19 is the next free slot).
3. Put the tokens you expect in every correct answer in
   `ontology_signals`. Keep the list small (2–4 tokens); a long list
   punishes correct answers that paraphrase.
4. For governed-metric scenarios, compute `gold_numeric_value` once
   by running the expected query by hand and record how you computed
   it in `gold_numeric_description`. Without this, the scorer can't
   distinguish a correct number from a wrong one.
5. Re-run the pipeline so the next notebook run hashes the new
   payload and `scripts/06_score.py` accepts it.

## Ontology markdown format

`input/schema/ontology.md` is parsed by
`src/truck_bench/markdown_parser/parser.py`. The parser is
deliberately minimalist — it expects a specific shape and ignores
unknown content.

### Structure

```markdown
# Entity Name

Optional description paragraph.

## Fields

- `field_name`: `type` (PK|FK|required|optional) — optional description
- `another_field`: `type` ...
```

### Recognised field attributes

* `PK` — marks the primary key. **Every entity must have exactly
  one.** Missing it silently yields an empty graph (no nodes at all
  for that entity); the F-item hardening added an explicit check.
* `FK(Target)` — marks a foreign key. `Target` is the name of another
  entity in this file. The parser emits a relationship edge from this
  entity to `Target`; the edge name is derived from the field name.
* `required` / `optional` — bindings-time only; does not affect the
  ontology shape.

### Recognised type tokens

`string`, `int`, `integer`, `bigint`, `long`, `float`, `double`,
`decimal`, `bool`, `boolean`, `date`, `datetime`, `timestamp`,
`uuid` (treated as string).

### Section: Relationship Diagram

Optional `## Relationship Diagram` section with a Mermaid or ASCII
block. Informational only; not parsed for edges. Edges come from
`FK(...)` annotations alone.

### Adding a new entity

1. Add a new `# EntityName` block. Include exactly one field
   annotated `(PK)`.
2. Add any `FK(...)` fields pointing at entities that also exist in
   the file.
3. Rerun `python scripts/01_parse_md.py` and inspect
   `outputs/ontology_summary.txt`.
4. Rerun `python scripts/02_build_mapping.py --strict` to confirm no
   relationships were silently dropped.

The test in `tests/test_markdown_parser.py` pins the current 11
entities / 19 FKs; extending it is fine, changing the existing
invariants will fail the suite.

## GQL query file format

Each `gql-queries/*.gql` is a plain text file with a header + a
query. The format:

```gql
// <one-line title>
// <optional multi-line description>
MATCH ...
RETURN ...
```

Rules:

* Lines starting with `//` are header comments. `scripts/
  04_refresh_and_validate.py` prints them above the result table so a
  reader can match columns to intent without re-reading the source.
* Everything else is the query body, passed verbatim to the graph
  model's `executeQuery` endpoint.
* Files are discovered with `glob("*.gql")`, sorted by name, and
  executed in order. The convention `cqNN.gql` keeps the listing
  deterministic.

### How they are scored

Each query's pass/fail is recorded in `outputs/_validation.json`:

* Pass: the API returned `status.code == "00000"` and at least one
  row.
* Fail: any other status, or the call raised.

The row count is informational; a query that returns zero rows is
still a "pass" as long as the API call succeeded. Use
`outputs/_validation.json` to diff against previous runs when
debugging.

### Adding a new competency query

1. Create `gql-queries/cq12.gql` (or pick the next free number).
2. Put a `// title` header, optionally a short description comment
   block, then the MATCH / RETURN.
3. Rerun `python scripts/04_refresh_and_validate.py` — the new file
   is picked up automatically.

Good competency queries are **small, one-invariant checks** (e.g.
"every Truck has at least one Terminal edge"). Reserve larger
analytical queries for the scenarios + data agents.

## Where to go next

* [`03-walkthrough.md`](03-walkthrough.md) — if you want to see
  these schemas exercised end-to-end.
* [`05-troubleshooting.md`](05-troubleshooting.md) — for anything
  that breaks in practice.
