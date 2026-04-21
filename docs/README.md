# Documentation

This folder is the reference companion to the repo's top-level
[`README.md`](../README.md). The split is intentional:

* `README.md` → the **quick-start path**. How to install, configure
  `.env`, run the pipeline, and open the notebook. Minimal theory.
* `docs/` (here) → the **reference material**. Concepts you need to
  understand *why* each script does what it does, what the scenarios
  are measuring, and what to do when something fails.

## Suggested reading order

If you've never touched Fabric IQ before:

1. **[01 — Fabric IQ primer](01-fabric-iq-primer.md)**
   Self-contained explainer of ontology, graph model, bindings,
   data agents, GQL, and NL2Ontology. No prior IQ knowledge assumed;
   Fabric basics (Lakehouse, Spark, medallion) are assumed.

2. **[02 — Repo tour](02-repo-tour.md)**
   The code map. Each script's inputs / outputs; the `src/truck_bench/`
   package layout; which test exercises which invariant.

3. **[03 — Walkthrough](03-walkthrough.md)**
   End-to-end run against a real Fabric workspace. Each stage has the
   command you type, the stdout snippet you should see, and the UI
   screen you should verify. This is the doc to follow on your first
   real run.

4. **[04 — Schema reference](04-schema-reference.md)**
   Field-by-field reference for `scenarios/truck_scenarios.json`,
   `input/schema/ontology.md`, and the `gql-queries/*.gql` format.
   Look here when you want to add a new scenario, a new entity, or a
   new competency query.

5. **[05 — Troubleshooting](05-troubleshooting.md)**
   Every known failure mode, with symptom → cause → fix → prevention.
   Check here first when a script complains; most gotchas are already
   catalogued.

## When to read what

| You are… | Start with |
|---|---|
| Evaluating whether to try the repo | 01 — primer |
| About to run the pipeline for the first time | 03 — walkthrough |
| Adding a new scenario or competency query | 04 — schema reference |
| Looking at a stack trace | 05 — troubleshooting |
| Understanding the codebase before a PR | 02 — repo tour |

Each document stands on its own — you don't need to read them in
order, but the primer is genuinely useful before the rest.
