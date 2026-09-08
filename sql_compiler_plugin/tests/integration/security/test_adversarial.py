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
    # The full set, not just violations[0]: EXISTS itself must never also
    # show up as a FUNCTION_NOT_ALLOWED -- see the structural-syntax tests
    # below for why that was possible.
    assert codes(result) == {ViolationCode.COLUMN_ACCESS_DENIED}
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


# -- table-valued functions in FROM ------------------------------------------


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM generate_series(1, 10)",
        "SELECT * FROM generate_series(1, 10) AS t(n)",
        "SELECT * FROM jsonb_each('{}'::jsonb)",
        "SELECT * FROM json_to_recordset('[]') AS x(a int, b text)",
        "SELECT * FROM regexp_split_to_table('a,b', ',')",
        "SELECT o.id FROM orders o JOIN generate_series(1, 10) AS g(n) ON o.id = g.n",
    ],
)
def test_table_valued_function_in_from_is_rejected_not_crashed(sql, compiler, policy):
    # This used to raise an uncaught ConfigurationError out of compile() --
    # a crash, not a rejection -- with a message embedding a fragment of the
    # query. It must now come back as an ordinary rejected CompileResult.
    result = compiler.compile(sql, policy=policy)
    assert not result.ok
    assert ViolationCode.NAME_RESOLUTION_FAILED in codes(result)


# -- NATURAL JOIN's invisible column predicate --------------------------------


def test_natural_join_cannot_smuggle_a_read_of_a_shared_denied_column():
    # employees.salary is denied; audit_log also has a column named `salary`
    # that IS granted. NATURAL JOIN implicitly joins on every same-named
    # column, so `... NATURAL JOIN audit_log` executes `ON e.salary =
    # a.salary` at runtime -- a read of the denied column with no visible
    # Column node for authorization to catch. This must be rejected outright,
    # not silently accepted the way it used to be.
    from sql_compiler import Catalog, Policy, SqlCompiler

    catalog = Catalog.from_dict(
        {
            "public": {
                "employees": {"id": "INT", "salary": "NUMERIC"},
                "audit_log": {"id": "INT", "salary": "NUMERIC", "note": "TEXT"},
            }
        }
    )
    policy = Policy.from_dict(
        {
            "tables": {
                "public.employees": {"columns": "*", "denied_columns": ["salary"]},
                "public.audit_log": ["id", "salary", "note"],
            }
        }
    )
    compiler = SqlCompiler(catalog=catalog)

    result = compiler.compile(
        "SELECT e.id FROM employees e NATURAL JOIN audit_log a", policy=policy
    )
    assert not result.ok
    assert codes(result) == {ViolationCode.NATURAL_JOIN_NOT_SUPPORTED}

    # The explicit equivalent must still work exactly as it does today --
    # USING is expanded into a real column by qualify(), so it is correctly
    # caught as a denied-column read rather than let through.
    using_result = compiler.compile(
        "SELECT e.id FROM employees e JOIN audit_log a USING (salary)", policy=policy
    )
    assert not using_result.ok
    assert ViolationCode.COLUMN_ACCESS_DENIED in codes(using_result)


# -- extensive query shapes: already correct, now pinned ---------------------


def test_window_function_partition_on_denied_column_is_caught(compiler, policy):
    sql = "SELECT id, ROW_NUMBER() OVER (PARTITION BY salary) FROM employees"
    result = compiler.compile(sql, policy=policy)
    assert not result.ok
    assert result.violations[0].column == "salary"


def test_window_function_order_by_on_denied_column_is_caught(compiler, policy):
    # `id` is unqualified and exists on both tables, so both must be aliased
    # or the query is ambiguous before authorization even runs.
    sql = (
        "SELECT o.id, SUM(o.amount) OVER (ORDER BY e.salary) "
        "FROM employees e, orders o"
    )
    result = compiler.compile(sql, policy=policy)
    assert not result.ok
    assert any(v.column == "salary" for v in result.violations)


def test_window_function_on_permitted_columns_is_accepted(compiler, policy):
    sql = "SELECT id, SUM(amount) OVER (PARTITION BY customer_id ORDER BY id) FROM orders"
    result = compiler.compile(sql, policy=policy)
    assert result.ok, result.violations


