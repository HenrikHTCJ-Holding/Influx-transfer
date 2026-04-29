import os
import sys
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd
import pyodbc
from influxdb_client import InfluxDBClient


def _env(name: str, *, required: bool = True, default: str | None = None) -> str:
    value = os.getenv(name, default)
    if required and (value is None or value == ""):
        raise RuntimeError(f"Missing required environment variable: {name}")
    assert value is not None
    return value


def _sql_conn() -> pyodbc.Connection:
    driver = os.getenv("SQLSERVER_DRIVER", "ODBC Driver 18 for SQL Server")
    host = _env("SQLSERVER_HOST")
    port = os.getenv("SQLSERVER_PORT", "1433")
    db = _env("SQLSERVER_DB")
    user = _env("SQLSERVER_USER")
    password = _env("SQLSERVER_PASSWORD")

    encrypt = os.getenv("SQLSERVER_ENCRYPT", "yes")
    trust_cert = os.getenv("SQLSERVER_TRUST_CERT", "no")
    timeout = os.getenv("SQLSERVER_TIMEOUT_SECONDS", "120")

    conn_str = (
        f"DRIVER={{{driver}}};"
        f"SERVER={host},{port};"
        f"DATABASE={db};"
        f"UID={user};PWD={password};"
        f"Encrypt={encrypt};TrustServerCertificate={trust_cert};"
        f"Connection Timeout={timeout};"
    )
    return pyodbc.connect(conn_str)


def _influx_client() -> InfluxDBClient:
    url = _env("INFLUX_URL")
    token = _env("INFLUX_TOKEN")
    org = _env("INFLUX_ORG")
    timeout_ms = int(os.getenv("INFLUX_TIMEOUT_MS", "120000"))
    return InfluxDBClient(url=url, token=token, org=org, timeout=timeout_ms)


def _build_flux_query(*, bucket: str, start: str) -> str:
    measurement = _env("INFLUX_MEASUREMENT")
    field_list = _env("INFLUX_FIELDS")  # comma-separated
    tag_cols = os.getenv(
        "INFLUX_TAG_COLUMNS",
        "ARC,Equipment\\\\Type,Machine\\\\Name,Project\\\\No,Section\\\\Type,Tower\\\\No",
    )

    fields = [f.strip() for f in field_list.split(",") if f.strip()]
    if not fields:
        raise RuntimeError("INFLUX_FIELDS must contain at least one field name")

    keep_cols = ["_time", "_field", "_value"] + [c.strip() for c in tag_cols.split(",") if c.strip()]
    keep_cols_flux = ", ".join([f'"{c}"' for c in keep_cols])

    filters = "\n      ".join([f'r._field == "{f}" or' for f in fields]).rstrip("or")

    group_cols = [c for c in keep_cols if c not in ("_time", "_value")]
    group_cols_flux = ", ".join([f'"{c}"' for c in group_cols])

    window_every = os.getenv("INFLUX_AGG_EVERY", "1m")
    agg_fn = os.getenv("INFLUX_AGG_FN", "mean")
    create_empty = os.getenv("INFLUX_CREATE_EMPTY", "true").lower() in ("1", "true", "yes")

    pivot_row_key = ["_time"] + [c for c in group_cols if c != "_field"]
    pivot_row_key_flux = ", ".join([f'"{c}"' for c in pivot_row_key])

    return f'''
from(bucket: "{bucket}")
  |> range(start: {start})
  |> filter(fn: (r) => r._measurement == "{measurement}")
  |> filter(fn: (r) =>
      {filters}
  )
  |> keep(columns: [{keep_cols_flux}])
  |> group(columns: [{group_cols_flux}])
  |> aggregateWindow(every: {window_every}, fn: {agg_fn}, createEmpty: {str(create_empty).lower()})
  |> pivot(
      rowKey: [{pivot_row_key_flux}],
      columnKey: ["_field"],
      valueColumn: "_value"
  )
'''


