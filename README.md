# tcdata

Python client library for pushing data into Taylor Collison's alt-data platform.
If you're an analyst writing a scraper, this is what you import at the end of it
to get your data onto the platform clients see.

## How the platform fits together

Three separate repos:

- **tcdata** (this one) — the library you import in your scraper.
- **tc-ingestion** — the API this library talks to (`POST /datasets`, `/push`,
  `/upload`). Deployed on Railway.
- **tc-frontend** — the client-facing site (dashboard, stock pages) and the
  analyst admin portal (manage clients, grant entitlements).

You never call tc-ingestion directly — `tcdata` wraps it.

## Before you start

You need two things from an admin (not something you set up yourself):

1. **An analyst account** — a row in the `analysts` table, linked to a login.
2. **An API key** — a per-analyst secret that authenticates your pushes.
   Ask your admin for it; there's no self-serve way to fetch it.

## Install

```bash
pip install git+https://github.com/mharper-tc/tcdata.git
```

## Configure

Set your API key as an environment variable before running your scraper:

```bash
export TC_DATA_KEY=your-api-key-here      # macOS/Linux
$env:TC_DATA_KEY = "your-api-key-here"    # Windows PowerShell
```

(Optional: `TC_DATA_URL` overrides the default ingestion URL — only needed if
you're testing against a local `tc-ingestion` instance instead of the deployed
one.)

## Usage

### 1. Create a dataset

Every dataset needs a ticker, a name, and a `kind` — do this once per dataset,
not on every scraper run (it creates a new row each time).

```python
import tcdata

dataset = tcdata.create_dataset(
    ticker="AAPL",
    name="Daily Close Price",
    kind="timeseries",              # or "file" for PDF/CSV attachments
    chart_type="line",              # or "stacked_bar" -- see below
    description="End-of-day close and adjusted close.",
    frequency="Daily",
    coverage="2020-present",
    company_name="Apple Inc.",      # only matters the first time this ticker appears
    company_sector="Technology",
)
print(dataset["id"])  # save this -- you'll pass it to push()/attach() below
```

You only own datasets you create — pushing to someone else's `dataset_id`
is rejected.

If `ticker` has never been used before, a `companies` row is created for it
automatically (falling back to the ticker itself as the name if you don't
pass `company_name`) — otherwise the stock page has nothing to show and
errors with "No company found". Only matters on the *first* dataset for a
new ticker; existing tickers are never overwritten.

#### Chart type

`chart_type` controls how the stock page charts this dataset's metrics:

- `"line"` (default) — charts the first metric only, as a line.
- `"stacked_bar"` — charts **every** metric in the dataset, stacked per date.
  Use this for metrics that make sense summed together (e.g. a set of
  percentages that add to 100%, or category counts). Keep unrelated metrics
  in separate datasets rather than mixing them into one stacked chart.

To change an existing dataset's chart type (or name/description/frequency/
coverage) without recreating it and losing its pushed history:

```python
tcdata.update_dataset(dataset_id=dataset["id"], chart_type="stacked_bar")
```

Only pass the fields you want to change.

### 2. Push time-series data

`push()` takes a **wide** dataframe — one `date` column, one column per
metric — and melts it to narrow rows for you:

```python
import pandas as pd

df = pd.DataFrame({
    "date":       ["2026-08-17", "2026-08-18"],
    "close":      [212.45, 213.10],
    "adj_close":  [212.45, 213.10],
})

tcdata.push(dataset_id=dataset["id"], df=df)
```

Re-pushing the same `(date, metric)` overwrites the value (safe to re-run for
corrections/backfills).

#### Optional: tell the frontend how to display a metric

`column_formats` maps metric name -> display format. Supported values:
`"usd"`, `"percent"`, `"number"`, `"thousands"`, `"millions"`, `"billions"`,
`"trillions"` (the last four divide the value and append K/M/B/T — handy for
large counts like token volumes). Anything else falls back to a plain number.
It merges with whatever's already set, so you only need to pass it when
introducing a new metric or changing an existing one:

```python
tcdata.push(
    dataset_id=dataset["id"],
    df=df,
    column_formats={"close": "usd", "adj_close": "usd"},
)
```

### 3. Attach a file (PDF/CSV)

For `kind="file"` datasets — coverage reports, analyst notes, etc:

```python
file_dataset = tcdata.create_dataset(
    ticker="AAPL", name="Analyst Coverage Report", kind="file"
)
tcdata.attach(dataset_id=file_dataset["id"], filepath="coverage_note.pdf")
```

Clients download these through an entitlement-checked signed URL — there's
no public link, so `attach()` is all you need to do; access control is
handled elsewhere (the admin portal's entitlements).

## Errors

Every call raises on failure (`requests.HTTPError` or a `ValueError` for bad
input) rather than returning a silent failure — wrap in `try`/`except` if your
scraper needs to keep going after one push fails. Common cases:

- `401` — `TC_DATA_KEY` missing or invalid.
- `403` — you tried to push to a `dataset_id` you don't own.
- `404` — `dataset_id` doesn't exist.
