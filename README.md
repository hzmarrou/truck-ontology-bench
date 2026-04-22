# truck-bench

End-to-end benchmark that stands up a **long-haul trucking** ontology on
Microsoft Fabric, loads 11 domain tables into a Lakehouse, provisions two
Fabric Data Agents — one schema-only (`NakedAgent`) and one
ontology-grounded (`OntologyAgent`) — and scores them side-by-side on a
curated scenario benchmark.

## What is Fabric IQ?

Fabric IQ is a workload inside Microsoft Fabric that adds a **semantic
layer on top of OneLake data**. You declare, once, the *meaning* of your
domain — the entities that exist, how they relate, how each is
uniquely identified — and multiple query engines (Spark SQL, graph via
GQL) can honour that meaning without reverse-engineering it from column
names.

Concretely, this repo exercises three IQ building blocks:

- **Ontology** — the declarative spec of entities, properties,
  relationships, and entity keys. Authored in Markdown
  (`input/schema/ontology.md`), pushed to Fabric via REST.
- **Graph model** — the instance layer that Fabric auto-projects from
  the ontology. Populated by explicitly triggering a **refresh**
  against the bound Lakehouse tables. Queryable in GQL.
- **Data Agent** — an AI agent, exposed via a `FabricOpenAI` client,
  configured against one or more data sources (the Lakehouse tables
  for `NakedAgent`, the ontology for `OntologyAgent`). It answers
  natural-language questions by emitting a query in the right language
  and running it.

If any of the terms above are unfamiliar, read
[`docs/01-fabric-iq-primer.md`](docs/01-fabric-iq-primer.md) before
continuing. The primer is self-contained and assumes only Fabric
basics (Lakehouse, Spark, capacity).

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
git clone https://github.com/hzmarrou/truck-ontology-bench
cd truck-ontology-bench
uv venv && uv pip install -e .[dev]

cp .env.example .env   # then edit .env with your five values

# Sanity check — no Fabric credentials needed, ~2 seconds.
# Must be green before you run the pipeline.
pytest -q
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

### Query the graph directly with GQL

You can also query the graph model without going through an agent. The
11 competency queries under `gql-queries/` are a good starting point.
For example, `gql-queries/cq02.gql` asks how many trucks call each
terminal home:

```gql
MATCH (t:Truck)-[:truck_home_terminal]->(term:Terminal)
RETURN term.name AS terminal_name, COUNT(t) AS truck_count
GROUP BY terminal_name
ORDER BY truck_count DESC
```

