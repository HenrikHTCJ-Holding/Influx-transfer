# InfluxDB → SQL Server transfer (Azure Pipelines)

This repo contains a Python job that extracts time-series data from **InfluxDB 2.x** and writes it to an **on‑prem SQL Server** table.

## Run locally

Install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate  # (Windows: .venv\Scripts\activate)
pip install -r requirements.txt
```

Set environment variables:

### InfluxDB (v2)

- `INFLUX_URL`
- `INFLUX_TOKEN` (secret)
- `INFLUX_ORG`
- `INFLUX_BUCKET`
- `INFLUX_MEASUREMENT`
- `INFLUX_FIELDS` (comma-separated; e.g. `Current[A],Voltage[V]`)
- `INFLUX_RANGE_START` (default `-24h`)

### SQL Server (on‑prem)

- `SQLSERVER_HOST`
- `SQLSERVER_DB`
- `SQLSERVER_USER`
- `SQLSERVER_PASSWORD` (secret)
- `SQLSERVER_SCHEMA` (default `dbo`)
- `SQLSERVER_TABLE`

Run:

```bash
python -m src.transfer.main
```

## Azure Pipelines

Pipeline file: `[azure-pipelines.yml](azure-pipelines.yml)`

### Required pipeline variables

Create these as pipeline variables (mark secrets as secret) or via a variable group:

- `ON_PREM_AGENT_POOL` (name of your self-hosted agent pool)

**Influx:**

- `INFLUX_URL`
- `INFLUX_TOKEN` (secret)
- `INFLUX_ORG`
- `INFLUX_BUCKET`
- `INFLUX_MEASUREMENT`
- `INFLUX_FIELDS`

**SQL Server:**

- `SQLSERVER_HOST`
- `SQLSERVER_DB`
- `SQLSERVER_USER`
- `SQLSERVER_PASSWORD` (secret)
- `SQLSERVER_TABLE`

Optional:

- `SQLSERVER_DRIVER` (default: `ODBC Driver 18 for SQL Server`)
- `SQLSERVER_PORT` (default: `1433`)
- `SQLSERVER_ENCRYPT` (default: `yes`)
- `SQLSERVER_TRUST_CERT` (default: `no`)
- `INFLUX_TAG_COLUMNS` (default: welding tags used in the original script)
- `INFLUX_AGG_EVERY` (default: `1m`)
- `INFLUX_AGG_FN` (default: `mean`)
- `INFLUX_CREATE_EMPTY` (default: `true`)
- `INFLUX_TIMEOUT_MS` (default: `120000`)
- `SQLSERVER_TIMEOUT_SECONDS` (default: `120`)

### SQL index (recommended)

To enforce idempotency and prevent duplicates, add a **unique index** on:

- `[Time]`, `[ARC]`, `[MachineName]`
