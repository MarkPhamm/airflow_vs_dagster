# airflow_vs_dagster

Learn the main differences between Apache Airflow and Dagster.

See [docs/COMPARISON.md](docs/COMPARISON.md) for a detailed comparison, and [docs/AIRFLOW.md](docs/AIRFLOW.md) / [docs/DAGSTER.md](docs/DAGSTER.md) for architecture deep dives.

## Prerequisites

- Python 3.12
- [uv](https://docs.astral.sh/uv/)

# Airlfow

## Airflow Project Structure

```text
airflow_setup/          # Airflow home directory
  dags/                 # DAG definitions
    example_dag.py      # Simple hello -> goodbye example DAG
  airflow.cfg           # Airflow config (auto-generated, gitignored)
  airflow.db            # SQLite metadata DB (auto-generated, gitignored)
```

## Airflow Setup

### Install dependencies

```bash
uv sync
```

### Set environment variables

All commands require `AIRFLOW_HOME` — this tells Airflow where to find its config (`airflow.cfg`), metadata database (`airflow.db`), and DAG files (`dags/`). Without it, Airflow defaults to `~/airflow`. We point it at the project's `airflow_setup/` directory instead:

```bash
export AIRFLOW_HOME="$(pwd)/airflow_setup"
```

### Initialize the database

```bash
uv run airflow db migrate
```

This creates a local SQLite database at `$AIRFLOW_HOME/airflow.db`.

### Run Airflow

```bash
uv run airflow standalone
```

This starts the scheduler, dag-processor, triggerer, and API server in a single process. On first run it creates an `admin` user — check the terminal output for the password line:

```text
Password for user 'admin': <generated-password>
```

The web UI is available at **<http://localhost:8082>**.

### Verify DAGs

```bash
uv run airflow dags list
```

You should see `example_dag` in the output.

## Components

| Component | Description |
| --- | --- |
| **API Server** | Serves the web UI and REST API (port 8082) |
| **Scheduler** | Monitors DAGs, triggers task instances based on schedules and dependencies |
| **DAG Processor** | Parses DAG files from `dags/` folder and serializes them to the metadata DB |
| **Triggerer** | Handles deferred (async) tasks |
| **Metadata DB** | SQLite database storing DAG state, run history, task instances, connections, variables |

---

# Dagster

## Dagster Project Structure

```text
dagster_setup/          # Dagster home directory
  definitions.py        # Asset and job definitions
  storage/              # Run and event log storage (auto-generated, gitignored)
  logs/                 # Dagster logs (auto-generated, gitignored)
  history/              # Run history (auto-generated, gitignored)
```

## Dagster Setup

### Install dependencies

```bash
uv sync
```

### Set environment variables

All commands require `DAGSTER_HOME` — this tells Dagster where to store its run history, event logs, and local instance configuration. Without it, Dagster uses a temporary directory that is lost between sessions. We point it at the project's `dagster_setup/` directory:

```bash
export DAGSTER_HOME="$(pwd)/dagster_setup"
```

### Run Dagster

```bash
uv run dagster dev --module-name dagster_setup.definitions --port 3001
```

This starts the Dagster webserver and daemon. No database initialization needed — Dagster handles it automatically on first run.

The web UI (Dagit) is available at **<http://localhost:3001>**.

### Verify assets

```bash
uv run dagster asset list --module-name dagster_setup.definitions
```

You should see `hello` and `goodbye` in the output.

## Components

| Component | Description |
| --- | --- |
| **Webserver** | Serves the Dagit UI and GraphQL API (port 3001) |
| **Daemon** | Background process that handles schedules, sensors, and run queuing |
| **Definitions** | Single Python entry point that declares assets, jobs, schedules, sensors, and resources |
| **Storage** | SQLite database storing run history, event logs, and asset materializations |
