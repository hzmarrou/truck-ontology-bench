# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

Nothing yet.

## [0.1.0] — 2026-04-21

Initial public release. Everything below is already in the repo at this tag.

### Added

- **End-to-end pipeline (R01–R21).** The numbered scripts
  `scripts/01_parse_md.py` through `scripts/06_score.py` stand up a
  Fabric ontology for a long-haul trucking domain (11 entities, 19
  relationships), load 11 JSONL seed files into Lakehouse Delta tables,
  push bindings + contextualizations, refresh the graph model, run 11
  GQL competency queries, provision a NakedAgent (Lakehouse-only) + an
  OntologyAgent (ontology-only) pair of Fabric Data Agents, and score
  their side-by-side answers on an 18-scenario benchmark. Each R-item
  corresponds to a focused commit visible via `git log`.
- **Contract tests** (`tests/test_fabric_client.py`) around the shared
  LRO poller (`src/truck_bench/fabric_client/lro.py`) covering Location
  guard, per-poll `Retry-After`, transient 429/5xx retry, wall-clock
  timeout, and the two success-state shapes (`Succeeded` for
  operations, `Completed` for job-instances).
- **OWL-lite parser contract** for the markdown ontology + a mapping
  fail-fast mode that refuses to emit a partial Fabric config when
  classes or relationships cannot be wired.
- **Deterministic numeric gold scoring** — governed-metric scenarios
  carry `gold_numeric_value` + `gold_numeric_tolerance_pct` so a
  lexically-correct-but-numerically-wrong answer fails a dedicated
  scorer dimension.
- **Scenario hash lock (F04)** — the comparison JSON produced by the
  notebook embeds `scenariosPayload` + `scenariosSha256`, and
  `scripts/06_score.py` scores against the embedded payload by default
  so a mutated local file can't silently rescore a historical run.

### Fixed (post-review, F01–F13)

A targeted round of fixes after independent review. Highlights:

- `scripts/05_setup_agents.py` + `scripts/06_score.py` now consume the
  canonical `tableName` from the ontology config instead of recomputing
  via a snake_case heuristic — entities like `MaintenanceEvent` now
  wire to `trk_maintenance_event` correctly on both the datasource and
  the scorer side.
- Per-question rows in the comparison JSON are joined by `scenario_id`
  (not question text); missing or duplicate IDs fail hard.
- Notebook timeout is enforced with an explicit poll loop around
  `runs.retrieve`; a wedged agent call now returns
  `<timeout after Ns>` instead of blocking the benchmark.
- Empty `ontology_signals` return `correct=None` (N/A) instead of
  forcing a False verdict that would double-penalise the OntologyAgent
  on ambiguity scenarios.
- Shared LRO poller (`fabric_client/lro.py`) replaces three separate
  poll loops in `ontology_api`, `graph_api`, and `data_agent_api` — a
  regression in one place is a regression everywhere.
- Setup cleanup uses exact-match name lists; a shared lakehouse no
  longer risks dropping another project's tables. Aggressive drop is
  now opt-in via `--aggressive-drop`.
- Graph-model resolution in `scripts/04_refresh_and_validate.py` is
  exact-displayName; ambiguous matches fail fast instead of picking the
  first sorted match.

### Documentation

- Least-privilege matrix in `README.md` + `.env.example` — workspace
  Admin is sufficient; no tenant-wide app role is required.
- OWL-lite contract documented with warnings on unsupported OWL axioms
  at parse time (in the sibling `nplrisk-ontology` repo — noted here
  because the same contract applies to the markdown-to-Fabric mapping
  used by this repo).

[Unreleased]: https://github.com/hzmarrou/truck-ontology-bench/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/hzmarrou/truck-ontology-bench/releases/tag/v0.1.0
