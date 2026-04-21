# Contributing

Thanks for picking up `truck-ontology-bench`. This document keeps the
contributor loop short: dev setup, how to run the checks locally, and
what a good PR looks like.

## Dev setup

```bash
# 1. Clone
git clone https://github.com/hzmarrou/truck-ontology-bench
cd truck-ontology-bench

# 2. Virtualenv (uv recommended — or use plain python -m venv)
uv venv
uv pip install -e .[dev]

# 3. Optional: wire real Fabric creds for scripts 03/04/05
cp .env.example .env
# edit .env with your five values — see README.md § "Service-principal permissions"
```

No Fabric credentials are needed for the test suite. The contract
tests stub every HTTP call.

## Running the checks

```bash
# Full test suite (~ 2 seconds)
pytest -q

# Linting
ruff check src tests scripts
```

All 50 tests must pass before a PR is considered reviewable.

## Commit / PR convention

Commits are focused and prefixed by the category that inspired them:

* `R##:` for items in the initial R01–R21 build (see `CHANGELOG.md`).
* `F##:` for items in the F01–F13 post-review hardening round.
* Otherwise, a short imperative subject (`add …`, `fix …`, `docs: …`,
  `test: …`). One commit per logical change.

The commit body explains the *why*; the diff explains the *what*.

## Adding a new scenario

Scenarios live in `scenarios/truck_scenarios.json`. Field reference is
in [`docs/04-schema-reference.md`](docs/04-schema-reference.md#scenario-schema).
Minimum fields: `scenario_id` (unique), `domain`, `user_question`,
`ontology_signals`. For governed-metric scenarios, add
`gold_numeric_value` + `gold_numeric_tolerance_pct` so the scorer can
catch numerically-wrong answers.

After editing, re-run the full pipeline so `scenariosSha256` in the
next comparison JSON reflects the new payload — otherwise
`scripts/06_score.py` will refuse to score against a mismatched local
file (see the hash-lock contract in `docs/04-schema-reference.md`).

## Where to find deeper material

* [`docs/01-fabric-iq-primer.md`](docs/01-fabric-iq-primer.md) —
  Fabric IQ concepts, for readers who know Fabric but not IQ.
* [`docs/02-repo-tour.md`](docs/02-repo-tour.md) —
  architecture + package layout.
* [`docs/03-walkthrough.md`](docs/03-walkthrough.md) —
  end-to-end run against a real Fabric workspace.
* [`docs/05-troubleshooting.md`](docs/05-troubleshooting.md) —
  every known failure mode.
