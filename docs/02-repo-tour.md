# 02 — Repo tour

This is the code map. Every script and every package module is listed
below with its role and the test file that locks its contract. Use
this doc when you're about to read the source or submit a PR.

## Top-level layout

```
truck-ontology-bench/
├── .env                       # your credentials (gitignored)
├── .env.example               # template
├── .gitignore
├── CHANGELOG.md
├── CONTRIBUTING.md
├── LICENSE
├── README.md
├── pyproject.toml             # hatchling, Python ≥ 3.11, 3 runtime deps
├── docs/                      # reference documentation (you are here)
├── gql-queries/               # 11 competency queries (cq01..cq11.gql)
├── input/
│   ├── data/seed/*.jsonl      # 11 seed files, ≈960 rows total
│   └── schema/
│       ├── ontology.md        # source-of-truth ontology spec
│       └── event_schemas.md   # informational; not consumed by code
├── notebooks/
│   └── compare_agents_fabric.ipynb   # runs the 18-scenario benchmark
├── outputs/                   # generated at runtime (gitignored)
├── scenarios/
│   └── truck_scenarios.json   # 18 benchmark questions + gold answers
├── scripts/                   # numbered pipeline entry points
└── src/truck_bench/           # the Python package
    ├── agents/
    ├── fabric_client/
    ├── mapping/
    ├── markdown_parser/
    └── scoring/
└── tests/                     # pytest (50 tests, ≈2 s)
```

## The numbered pipeline

Every script is idempotent and writes a machine-readable artifact to
`outputs/`. The happy path is to run them in order; each reads the
artifacts the previous one wrote.

| # | Script | Reads | Writes | Role |
|---|---|---|---|---|
| 01 | `scripts/01_parse_md.py` | `input/schema/ontology.md` | `outputs/parsed_ontology.json`, `outputs/ontology_summary.txt` | Parse the markdown into a neutral dataclass model. No Fabric calls. |
| 02 | `scripts/02_build_mapping.py` | `outputs/parsed_ontology.json` | `outputs/ontology-config.json` | Build the Fabric-ready ontology config. Produces entity tableNames, relationship edges, junction-table context. Fail-fast mode (`--strict`) refuses partial configs. |
| 03 | `scripts/03_setup.py` | `ontology-config.json`, `.env`, seed JSONL | `outputs/_state.json` | Create the ontology in Fabric, load Delta tables, push bindings + contextualizations. Uses shared LRO poller. |
| 04 | `scripts/04_refresh_and_validate.py` | `_state.json`, `gql-queries/*.gql` | `outputs/_validation.json` | Refresh the graph model; run every competency query; pass/fail summary. |
| 05 | `scripts/05_setup_agents.py` | `_state.json`, `ontology-config.json`, `truck_scenarios.json` | `outputs/_agents.json`, `outputs/agent-comparison-questions.json` | Upsert NakedAgent (Lakehouse-only) + OntologyAgent (ontology-only). |
| 06 | `scripts/06_score.py` | `_agent_comparison.json` (from notebook), `truck_scenarios.json` (optional) | `outputs/scorecard.md`, `outputs/scorecard.json` | Multi-dimensional scoring: critic verdict, signals, relationships, ambiguity, guardrail, numeric gold. Verifies `scenariosSha256` hash-lock. |

There is also `scripts/_build_notebook.py` — a utility that
regenerates `notebooks/compare_agents_fabric.ipynb` from source cells.
It does **not** talk to Fabric; run it only when you intentionally
want to change the notebook, then upload the new `.ipynb` to your
workspace.

## The Python package

```
src/truck_bench/
├── agents/              # data-agent provisioning
│   ├── provision.py
│   └── instructions.py  # agent system prompts
├── fabric_client/       # REST clients
│   ├── auth.py
│   ├── config.py
│   ├── data_agent_api.py
│   ├── definition_builder.py
│   ├── graph_api.py
│   ├── lakehouse_sync.py
│   ├── livy_api.py
│   ├── lro.py           # ← shared LRO poller (see below)
│   └── ontology_api.py
├── mapping/
│   ├── md_to_fabric.py  # entities → Fabric config; fail-fast mode
├── markdown_parser/
│   ├── model.py         # dataclasses
│   └── parser.py        # ontology.md → neutral model
└── scoring/
    ├── evaluator.py     # 7-dimension scorer + scorecard renderer
    └── scenarios.py     # Scenario / GoldenAnswer dataclasses
```

### The shared LRO poller

`src/truck_bench/fabric_client/lro.py` is the single implementation of
Fabric's long-running-operation poll loop. Every other client that
accepts a 202 response (`ontology_api`, `graph_api`,
`data_agent_api`, plus the `GraphClient.refresh` job-instance LRO)
delegates to `poll_lro()`. The contract:

* Requires a `Location` header; a 202 without one fails fast.
* Honours `Retry-After` on every poll response, not only the initial
  202.
* Retries transient 429/5xx/network errors up to `network_retries`
  times with exponential backoff.
* Enforces a wall-clock `max_wait_seconds` cap; a wedged LRO raises
  `TimeoutError` instead of blocking forever.
* Accepts a `success_states` set so the same loop handles both the
  operations shape (`Succeeded` + `/result` tail) and the job-instance
  shape (`Completed`, no result tail).

Tests: `tests/test_fabric_client.py` covers all four variants.

### Scoring architecture

`scoring/evaluator.py` scores each agent answer along up to seven
independent dimensions:

1. Critic verdict (yes/no/unclear from the notebook).
2. `metric_correct` — did the agent pick the gold metric?
3. `tables_correct` — did it reference the required tables?
4. `relationships_correct` — did it reference the required relationships?
5. `ambiguity_detected` — did it flag ambiguity when expected?
6. `guardrail_respected` — did it recommend rather than execute?
7. `signals_correct` — did it include every required `ontology_signals`
   token (case + separator insensitive)?
8. `numeric_correct` — does the free-text answer contain a number
   within `gold_numeric_tolerance_pct` of `gold_numeric_value`?

A dimension only contributes to `max_score` when the scenario declares
an expectation for it, so sanity questions and full multi-hop
scenarios share the same scoring code.

`scoring/scenarios.py` defines the dataclasses and the
`load_scenarios()` / `golden_answers_from_scenarios()` helpers. See
[`04-schema-reference.md`](04-schema-reference.md) for the JSON
schema.

## Where each test lives

| Test file | Locks |
|---|---|
| `tests/test_markdown_parser.py` | 11 entities, PK detection, 19 FKs, type normalization |
| `tests/test_mapping.py` | 11 entities / 19 relationships in the Fabric config, naming, Route's split terminals, Trip's five edges |
| `tests/test_agent_wiring.py` | Canonical `tableName` used in datasource elements (F01 regression guard) |
| `tests/test_evaluator.py` | Signal normalization, critic + signals multi-dim scoring, numeric gold tolerance, scorecard rendering |
| `tests/test_fabric_client.py` | Auth cache + refresh margin, 429/5xx retry, LRO Location guard, per-poll Retry-After, timeout, graph-refresh completed-state, data-agent LRO path |
| `tests/test_scorer_lock.py` | Scenario hash integrity, scenario_id uniqueness, row-index validation (F03/F04 contract) |

No test hits the real Fabric API. Everything is stubbed, so `pytest
-q` runs clean offline in about two seconds.

## Where to go next

* [`03-walkthrough.md`](03-walkthrough.md) — take all the above and
  run it end-to-end against your Fabric workspace.
* [`04-schema-reference.md`](04-schema-reference.md) — field-by-field
  spec for scenarios, ontology markdown, and GQL files.
