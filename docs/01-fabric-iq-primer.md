# 01 — Fabric IQ primer

A self-contained introduction to Microsoft Fabric IQ for readers who
know Fabric (Lakehouse, OneLake, Spark, capacity, workspaces) but have
never touched IQ. If a concept is already familiar, skim; nothing here
is load-bearing for running the repo — that's what
[`03-walkthrough.md`](03-walkthrough.md) is for.

## What Fabric IQ is, in one paragraph

Fabric IQ is a workload inside Microsoft Fabric that adds a **semantic
layer on top of OneLake data**. It lets you declare the *meaning* of
your domain — what things exist, how they relate, how they are
identified — once, and then have multiple query engines (SQL, Spark
KQL, graph) honour that meaning without each of them learning it
independently. The bet is that AI agents answering business questions
will make better choices when they read an explicit definition than
when they reverse-engineer one from column names.

Fabric IQ is not a single thing. It's five: the **ontology**, the
**graph model**, **data agents**, **operations agents** (not used in
this repo), and **plan** (also not used here). This repo exercises the
first three.

## The core building blocks

### Ontology

An ontology is a machine-readable map of the business concepts in your
domain. Concretely, it is a definition of:

* **Entities** — the nouns. In this repo: `Truck`, `Trailer`, `Driver`,
  `Trip`, `Route`, and so on. Each entity has a name, a description
  (so an agent knows what it means), and a list of typed **properties**
  (`truck_number`, `status`, `make`, `year`).
* **Relationships** — the verbs. `Trip → Driver` (who drove it),
  `Trip → Route` (what path it took), `Truck → Terminal` (where it
  calls home). Each relationship has a name that a graph query can
  use.
* **Entity keys** — the unique identifier property for each entity
  (`truck_id`, `driver_id`, …). **Without an entity key the graph
  model will materialise zero nodes for that entity**, even if the
  ontology compiles cleanly. This is the single most common first-try
  failure mode.
* **Bindings** — the glue from an ontology entity to a physical
  Lakehouse table. The binding says "the `Truck` entity is backed by
  the `trk_truck` Delta table; map these ontology properties to these
  columns".
* **Contextualizations** — the specialised bindings used for
  relationships, especially many-to-many joins. They say "the
  `trip_driver` edge is materialised by the `driver_id` column on the
  `trk_trip` row".

The ontology is a **declarative artifact**. You author it (this repo
uses `input/schema/ontology.md`), push it to Fabric via REST, and
Fabric takes care of projecting its structure into a graph model and
keeping the bindings consistent with the Lakehouse schema.

### Graph model

The graph model is the **instance layer** beneath the ontology. The
ontology says "`Truck` has a `truck_home_terminal` edge to `Terminal`";
the graph materialises one node per actual truck and one edge per
actual truck-to-terminal pair, by reading the rows in the Lakehouse
tables the bindings point at.

Two important consequences:

1. **The graph is a projection, not live.** You populate it by
   explicitly triggering a **refresh** (the `jobs/instances?jobType=
   RefreshGraph` endpoint, wrapped in this repo by
   `GraphClient.refresh()`). If you load new data into the Lakehouse
   and skip the refresh, graph queries see stale data. This repo's
   notebook banner reminds the user of this on every run.
2. **Refresh is not always reliable.** Fabric sometimes auto-cancels a
   refresh job when it detects another refresh is running for the
   same model. Retry logic is built in; if it still fails, the Fabric
   UI's "Refresh now" button works. This is a documented rough edge.

### GQL — the graph query language

GQL (Graph Query Language, ISO standard since 2024) is how you query a
Fabric graph model. It is **not** GraphQL (an API layer); think of it
as "SQL for graphs". Pattern-match nodes + edges; return projections.

A query from `gql-queries/cq02.gql`:

```gql
MATCH (t:Truck)-[:truck_home_terminal]->(term:Terminal)
RETURN term.name AS terminal_name, COUNT(t) AS truck_count
GROUP BY terminal_name
ORDER BY truck_count DESC
```

Why use GQL instead of SQL? Two classes of questions are dramatically
shorter:

