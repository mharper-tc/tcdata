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

import mimetypes
import os
import requests
import pandas as pd

__version__ = "0.8.1"

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
    chart_type: str = "line",
    description: str | None = None,
    frequency: str | None = None,
    coverage: str | None = None,
    company_name: str | None = None,
    company_sector: str | None = None,
) -> dict:
    """
    Create a new dataset you'll then push/attach data to. Returns the created
    row, including its "id" -- pass that as dataset_id to push()/attach().

    kind is "timeseries" for push() data or "file" for attach() (PDF/CSV)
    datasets.

    chart_type ("line" or "stacked_bar") only matters for kind="timeseries" --
    it controls how the frontend charts this dataset's metrics. "stacked_bar"
    plots every metric in this dataset as a stacked segment per date, so keep
    metrics that should chart together (e.g. a set of percentages that sum to
    100%) in their own dataset rather than mixed with unrelated metrics.

    If this is the first dataset created for this ticker, a companies row is
    auto-created too (so the stock page has something to show) -- pass
    company_name/company_sector to set it properly, otherwise it falls back
    to the ticker itself as the name. Ignored if the ticker already has a
    companies row.
    """
    if kind not in ("timeseries", "file"):
        raise ValueError("kind must be 'timeseries' or 'file'")
    if chart_type not in ("line", "stacked_bar"):
        raise ValueError("chart_type must be 'line' or 'stacked_bar'")

    resp = requests.post(
        f"{_base_url()}/datasets",
        json={
            "ticker": ticker,
            "name": name,
            "kind": kind,
            "chart_type": chart_type,
            "description": description,
            "frequency": frequency,
            "coverage": coverage,
            "company_name": company_name,
            "company_sector": company_sector,
        },
        headers=_headers(),
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def update_dataset(
    dataset_id: int,
    name: str | None = None,
    description: str | None = None,
    frequency: str | None = None,
    coverage: str | None = None,
    chart_type: str | None = None,
) -> dict:
    """
    Change an existing dataset's metadata -- e.g. switching chart_type from
    "line" to "stacked_bar" -- without recreating it and losing its pushed
    history. Only pass the fields you want to change; the rest are left as-is.
    """
    if chart_type is not None and chart_type not in ("line", "stacked_bar"):
        raise ValueError("chart_type must be 'line' or 'stacked_bar'")

    fields = {
        "name": name,
        "description": description,
        "frequency": frequency,
        "coverage": coverage,
        "chart_type": chart_type,
    }
    updates = {k: v for k, v in fields.items() if v is not None}
    if not updates:
        raise ValueError("pass at least one field to update")

    resp = requests.patch(
        f"{_base_url()}/datasets/{dataset_id}",
        json=updates,
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
            files={"file": (filename, f, mimetypes.guess_type(filename)[0] or "application/octet-stream")},
            headers=_headers(),
            timeout=60,
        )
    resp.raise_for_status()
    return resp.json()


def post_desk_note(
    ticker: str,
    title: str,
    filepath: str,
    subtext: str | None = None,
    report_date: str | None = None,
    kind: str = "desk_notes",
) -> dict:
    """
    Upload a desk note or formal note (PDF) for a ticker -- shows up in the
    corresponding section on that ticker's stock page. Simpler than
    create_dataset() + attach(): your collection for this ticker is found or
    created automatically, so there's no dataset_id to manage.

    subtext is an optional one-line summary shown under the note's title.
    report_date ("YYYY-MM-DD") is the date the report is actually about --
    distinct from when it happens to be uploaded. Defaults to the upload date
    if not given.
    kind is "desk_notes" (default) or "formal_notes".

        tcdata.post_desk_note(
            ticker="MP1", title="Q3 thesis update", filepath="note.pdf",
            report_date="2026-08-24",
        )
        tcdata.post_desk_note(
            ticker="MP1", title="Initiation of Coverage", filepath="report.pdf",
            kind="formal_notes",
        )
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(filepath)
    if kind not in ("desk_notes", "formal_notes"):
        raise ValueError("kind must be 'desk_notes' or 'formal_notes'")

    filename = os.path.basename(filepath)
    data = {"ticker": ticker, "title": title, "kind": kind}
    if subtext:
        data["subtext"] = subtext
    if report_date:
        data["report_date"] = report_date
    with open(filepath, "rb") as f:
        resp = requests.post(
            f"{_base_url()}/desk-notes",
            data=data,
            files={"file": (filename, f, mimetypes.guess_type(filename)[0] or "application/octet-stream")},
            headers=_headers(),
            timeout=60,
        )
    resp.raise_for_status()
    return resp.json()