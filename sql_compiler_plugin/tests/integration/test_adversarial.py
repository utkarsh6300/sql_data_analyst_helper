"""Adversarial tests.

The first four cases are the bypasses chat2-1.txt demonstrated against the
naive implementation in chat.txt -- each one passed all three of its "security
checks". They are the reason this package resolves names before authorizing
anything, and they must never regress.
"""

from __future__ import annotations

import pytest

from sql_compiler import ViolationCode

pytestmark = [pytest.mark.integration, pytest.mark.security]


def codes(result):
    return {v.code for v in result.violations}


# -- the four documented bypasses --------------------------------------------


def test_bare_star_does_not_smuggle_denied_columns(compiler, policy):
    # `SELECT *` is an exp.Star, not an exp.Column, so a checker that iterates
    # exp.Column nodes runs zero column checks against it.
    result = compiler.compile("SELECT * FROM employees", policy=policy)
    assert not result.ok
    assert ViolationCode.COLUMN_ACCESS_DENIED in codes(result)
    denied = {v.column for v in result.violations}
    assert {"salary", "ssn"} <= denied


def test_star_is_allowed_when_every_expanded_column_is_permitted(compiler, policy):
    result = compiler.compile("SELECT * FROM orders", policy=policy)
    # tenant_id is not granted, so this must fail -- and fail naming tenant_id,
    # proving the star was really expanded rather than skipped.
    assert not result.ok
    assert {v.column for v in result.violations} == {"tenant_id"}


def test_other_schema_cannot_impersonate_a_granted_table(compiler, policy):
    # table.name == "orders" for both public.orders and secret.orders; only a
    # schema-qualified comparison tells them apart.
    result = compiler.compile("SELECT id FROM secret.orders", policy=policy)
    assert not result.ok
    assert ViolationCode.TABLE_ACCESS_DENIED in codes(result)
    assert result.violations[0].table == "secret.orders"


def test_drop_table_is_rejected(compiler, policy):
    # exp.Table nodes appear in DDL too, so passing a table allow-list says
    # nothing about the statement being a read.
    result = compiler.compile("DROP TABLE orders", policy=policy)
    assert not result.ok
    assert codes(result) & {
        ViolationCode.NON_SELECT_STATEMENT,
        ViolationCode.FORBIDDEN_EXPRESSION,
    }


def test_tableless_function_call_is_rejected(compiler, policy):
    # No Table, no Column, no FROM: nothing for table or column checks to see.
    result = compiler.compile("SELECT version()", policy=policy)
    assert not result.ok
    assert ViolationCode.FUNCTION_NOT_ALLOWED in codes(result)


def test_file_reading_function_is_rejected(compiler, policy):
    result = compiler.compile("SELECT pg_read_file('/etc/passwd')", policy=policy)
    assert not result.ok
    assert ViolationCode.FUNCTION_NOT_ALLOWED in codes(result)
    assert result.violations[0].function == "PG_READ_FILE"


# -- aliases -----------------------------------------------------------------


def test_alias_is_resolved_to_its_base_table(compiler, policy):
    # p.salary must be understood as employees.salary, not as an unknown
    # column of an unknown relation named p.
    result = compiler.compile("SELECT p.salary FROM employees p", policy=policy)
    assert not result.ok
    assert result.violations[0].code == ViolationCode.COLUMN_ACCESS_DENIED
    assert result.violations[0].table == "public.employees"
    assert result.violations[0].column == "salary"


def test_alias_on_a_permitted_column_is_accepted(compiler, policy):
    result = compiler.compile("SELECT o.amount FROM orders o", policy=policy)
    assert result.ok, result.violations


def test_same_column_name_in_two_tables_is_two_permissions(compiler, policy):
    # employees.name is granted, and so is customers.name; a flat column
    # allow-list could not tell these apart from employees.salary.
    assert compiler.compile("SELECT name FROM customers", policy=policy).ok
    assert compiler.compile("SELECT name FROM employees", policy=policy).ok


# -- CTEs --------------------------------------------------------------------


def test_cte_name_is_not_treated_as_a_base_table(compiler, policy):
    # The naive implementation rejected this, because `t` looks like an
    # exp.Table that is not on the allow-list.
    sql = "WITH t AS (SELECT id, amount FROM orders) SELECT * FROM t"
    result = compiler.compile(sql, policy=policy)
    assert result.ok, result.violations