def test_recursive_cte_is_resolved_like_any_other_cte(compiler, policy):
    sql = (
        "WITH RECURSIVE t AS ("
        "SELECT id FROM orders WHERE id = 1 "
        "UNION ALL "
        "SELECT o.id FROM orders o JOIN t ON o.id = t.id + 1"
        ") SELECT * FROM t"
    )
    result = compiler.compile(sql, policy=policy)
    assert result.ok, result.violations


def test_recursive_cte_hiding_a_denied_column_is_caught(compiler, policy):
    sql = (
        "WITH RECURSIVE t AS ("
        "SELECT id, salary FROM employees WHERE id = 1 "
        "UNION ALL "
        "SELECT e.id, e.salary FROM employees e JOIN t ON e.id = t.id + 1"
        ") SELECT * FROM t"
    )
    result = compiler.compile(sql, policy=policy)
    assert not result.ok
    assert result.violations[0].column == "salary"


def test_lateral_subquery_reading_a_denied_column_is_caught(compiler, policy):
    sql = (
        "SELECT o.id, e.salary FROM orders o "
        "CROSS JOIN LATERAL (SELECT salary FROM employees WHERE id = o.customer_id) e"
    )
    result = compiler.compile(sql, policy=policy)
    assert not result.ok
    assert result.violations[0].column == "salary"


def test_values_clause_needs_no_table_authorization(compiler, policy):
    sql = "SELECT * FROM (VALUES (1, 2), (3, 4)) AS t(a, b)"
    result = compiler.compile(sql, policy=policy)
    assert result.ok, result.violations


def test_filter_clause_on_a_denied_column_is_caught(compiler, policy):
    sql = "SELECT SUM(amount) FILTER (WHERE salary > 1) FROM employees, orders"
    result = compiler.compile(sql, policy=policy)
    assert not result.ok
    assert any(v.column == "salary" for v in result.violations)


def test_grouping_sets_on_a_denied_column_is_caught(compiler, policy):
    sql = "SELECT salary, SUM(amount) FROM employees, orders GROUP BY GROUPING SETS ((salary), ())"
    result = compiler.compile(sql, policy=policy)
    assert not result.ok
    assert any(v.column == "salary" for v in result.violations)


def test_distinct_on_a_denied_column_is_caught(compiler, policy):
    sql = "SELECT DISTINCT ON (salary) id, salary FROM employees"
    result = compiler.compile(sql, policy=policy)
    assert not result.ok
    assert any(v.column == "salary" for v in result.violations)


def test_scalar_subquery_in_select_list_reading_a_denied_column_is_caught(compiler, policy):
    sql = "SELECT o.id, (SELECT salary FROM employees WHERE id = o.customer_id) FROM orders o"
    result = compiler.compile(sql, policy=policy)
    assert not result.ok
    assert result.violations[0].column == "salary"


def test_in_subquery_reading_a_denied_table_is_caught(compiler, policy):
    sql = "SELECT id FROM orders WHERE customer_id IN (SELECT id FROM secret.orders)"
    result = compiler.compile(sql, policy=policy)
    assert not result.ok
    assert ViolationCode.TABLE_ACCESS_DENIED in codes(result)


@pytest.mark.parametrize(
    "sql",
    [
        "EXPLAIN SELECT * FROM orders",
        # The higher-risk variant: unlike plain EXPLAIN, ANALYZE actually
        # executes the query to gather real timings.
        "EXPLAIN ANALYZE SELECT * FROM orders",
        "EXPLAIN (ANALYZE, VERBOSE) SELECT * FROM orders",
    ],
)
def test_explain_is_rejected_not_executed(sql, compiler, policy):
    # EXPLAIN is not modelled by the allowed-root check, and Postgres EXPLAIN
    # ANALYZE actually executes the query -- this must never slip through as
    # a Command fallback either.
    result = compiler.compile(sql, policy=policy)
    assert not result.ok


def test_stacked_statement_is_rejected_end_to_end(compiler, policy):
    # Validating only the first statement and then executing the original
    # string is the classic stacked-query bypass (see
    # sql_compiler/passes/parse.py). Pinned here too, not just at the parse
    # pass's own unit tests, so a regression that only shows up through the
    # full compile() pipeline (e.g. a change in how passes are wired) is
    # also caught.
    result = compiler.compile("SELECT id FROM orders; DROP TABLE orders", policy=policy)
    assert not result.ok
    assert result.sql is None
    assert ViolationCode.MULTIPLE_STATEMENTS in codes(result)


