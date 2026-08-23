"""Pass 1: exactly one parseable statement, or nothing.

Everything downstream works on the tree this pass returns, so the pass has to
refuse anything it cannot represent as a single tree -- most importantly
stacked statements, where analysing the first and executing the string is the
classic bypass.
"""

from __future__ import annotations

import pytest
from sqlglot import exp

from sql_compiler.errors import RepairAction, ViolationCode
from sql_compiler.passes.parse import parse_single_statement

pytestmark = pytest.mark.unit


def codes(violations):
    return [v.code for v in violations]


# -- success -----------------------------------------------------------------


def test_a_single_select_returns_a_tree_and_no_violations():
    statement, violations = parse_single_statement("SELECT id FROM orders", "postgres")
    assert violations == []
    assert isinstance(statement, exp.Select)


def test_trailing_semicolon_is_not_a_second_statement():
    # sqlglot yields a None entry for the empty tail.
    statement, violations = parse_single_statement("SELECT id FROM orders;", "postgres")
    assert violations == []
    assert statement is not None


def test_leading_comments_and_whitespace_are_fine():
    statement, violations = parse_single_statement(
        "-- the model likes to explain itself\n  SELECT id FROM orders", "postgres"
    )
    assert violations == []
    assert statement is not None


def test_the_dialect_is_honoured():
    # Parsed under the catalog's dialect, so dialect-specific syntax resolves.
    _, violations = parse_single_statement(
        "SELECT id FROM orders LIMIT 1", "snowflake"
    )
    assert violations == []


# -- empty input -------------------------------------------------------------


@pytest.mark.parametrize("sql", ["", "   ", "\n\t "])
def test_blank_input_is_rejected(sql):
    statement, violations = parse_single_statement(sql, "postgres")
    assert statement is None
    assert codes(violations) == [ViolationCode.EMPTY_STATEMENT]


def test_none_input_is_rejected():
    statement, violations = parse_single_statement(None, "postgres")  # type: ignore[arg-type]
    assert statement is None
    assert codes(violations) == [ViolationCode.EMPTY_STATEMENT]


def test_comment_only_input_is_rejected():
    statement, violations = parse_single_statement("-- nothing here", "postgres")
    assert statement is None
    assert codes(violations) == [ViolationCode.EMPTY_STATEMENT]


def test_a_lone_semicolon_is_rejected():
    statement, violations = parse_single_statement(";", "postgres")
    assert statement is None
    assert codes(violations) == [ViolationCode.EMPTY_STATEMENT]


# -- unparseable input -------------------------------------------------------


def test_unparseable_sql_is_rejected():
    statement, violations = parse_single_statement("SELECT FROM WHERE (((", "postgres")
    assert statement is None
    assert codes(violations) == [ViolationCode.PARSE_ERROR]


def test_parse_failure_asks_for_a_rewrite():
    _, violations = parse_single_statement("SELECT FROM WHERE (((", "postgres")
    assert violations[0].action == RepairAction.REWRITE_QUERY


def test_parser_feedback_is_one_short_line():
    # The raw parser error is multi-line and quotes the query back; neither
    # belongs in a payload that may reach a user.
    _, violations = parse_single_statement("SELECT FROM WHERE (((", "postgres")
    message = violations[0].details["parser_message"]
    assert "\n" not in message
    assert len(message) <= 200


# -- stacked statements ------------------------------------------------------


def test_stacked_statements_are_rejected():
    # Validating only the first statement and then executing the original
    # string is the classic stacked-query bypass.
    statement, violations = parse_single_statement(
        "SELECT 1; DROP TABLE orders", "postgres"
    )
    assert statement is None
    assert codes(violations) == [ViolationCode.MULTIPLE_STATEMENTS]
    assert violations[0].details["statement_count"] == 2


def test_stacked_statements_ask_for_a_single_select():
    _, violations = parse_single_statement("SELECT 1; SELECT 2", "postgres")
    assert violations[0].action == RepairAction.USE_SINGLE_SELECT


def test_two_harmless_selects_are_still_rejected():
    # The rule is one statement, not "no dangerous statements".
    _, violations = parse_single_statement(
        "SELECT id FROM orders; SELECT id FROM customers", "postgres"
    )
    assert codes(violations) == [ViolationCode.MULTIPLE_STATEMENTS]


def test_the_statement_count_is_reported():
    _, violations = parse_single_statement("SELECT 1; SELECT 2; SELECT 3", "postgres")
    assert violations[0].details["statement_count"] == 3


def test_rejection_does_not_echo_the_query_text():
    _, violations = parse_single_statement(
        "SELECT 1; DROP TABLE payroll_secrets", "postgres"
    )
    blob = violations[0].message + str(violations[0].details)
    assert "payroll_secrets" not in blob
