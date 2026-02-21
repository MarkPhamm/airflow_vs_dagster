# Airflow Architecture

## How Airflow Works

Airflow is a **task orchestrator**. You define tasks in Python, group them into DAGs (Directed Acyclic Graphs), and Airflow executes them on a schedule. The system is built around several independent processes that communicate through a shared metadata database.

```text
                 +-------------------+
                 |   DAG Files (.py) |
                 +--------+----------+
                          |
                          v
               +----------+-----------+
               |    DAG Processor     |  Parses DAG files, serializes to DB
               +----------+-----------+
                          |
                          v
               +----------+-----------+
               |    Metadata DB       |  Central state store (SQLite/Postgres)
               +----------+-----------+
                     ^    |    ^
                     |    v    |
          +----------+--+ +---+----------+
          |  Scheduler  | | API Server   |  Web UI + REST API
          +----------+--+ +--------------+
                     |
                     v
               +-----+------+
               |  Executor   |  Runs tasks (LocalExecutor, CeleryExecutor, etc.)
               +-----+------+
                     |
                     v
               +-----+------+
               |  Workers    |  Actual task execution
               +-------------+
```

## Processes

### Scheduler

The brain of Airflow. It continuously:

1. Checks the metadata DB for DAGs with pending runs
2. Creates DAG runs based on schedules
3. Queues task instances that have their dependencies met
4. Sends queued tasks to the executor
5. Monitors task state via heartbeats

Without the scheduler, nothing runs. If it crashes (like the `HTTPStatusError` issue we hit), tasks stay in "Queued" forever.

### DAG Processor

Separate from the scheduler in Airflow 3. It:

1. Scans the `dags/` folder for Python files
2. Imports each file and extracts DAG objects
3. Serializes DAGs to the metadata DB

This is why DAG changes take ~30 seconds to appear — the processor runs on an interval. Logs are in `logs/dag_processor/`.

### API Server

Serves the web UI and REST API on port 8082 (default 8080). In Airflow 3, this also hosts the **Execution API** that workers use to report task status back. This is why we had to set `execution_api_server_url` when we changed the port.

### Triggerer

Handles **deferred tasks** — tasks that are waiting on an external event (e.g., waiting for a file to appear, an API to respond). Instead of occupying a worker slot while waiting, deferred tasks release the slot and the triggerer watches for the trigger condition.

### Executor

Determines *how* tasks run. Configured in `airflow.cfg`:

- **LocalExecutor** (our setup): Spawns tasks as local subprocesses. Good for development.
- **CeleryExecutor**: Distributes tasks to Celery workers. For production multi-node setups.
- **KubernetesExecutor**: Launches each task as a Kubernetes pod. For cloud-native deployments.

## Generated Files

### `airflow.cfg`

The main configuration file (~2300 lines). Auto-generated on first `db migrate` with defaults. Organized in sections:

| Section | Controls |
| --- | --- |
| `[core]` | Executor, DAG folder, parallelism, timezone |
| `[database]` | DB connection string, pool sizes |
| `[api]` | API server port, CORS, auth |
| `[scheduler]` | Parsing interval, heartbeat, max active runs |
| `[logging]` | Log format, log folder, remote logging |

Key settings we changed:

- `port = 8082` — API server port (under `[api]`)
- `execution_api_server_url = http://localhost:8082/execution/` — so workers can find the API server (under `[core]`)
- `load_examples = True` — loads Airflow's built-in example DAGs (under `[core]`)

Config values can be overridden with environment variables using the pattern `AIRFLOW__SECTION__KEY` (e.g., `AIRFLOW__API__PORT=8082`).

### `airflow.db`

SQLite metadata database. Stores everything Airflow needs to operate:

- **DAG definitions** (serialized from DAG processor)
- **DAG runs** (scheduled, manual, backfill)
- **Task instances** (state, start/end time, try number, executor config)
- **XCom** (cross-communication data passed between tasks)
- **Connections** (database credentials, API keys)
- **Variables** (key-value config store)
- **Users and permissions**

In production, this would be PostgreSQL or MySQL. SQLite is fine for local development but doesn't handle concurrent writes well.

### `airflow.db-shm` and `airflow.db-wal`

SQLite WAL (Write-Ahead Logging) files. These enable concurrent reads while writing:

- `.db-wal`: Write-ahead log — new writes go here first before being checkpointed to the main `.db` file
- `.db-shm`: Shared memory file — coordinates access between multiple processes reading/writing the DB

These are temporary and get cleaned up when all connections close.

### `simple_auth_manager_passwords.json.generated`

Stores hashed passwords for the simple auth manager (Airflow 3's default). Contains the auto-generated admin password you see in the `standalone` output.

### `logs/`

Hierarchical log structure:

```text
logs/
  dag_id=example_dag/
    run_id=manual__2026-02-21T21:21:01/
      task_id=hello/
        attempt=1.log       # First execution attempt
        attempt=2.log       # Retry
      task_id=goodbye/
        attempt=1.log
    run_id=scheduled__2026-02-21T00:00:00+00:00/
      ...
  dag_processor/
    2026-02-21/
      dags-folder/
        example_dag.py.log  # DAG parsing logs
```

Each task attempt gets its own log file. The naming pattern `dag_id -> run_id -> task_id -> attempt` makes it easy to trace execution.

### `dags/`

Where you put DAG files. The DAG processor scans this folder. Any `.py` file containing a `DAG` object gets picked up. Subdirectories are scanned too.