* **Multi-hop traversals.** "Find all drivers who have hauled a load
  for a customer whose terminal is in X" is one chained `MATCH`
  pattern in GQL; the SQL version involves three or four joins that
  an agent often gets wrong.
* **Relationship-centric questions.** "What trips connect Atlanta and
  Chicago *in either direction*?" The graph expresses the symmetry
  naturally; SQL needs to enumerate both orderings.

Where GQL is **still weak today** (as of the Fabric preview at the
time of this repo):

* `NOT EXISTS` / anti-join patterns (agent-authored queries refuse
  outright — see scenario Q12).
* Conditional aggregation — `CASE WHEN … THEN …` inside `SUM()` for
  things like "percentage of trips that arrived on time" (scenario
  Q15).

Those limitations are the headline content of
[`03-walkthrough.md`](03-walkthrough.md#what-works-and-what-does-not)
and [`05-troubleshooting.md`](05-troubleshooting.md).

### Data Agents

A Fabric **Data Agent** is a configured AI agent that can be asked
natural-language questions about one or more registered data sources.
Under the hood it's exposed through an OpenAI-compatible Assistants
API (Fabric's `FabricOpenAI` client is the wrapper). For each
question, the agent picks a data source, generates a query in the
right language, executes it, and synthesises a natural-language
answer with the results.

This repo provisions **two data agents** to measure whether the
ontology actually helps:

* **NakedAgent** — wired to the **Lakehouse only**. It sees raw Delta
  tables and column names. It emits Spark SQL.
* **OntologyAgent** — wired to the **ontology only**. It sees entity
  names, relationship names, and property descriptions. It emits
  GQL against the graph model (which is bound to the same Lakehouse
  tables underneath).

Both agents see the same underlying data. They differ in which
*semantic surface* is visible to them. When they disagree, the
benchmark tells you whether the ontology's extra context paid off for
that question or whether the platform's GQL gap made it worse.

### NL2Ontology

"NL2Ontology" is Microsoft's term for the translation layer that
converts plain-English questions to ontology-grounded queries. It's
what makes the OntologyAgent possible: instead of pattern-matching the
user's text against column names, the model reads the ontology's
entity + property *descriptions* and uses those as the vocabulary it
maps into.

In practice, how good NL2Ontology is depends heavily on how rich your
ontology descriptions are. This repo's
`input/schema/ontology.md` is deliberately plain so you can see how
much value the descriptions add; tuning descriptions is out of scope
for the benchmark.

## The two-engine story this repo measures

The benchmark in this repo is a side-by-side comparison:

| Agent | Sees | Queries | Strengths (on this set) | Weaknesses |
|---|---|---|---|---|
| NakedAgent | 11 raw Lakehouse tables with FK columns | Spark SQL | Works; easy mental model | Silently picks one interpretation of ambiguous questions; no semantic vocabulary; wrong joins on multi-hop |
| OntologyAgent | 11 entities + 19 relationships on the graph | GQL | Better multi-hop + clarification behaviour | Refuses on anti-joins and conditional aggregations (GQL gap, not agent quality) |

The scenarios in `scenarios/truck_scenarios.json` are chosen so the
difference shows up:

* 3 sanity checks where both should tie.
* 5 multi-hop traversals where the ontology should help.
* 3 governed-metric scenarios with numeric gold values to catch
  lexically-right-but-numerically-wrong answers.
* 2 ambiguity scenarios where refusing or clarifying is the correct
  behaviour.
* 1 guardrail scenario where executing would be wrong.

The results the current Fabric preview produces on this set are
**honest, not flattering to either side**; read
[`03-walkthrough.md`](03-walkthrough.md#what-works-and-what-does-not)
for the actual scorecard analysis rather than the marketing claims.

## Where to go next

* [`02-repo-tour.md`](02-repo-tour.md) — the code map.
* [`03-walkthrough.md`](03-walkthrough.md) — the first-run playbook.
* [`04-schema-reference.md`](04-schema-reference.md) — if you want to
  author your own scenarios or entities.
* [`05-troubleshooting.md`](05-troubleshooting.md) — when something
  breaks.
