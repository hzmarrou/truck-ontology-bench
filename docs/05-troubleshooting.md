# 05 — Troubleshooting

Every known failure mode, with symptom → cause → fix → prevention.
Check here *first* when a script complains; most gotchas are already
catalogued.

## Install / local-dev

### `pytest -q` fails with `ModuleNotFoundError: truck_bench`

* **Cause:** package not installed; you're on a bare `python` without
  an activated virtualenv.
* **Fix:** `uv venv && uv pip install -e .[dev]` (or
  `python -m venv .venv && source .venv/bin/activate && pip install -e .[dev]`).

### `python scripts/01_parse_md.py` fails with `RuntimeError: Missing required environment variables`

* **Cause:** `.env` missing or incomplete. Even script 01 loads config
  (though it doesn't call Fabric).
* **Fix:** `cp .env.example .env` and fill the five values.

## Fabric credentials + permissions

### `403` on `POST /ontologies` during `scripts/03_setup.py`

* **Symptom:** `HTTPError: 403 Client Error: Forbidden for url: …/ontologies`.
* **Cause:** the service principal is not **Admin** on the target
  workspace.
* **Fix:** in the Fabric portal: *Workspace → Manage access → Add
  people or groups → pick the SP → Admin → Add*.
* **Prevention:** the least-privilege matrix in the root README
  specifies Admin. `Contributor` is not enough because it cannot
  create ontologies or data agents.

### `401` on the AAD token request

* **Cause:** bad tenant id, client id, or client secret in `.env`.
* **Fix:** re-verify all three values from the Entra app registration.
  The secret's *value* (not the *id*) goes into `AZURE_CLIENT_SECRET`.

## Ontology creation

### `409 Conflict` on `POST /ontologies`

* **Symptom:** `create returned 409 (attempt 1); waiting 10s before
  retry...` printed by `scripts/03_setup.py`.
* **Cause:** Fabric's name reservation lags a previous delete. The
  display name is not available yet even though `list_ontologies`
  shows nothing.
* **Fix:** the script already retries up to 12 times with a 10-second
  backoff — wait for it. If all 12 retries fail, wait 2 minutes and
  rerun; rare but documented.
* **Prevention:** don't delete + recreate the same ontology name in
  rapid succession.

### Graph appears empty after `03_setup.py`

* **Symptom:** `cq01.gql` returns zero rows; `cq02.gql` shows zero
  trucks; entities seem to be missing.
* **Cause:** at least one entity in `input/schema/ontology.md` is
  missing a `(PK)` annotation, so its bindings push fine but the
  graph materialisation step finds no unique identifier and creates
  zero nodes.
* **Fix:** ensure every `# EntityName` block has exactly one field
  annotated `(PK)`. Rerun `scripts/01_parse_md.py`,
  `scripts/02_build_mapping.py`, `scripts/03_setup.py`, and refresh
  the graph.
* **Prevention:** `tests/test_markdown_parser.py` locks the PK count
  per entity.

## Graph refresh

### Refresh returns `Cancelled` almost immediately

* **Symptom:** `refresh status: Cancelled` with no
  `failureReason`, less than two seconds after POST.
* **Cause:** Fabric auto-cancels a refresh when it detects another
  refresh is already running or was triggered too recently for the
  same graph model. This is a platform behaviour, not a bug in your
  code.
* **Fix:** the script already retries once after a 60-second pause.
  If the second attempt also cancels, open the graph model in the
  Fabric UI and click "Refresh now". Then rerun the script with
  `--skip-refresh`.
* **Prevention:** don't rerun `scripts/04_refresh_and_validate.py`
  while another refresh is in progress.

### Graph refresh times out

* **Symptom:** `TimeoutError: Graph refresh exceeded 1800s timeout`.
* **Cause:** real platform slowness, or the refresh is stuck. 30
  minutes is already generous for this repo's ≈ 960 rows.
* **Fix:** increase `--max-wait-seconds` (if the CLI exposes it) or
  fall back to the UI.

## Data Agents

### `ValueError: Lakehouse <id> not found in workspace`

* **Symptom:** `scripts/05_setup_agents.py` fails on
  `lookup_lakehouse_display_name`.
* **Cause:** `FABRIC_LAKEHOUSE_ID` in `.env` points at a lakehouse
  the SP cannot see, or at the auto-created ontology lakehouse that
  the workspace provisioned alongside the ontology.
* **Fix:** confirm the id in the Fabric portal (Lakehouse → settings →
  copy ID). Make sure it's your **target** Lakehouse, not the
  auto-created one.

### Agent answers are empty or include "I cannot access the data"

* **Symptom:** the notebook's `ask_agent` returns `"<empty>"` or a
  refusal even for a simple sanity question.
* **Causes:**
  1. The graph model hasn't been refreshed since `03_setup.py`; the
     OntologyAgent sees an empty graph.
  2. The Lakehouse is not attached as the *default* on the notebook;
     `FabricOpenAI` has nowhere to load Python context from.
  3. Data Agent tenant settings are disabled; the request goes
     through but the agent can't reach the model.
* **Fix:** in order:
  1. Rerun `scripts/04_refresh_and_validate.py`.
  2. Re-attach the Lakehouse as the default in the notebook's
     sidebar.
  3. Enable the Fabric Data Agent tenant settings (requires a
     tenant admin).

### Notebook cells hang indefinitely

* **Symptom:** a single question runs for many minutes with no
  output.
* **Cause:** before F05 / R10 this was real. The current notebook
  enforces `MAX_ANSWER_WAIT_SECONDS = 300` with an explicit poll +
  cancel loop; a stuck call returns `"<timeout after 300s>"` and the
  loop continues.
* **Fix:** you shouldn't see this if you uploaded the current
  notebook. If you're on an older upload, re-upload
  `notebooks/compare_agents_fabric.ipynb` from the repo head and
  rerun.

## SDK / runtime issues

### `Jinja2` templating errors in the notebook

* **Symptom:** `TemplateError: ...` from a cell that imports
  `fabric.dataagent.client`.
* **Cause:** Fabric runtime ships a newer `Jinja2` than the Data Agent
  SDK supports. The SDK's template rendering breaks on anything newer
  than 3.1.6.
* **Fix:** the notebook pins `Jinja2==3.1.6` in the `%pip install`
  cell (cell 1). Make sure that cell ran successfully before running
  later cells.

### `OpenAI.__init__() got unexpected keyword argument 'data_agent_stage'`

* **Cause:** newer versions of `fabric-data-agent-sdk` removed the
  `data_agent_stage` kwarg from the `FabricOpenAI` constructor.
* **Fix:** the notebook's `_make_client()` already tries with and
  without the kwarg and falls back. If you see this error it means
  both attempts failed; upgrade or pin the SDK version, then rerun.

### `CANNOT_MERGE_TYPE BooleanType vs StructType` from `evaluate_data_agent`

* **Cause:** a bug in the Data Agent SDK's Spark writer when per-row
  response shapes differ across questions.
* **Fix:** this repo's notebook does **not** use `evaluate_data_agent`
  for that reason. It calls `FabricOpenAI` directly and scores
  answers itself. If you're porting code that uses
  `evaluate_data_agent`, expect to bypass it.

## Scoring

### `scripts/06_score.py` fails with `no scenariosPayload — this file was produced by a pre-R04 notebook`

* **Cause:** the comparison JSON was generated by an older notebook
  version that didn't embed the scenarios payload.
* **Fix:** re-upload the current `notebooks/compare_agents_fabric.ipynb`
  and rerun, or (one-off only) pass
  `--scenarios-from local --override-scenario-hash` to score against
  your local `scenarios/truck_scenarios.json` regardless.

### `scripts/06_score.py` fails with `Local scenarios sha256 … does not match scenariosSha256`

* **Cause:** you edited `scenarios/truck_scenarios.json` after the
  notebook ran, so the local file no longer matches the hash the
  notebook recorded.
* **Fix:** either rerun the notebook (so the new hash is recorded),
  or pass `--override-scenario-hash` if the divergence is intentional
  (you'll see a warning recorded on the scorecard).

### `duplicate scenario_id(s) in perQuestion`

* **Cause:** a typo in `scenarios/truck_scenarios.json` produced two
  rows with the same id.
* **Fix:** grep for the id, deduplicate, rerun the pipeline. The
  scorer intentionally fails hard here to prevent silent drops.

## Misc

### `UnicodeEncodeError` printing route names on Windows

* **Symptom:** `cp1252 codec can't encode character` from
  `scripts/04_refresh_and_validate.py`.
* **Cause:** some route names in the seed data use the arrow `→`,
  which Windows `cp1252` stdout cannot print.
* **Fix:** already handled — the script reconfigures `sys.stdout` to
  UTF-8 on Windows before printing.
* **Prevention:** you shouldn't see this if you're on the current
  repo head.

### Where do artifacts go?

All generated artifacts land in `outputs/`, which is gitignored. The
happy-path flow is:

```
01 → parsed_ontology.json + ontology_summary.txt
02 → ontology-config.json
03 → _state.json
04 → _validation.json
05 → _agents.json + agent-comparison-questions.json
notebook → Files/truck/_agent_comparison.json (on Lakehouse)
download → outputs/_agent_comparison.json
06 → scorecard.md + scorecard.json
```

If a later script can't find an earlier script's artifact, rerun the
earlier one. They're all idempotent.

## Still stuck?

Open an issue on
[github.com/hzmarrou/truck-ontology-bench/issues](https://github.com/hzmarrou/truck-ontology-bench/issues)
with the failing command, the full stdout, and your Fabric capacity
SKU. If it's a Fabric-platform issue (refresh cancellation, GQL
limitation, SDK drift) there's a good chance it's already mentioned
here — link the symptom back to the entry above and we'll update the
doc if the fix has shifted.
