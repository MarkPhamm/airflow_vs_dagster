from datetime import datetime

from airflow.sdk import DAG, task

with DAG(
    dag_id="example_dag",
    start_date=datetime(2025, 1, 1),
    schedule="@daily",
    catchup=False,
    tags=["example"],
) as dag:

    @task
    def hello():
        print("Hello from Airflow!")
        return "hello"

    @task
    def goodbye(greeting: str):
        print(f"Received: {greeting}. Goodbye!")

    goodbye(hello())
