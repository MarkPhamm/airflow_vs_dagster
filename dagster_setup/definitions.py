import dagster as dg


@dg.asset
def hello() -> str:
    print("Hello from Dagster!")
    return "hello"


@dg.asset(deps=[hello])
def goodbye() -> None:
    print("Goodbye from Dagster!")


defs = dg.Definitions(assets=[hello, goodbye])
