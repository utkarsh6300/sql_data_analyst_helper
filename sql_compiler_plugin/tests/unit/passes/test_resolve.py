"""Pass 3: resolve every name to a real table and column.

This is the pass everything else depends on, and the one that closes the four
documented bypasses.  Testing it directly -- rather than only through the
compiler -- pins down *what it extracts*, not just whether the query was
eventually rejected: a query can be denied for the right reason by accident if
resolution attributed a column to the wrong table.
"""

from __future__ import annotations

import pytest
import sqlglot

from sql_compiler import Catalog, TableRef
from sql_compiler.errors import ViolationCode
from sql_compiler.ir import ColumnRef
from sql_compiler.passes.resolve import resolve

pytestmark = pytest.mark.unit


ORDERS = TableRef("public", "orders")
EMPLOYEES = TableRef("public", "employees")
CUSTOMERS = TableRef("public", "customers")
SECRET_ORDERS = TableRef("secret", "orders")


def run(sql: str, catalog: Catalog):
    """Parse and resolve, the way the compiler does."""
    return resolve(sqlglot.parse_one(sql, dialect=catalog.dialect), catalog)


def codes(violations):
    return [v.code for v in violations]


def columns_of(resolved, ref: TableRef):
    return {c.column for c in resolved.column_refs if c.table == ref}


# -- fail-closed gates -------------------------------------------------------


def test_an_empty_catalog_is_reported_not_silently_permissive(catalog):
    resolved, violations = run("SELECT id FROM orders", Catalog.from_dict({}))
    assert resolved is None
    assert codes(violations) == [ViolationCode.EMPTY_CATALOG]


def test_an_empty_catalog_is_not_repairable():
    _, violations = run("SELECT id FROM orders", Catalog.from_dict({}))
    assert violations[0].action.value == "NOT_REPAIRABLE"


def test_an_unknown_table_is_reported_as_a_missing_table(catalog):
    # sqlglot reports a missing table as an unresolvable *column*, which is an
    # actively misleading thing to hand a repair loop.
    resolved, violations = run("SELECT id FROM nonexistent", catalog)
    assert resolved is None
    assert codes(violations) == [ViolationCode.UNKNOWN_TABLE]
    assert violations[0].table == "public.nonexistent"


def test_every_unknown_table_is_reported_in_a_stable_order(catalog):
    _, violations = run(
        "SELECT 1 FROM zeta z JOIN alpha a ON a.id = z.id", catalog
    )
    assert [v.table for v in violations] == ["public.alpha", "public.zeta"]


def test_an_unknown_column_is_rejected_rather_than_passed_through(catalog):
    resolved, violations = run("SELECT nonexistent FROM orders", catalog)
    assert resolved is None
    assert codes(violations) == [ViolationCode.NAME_RESOLUTION_FAILED]


def test_a_resolver_failure_reports_one_short_line(catalog):
    _, violations = run("SELECT nonexistent FROM orders", catalog)
    message = violations[0].details.get("resolver_message", "")
    assert "\n" not in message
    assert len(message) <= 200


def test_a_table_outside_the_catalog_schema_is_not_inferred(catalog):
    # infer_schema=False: an inferred table is an unauthorized table wearing
    # a disguise.
    resolved, violations = run("SELECT id FROM other_schema.orders", catalog)
    assert resolved is None
    assert codes(violations) == [ViolationCode.UNKNOWN_TABLE]


def test_a_quoted_name_is_not_folded_into_a_known_table(catalog):
    resolved, violations = run('SELECT id FROM "Orders"', catalog)
    assert resolved is None
    assert codes(violations) == [ViolationCode.UNKNOWN_TABLE]


# -- star expansion ----------------------------------------------------------


def test_star_is_expanded_into_every_catalog_column(catalog):
    # A star is an exp.Star, not an exp.Column, so anything that iterates
    # columns sees nothing to check until it has been expanded.
    resolved, violations = run("SELECT * FROM employees", catalog)
    assert violations == []
    assert columns_of(resolved, EMPLOYEES) == {"id", "name", "salary", "ssn"}


def test_a_qualified_star_is_expanded(catalog):
    resolved, violations = run("SELECT e.* FROM employees e", catalog)
    assert violations == []
    assert columns_of(resolved, EMPLOYEES) == {"id", "name", "salary", "ssn"}


def test_a_star_over_a_join_is_expanded_for_both_sides(catalog):
    sql = "SELECT * FROM orders o JOIN customers c ON c.id = o.customer_id"
    resolved, violations = run(sql, catalog)
    assert violations == []
    assert columns_of(resolved, ORDERS) >= {"id", "amount", "tenant_id"}
    assert columns_of(resolved, CUSTOMERS) >= {"name", "region"}


