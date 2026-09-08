"""Pass 2: prove the statement is a pure read, deny-by-default.

Operates on an already-parsed tree, so these cases are about the deny list and
about walking the whole tree rather than trusting its root.
"""

from __future__ import annotations

import pytest
import sqlglot
from sqlglot import exp

from sql_compiler.errors import ViolationCode
from sql_compiler.passes.readonly import (
    ALLOWED_ROOT_TYPES,
    FORBIDDEN_NODE_TYPES,
    check_read_only,
)

pytestmark = pytest.mark.unit


def codes(violations):
    return [v.code for v in violations]


def guard(sql: str, dialect: str = "postgres"):
    """Parse, then run pass 2 the way the compiler does."""
    return check_read_only(sqlglot.parse_one(sql, dialect=dialect))


# -- reads are allowed -------------------------------------------------------


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT id FROM orders",
        "WITH x AS (SELECT id FROM orders) SELECT * FROM x",
        "SELECT id FROM orders UNION SELECT id FROM archive",
        "SELECT id FROM orders EXCEPT SELECT id FROM archive",
        "SELECT id FROM orders INTERSECT SELECT id FROM archive",
        "SELECT * FROM (SELECT id FROM orders) t",
        "SELECT id FROM orders ORDER BY id FETCH FIRST 10 ROWS ONLY",
        "SELECT id FROM orders LIMIT 10 OFFSET 5",
        "SELECT COUNT(*) FROM orders GROUP BY tenant_id HAVING COUNT(*) > 1",
        "SELECT id FROM orders WHERE id IN (SELECT id FROM customers)",
    ],
)
def test_read_only_selects_pass(sql):
    assert guard(sql) == []


def test_fetch_is_not_denied():
    # FETCH FIRST n ROWS ONLY is standard row limiting, not a cursor op.
    assert exp.Fetch not in FORBIDDEN_NODE_TYPES


# -- root statement type -----------------------------------------------------


@pytest.mark.parametrize(
    "sql",
    [
        "DROP TABLE orders",
        "INSERT INTO orders VALUES (1)",
        "UPDATE orders SET amount = 1",
        "DELETE FROM orders",
        "ALTER TABLE orders ADD COLUMN x INT",
        "TRUNCATE TABLE orders",
        "CREATE TABLE t (id INT)",
        "GRANT SELECT ON orders TO bob",
        "REVOKE SELECT ON orders FROM bob",
        "SET search_path = evil",
        "COPY orders TO '/tmp/leak.csv'",
        "COMMIT",
        "ROLLBACK",
        "MERGE INTO orders USING orders AS src ON orders.id = src.id WHEN MATCHED THEN DELETE",
        "CALL some_proc()",
        "EXECUTE some_stmt",
        "PREPARE some_stmt AS SELECT 1",
    ],
)
def test_non_select_roots_are_rejected(sql):
    assert codes(guard(sql))[0] in {
        ViolationCode.NON_SELECT_STATEMENT,
        ViolationCode.FORBIDDEN_EXPRESSION,
    }


def test_a_disqualifying_root_is_reported_once_without_extra_noise():
    # Walking a statement that cannot run anyway only adds confusing detail.
    violations = guard("DROP TABLE orders")
    assert len(violations) == 1


def test_the_statement_type_is_reported_for_the_repair_loop():
    violations = guard("INSERT INTO orders VALUES (1)")
    assert violations[0].details["statement_type"] == "INSERT"


def test_select_is_an_allowed_root():
    assert exp.Select in ALLOWED_ROOT_TYPES


def test_a_bare_parenthesized_select_is_still_walked():
    # A top-level (SELECT ...) is exp.Paren wrapping exp.Select -- an allowed
    # root, but only if the pass still walks inside it rather than treating
    # the parenthesis as opaque.
    assert guard("(SELECT id FROM orders)") == []


def test_a_write_inside_a_bare_paren_root_is_still_caught():
    assert (
        ViolationCode.FORBIDDEN_EXPRESSION
        in codes(guard("(WITH d AS (DELETE FROM orders RETURNING id) SELECT * FROM d)"))
    )


# -- the whole tree, not just the root ---------------------------------------


