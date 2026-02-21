# Dagster Architecture

## How Dagster Works

Dagster is a **data asset orchestrator**. Instead of defining tasks and execution order, you define the data assets your pipeline produces and their dependencies. Dagster figures out the execution plan from the asset graph.

The architecture is simpler than Airflow — two main processes plus a storage backend:

```text
               +----------------------+
               |  definitions.py      |  Assets, jobs, schedules, resources
               +-----------+----------+
                           |
                           v
               +-----------+----------+
               |    Webserver         |  Dagit UI + GraphQL API
               +-----------+----------+
                           |
                           v
               +-----------+----------+
               |    Storage (SQLite)  |  Runs, events, schedules
               +-----------+----------+
                     ^     |
                     |     v
               +-----+----+-----+
               |     Daemon      |  Schedules, sensors, run queue
               +-----------------+
```

## Processes

### Webserver (Dagit)

Serves the web UI on port 3001 (default 3000). Provides:

- **Asset lineage graph** — visual map of all assets and their dependencies
- **Materialization history** — when each asset was last computed
- **Run viewer** — logs, step timeline, stdout/stderr for each run
- **GraphQL API** — programmatic access to everything in the UI
- **Launchpad** — trigger runs with config overrides

Unlike Airflow, the webserver also handles run execution in `dagster dev` mode. In production, a separate **run launcher** (e.g., Docker, K8s) handles execution.

### Daemon

Background process that handles:

- **SchedulerDaemon** — triggers runs based on cron schedules
- **SensorDaemon** — polls external systems (new files, DB changes, etc.) and triggers runs
- **BackfillDaemon** — manages partition backfills
- **QueuedRunCoordinatorDaemon** — rate-limits concurrent runs
- **AssetDaemon** — auto-materializes assets when dependencies update
- **FreshnessDaemon** — checks asset freshness policies

All six daemons run within a single daemon process — much simpler than Airflow's separate scheduler/triggerer/processor.

### `dagster dev` vs Production

`dagster dev` starts everything in one command (webserver + daemon). It also:

- Auto-reloads code changes (no restart needed)
- Uses an in-process executor (tasks run in the same process)
- Enables the Dagit UI with debug features

In production, you'd run `dagster-webserver` and `dagster-daemon` as separate services, with a run launcher (Docker/K8s) for task isolation.

## Definitions

The single entry point for your Dagster project. Everything is registered in one `Definitions` object:

```python
defs = Definitions(
    assets=[...],        # Data assets
    jobs=[...],          # Groups of assets to run together
    schedules=[...],     # Cron-based triggers
    sensors=[...],       # Event-based triggers
    resources=[...],     # Shared dependencies (DB connections, API clients)
)
```

This is a major difference from Airflow — no scanning a folder for DAG files. One explicit Python object declares everything.

## Generated Files

### `dagster.yaml`

Main configuration file. Much simpler than Airflow's `airflow.cfg` — most things are configured in Python via the `Definitions` object. The YAML is mainly for infrastructure settings:

```yaml
telemetry:
  enabled: false
```

Optional sections include:

| Section | Controls |
| --- | --- |
| `storage` | Override storage backend (default: SQLite in DAGSTER_HOME) |
| `run_launcher` | How runs are executed (default: in-process) |
| `run_coordinator` | Run queuing and concurrency limits |
| `compute_logs` | Where stdout/stderr logs are stored |
| `telemetry` | Usage telemetry opt-in/out |

### `history/`

Contains the run history databases:

```text
history/
  runs.db           # Main SQLite database — all run metadata and event logs
  runs/
    index.db        # Index database for fast run lookups
    .db             # Additional metadata
```

**`runs.db`** is the equivalent of Airflow's `airflow.db`. It stores:

- **Run records** — run ID, status, start/end time, config
- **Event logs** — every step event (started, succeeded, failed, output, etc.)
- **Asset materializations** — what assets were produced, with metadata
- **Asset observations** — recorded metadata without materializing

In production, this would be PostgreSQL.

### `schedules/`

```text
schedules/
  schedules.db      # SQLite database for schedule state
```

Tracks schedule tick history — when each schedule was last evaluated and what runs it launched. Separate from `runs.db` for isolation.

### `.telemetry/`

```text
.telemetry/
  id.yaml           # Unique instance UUID
```

Contains a randomly generated UUID identifying this Dagster instance. Used for anonymous usage telemetry (disabled in our `dagster.yaml`). Safe to ignore.

### `.nux/`

```text
.nux/
  nux.yaml          # New User Experience tracking
```

Tracks onboarding state — whether you've seen the welcome screen, tooltips, etc. The name stands for "New User Experience." Contains something like:

```yaml
seen: 1
```

### `.logs_queue/`

Buffer directory for log output. Dagster writes logs here before flushing to the compute log storage backend. Usually empty when idle.

## Key Architectural Differences from Airflow

| Aspect | Airflow | Dagster |
| --- | --- | --- |
| **Config file** | `airflow.cfg` (~2300 lines, INI format) | `dagster.yaml` (~5 lines, infrastructure only) |
| **Metadata DB** | Single `airflow.db` with all state | Split: `runs.db` + `schedules.db` + `index.db` |
| **Process count** | 4 (scheduler, dag-processor, API server, triggerer) | 2 (webserver, daemon) |
| **Code loading** | Scans `dags/` folder for .py files on interval | Imports a single `Definitions` object on startup |
| **DB init** | Manual `airflow db migrate` | Automatic on first run |
| **Log structure** | File-per-task-attempt in nested directories | Stored in `runs.db` event log, streamed to UI |
