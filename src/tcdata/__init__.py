"""
tcdata - Taylor Collison alt-data client library.

Analysts start a scraper with:

    import tcdata
    dataset = tcdata.create_dataset(ticker="AAPL", name="Daily Close Price")
    tcdata.push(dataset_id=dataset["id"], df=my_wide_dataframe)   # time-series
    tcdata.attach(dataset_id=dataset["id"], filepath="note.pdf")  # a file

Requires the TC_DATA_KEY environment variable (the analyst's API key).
The wide -> narrow melt happens here, so scrapers stay simple.
"""

import os
import requests
import pandas as pd

__version__ = "0.3.0"

DEFAULT_URL = "https://web-production-80d10.up.railway.app"


def _base_url() -> str:
    return os.environ.get("TC_DATA_URL", DEFAULT_URL).rstrip("/")


def _api_key() -> str:
    key = os.environ.get("TC_DATA_KEY")
    if not key:
        raise RuntimeError(
            "TC_DATA_KEY environment variable is not set. "
            "Set it to your Taylor Collison API key before pushing."
        )
    return key


def _headers() -> dict:
    return {"X-API-Key": _api_key()}


def create_dataset(
    ticker: str,
    name: str,
    kind: str = "timeseries",
    description: str | None = None,
    frequency: str | None = None,
    coverage: str | None = None,
) -> dict:
    """
    Create a new dataset you'll then push/attach data to. Returns the created
    row, including its "id" -- pass that as dataset_id to push()/attach().

    kind is "timeseries" for push() data or "file" for attach() (PDF/CSV)
    datasets.
    """
    if kind not in ("timeseries", "file"):
        raise ValueError("kind must be 'timeseries' or 'file'")

    resp = requests.post(
        f"{_base_url()}/datasets",
        json={
            "ticker": ticker,
            "name": name,
            "kind": kind,
            "description": description,
            "frequency": frequency,
            "coverage": coverage,
        },
        headers=_headers(),
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def push(
    dataset_id: int,
    df: pd.DataFrame,
    date_column: str = "date",
    column_formats: dict[str, str] | None = None,
) -> dict:
    """
    Push a WIDE time-series dataframe to the platform.

    Expects a date column plus one column per metric, e.g.:

        date        avg_price   sku_count
        2026-08-15  43.75       1902

    Everything except the date column is treated as a metric, melted to
    narrow rows (date, metric, value) and sent to /push.

    column_formats optionally maps metric name -> display format
    (e.g. {"avg_price": "usd", "sku_count": "number"}), stored on the
    dataset so the frontend knows how to render each metric.
    """
    if date_column not in df.columns:
        raise ValueError(
            f"dataframe must have a '{date_column}' column; got {list(df.columns)}"
        )

    narrow = df.melt(
        id_vars=[date_column],
        var_name="metric",
        value_name="value",
    ).dropna(subset=["value"])

    rows = [
        {
            "date": str(pd.to_datetime(r[date_column]).date()),
            "metric": str(r["metric"]),
            "value": float(r["value"]),
        }
        for _, r in narrow.iterrows()
    ]

    if not rows:
        raise ValueError("no data rows to push after melting")

    payload = {"dataset_id": dataset_id, "rows": rows}
    if column_formats:
        payload["column_formats"] = column_formats

    resp = requests.post(
        f"{_base_url()}/push",
        json=payload,
        headers=_headers(),
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def attach(dataset_id: int, filepath: str) -> dict:
    """
    Upload a file (PDF or CSV) to the platform, attached to a dataset.
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(filepath)

    filename = os.path.basename(filepath)
    with open(filepath, "rb") as f:
        resp = requests.post(
            f"{_base_url()}/upload",
            data={"dataset_id": dataset_id},
            files={"file": (filename, f)},
            headers=_headers(),
            timeout=60,
        )
    resp.raise_for_status()
    return resp.json()