@pytest.mark.parametrize(
    "sql",
    [
        # Postgres data-modifying CTEs: root is Select, body writes.
        "WITH x AS (INSERT INTO orders VALUES (1) RETURNING id) SELECT * FROM x",
        "WITH d AS (DELETE FROM orders RETURNING id) SELECT * FROM d",
        "WITH u AS (UPDATE orders SET amount = 0 RETURNING id) SELECT * FROM u",
        # SELECT ... INTO creates a table.
        "SELECT id INTO new_table FROM orders",
        # FOR UPDATE takes write locks and needs a writable transaction.
        "SELECT * FROM orders FOR UPDATE",
    ],
)
def test_writes_hidden_under_a_select_root_are_rejected(sql):
    violations = guard(sql)
    assert ViolationCode.FORBIDDEN_EXPRESSION in codes(violations), sql


def test_a_write_nested_deep_in_a_subquery_is_found():
    sql = (
        "SELECT id FROM orders WHERE id IN ("
        "  WITH w AS (DELETE FROM audit RETURNING id) SELECT id FROM w"
        ")"
    )
    assert ViolationCode.FORBIDDEN_EXPRESSION in codes(guard(sql))


def test_each_forbidden_type_is_reported_once():
    sql = (
        "WITH a AS (INSERT INTO t VALUES (1) RETURNING id), "
        "b AS (INSERT INTO t VALUES (2) RETURNING id) "
        "SELECT * FROM a JOIN b ON a.id = b.id"
    )
    violations = guard(sql)
    assert len(violations) == 1
    assert violations[0].details["expression_type"] == "INSERT"


def test_distinct_forbidden_types_are_all_reported():
    # A repair loop that learns one problem per round trip converges slowly.
    sql = (
        "WITH a AS (INSERT INTO t VALUES (1) RETURNING id), "
        "b AS (DELETE FROM t RETURNING id) "
        "SELECT * FROM a JOIN b ON a.id = b.id"
    )
    reported = {v.details["expression_type"] for v in guard(sql)}
    assert reported == {"INSERT", "DELETE"}


# -- unmodelled syntax -------------------------------------------------------


def test_command_is_in_the_deny_list():
    # sqlglot wraps anything it cannot model in a Command node. If Command
    # were allowed, every unmodelled statement would pass silently.
    assert exp.Command in FORBIDDEN_NODE_TYPES


@pytest.mark.parametrize("sql", ["VACUUM FULL", "REINDEX TABLE orders", "LISTEN chan"])
def test_unsupported_syntax_is_denied_not_ignored(sql):
    assert codes(guard(sql))[0] in {
        ViolationCode.NON_SELECT_STATEMENT,
        ViolationCode.FORBIDDEN_EXPRESSION,
    }


def test_an_unmodelled_statement_is_labelled_by_its_keyword():
    violations = guard("VACUUM FULL")
    label = violations[0].details.get("statement_type") or violations[0].details.get(
        "expression_type"
    )
    assert "VACUUM" in label


def test_unmodelled_statement_with_no_keyword_gets_a_generic_label():
    # _friendly()'s fallback for an exp.Command whose `this` is empty --
    # every other unmodelled-statement test here has a real leading keyword.
    command = exp.Command(this="")
    violations = check_read_only(command)
    assert violations[0].details["statement_type"] == "unsupported statement"


# -- the deny list itself ----------------------------------------------------


def test_the_deny_list_resolved_to_real_expression_classes():
    # Names are looked up on `exp` so an upgrade that renames a class degrades
    # to a smaller list rather than an ImportError -- but whatever survives
    # must be usable with isinstance.
    assert FORBIDDEN_NODE_TYPES
    for node_type in FORBIDDEN_NODE_TYPES:
        assert isinstance(node_type, type)
        assert issubclass(node_type, exp.Expression)


def test_the_allowed_root_list_resolved_to_real_expression_classes():
    assert ALLOWED_ROOT_TYPES
    for node_type in ALLOWED_ROOT_TYPES:
        assert issubclass(node_type, exp.Expression)


@pytest.mark.parametrize(
    "name",
    ["Insert", "Update", "Delete", "Create", "Drop", "Alter", "Grant", "Command", "Into"],
)
def test_the_essential_denials_are_present(name):
    # These are the ones whose absence would be a hole rather than a
    # tolerable version difference.
    assert getattr(exp, name) in FORBIDDEN_NODE_TYPES


# -- disclosure --------------------------------------------------------------


def test_violations_do_not_echo_the_query_text():
    # Error payloads flow back to the LLM and possibly to users; echoing the
    # rejected SQL turns a rejection into a disclosure channel.
    violations = guard("SELECT secret_column INTO leak FROM payroll")
    assert violations
    for violation in violations:
        blob = violation.message + str(violation.details)
        assert "secret_column" not in blob
        assert "payroll" not in blob