def test_pg_sleep_is_denied_by_the_function_allowlist(compiler, policy):
    result = compiler.compile("SELECT pg_sleep(9999)", policy=policy)
    assert not result.ok
    assert ViolationCode.FUNCTION_NOT_ALLOWED in codes(result)


def test_information_schema_probing_is_denied_as_unknown(compiler, policy):
    result = compiler.compile("SELECT * FROM information_schema.columns", policy=policy)
    assert not result.ok
    assert ViolationCode.UNKNOWN_TABLE in codes(result)


def test_pg_catalog_probing_is_denied_as_unknown(compiler, policy):
    result = compiler.compile("SELECT * FROM pg_catalog.pg_shadow", policy=policy)
    assert not result.ok
    assert ViolationCode.UNKNOWN_TABLE in codes(result)


# -- structural SQL syntax mistaken for a callable function -------------------
#
# exp.Exists, exp.Connector (AND/OR/XOR) and exp.Case/exp.If are all,
# structurally, subclasses of exp.Func in sqlglot's hierarchy -- a parsing
# convenience, not a sign that they are functions a policy should have to
# allow-list. Before the fix in resolve.py's _collect_functions, every one
# of these was denied by default the same way pg_read_file() is, which meant
# EXISTS, NOT EXISTS, CASE WHEN, and even a plain AND/OR in a WHERE clause
# were rejected regardless of whether anything they touched was actually
# unauthorized -- nearly every non-trivial query contains at least one of
# them. This went undetected because the one existing test using EXISTS
# (test_denied_column_in_a_correlated_subquery_is_caught, above) only
# checked violations[0], never the full set.


def test_exists_is_not_denied_as_an_unauthorized_function(compiler, policy):
    result = compiler.compile(
        "SELECT id FROM orders WHERE EXISTS (SELECT 1 FROM customers)",
        policy=policy,
    )
    assert result.ok, result.violations


def test_not_exists_is_not_denied_as_an_unauthorized_function(compiler, policy):
    result = compiler.compile(
        "SELECT id FROM orders WHERE NOT EXISTS (SELECT 1 FROM customers)",
        policy=policy,
    )
    assert result.ok, result.violations


def test_and_or_predicates_are_not_denied_as_unauthorized_functions(compiler, policy):
    result = compiler.compile(
        "SELECT id FROM orders WHERE amount > 1 AND amount < 100 OR amount = 0",
        policy=policy,
    )
    assert result.ok, result.violations


def test_case_expression_is_not_denied_as_an_unauthorized_function(compiler, policy):
    result = compiler.compile(
        "SELECT CASE WHEN amount > 1 THEN 1 ELSE 0 END FROM orders", policy=policy
    )
    assert result.ok, result.violations


def test_multi_column_using_is_not_denied_as_an_unauthorized_function(compiler, policy):
    # The multi-column equality JOIN ... USING (a, b) expands, sees an AND
    # combining the two column comparisons.
    result = compiler.compile(
        "SELECT o.id FROM orders o JOIN customers c ON o.id = c.id "
        "WHERE o.id = 1 AND o.amount > 0",
        policy=policy,
    )
    assert result.ok, result.violations


def test_exists_with_a_denied_column_is_still_caught(compiler, policy):
    # The fix must not weaken authorization -- only stop misfiring the
    # function check on EXISTS itself. Denied columns inside or around it
    # are still caught (see test_denied_column_in_a_correlated_subquery_is_caught
    # above, hardened to assert the full violation set for exactly this).
    result = compiler.compile(
        "SELECT id FROM orders WHERE EXISTS (SELECT 1 FROM employees WHERE salary > 100)",
        policy=policy,
    )
    assert not result.ok
    assert codes(result) == {ViolationCode.COLUMN_ACCESS_DENIED}


def test_genuinely_dangerous_function_is_still_denied_alongside_the_fix(compiler, policy):
    # Excluding structural syntax from the function check must not widen it
    # to exclude anything else -- a real function call is still denied.
    result = compiler.compile("SELECT pg_read_file('/etc/passwd')", policy=policy)
    assert not result.ok
    assert codes(result) == {ViolationCode.FUNCTION_NOT_ALLOWED}