def test_a_star_inside_a_cte_is_expanded(catalog):
    resolved, violations = run(
        "WITH t AS (SELECT * FROM employees) SELECT id FROM t", catalog
    )
    assert violations == []
    assert columns_of(resolved, EMPLOYEES) == {"id", "name", "salary", "ssn"}


def test_no_star_survives_resolution(catalog):
    # One surviving star would mean unchecked columns reaching the database.
    resolved, _ = run("SELECT * FROM orders", catalog)
    assert not list(resolved.expression.find_all(sqlglot.exp.Star))


# -- aliases -----------------------------------------------------------------


def test_a_table_alias_resolves_to_its_base_table(catalog):
    resolved, violations = run("SELECT p.salary FROM employees p", catalog)
    assert violations == []
    assert resolved.base_tables == {EMPLOYEES}
    assert ColumnRef(table=EMPLOYEES, column="salary") in resolved.column_refs


def test_an_output_alias_does_not_hide_what_is_read(catalog):
    resolved, _ = run("SELECT salary AS not_a_salary FROM employees", catalog)
    assert columns_of(resolved, EMPLOYEES) == {"salary"}


def test_an_alias_that_shadows_another_table_name_resolves_correctly(catalog):
    # `customers orders` aliases customers to the name of a real table.
    resolved, violations = run("SELECT orders.name FROM customers orders", catalog)
    assert violations == []
    assert resolved.base_tables == {CUSTOMERS}
    assert columns_of(resolved, CUSTOMERS) == {"name"}


# -- schema qualification ----------------------------------------------------


def test_an_unqualified_table_takes_the_default_schema(catalog):
    resolved, _ = run("SELECT id FROM orders", catalog)
    assert resolved.base_tables == {ORDERS}


def test_another_schema_cannot_pose_as_the_default_one(catalog):
    # table.name is "orders" for both; only a schema-qualified comparison
    # tells them apart.
    resolved, violations = run("SELECT id FROM secret.orders", catalog)
    assert violations == []
    assert resolved.base_tables == {SECRET_ORDERS}
    assert ORDERS not in resolved.base_tables


def test_both_same_named_tables_can_appear_at_once(catalog):
    sql = "SELECT a.id, b.id FROM public.orders a JOIN secret.orders b ON a.id = b.id"
    resolved, violations = run(sql, catalog)
    assert violations == []
    assert resolved.base_tables == {ORDERS, SECRET_ORDERS}


def test_the_regenerated_sql_is_fully_qualified(catalog):
    resolved, _ = run("select amount from orders", catalog)
    assert '"public"."orders"' in resolved.expression.sql(dialect=catalog.dialect)


# -- CTEs and derived tables -------------------------------------------------


def test_a_cte_name_is_not_a_base_table(catalog):
    resolved, violations = run(
        "WITH t AS (SELECT id, amount FROM orders) SELECT * FROM t", catalog
    )
    assert violations == []
    assert resolved.base_tables == {ORDERS}


def test_a_cte_shadowing_a_real_table_name_is_not_that_table(catalog):
    # `employees` here is a locally defined CTE, not public.employees.
    sql = "WITH employees AS (SELECT id FROM orders) SELECT id FROM employees"
    resolved, violations = run(sql, catalog)
    assert violations == []
    assert resolved.base_tables == {ORDERS}
    assert EMPLOYEES not in resolved.base_tables


def test_a_cte_name_is_not_reported_as_an_unknown_table(catalog):
    # The unknown-table check runs before qualification, so it has to make the
    # CTE-versus-table distinction itself.
    _, violations = run(
        "WITH nowhere AS (SELECT id FROM orders) SELECT id FROM nowhere", catalog
    )
    assert violations == []


def test_columns_inside_a_cte_are_traced_to_the_base_table(catalog):
    resolved, _ = run(
        "WITH t AS (SELECT id, salary FROM employees) SELECT id FROM t", catalog
    )
    assert "salary" in columns_of(resolved, EMPLOYEES)


def test_nested_ctes_are_followed_to_the_base_table(catalog):
    sql = (
        "WITH a AS (SELECT id, salary FROM employees), "
        "b AS (SELECT id, salary FROM a) "
        "SELECT id FROM b"
    )
    resolved, violations = run(sql, catalog)
    assert violations == []
    assert resolved.base_tables == {EMPLOYEES}
    assert "salary" in columns_of(resolved, EMPLOYEES)


def test_a_derived_table_is_traced_to_its_base_table(catalog):
    resolved, violations = run(
        "SELECT x.salary FROM (SELECT salary FROM employees) x", catalog
    )
    assert violations == []
    assert resolved.base_tables == {EMPLOYEES}
    assert columns_of(resolved, EMPLOYEES) == {"salary"}


