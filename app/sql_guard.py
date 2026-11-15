"""Validate model-written SQL before it reaches the database.

This is the second of two layers. The first is the database itself: each role
connects as a user that can only SELECT from its own view. This layer rejects
a bad query earlier and with a clearer error, and adds the row limit.

The query is parsed into a syntax tree with sqlglot, checked, and then
regenerated from the tree. What runs is the regenerated SQL, so the database
never sees text that was not checked.
"""

from __future__ import annotations

import sqlglot
from sqlglot import exp

MAX_ROWS = 200

# Functions the model may use. Anything not listed is rejected, including
# every function sqlglot does not recognise (pg_sleep, pg_read_file, ...).
_ALLOWED_FUNCTION_NAMES = [
    # aggregates and window functions
    "Count", "Sum", "Avg", "Min", "Max", "Median", "PercentileCont", "GroupConcat",
    "RowNumber", "Rank", "DenseRank",
    # numbers
    "Round", "Abs", "Ceil", "Floor",
    # text
    "Lower", "Upper", "Initcap", "Length", "Trim", "Concat", "Left", "Right", "Substring",
    # dates
    "CurrentDate", "CurrentTimestamp", "Extract", "DateTrunc", "TimestampTrunc", "ToChar",
    # logic and conversion (sqlglot models these as functions)
    "Case", "If", "And", "Or", "Coalesce", "Nullif", "Cast", "Greatest", "Least",
]
ALLOWED_FUNCTIONS = tuple(getattr(exp, n) for n in _ALLOWED_FUNCTION_NAMES if hasattr(exp, n))

# Node types that have no place in a read-only question.
FORBIDDEN_NODES = (
    exp.Insert, exp.Update, exp.Delete, exp.Merge, exp.Create, exp.Drop, exp.Alter,
    exp.Command, exp.Copy, exp.Into, exp.Lock, exp.With, exp.Set, exp.Transaction,
)


class SqlRejected(ValueError):
    """The query broke a rule. The message is safe to show the model."""


def validate_sql(sql: str, allowed_view: str) -> str:
    """Return safe SQL to run, or raise SqlRejected.

    Rules:
      1. Exactly one statement, and it is a SELECT.
      2. Every table it reads is `allowed_view`. No other relation, no CTEs.
      3. Only functions on the allow-list.
      4. At most MAX_ROWS rows come back.
    """
    try:
        statements = sqlglot.parse(sql, read="postgres")
    except sqlglot.errors.SqlglotError as err:
        raise SqlRejected(f"Could not parse the SQL: {str(err).splitlines()[0]}") from None

    statements = [s for s in statements if s is not None]
    if len(statements) != 1:
        raise SqlRejected("Send exactly one SQL statement.")
    tree = statements[0]

    if not isinstance(tree, exp.Select):
        raise SqlRejected("Only a single SELECT statement is allowed.")

    for node in tree.walk():
        if isinstance(node, FORBIDDEN_NODES):
            raise SqlRejected(
                f"{type(node).__name__.upper()} is not allowed. Write one plain SELECT; "
                "use subqueries instead of WITH."
            )

        if isinstance(node, exp.Table):
            # A table reference must be a plain name (not a function call in
            # FROM), in the default or public schema, and must be the view.
            plain_name = isinstance(node.this, exp.Identifier)
            if not plain_name or node.catalog or node.db not in ("", "public") or node.name != allowed_view:
                raise SqlRejected(f"You may only read from {allowed_view}.")

        if isinstance(node, exp.Func) and not isinstance(node, ALLOWED_FUNCTIONS):
            name = node.name if isinstance(node, exp.Anonymous) else node.sql_name()
            raise SqlRejected(f"The function {name} is not allowed.")

    # Cap the rows: add a LIMIT when there is none, lower it when it is too high.
    limit = tree.args.get("limit")
    limit_value = limit.expression if limit is not None else None
    within_cap = (
        isinstance(limit_value, exp.Literal)
        and limit_value.is_int
        and int(limit_value.this) <= MAX_ROWS
    )
    if not within_cap:
        tree = tree.limit(MAX_ROWS)

    # comments=False: the model's comments are dropped, not sent to the database.
    return tree.sql(dialect="postgres", comments=False)
