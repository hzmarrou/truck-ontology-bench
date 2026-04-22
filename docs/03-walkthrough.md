# 03 — Walkthrough

A narrative first-run guide. Read this once before you touch the
terminal; follow it step-by-step on the run. Every command produces
an artifact you can inspect; every step has a UI verification you can
do in the Fabric portal.

If something goes sideways, jump to
[`05-troubleshooting.md`](05-troubleshooting.md) — nearly every known
failure mode is already catalogued there.

## Prerequisites (one-time)

You need:

* **Python 3.11+** and [`uv`](https://docs.astral.sh/uv/) (or plain
  `pip`).
* A **Microsoft Fabric capacity** (F2+ or P1+) with [Fabric Data Agent
  tenant settings](https://learn.microsoft.com/en-us/fabric/data-science/data-agent-tenant-settings)
  enabled, including "Capacities can be designated as Fabric Copilot
  capacities" and cross-geo processing/storing for AI.
* An **Entra service principal** that is **Admin on the target Fabric
  workspace**. No tenant-wide app role is required. See the
  least-privilege matrix in the repo root [`README.md`](../README.md).
* A **Lakehouse** inside that workspace (do *not* use the auto-created
  lakehouse that an ontology provisions for itself).

Clone, create a virtualenv, install, copy `.env.example` → `.env`
with your five values:

```bash
git clone https://github.com/hzmarrou/truck-ontology-bench
cd truck-ontology-bench
uv venv
uv pip install -e .[dev]
cp .env.example .env
# edit .env
```

Sanity check: `pytest -q` → 50 passed.

## Stage 01 — Parse the markdown ontology

Nothing Fabric-specific happens here. This stage validates that the
markdown spec parses and the Fabric config is structurally sound.

```bash
python scripts/01_parse_md.py
```

Expected stdout:

```
Parsed 11 entities, 19 relationships from input/schema/ontology.md
Wrote outputs/parsed_ontology.json
Wrote outputs/ontology_summary.txt
```

**Verify:** `outputs/ontology_summary.txt` lists 11 entities including
`Truck`, `Trip`, `Driver`, `Terminal`.

## Stage 02 — Build the Fabric config

```bash
python scripts/02_build_mapping.py
```

Expected stdout ends with:

```
Ontology: Truck_Logistics  (11 entities, 19 relationships)
  entity: Terminal              table=trk_terminal      ...
  ...
Wrote outputs/ontology-config.json
```

If the mapping report at the end of the output lists skipped
relationships, rerun with `--strict` to fail fast and fix the cause.

**Verify:** `outputs/ontology-config.json` contains an `entities`
array of 11 objects, each with a `tableName` starting `trk_`, and a
`relationships` array of 19 objects. This is the artifact every
downstream Fabric step reads.

## Stage 03 — Create the ontology in Fabric

This is the first stage that talks to Fabric. Expect 2–3 minutes on
F2 capacity.

```bash
python scripts/03_setup.py
```

What happens, in order:

1. Cleanup of stale artifacts from previous runs (exact-match
   manifest; won't touch unrelated artifacts in a shared workspace).
2. Ontology created via REST (`POST /ontologies`, followed by LRO
   poll). Fabric's name reservation sometimes lags the create, so the
   script retries on 409 Conflict with backoff.
3. Entity + relationship schema pushed as a base64-encoded definition
   part.
4. A Livy Spark session opens; Delta tables are created and JSONL
   seed files loaded.
5. The definition is re-fetched, bindings + contextualizations are
   added, and the final definition is pushed.

Expected stdout ends with `Setup complete. State -> outputs/_state.json`.

**Verify in the Fabric UI:**

* Open the target workspace. You should see a new **Ontology** item
  named `Truck_Logistics`.
* You should see an auto-provisioned **Graph model** of the same
  name. (Fabric creates a second companion Lakehouse alongside it —
  this is expected; leave it alone.)
* Open your target Lakehouse → Tables. You should see 11 tables
  prefixed `trk_`: `trk_truck`, `trk_driver`, `trk_trip`, …

If anything fails, see
[`05-troubleshooting.md`](05-troubleshooting.md) — especially the
"403 on PUT /ontologies" and "409 Conflict on create_ontology"
entries.

## Stage 04 — Refresh + validate the graph

```bash
python scripts/04_refresh_and_validate.py
```

Two things happen:

1. A graph-model refresh is triggered (`jobs/instances?jobType=
   RefreshGraph`). The LRO poller waits for `status=Completed`.
2. Every `gql-queries/*.gql` is executed and its row count is
   printed.

Expected stdout includes lines like:

```
Graph model: Truck_Logistics  (...)
Triggering graph refresh...
  refresh attempt 1/2...
  refresh status: Completed

--- cq01.gql ---
  CQ1: How many entity nodes are loaded in the graph?
  total_nodes
  -----------
  960
  (1 rows)
...
Results: 11 passed, 0 failed out of 11  -> outputs/_validation.json
```

If the first refresh returns `Cancelled`, the script waits 60 s and
retries once. If both attempts are cancelled, use the Fabric UI's
"Refresh now" button on the graph model and rerun with
`--skip-refresh`. This is an acknowledged platform quirk; see
[`05-troubleshooting.md`](05-troubleshooting.md#graph-refresh-auto-cancelled).

### If the refresh hits `TimeoutError` after 30 minutes

This is a different failure from `Cancelled`. The heartbeat
prints `still InProgress` for the whole 30-minute window, then the
script raises `TimeoutError: Graph refresh exceeded 1800s timeout`.
Known Fabric preview bug: the refresh job actually finishes and
materialises the graph, but its status endpoint never transitions to
`Completed`.

**Recovery — one command:**

```bash
python scripts/04_refresh_and_validate.py --skip-refresh
```

If `cq01.gql` reports ≈ 960 nodes, the data is fine and you can
continue to Stage 05. If it reports 0 nodes, the refresh really did
fail; click `Refresh now` in the Fabric UI and rerun with
`--skip-refresh` again once the UI says the refresh completed.

**Do not pass `--skip-refresh` on the first run.** A fresh workspace
needs the initial refresh to actually do its work; skipping it on day
1 leaves you with an empty graph and no signal about why.

**Verify in the Fabric UI:**

* Open the graph model; paste any `gql-queries/cq*.gql` contents into
  the query editor; run. The row counts should match what the script
  printed.

## Stage 05 — Provision the two Data Agents

```bash
python scripts/05_setup_agents.py
```

Expected stdout:

```
Lakehouse: ... (id)
Ontology:  Truck_Logistics (id)

[1] Provisioning NakedAgent...
Updated agent metadata: NakedAgent (<guid>)
Updated definition for: NakedAgent

[2] Provisioning OntologyAgent...
Updated agent metadata: OntologyAgent (<guid>)
Updated definition for: OntologyAgent

Data agent setup complete.
```

**Verify in the Fabric UI:**

* Workspace items now include two `Data Agent`s: `NakedAgent` and
  `OntologyAgent`. Open each and check the "Data sources" tab:
  NakedAgent should have exactly one source (the Lakehouse);
  OntologyAgent should have exactly one source (the ontology).

## Stage 06 — Run the notebook

Data agents require a **user identity** to chat with, so this step
runs in a Fabric notebook rather than from the service principal.

1. In your workspace, **Upload** `notebooks/compare_agents_fabric.ipynb`.
2. Open the uploaded notebook and attach the target Lakehouse as the
   **default** Lakehouse (sidebar → Lakehouses → + Add → star).
3. Run all cells. On an F2 capacity, the 18-question loop takes
   5–10 minutes.
4. When the last cell finishes, a file
   `Files/truck/_agent_comparison.json` appears in the Lakehouse. It
   contains:
   * `scenariosSha256` + `scenariosPayload` (the hash-locked question
     bank).
   * 18 per-question rows with `scenario_id`, the two agents'
     answers, and a Boolean / None verdict from the lexical scorer.

Download that file to your local `outputs/_agent_comparison.json`
(OneLake Explorer or the Fabric UI both work).

## Stage 07 — Score locally

```bash
python scripts/06_score.py
```

The scorer verifies `scenariosSha256` against the embedded payload,
then runs the 7-dimension evaluator. Output:

```
# NakedAgent vs OntologyAgent — scorecard
| Scenario | Domain | Naked | Ontology | Winner | Notes |
...

## Summary
| Agent    | Score | Max | Accuracy |
| Naked    | 30    | 37  | 81%      |
| Ontology | 30    | 37  | 81%      |
```

The markdown scorecard lands in `outputs/scorecard.md`; the JSON
variant in `outputs/scorecard.json` carries the same rows plus the
embedded payload so future re-scoring is reproducible.

## What works and what does not

This benchmark is deliberately chosen to expose both sides. What the
current Fabric IQ preview produces on this set (at the time of this
repo) is:

**Works well (both agents):**

* Sanity questions (Q01–Q03), every multi-hop traversal in the set
  (Q04–Q11), the ambiguity-friendly phrasing cases, and the
  one-relationship graph questions.

**Genuinely rough — Fabric GQL engine limitations (not agent quality):**

These are **engine-level rejections**. Running `cq08.gql`, `cq10.gql`,
and `cq11.gql` by hand via `scripts/04_refresh_and_validate.py`
returns `syntax error or access rule violation` directly from
`executeQuery`. The OntologyAgent's refusals on Q12 / Q15 / Q07 are
it correctly recognising that the engine below cannot execute the
pattern. This is a platform gap, not an agent authoring gap.

* **Substring / pattern match** (`LIKE '%H%'` — Q07, cq08). Needed
  for "loads requiring the hazmat 'H' endorsement". Fabric GQL does
  not accept `LIKE` today. SQL handles it trivially.
* **Anti-join** (`WHERE NOT EXISTS { MATCH ... }` — Q12, cq11).
  Needed for "trucks that have never had a maintenance event". Not
  accepted in Fabric GQL. SQL handles it with `LEFT JOIN ... IS
  NULL`.
* **Conditional aggregation** (`CASE WHEN … THEN … END` inside
  `SUM()` — Q15, cq10). Needed for "maintenance spend per 10k miles
  by truck make" and for on-time rates. Not accepted in Fabric GQL.
  SQL handles it directly.

All three patterns are specified in ISO GQL 2024 and supported by
Neo4j Cypher, TigerGraph, Memgraph, and ArangoDB. The gap is specific
to Fabric's preview dialect.

**Separate issue — refresh LRO control plane:**

The graph refresh REST endpoint often leaves its LRO status at
`InProgress` long after the actual refresh has finished — observed
30+ minutes on F16 with only ~960 rows. The data is correctly
materialised (run `scripts/04_refresh_and_validate.py --skip-refresh`
and check `cq01.gql`'s node count to confirm). This breaks any
automation that waits for `status=Completed`.

**Numeric precision — a separate weakness:**

* On Q13 (on-time rate) both agents often return fractions
  (`0.0`, `1.0`) instead of the expected percentage. The numeric-gold
  scorer dimension catches this; without it the lexical scorer would
  rate both agents correct.

**Where the OntologyAgent is genuinely better:**

* Ambiguity framing (Q16 — "active trucks could mean any of three
  things"). The agent clarifies instead of silently picking one
  interpretation. The NakedAgent picks `status='active'` literally
  and returns zero.
* Guardrail behaviour on action-oriented questions (Q18 — "dispatch
  this truck"). The agent refuses to execute and surfaces
  preconditions (HOS, truck availability). The NakedAgent only
  refuses; it does not list the preconditions.

**Where the NakedAgent is genuinely better:**

* Exactly the two GQL-gap cases above (Q12, Q15). On those, SQL is
  the right tool today.

The honest summary: on the questions this benchmark measures, the two
agents are interchangeable for the easy two-thirds and diverge on
specific, identifiable cases. Whether the ontology is worth adopting
depends on whether the governance, audit-trail, and consistent
terminology benefits (not measured here) matter to your use case.
Capsule 22 of the source material lays this out in more detail.

## Where to go next

* [`04-schema-reference.md`](04-schema-reference.md) if you want to
  add your own scenarios or entities.
* [`05-troubleshooting.md`](05-troubleshooting.md) for any error you
  actually hit.
