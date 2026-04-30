import json
import logging
from datetime import datetime, timezone

import azure.functions as func

from src.transfer.main import transfer


def main(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("HTTP trigger received for Influx to SQL transfer.")
    try:
        rows_upserted, rows = transfer()
        body = {
            "ok": True,
            "message": "Transfer completed successfully.",
            "rowsUpserted": rows_upserted,
            "rowCount": len(rows),
            "rows": rows,
            "triggeredAtUtc": datetime.now(timezone.utc).isoformat(),
        }
        return func.HttpResponse(
            body=json.dumps(body),
            status_code=200,
            mimetype="application/json",
        )
    except Exception as exc:
        logging.exception("Influx to SQL transfer failed.")
        body = {
            "ok": False,
            "message": "Transfer failed.",
            "error": str(exc),
            "triggeredAtUtc": datetime.now(timezone.utc).isoformat(),
        }
        return func.HttpResponse(
            body=json.dumps(body),
            status_code=500,
            mimetype="application/json",
        )

