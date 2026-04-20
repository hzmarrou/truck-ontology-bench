# truck-bench

End-to-end benchmark that stands up a **long-haul trucking** ontology on
Microsoft Fabric, loads 11 domain tables into a Lakehouse, provisions two
Fabric Data Agents — one schema-only (`NakedAgent`) and one
ontology-grounded (`OntologyAgent`) — and scores them side-by-side on a
curated scenario benchmark.

## What you get

- A Markdown-authored ontology (11 entities: Terminal, Truck, Trailer,
  Driver, Customer, Route, Load, Trip, MaintenanceEvent, ServiceTicket,
  DriverHOSLog) parsed into a Fabric ontology
- 11 Lakehouse Delta tables populated from ~960 rows of seed JSONL data
- 19 automatically-derived relationships (based on FK annotations in the
  Markdown), plus 11 GQL competency queries
- Two provisioned Fabric Data Agents:
  - **`NakedAgent`** — wired to the Lakehouse tables only (Spark SQL
    engine; no ontology hints)
  - **`OntologyAgent`** — wired to the ontology **only** (GQL engine;
    the ontology runtime resolves the graph against the same Lakehouse
    through the bindings / contextualizations, but the agent has no
    direct SQL access)
- An 18-scenario benchmark covering sanity, multi-hop traversal,
  graph reasoning, governed metrics (on-time delivery, fleet MPG,
  maintenance cost per 10k miles), ambiguity, and action-guardrail cases
- A multi-dimensional scorecard (Markdown + JSON) combining critic
  verdict, normalized signal-token coverage, and a deterministic
  numeric-gold check. The scorecard embeds the exact scenarios payload
  (with sha256) it was produced against, so re-reviewing the result is
  reproducible.

## Prerequisites

- Python 3.11+ and [`uv`](https://docs.astral.sh/uv/) (or plain `pip`)
- A Microsoft Fabric capacity (F2+ or P1+) with the
  [Fabric Data Agent tenant settings](https://learn.microsoft.com/en-us/fabric/data-science/data-agent-tenant-settings)
  enabled

### Service-principal permissions (least privilege)

The SP is used only by the numbered scripts (`01`..`05`). The
user-context notebook runs as a user, so the SP does NOT need any
OpenAI / Assistants API permissions.

| Resource | Level needed | Why |
|---|---|---|
| Target Fabric workspace | **Admin** | Create/update ontologies, graph models, data agents; run Livy Spark sessions against the lakehouse |
| Target Lakehouse (in that workspace) | inherits from workspace Admin | `scripts/03_setup.py` creates tables + bindings |
| Entra app Graph scopes | *none* | The scripts talk only to the Fabric API (`api.fabric.microsoft.com`); no MS Graph calls |
| Tenant-level app roles | *none required* | `Tenant.ReadWrite.All` is not used. Fabric scopes come from the workspace Admin assignment, not from a tenant-wide app role |

Fabric workspace role mappings are documented in
[Microsoft's workspace-role reference](https://learn.microsoft.com/en-us/fabric/fundamentals/roles-workspaces).
Keep the SP scoped to the benchmark workspace — creating a fresh
workspace per evaluation keeps the blast radius minimal.

## Setup

```bash
git clone <this-repo>
cd truck-ontology-bench
uv venv && uv pip install -e .[dev]

cp .env.example .env   # then edit .env with your five values
```

## Pipeline

Each numbered script has a single job. Run them in order.

```bash
# 1. Parse the Markdown ontology -> outputs/parsed_ontology.json
python scripts/01_parse_md.py

# 2. Merge with the Markdown spec -> outputs/ontology-config.json
python scripts/02_build_mapping.py

# 3. Create the ontology in Fabric, create + load the 11 Delta tables
#    from JSONL seed data, push bindings and contextualizations.
python scripts/03_setup.py

# 4. Trigger a graph refresh, wait for Completed, then run every
#    gql-queries/*.gql. Writes outputs/_validation.json.
python scripts/04_refresh_and_validate.py

# 5. Provision NakedAgent + OntologyAgent, write outputs/_agents.json
python scripts/05_setup_agents.py
```

### Run the agent comparison (Fabric notebook, user context)

Provisioning runs under the service principal. Agent chat requires a
user identity (SP tokens are rejected by the AISkill `/assistants`
endpoint). So the comparison runs in a Fabric notebook:

1. Upload `notebooks/compare_agents_fabric.ipynb` to your workspace
2. Attach your lakehouse as the **default lakehouse** on the notebook
3. (Optional) upload `scenarios/truck_scenarios.json` to
   `Files/truck/agent-comparison-questions.json` in the lakehouse so
   you can iterate on the scenarios without re-uploading the notebook
4. Run all cells

The notebook uses `FabricOpenAI` (OpenAI Assistants API) to call each
agent directly, scores answers with a deterministic token match against
each scenario's `ontology_signals`, and writes
`Files/truck/_agent_comparison.json` to the lakehouse.

### Score the comparison

Download `_agent_comparison.json` from the lakehouse to
`outputs/_agent_comparison.json`, then:

```bash
python scripts/06_score.py
```

Produces `outputs/scorecard.md` and `outputs/scorecard.json`.
`OntologyAgent` should clearly beat `NakedAgent` on multi-hop
traversals, governed-metric scenarios, negation (Q12), and
ambiguity / guardrail cases (Q16, Q17, Q18).

## Repository layout

```
truck-ontology-bench/
├── input/
│   ├── schema/
│   │   ├── ontology.md            Markdown ontology spec (source of truth)
│   │   └── event_schemas.md       Streaming event schemas (out of scope v0.1)
│   └── data/seed/*.jsonl          11 JSONL seed files (~960 rows)
├── scenarios/
│   └── truck_scenarios.json       18 benchmark scenarios
├── gql-queries/
│   └── cq01..11.gql               Competency queries
├── scripts/                       Numbered pipeline entry points
├── notebooks/
│   └── compare_agents_fabric.ipynb  Fabric notebook for agent comparison
├── src/truck_bench/
│   ├── fabric_client/             Fabric REST clients (auth, ontology, graph, Livy, data agent)
│   ├── markdown_parser/           Parse ontology.md into a neutral dataclass model
│   ├── mapping/                   Convert parsed ontology -> Fabric config
│   ├── agents/                    Data Agent provisioning + trucking-tuned instructions
│   └── scoring/                   Scenario-based scorer + scorecard renderer
├── tests/                         pytest unit tests
└── outputs/                       Generated at runtime (gitignored)
```

## Troubleshooting

- **403 on the first `POST /ontologies`** — the service principal is not
  Admin on the target workspace. Fix it in *Workspace settings → Manage
  access*.
- **Graph refresh stuck on `Cancelled`** — Fabric auto-cancels
  overlapping refresh jobs. Wait ~60 s and retry a single clean refresh.
  If the cancellation persists, click "Refresh now" in the Fabric UI.
- **Notebook `evaluate_data_agent` is not used here** — the current
  notebook uses `FabricOpenAI` directly. If you prefer the canonical
  evaluation path, it is documented at
  https://learn.microsoft.com/en-us/fabric/data-science/evaluate-data-agent.
- **`KeyError: 'actual_answer'`** — the notebook here does not use the
  `evaluate_data_agent` critic prompt, so the SDK's `{actual_answer}`
  placeholder constraint does not apply. If you bolt on
  `evaluate_data_agent`, remember the critic prompt may only reference
  `{query}` and `{expected_answer}`.

## License

MIT
