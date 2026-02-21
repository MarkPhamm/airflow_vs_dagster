# Airflow vs Dagster Comparison

*(See also: [Dagster vs Airflow: In-depth Comparison](https://dagster.io/blog/dagster-airflow))*

## Why Dagster Exists

Airflow was built in 2014 at Airbnb to orchestrate **tasks** — "run this script, then that script, on a schedule." It works well for ETL pipelines where you care about *execution order*. But as data platforms grew, teams ran into problems:

- **Airflow doesn't know what data exists.** A DAG with 5 tasks produces tables, files, ML models — but Airflow only tracks whether each task succeeded or failed. If a table is stale or missing, you have to figure out which task to rerun yourself.
- **DAGs describe execution, not data.** Two DAGs can write to the same table with no warning. There's no way to see "what upstream data does this dashboard depend on?" without reading the code.
- **Testing is painful.** Tasks depend on Airflow's runtime context (XCom, connections, variables). You can't just call a task function in a unit test.

Dagster (2018, Elementl) was built to fix this by making **data assets** the core abstraction instead of tasks. Instead of "run task A then task B," you declare "table X depends on table Y" and Dagster figures out the execution.

## Tasks and DAGs vs Assets

This is the fundamental difference between the two systems.

### Airflow: Task-centric

In Airflow, you define **tasks** grouped into a **DAG** (Directed Acyclic Graph). The DAG describes *what to execute and in what order*:

```python
# Airflow: you define tasks and their execution order
@task
def extract():
    return pull_from_api()

@task
def transform(raw_data):
    return clean(raw_data)

@task
def load(clean_data):
    write_to_db(clean_data)

# The DAG is an execution plan
load(transform(extract()))
```

Airflow sees this as: "run `extract`, then `transform`, then `load`." It doesn't know or care what data each task produces. If `transform` fails and you fix the bug, you clear the task instance and rerun it — but Airflow doesn't know whether the output table is fresh or stale.

### Dagster: Data-centric

In Dagster, you define **assets** — the data artifacts your pipeline produces. Dependencies are between the *data*, not the *tasks*:

```python
# Dagster: you define data assets and their dependencies
@asset
def raw_data():
    return pull_from_api()

@asset
def clean_data(raw_data):
    return clean(raw_data)

@asset
def report(clean_data):
    write_to_db(clean_data)
```

Dagster sees this as: "`report` depends on `clean_data`, which depends on `raw_data`." The UI shows a lineage graph of your data. You can see when each asset was last materialized, whether it's stale, and what depends on it. If `raw_data` gets updated, Dagster knows `clean_data` and `report` are now stale.

### What this means in practice

| Scenario | Airflow | Dagster |
| --- | --- | --- |
| "Is this table fresh?" | Check task run history, hope the right DAG ran | Asset page shows last materialization time and staleness |
| "What depends on this table?" | Read the code of every DAG | Lineage graph shows all downstream assets |
| "Rerun just this table" | Clear the task instance, hope XCom state is still valid | Click "Materialize" on the asset |
| "Run this pipeline on a subset of data" | Build custom logic with Airflow params | Partitioned assets — built-in support for date/key partitions |
| "Test my pipeline logic" | Spin up Airflow or mock the context | `materialize_to_memory([my_asset])` in a pytest |
| "Two teams write to the same table" | Silent conflict, last writer wins | Dagster warns about duplicate asset definitions |

## Feature-by-Feature Comparison

### Passing Data Between Steps

**Airflow: XCom (Cross-Communication)**

XCom lets tasks push and pull small pieces of data through the metadata database. When a task returns a value, it's serialized and stored in `airflow.db`. Downstream tasks pull it by referencing the upstream task ID.

```python
@task
def extract():
    return {"user_count": 42}  # Automatically pushed to XCom

@task
def report(data):
    print(data["user_count"])  # Pulled from XCom

report(extract())  # Airflow wires the XCom transfer
```

Limitations: XCom is stored in the metadata DB, so it's meant for small data (configs, row counts, file paths) — not DataFrames or large datasets. Passing large data requires writing to external storage and passing the path via XCom.

**Dagster: IO Managers**

Dagster handles data passing through **IO Managers** — pluggable backends that control how asset outputs are stored and loaded. The default stores data in memory or local files, but you can swap in S3, GCS, or a database.

```python
@asset
def extract():
    return {"user_count": 42}  # Stored by the IO manager

@asset
def report(extract):
    print(extract["user_count"])  # Loaded by the IO manager
```

The key difference: IO managers are **typed and configurable**. You can have one IO manager that writes Parquet to S3 in production and another that keeps everything in memory for tests — without changing asset code.

---

### Connecting to External Systems

**Airflow: Hooks and Connections**

A **Connection** is a stored credential (host, port, login, password) managed in the UI or environment variables. A **Hook** is a Python class that uses a Connection to interact with an external system.

```python
from airflow.providers.postgres.hooks.postgres import PostgresHook

@task
def query_db():
    hook = PostgresHook(postgres_conn_id="my_postgres")  # Uses stored Connection
    records = hook.get_records("SELECT * FROM users")
    return records
```

Connections are stored in `airflow.db` (encrypted with Fernet key) or as environment variables (`AIRFLOW_CONN_MY_POSTGRES`). Hooks are provided by **provider packages** (e.g., `apache-airflow-providers-postgres`).

**Dagster: Resources**

A **Resource** is a configurable, injectable dependency. Instead of tasks reaching out to fetch their own connections, resources are declared centrally and injected into assets.

```python
from dagster import asset, ConfigurableResource
import psycopg2

class PostgresResource(ConfigurableResource):
    host: str
    port: int = 5432
    user: str
    password: str
    database: str

    def query(self, sql):
        conn = psycopg2.connect(host=self.host, port=self.port, ...)
        return conn.cursor().execute(sql).fetchall()

@asset
def users(postgres: PostgresResource):  # Injected automatically
    return postgres.query("SELECT * FROM users")

defs = Definitions(
    assets=[users],
    resources={"postgres": PostgresResource(host="localhost", ...)},
)
```

Resources are type-checked, testable (swap in a mock resource), and defined in Python — no UI or env var wiring needed.

---

### Operators vs Assets

**Airflow: Operators**

Operators are pre-built task templates for common operations. Instead of writing Python to interact with every system, you use an Operator.

```python
from airflow.providers.common.sql.operators.sql import SQLExecuteQueryOperator

query_task = SQLExecuteQueryOperator(
    task_id="run_query",
    conn_id="my_postgres",
    sql="INSERT INTO summary SELECT * FROM raw_data",
)
```

Common operators: `BashOperator`, `PythonOperator`, `SQLExecuteQueryOperator`, `S3ToRedshiftOperator`. They come from provider packages and abstract away boilerplate.

**Dagster: No direct equivalent — assets are the abstraction**

Dagster doesn't have operators because assets are already Python functions. You use resources and normal Python libraries directly. The closest equivalent is pre-built **integrations** (e.g., `dagster-dbt`, `dagster-airbyte`) that expose external tools as assets.

---

### Scheduling

**Airflow: Schedule on the DAG**

Each DAG has a `schedule` parameter. The scheduler creates DAG runs at each interval.

```python
with DAG(
    dag_id="daily_etl",
    schedule="@daily",          # Cron presets or cron expression
    start_date=datetime(2025, 1, 1),
    catchup=False,              # Don't backfill missed runs
):
    ...
```

Schedules are time-based only. For event-driven triggers, you use **Sensors** — tasks that poll and wait for a condition (file exists, partition ready, etc.). Sensors occupy a worker slot while waiting (unless using deferrable sensors).

**Dagster: Schedules, Sensors, and Auto-Materialization**

Dagster supports three trigger mechanisms:

```python
# 1. Cron schedule (same as Airflow)
@schedule(cron_schedule="0 0 * * *", target=my_job)
def daily_schedule():
    return {}

# 2. Sensor — event-driven, doesn't occupy a worker
@sensor(target=my_job)
def new_file_sensor(context):
    if check_for_new_file():
        yield RunRequest()

# 3. Auto-materialization — Dagster reruns assets when upstream data changes
@asset(auto_materialize_policy=AutoMaterializePolicy.eager())
def downstream(upstream):
    ...
```

Auto-materialization is unique to Dagster — no equivalent in Airflow. When `upstream` gets a new materialization, Dagster automatically triggers `downstream`.

---

### Partitions and Backfills

**Airflow: Catchup and Manual Backfills**

Airflow partitions by **execution date**. Setting `catchup=True` makes Airflow create runs for every missed schedule interval. Backfills are triggered via CLI:

```bash
airflow dags backfill --start-date 2025-01-01 --end-date 2025-01-31 my_dag
```

Each backfill run is a full DAG run for that date. There's no built-in concept of partitioning by key (e.g., by customer, region).

**Dagster: First-Class Partitions**

Partitions are a core concept. Assets can be partitioned by time, keys, or custom logic:

```python
daily_partitions = DailyPartitionsDefinition(start_date="2025-01-01")

@asset(partitions_def=daily_partitions)
def daily_events(context):
    date = context.partition_key  # "2025-01-15"
    return fetch_events(date)

# Also supports static partitions
region_partitions = StaticPartitionsDefinition(["us-east", "us-west", "eu"])

@asset(partitions_def=region_partitions)
def regional_report(context):
    region = context.partition_key
    ...
```

The UI shows partition status as a grid — you can see which partitions are materialized, stale, or failed, and backfill specific partitions with a click.

---

### Testing

**Airflow: Hard to unit test**

Tasks depend on Airflow's runtime context. Testing typically requires either running a full Airflow instance or heavy mocking:

```python
# You can test the underlying function, but not the Airflow wiring
def test_extract():
    # Can't easily test XCom, connections, or operator behavior
    # without mocking airflow internals
    result = extract_logic()
    assert result == expected
```

Airflow 3 improved this with the TaskFlow API, but testing cross-task data flow (XCom), connections, and operator behavior still requires integration tests.

**Dagster: Built for testing**

Assets are plain functions. Dagster provides `materialize_to_memory()` for integration tests without any infrastructure:

```python
def test_pipeline():
    result = materialize_to_memory([raw_data, clean_data, report])
    assert result.success
    assert result.output_for_node("clean_data") == expected

def test_with_mock_resource():
    result = materialize_to_memory(
        [users],
        resources={"postgres": MockPostgres()},  # Swap resource for testing
    )
    assert result.success
```

---

### Error Handling and Retries

**Airflow: Task-level retries**

Retries are configured per task. When a task fails, Airflow retries it after a delay:

```python
@task(retries=3, retry_delay=timedelta(minutes=5))
def flaky_api_call():
    ...
```

You can also set `on_failure_callback`, `on_retry_callback`, and `sla_miss_callback` for alerting. Failed tasks can be manually cleared and rerun from the UI.

**Dagster: Op-level retries + run-level retries**

Dagster supports retries at both the op (step) level and the full run level:

```python
@asset(retry_policy=RetryPolicy(max_retries=3, delay=5))
def flaky_asset():
    ...
```

Dagster also has **run failure sensors** — custom logic that triggers when a run fails (e.g., send a Slack alert, create a PagerDuty incident).

---

### Variables and Configuration

**Airflow: Variables**

Key-value pairs stored in `airflow.db`, accessible from any task:

```python
from airflow.models import Variable

@task
def my_task():
    api_key = Variable.get("api_key")
    threshold = Variable.get("threshold", default_var=100, deserialize_json=True)
```

Variables are managed in the UI or CLI. They're untyped strings (or JSON). Every `Variable.get()` call hits the database.

**Dagster: Config and Resources**

Configuration is type-checked and passed explicitly:

```python
from dagster import asset, Config

class MyConfig(Config):
    api_key: str
    threshold: int = 100

@asset
def my_asset(config: MyConfig):
    print(config.api_key)
    print(config.threshold)
```

Config is validated before the run starts — you get errors at launch time, not mid-pipeline. For shared config, use resources instead.

## Quick Comparison

| Aspect | Airflow | Dagster |
| --- | --- | --- |
| **Core abstraction** | Tasks and DAGs (task-centric) | Assets and software-defined assets (data-centric) |
| **Scheduling model** | Time-based schedules and cron expressions | Time-based, asset-materialization triggers, and sensors |
| **Data awareness** | Tasks are opaque — Airflow doesn't know what data a task produces | Assets are first-class — Dagster tracks what data exists and its lineage |
| **Testing** | Requires a running Airflow instance or mocking the execution context | Assets are plain Python functions, testable with `materialize_to_memory()` |
| **Local development** | Needs `db migrate` + multiple services (scheduler, webserver, etc.) | `dagster dev` starts everything in one command |
| **Configuration** | `airflow.cfg` file + environment variable overrides | `dagster.yaml` + Python-native `Definitions` object |
| **Parameterization** | Airflow Variables, Connections, and Params | Dagster Resources and Config schemas (type-checked) |
| **Retry/backfill** | Reruns tasks by clearing task instances | Reruns by re-materializing assets, with partition-aware backfills |
| **UI focus** | Task run history, Gantt charts, task logs | Asset lineage graph, materialization history, asset health |