def _rename_and_clean(df: pd.DataFrame) -> pd.DataFrame:
    rename_map = {
        "_time": "Time",
        "Equipment\\Type": "EquipmentType",
        "Machine\\Name": "MachineName",
        "Project\\No": "ProjectNo",
        "Section\\Type": "SectionType",
        "Tower\\No": "TowerNo",
        "Current[A]": "Current",
        "Voltage[V]": "Voltage",
        "WFS\\[in/min]": "WireSpeed",
        "Target\\Current[A]": "TargetCurrent",
        "Target\\Voltage[V]": "TargetVoltage",
    }
    df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})

    if "Time" in df.columns:
        df["Time"] = pd.to_datetime(df["Time"], utc=True, errors="coerce")

    numeric_cols = [c for c in ["Current", "Voltage", "WireSpeed", "TargetCurrent", "TargetVoltage"] if c in df.columns]
    for c in numeric_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    df = df.replace([np.inf, -np.inf], np.nan)
    if numeric_cols:
        df[numeric_cols] = df[numeric_cols].astype(object).where(pd.notnull(df[numeric_cols]), None)

    text_not_null = ["ARC", "EquipmentType", "MachineName", "ProjectNo", "SectionType", "TowerNo"]
    for c in text_not_null:
        if c not in df.columns:
            df[c] = ""
        df[c] = df[c].astype(object).where(df[c].notna(), "")
        df[c] = df[c].apply(lambda x: "" if x is None else str(x))

    keep_cols = [
        "Time",
        "ARC",
        "EquipmentType",
        "MachineName",
        "ProjectNo",
        "SectionType",
        "TowerNo",
        "Current",
        "Voltage",
        "WireSpeed",
        "TargetCurrent",
        "TargetVoltage",
    ]
    df = df.loc[:, [c for c in keep_cols if c in df.columns]]
    return df


def _qualified_table() -> str:
    schema = os.getenv("SQLSERVER_SCHEMA", "dbo")
    table = _env("SQLSERVER_TABLE")
    # Avoid SQL injection by restricting to simple identifiers.
    for part in (schema, table):
        if not part.replace("_", "").isalnum():
            raise RuntimeError(f"Invalid SQL identifier: {part!r}")
    return f"[{schema}].[{table}]"


def _upsert_by_key(cur: pyodbc.Cursor, *, table_sql: str, df: pd.DataFrame) -> int:
    if df.empty:
        return 0

    key_cols = ["Time", "ARC", "MachineName"]
    missing = [c for c in key_cols if c not in df.columns]
    if missing:
        raise RuntimeError(f"Expected key columns to exist for upsert keying: {missing}")

    # Drop rows with any null key part to avoid violating key assumptions.
    df = df.dropna(subset=key_cols).copy()
    if df.empty:
        return 0

    cols = list(df.columns)
    insert_cols_sql = ", ".join(f"[{c}]" for c in cols)
    source_select_sql = ", ".join([f"? AS [{c}]" for c in cols])

    update_cols = [c for c in cols if c not in key_cols]
    if not update_cols:
        raise RuntimeError(f"Upsert requires at least one non-key column besides {key_cols}")

    update_set_sql = ", ".join([f"tgt.[{c}] = src.[{c}]" for c in update_cols])

    sql = f"""
MERGE {table_sql} AS tgt
USING (SELECT {source_select_sql}) AS src
ON (tgt.[Time] = src.[Time] AND tgt.[ARC] = src.[ARC] AND tgt.[MachineName] = src.[MachineName])
WHEN MATCHED THEN
  UPDATE SET {update_set_sql}
WHEN NOT MATCHED THEN
  INSERT ({insert_cols_sql})
  VALUES ({", ".join([f"src.[{c}]" for c in cols])});
"""

    rows = list(df.itertuples(index=False, name=None))
    cur.fast_executemany = True
    cur.executemany(sql, rows)
    return len(rows)


def _to_json_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    result = df.copy()
    if "Time" in result.columns:
        result["Time"] = pd.to_datetime(result["Time"], utc=True, errors="coerce")
        result["Time"] = result["Time"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        result["Time"] = result["Time"].where(result["Time"].notna(), None)
    return result.to_dict(orient="records")


def transfer() -> tuple[int, list[dict[str, Any]]]:
    bucket = _env("INFLUX_BUCKET")
    start = os.getenv("INFLUX_RANGE_START", "-24h")

    print(f"[{datetime.now(timezone.utc).isoformat()}] Starting transfer (start={start}, key=Time+ARC+MachineName)")

    query = _build_flux_query(bucket=bucket, start=start)

    with _influx_client() as client:
        dfs = client.query_api().query_data_frame_stream(query)
        df = pd.concat(list(dfs), ignore_index=True) if dfs is not None else pd.DataFrame()

    df = _rename_and_clean(df)
    if df.empty:
        print("No rows returned from Influx for the selected range; nothing to insert.")
        return 0, []

    records = _to_json_records(df)

    table_sql = _qualified_table()
    conn = _sql_conn()
    try:
        cur = conn.cursor()
        affected = _upsert_by_key(cur, table_sql=table_sql, df=df)
        conn.commit()
        print(f"Upserted {affected} rows into {table_sql} (key=[Time, ARC, MachineName]).")
    finally:
        conn.close()

    return affected, records


def main() -> int:
    affected, _ = transfer()
    return affected


if __name__ == "__main__":
    try:
        main()
        raise SystemExit(0)
    except Exception as e:
        print(f"Transfer failed: {e}", file=sys.stderr)
        raise
