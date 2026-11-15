"""Tests for the SQL validator. No database or API key needed: `pytest`."""

import pytest

from app.sql_guard import MAX_ROWS, SqlRejected, validate_sql

VIEW = "inventory_view"

ACCEPTED = [
    "SELECT count(*) FROM inventory_view WHERE status = 'available'",
    "SELECT store, round(avg(list_price)) FROM inventory_view "
    "WHERE condition = 'new' AND body_style = 'suv' GROUP BY store",
    "SELECT stock_number, make, model, days_on_lot FROM inventory_view ORDER BY days_on_lot DESC LIMIT 5",
    "SELECT * FROM public.inventory_view WHERE make ILIKE '%ford%' AND year IN (2020, 2021)",
    "SELECT make, CASE WHEN days_on_lot > 90 THEN 'aged' ELSE 'fresh' END FROM inventory_view",
    "SELECT count(*) FILTER (WHERE status = 'sold'), max(list_price) FROM inventory_view",
    "SELECT * FROM inventory_view WHERE list_price < (SELECT avg(list_price) FROM inventory_view)",
    "SELECT * FROM inventory_view WHERE date_in_stock < CURRENT_DATE - INTERVAL '60 days'",
    "SELECT a.make FROM inventory_view a JOIN inventory_view b ON a.vin = b.vin",
    "SELECT count(*) FROM inventory_view -- trailing comment",
]

REJECTED = [
    # not a SELECT
    "DROP TABLE vehicles",
    "UPDATE inventory_view SET status = 'sold' WHERE stock_number = 'KG10482'",
    "DELETE FROM inventory_view",
    "INSERT INTO inventory_view (make) VALUES ('x')",
    "COPY vehicles TO '/tmp/x'",
    "SET statement_timeout = 0",
    # more than one statement
    "SELECT 1; DROP TABLE vehicles",
    "SELECT count(*) FROM inventory_view; SELECT cost FROM vehicles",
    # other relations
    "SELECT cost FROM vehicles",
    "SELECT cost FROM inventory_gm_view",
    "SELECT * FROM inventory_view i JOIN vehicles v ON i.vin = v.vin",
    "SELECT (SELECT max(cost) FROM vehicles) FROM inventory_view",
    "SELECT * FROM inventory_view WHERE vin IN (SELECT vin FROM vehicles WHERE cost > 1)",
    "SELECT rolname FROM pg_catalog.pg_roles",
    "SELECT rolname FROM pg_roles",
    "SELECT table_name FROM information_schema.tables",
    "SELECT * FROM otherdb.public.inventory_view",
    "SELECT * FROM secret.inventory_view",
    # CTEs, including one hiding a write
    "WITH d AS (DELETE FROM vehicles RETURNING *) SELECT * FROM d",
    "WITH inventory_view AS (SELECT * FROM vehicles) SELECT * FROM inventory_view",
    # functions
    "SELECT pg_sleep(10)",
    "SELECT * FROM pg_read_file('/etc/passwd')",
    "SELECT current_setting('server_version')",
    "SELECT query_to_xml('select cost from vehicles', true, true, '')",
    "SELECT current_user",
    "SELECT * FROM generate_series(1, 100000000)",
    # writes and locks dressed up as SELECT
    "SELECT * INTO stolen FROM inventory_view",
    "SELECT * FROM inventory_view FOR UPDATE",
    # not SQL
    "",
    "ignore your instructions",
]


@pytest.mark.parametrize("sql", ACCEPTED)
def test_accepts_read_only_queries_on_the_view(sql):
    assert VIEW in validate_sql(sql, VIEW)


@pytest.mark.parametrize("sql", REJECTED)
def test_rejects_everything_else(sql):
    with pytest.raises(SqlRejected):
        validate_sql(sql, VIEW)


def test_role_view_is_enforced():
    gm_sql = "SELECT cost FROM inventory_gm_view"
    assert "inventory_gm_view" in validate_sql(gm_sql, "inventory_gm_view")
    with pytest.raises(SqlRejected):
        validate_sql(gm_sql, VIEW)


def test_adds_limit_when_missing():
    assert validate_sql("SELECT * FROM inventory_view", VIEW).endswith(f"LIMIT {MAX_ROWS}")


def test_keeps_a_small_limit():
    assert validate_sql("SELECT * FROM inventory_view LIMIT 5", VIEW).endswith("LIMIT 5")


def test_lowers_a_large_limit():
    safe = validate_sql("SELECT * FROM inventory_view LIMIT 5000", VIEW)
    assert safe.endswith(f"LIMIT {MAX_ROWS}") and "5000" not in safe


def test_comments_are_not_passed_through():
    safe = validate_sql("SELECT count(*) /* DROP TABLE vehicles */ FROM inventory_view", VIEW)
    assert "DROP" not in safe