def test_denied_column_hidden_inside_a_cte_is_caught(compiler, policy):
    sql = "WITH t AS (SELECT id, salary FROM employees) SELECT id FROM t"
    result = compiler.compile(sql, policy=policy)
    assert not result.ok
    assert result.violations[0].column == "salary"


def test_denied_table_hidden_inside_a_cte_is_caught(compiler, policy):
    sql = "WITH t AS (SELECT id FROM secret.orders) SELECT id FROM t"
    result = compiler.compile(sql, policy=policy)
    assert not result.ok
    assert ViolationCode.TABLE_ACCESS_DENIED in codes(result)


def test_nested_ctes_are_followed_to_the_base_table(compiler, policy):
    sql = (
        "WITH a AS (SELECT id, salary FROM employees), "
        "b AS (SELECT id FROM a) "
        "SELECT id FROM b"
    )
    result = compiler.compile(sql, policy=policy)
    assert not result.ok
    assert result.violations[0].column == "salary"


def test_star_inside_a_cte_is_expanded(compiler, policy):
    sql = "WITH t AS (SELECT * FROM employees) SELECT id FROM t"
    result = compiler.compile(sql, policy=policy)
    assert not result.ok
    assert {"salary", "ssn"} <= {v.column for v in result.violations}


# -- subqueries and joins ----------------------------------------------------


def test_denied_table_in_a_join_is_caught(compiler, policy):
    sql = "SELECT c.name FROM customers c JOIN secret.orders o ON o.id = c.id"
    result = compiler.compile(sql, policy=policy)
    assert not result.ok
    assert ViolationCode.TABLE_ACCESS_DENIED in codes(result)


def test_denied_column_in_a_derived_table_is_caught(compiler, policy):
    sql = "SELECT x.salary FROM (SELECT salary FROM employees) x"
    result = compiler.compile(sql, policy=policy)
    assert not result.ok
    assert result.violations[0].column == "salary"


def test_denied_column_in_a_where_clause_is_caught(compiler, policy):
    # Reading a column in a predicate is still reading it, and supports
    # binary-search style extraction.
    sql = "SELECT id FROM employees WHERE salary > 100000"
    result = compiler.compile(sql, policy=policy)
    assert not result.ok
    assert result.violations[0].column == "salary"


def test_denied_column_in_a_correlated_subquery_is_caught(compiler, policy):
    sql = (
        "SELECT c.name FROM customers c "
        "WHERE EXISTS (SELECT 1 FROM employees e WHERE e.ssn = c.name)"
    )
    result = compiler.compile(sql, policy=policy)
    assert not result.ok
    assert result.violations[0].column == "ssn"


def test_denied_column_in_order_by_is_caught(compiler, policy):
    sql = "SELECT id FROM employees ORDER BY salary DESC"
    result = compiler.compile(sql, policy=policy)
    assert not result.ok
    assert result.violations[0].column == "salary"


def test_denied_column_in_a_set_operation_branch_is_caught(compiler, policy):
    sql = "SELECT id FROM orders UNION ALL SELECT salary FROM employees"
    result = compiler.compile(sql, policy=policy)
    assert not result.ok
    assert result.violations[0].column == "salary"


def test_denied_column_behind_an_aggregate_is_caught(compiler, policy):
    sql = "SELECT AVG(salary) FROM employees"
    result = compiler.compile(sql, policy=policy)
    assert not result.ok
    assert result.violations[0].column == "salary"


def test_denied_column_behind_an_output_alias_is_caught(compiler, policy):
    # Renaming the output does not change what is read.
    sql = "SELECT salary AS not_a_salary FROM employees"
    result = compiler.compile(sql, policy=policy)
    assert not result.ok
    assert result.violations[0].column == "salary"


# -- unknown objects ---------------------------------------------------------


def test_unknown_table_is_denied_not_ignored(compiler, policy):
    result = compiler.compile("SELECT id FROM nonexistent", policy=policy)
    assert not result.ok
    assert ViolationCode.UNKNOWN_TABLE in codes(result)


def test_unknown_column_is_denied_not_ignored(compiler, policy):
    result = compiler.compile("SELECT nonexistent FROM orders", policy=policy)
    assert not result.ok
    assert ViolationCode.NAME_RESOLUTION_FAILED in codes(result)


def test_quoted_identifier_case_is_not_folded_away(compiler, policy):
    # "Orders" is a different table from orders in Postgres.
    result = compiler.compile('SELECT id FROM "Orders"', policy=policy)
    assert not result.ok
    assert ViolationCode.UNKNOWN_TABLE in codes(result)