`scripts/04_refresh_and_validate.py` runs every `cq*.gql` against the
graph model and records pass/fail in `outputs/_validation.json`. See
[`gql-queries/README.md`](gql-queries/README.md) for the full list
and [`docs/04-schema-reference.md`](docs/04-schema-reference.md#gql-query-file-format)
for the file format.

### Score the comparison

Download `_agent_comparison.json` from the lakehouse to
`outputs/_agent_comparison.json`, then:

```bash
python scripts/06_score.py
```

Produces `outputs/scorecard.md` and `outputs/scorecard.json`. The
scorer grades each answer along up to seven independent dimensions
(critic verdict, table coverage, relationship coverage, ambiguity
detection, guardrail respect, signal-token coverage, numeric-gold
precision) — see [`docs/02-repo-tour.md`](docs/02-repo-tour.md#scoring-architecture)
for detail.

### What the benchmark actually shows

On the 18 questions in this set, against the current Fabric preview,
**the two agents are roughly tied on aggregate accuracy** and differ
only on specific, identifiable cases. Read
[`docs/03-walkthrough.md`](docs/03-walkthrough.md#what-works-and-what-does-not)
for the honest analysis — where the ontology helps, where a GQL
platform gap makes it hurt, and what the benchmark does *not*
measure.

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

- **403 on the first `POST /ontologies`** — the service principal is
  not Admin on the target workspace. Fix it in *Workspace settings →
  Manage access*.
- **409 Conflict on `create_ontology`** — Fabric's displayName
  reservation lags deletion. The script retries up to 12× with backoff;
  wait it out, or wait 2 minutes and rerun.
- **Graph is empty after setup** — at least one entity is missing a
  `(PK)` annotation, so bindings push fine but the graph materialises
  zero nodes. Check `input/schema/ontology.md`.
- **Graph refresh stuck on `Cancelled`** — Fabric auto-cancels
  overlapping refresh jobs. Wait ~60 s and retry; if it persists, use
  the Fabric UI "Refresh now" and rerun with `--skip-refresh`.
- **`Jinja2` template error in the notebook** — the Fabric runtime
  ships a newer Jinja2 than `fabric-data-agent-sdk` supports. The
  notebook's first cell pins `Jinja2==3.1.6`; make sure it ran.
- **`OpenAI.__init__() got unexpected keyword argument 'data_agent_stage'`** —
  newer SDKs dropped the kwarg. The notebook's `_make_client()` already
  tries with and without; if both fail, pin or upgrade the SDK version.
- **`evaluate_data_agent` with `CANNOT_MERGE_TYPE`** — bug in the SDK's
  Spark writer on mixed-row-shape responses. This repo bypasses it and
  calls `FabricOpenAI` directly for exactly that reason.

Every failure mode this repo has ever hit is catalogued in
[`docs/05-troubleshooting.md`](docs/05-troubleshooting.md) with
symptom → cause → fix → prevention.

## What works well / what's still rough

**Works well on Fabric today:** declaring ontologies via REST, the
ontology-to-Lakehouse sync, running GQL multi-hop traversals on the
graph, provisioning Data Agents, and the two-agent comparison pattern.
50 unit tests run offline in ≈ 2 seconds; no network.

**Still rough — Fabric GQL engine (not agent quality):** hand-written
queries for substring matching (`LIKE`), conditional aggregation
(`CASE WHEN … END` inside `SUM()`), and anti-joins
(`WHERE NOT EXISTS { ... }`) are rejected directly by `executeQuery`
as `syntax error or access rule violation`. These patterns are
specified in ISO GQL 2024 and work in Cypher, TigerGraph, Memgraph,
and ArangoDB; Fabric's dialect is a strict subset today. The
OntologyAgent's refusals on Q07 / Q12 / Q15 are it correctly
recognising that the engine below can't run those patterns — it's not
an agent bug.

**Still rough — graph-refresh control plane:** the refresh LRO
status endpoint can stay `InProgress` for 30+ minutes even after the
refresh has actually finished (observed on F16 with ~960 rows). The
data materialises correctly; only the status never transitions. Run
`python scripts/04_refresh_and_validate.py --skip-refresh` and check
`cq01.gql`'s node count to confirm data is present.

**SDK drift:** `data_agent_stage` kwarg, `Jinja2` version pin, the
`evaluate_data_agent` Spark-write bug — all baked into the notebook
as workarounds.

None of these are secret — every item is documented in
[`docs/05-troubleshooting.md`](docs/05-troubleshooting.md) and called
out with the maturity take in
[`docs/01-fabric-iq-primer.md`](docs/01-fabric-iq-primer.md#maturity--read-before-betting-a-project-on-this).

## Documentation

- [`docs/README.md`](docs/README.md) — reading order + nav.
- [`docs/01-fabric-iq-primer.md`](docs/01-fabric-iq-primer.md) —
  concepts, no Fabric IQ background assumed.
- [`docs/02-repo-tour.md`](docs/02-repo-tour.md) — architecture +
  code map.
- [`docs/03-walkthrough.md`](docs/03-walkthrough.md) — first-run
  playbook against a real Fabric workspace.
- [`docs/04-schema-reference.md`](docs/04-schema-reference.md) —
  scenario JSON, ontology Markdown, and GQL file formats.
- [`docs/05-troubleshooting.md`](docs/05-troubleshooting.md) —
  full runbook.

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for dev setup, test commands,
and PR conventions. Changes to the scenario bank, the ontology
Markdown, or the GQL queries should come with a corresponding update
in `docs/`.

## License

See [`LICENSE`](LICENSE). MIT.
