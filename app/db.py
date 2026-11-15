"""Run a validated query as the signed-in role's read-only database user."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

import psycopg

from app.config import Role

STATEMENT_TIMEOUT_MS = 3000


@dataclass
class QueryResult:
    columns: list[str]
    rows: list[list]


def _json_safe(value):
    """Turn database types into values that JSON can carry."""
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else round(float(value), 2)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def run_query(role: Role, safe_sql: str) -> QueryResult:
    """Run SQL that has already passed validate_sql.

    The connection uses the role's own database user, which can SELECT from
    one view and nothing else. The timeout is set here as well as on the
    database user, so it holds even if one of the two is misconfigured.
    """
    with psycopg.connect(
        role.db_url,
        options=f"-c statement_timeout={STATEMENT_TIMEOUT_MS} -c default_transaction_read_only=on",
        connect_timeout=5,
    ) as conn:
        cur = conn.execute(safe_sql)
        columns = [col.name for col in cur.description]
        rows = [[_json_safe(v) for v in row] for row in cur.fetchall()]
    return QueryResult(columns, rows)
