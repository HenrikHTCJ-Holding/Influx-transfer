# InfluxDB query → JSON (Azure Functions, Power Automate)

This repo contains a Python **Azure Function** that queries **InfluxDB 2.x** and returns **JSON** (`rows`) for **Power Automate** to turn into a CSV and save to SharePoint.

There is **no SQL Server write** in this path.

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

Optional:

- `INFLUX_TAG_COLUMNS`
- `INFLUX_AGG_EVERY` (default `1m`)
- `INFLUX_AGG_FN` (default `mean`)
- `INFLUX_CREATE_EMPTY` (default `true`)
- `INFLUX_TIMEOUT_MS` (default `120000`)

Run the query script:

```bash
python -m src.transfer.main
```

## Run as Azure Function locally

1. Copy `local.settings.json.example` to `local.settings.json`.
2. Fill in all required `INFLUX_*` values.
3. Start the function host:

```bash
func start
```

HTTP endpoint route is `influx-to-sql-transfer` and method is `POST`.
With `auth_level=FUNCTION`, call it using the function key (Power Automate can send this as query param `code`).

Successful HTTP response contains:

- `rowsUpserted`: same as `rowCount` (kept for backward compatibility with earlier flows)
- `rowCount`: number of rows returned
- `rows`: array of row objects (JSON-safe, `Time` in UTC ISO format)

In Power Automate:

1. Use **HTTP** action to call the endpoint.
2. Use **Parse JSON** on `body('HTTP')?['rows']`.
3. Use **Create CSV table** from the parsed array.
4. Use **SharePoint - Create file** to save the CSV in your target folder.

## Azure App settings (Function App)

In Azure Portal → Function App → **Environment variables** → **Application settings**, set the same `INFLUX_*` variables as above. No SQL settings are required.
