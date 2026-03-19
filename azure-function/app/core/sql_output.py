import json
import logging
from datetime import datetime, timezone

import pyodbc

logger = logging.getLogger("rfp_function.sql")


def write_result_to_sql(
    credential,
    sql_server: str,
    sql_database: str,
    sql_schema: str,
    sql_table: str,
    sql_driver: str,
    sql_encrypt: bool,
    sql_trust_server_certificate: bool,
    run_id: str,
    rfp_blob_name: str,
    result: dict,
) -> None:
    token = credential.get_token("https://database.windows.net/.default").token
    token_bytes = token.encode("utf-16-le")
    encrypt = "yes" if sql_encrypt else "no"
    trust_cert = "yes" if sql_trust_server_certificate else "no"
    conn_str = (
        f"Driver={{{sql_driver}}};"
        f"Server=tcp:{sql_server},1433;"
        f"Database={sql_database};"
        f"Encrypt={encrypt};"
        f"TrustServerCertificate={trust_cert};"
        "Connection Timeout=30;"
    )
    table_name = f"{sql_schema}.{sql_table}".strip(".")
    query = (
        f"INSERT INTO {table_name} "
        "(run_id, rfp_blob_name, output_json, created_at) "
        "VALUES (?, ?, ?, ?)"
    )
    with pyodbc.connect(conn_str, attrs_before={1256: token_bytes}) as conn:
        cursor = conn.cursor()
        cursor.execute(
            query,
            run_id,
            rfp_blob_name,
            json.dumps(result),
            datetime.now(timezone.utc),
        )
        conn.commit()
    logger.info("Result inserted into SQL for run_id=%s", run_id)
