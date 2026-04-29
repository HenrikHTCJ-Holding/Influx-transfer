# InfluxDB → SQL Server transfer (Azure Functions)

This repo contains a Python job that extracts time-series data from **InfluxDB 2.x** and writes it to an **on-prem SQL Server** table.
It now runs as an **Azure Function** HTTP trigger via `function_app.py`, suitable for Power Automate.

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

## Run as Azure Function locally

1. Copy `local.settings.json.example` to `local.settings.json`.
2. Fill in all required `INFLUX_*` and `SQLSERVER_*` values.
3. Start the function host:

```bash
func start
```

HTTP endpoint route is `influx-to-sql-transfer` and method is `POST`.
With `auth_level=FUNCTION`, call it using the function key (Power Automate can send this as query param `code`).

Successful HTTP response contains:
- `rowsUpserted`: number of rows merged into SQL
- `rowCount`: number of rows returned
- `rows`: array of row objects (JSON-safe, `Time` in UTC ISO format)

In Power Automate:
1. Use **HTTP** action to call the endpoint.
2. Use **Parse JSON** on `body('HTTP')?['rows']`.
3. Use **Create CSV table** from the parsed array.
4. Use **SharePoint - Create file** to save the CSV in your target folder.

### SQL index (recommended)

To enforce idempotency and prevent duplicates, add a **unique index** on:

- `[Time]`, `[ARC]`, `[MachineName]`
