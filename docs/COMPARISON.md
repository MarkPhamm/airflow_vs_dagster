# Airflow vs Dagster Comparison

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