# -- where the columns hide --------------------------------------------------


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT id FROM employees WHERE salary > 100000",
        "SELECT id FROM employees ORDER BY salary DESC",
        "SELECT id FROM employees GROUP BY id, salary",
        "SELECT AVG(salary) FROM employees",
        "SELECT id FROM employees GROUP BY id HAVING AVG(salary) > 1",
        "SELECT CASE WHEN salary > 1 THEN 1 ELSE 0 END FROM employees",
        "SELECT id FROM orders UNION ALL SELECT salary FROM employees",
    ],
)
def test_a_column_read_anywhere_is_collected(sql, catalog):
    resolved, violations = run(sql, catalog)
    assert violations == []
    assert "salary" in columns_of(resolved, EMPLOYEES), sql


def test_a_correlated_subquery_column_is_attributed_to_its_own_table(catalog):
    sql = (
        "SELECT c.name FROM customers c "
        "WHERE EXISTS (SELECT 1 FROM employees e WHERE e.ssn = c.name)"
    )
    resolved, violations = run(sql, catalog)
    assert violations == []
    assert columns_of(resolved, EMPLOYEES) == {"ssn"}
    assert "name" in columns_of(resolved, CUSTOMERS)


def test_a_join_condition_counts_as_reading_both_columns(catalog):
    sql = "SELECT c.name FROM customers c JOIN orders o ON o.customer_id = c.id"
    resolved, _ = run(sql, catalog)
    assert "customer_id" in columns_of(resolved, ORDERS)
    assert "id" in columns_of(resolved, CUSTOMERS)


def test_column_case_is_normalized(catalog):
    resolved, violations = run("SELECT AMOUNT FROM orders", catalog)
    assert violations == []
    assert columns_of(resolved, ORDERS) == {"amount"}


def test_a_tableless_select_reads_nothing(catalog):
    resolved, violations = run("SELECT 1", catalog)
    assert violations == []
    assert resolved.base_tables == set()
    assert resolved.column_refs == []


# -- functions ---------------------------------------------------------------


def function_names(resolved):
    return {f.display for f in resolved.functions}


def test_a_function_call_is_collected(catalog):
    resolved, _ = run("SELECT COUNT(id) FROM orders", catalog)
    assert "COUNT" in function_names(resolved)


def test_an_unmodelled_function_is_collected_by_its_real_name(catalog):
    # sql_name() is the useless literal "ANONYMOUS" for these; the real name
    # lives in `this`, and this is exactly the dangerous case.
    resolved, violations = run("SELECT pg_read_file('/etc/passwd')", catalog)
    assert violations == []
    assert "PG_READ_FILE" in function_names(resolved)


def test_a_canonicalized_function_carries_every_spelling(catalog):
    # DATE_TRUNC parses to a TimestampTrunc node whose sql_name() differs from
    # how it renders, so an allow-list entry may match any of them.
    resolved, _ = run("SELECT DATE_TRUNC('day', CURRENT_DATE) FROM orders", catalog)
    candidates = set().union(*(f.candidates for f in resolved.functions))
    assert "DATE_TRUNC" in candidates


def test_nested_functions_are_all_collected(catalog):
    resolved, _ = run("SELECT UPPER(TRIM(name)) FROM customers", catalog)
    assert {"UPPER", "TRIM"} <= function_names(resolved)


def test_the_same_function_is_recorded_once(catalog):
    resolved, _ = run("SELECT COUNT(id), COUNT(amount) FROM orders", catalog)
    assert sum(1 for f in resolved.functions if f.display == "COUNT") == 1


def test_a_function_inside_a_cte_is_collected(catalog):
    resolved, _ = run(
        "WITH t AS (SELECT version() AS v) SELECT v FROM t", catalog
    )
    assert "VERSION" in function_names(resolved)


def test_a_function_in_a_where_clause_is_collected(catalog):
    resolved, _ = run(
        "SELECT id FROM customers WHERE UPPER(name) = 'X'", catalog
    )
    assert "UPPER" in function_names(resolved)


# -- purity ------------------------------------------------------------------


def test_the_input_tree_is_not_mutated(catalog):
    statement = sqlglot.parse_one("SELECT * FROM orders", dialect=catalog.dialect)
    before = statement.sql(dialect=catalog.dialect)
    resolve(statement, catalog)
    assert statement.sql(dialect=catalog.dialect) == before


def test_resolution_is_idempotent(catalog):
    once, _ = run("SELECT amount FROM orders", catalog)
    sql = once.expression.sql(dialect=catalog.dialect)
    twice, violations = run(sql, catalog)
    assert violations == []
    assert twice.expression.sql(dialect=catalog.dialect) == sql
