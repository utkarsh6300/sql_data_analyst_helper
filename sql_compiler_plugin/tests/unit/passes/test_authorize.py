"""Pass 4: check what the query reads against what the subject may read.

These tests build a ``ResolvedQuery`` by hand rather than by parsing, which is
the point: authorization is meant to be nothing but set lookups over already
resolved names, so it should be testable without a parser anywhere in sight.
If a case here needs SQL to express, the logic has leaked upstream.
"""

from __future__ import annotations

import pytest

from sql_compiler import ALL_COLUMNS, Policy, TablePolicy, TableRef
from sql_compiler.errors import RepairAction, ViolationCode
from sql_compiler.ir import ColumnRef, FunctionRef, ResolvedQuery
from sql_compiler.passes.authorize import authorize

pytestmark = pytest.mark.unit


ORDERS = TableRef("public", "orders")
EMPLOYEES = TableRef("public", "employees")
CUSTOMERS = TableRef("public", "customers")
SECRET_ORDERS = TableRef("secret", "orders")


def resolved(tables=(), columns=(), functions=()) -> ResolvedQuery:
    """A ResolvedQuery with no expression -- authorize never reads one."""
    return ResolvedQuery(
        expression=None,  # type: ignore[arg-type]
        base_tables=set(tables),
        column_refs=[ColumnRef(table=t, column=c) for t, c in columns],
        functions=[
            FunctionRef(display=name, candidates=frozenset({name})) for name in functions
        ],
    )


def codes(violations):
    return [v.code for v in violations]


@pytest.fixture
def grants() -> Policy:
    """orders fully granted; employees granted except salary and ssn."""
    return Policy(
        tables={
            ORDERS: TablePolicy(
                table=ORDERS, allowed_columns=frozenset({"id", "customer_id", "amount"})
            ),
            EMPLOYEES: TablePolicy(
                table=EMPLOYEES,
                allowed_columns=ALL_COLUMNS,
                denied_columns=frozenset({"salary", "ssn"}),
            ),
        }
    )


# -- the permitted case ------------------------------------------------------


def test_a_fully_permitted_query_yields_nothing(grants):
    query = resolved(
        tables=[ORDERS],
        columns=[(ORDERS, "id"), (ORDERS, "amount")],
        functions=["COUNT"],
    )
    assert authorize(query, grants) == []


def test_an_empty_query_yields_nothing(grants):
    assert authorize(resolved(), grants) == []


# -- tables ------------------------------------------------------------------


def test_an_ungranted_table_is_denied(grants):
    violations = authorize(resolved(tables=[CUSTOMERS]), grants)
    assert codes(violations) == [ViolationCode.TABLE_ACCESS_DENIED]
    assert violations[0].table == "public.customers"
    assert violations[0].action == RepairAction.REMOVE_TABLE


def test_a_table_in_another_schema_is_a_different_permission(grants):
    # public.orders is granted; secret.orders must not ride along.
    violations = authorize(resolved(tables=[SECRET_ORDERS]), grants)
    assert codes(violations) == [ViolationCode.TABLE_ACCESS_DENIED]
    assert violations[0].table == "secret.orders"


def test_denied_tables_are_reported_in_a_stable_order(grants):
    violations = authorize(
        resolved(tables=[SECRET_ORDERS, CUSTOMERS]), grants
    )
    assert [v.table for v in violations] == ["public.customers", "secret.orders"]


def test_an_empty_policy_denies_every_table():
    violations = authorize(resolved(tables=[ORDERS, EMPLOYEES]), Policy())
    assert codes(violations) == [ViolationCode.TABLE_ACCESS_DENIED] * 2


# -- columns -----------------------------------------------------------------


def test_a_denied_column_of_a_granted_table_is_reported(grants):
    violations = authorize(
        resolved(tables=[EMPLOYEES], columns=[(EMPLOYEES, "salary")]), grants
    )
    assert codes(violations) == [ViolationCode.COLUMN_ACCESS_DENIED]
    assert violations[0].table == "public.employees"
    assert violations[0].column == "salary"
    assert violations[0].action == RepairAction.REMOVE_COLUMN


def test_an_ungranted_column_is_reported(grants):
    # tenant_id exists on orders but is not in the grant.
    violations = authorize(
        resolved(tables=[ORDERS], columns=[(ORDERS, "tenant_id")]), grants
    )
    assert codes(violations) == [ViolationCode.COLUMN_ACCESS_DENIED]
    assert violations[0].column == "tenant_id"


def test_every_denied_column_is_collected(grants):
    # A repair loop that learns one problem per round trip converges slowly.
    violations = authorize(
        resolved(
            tables=[EMPLOYEES],
            columns=[(EMPLOYEES, "salary"), (EMPLOYEES, "ssn")],
        ),
        grants,
    )
    assert {v.column for v in violations} == {"salary", "ssn"}


def test_the_same_denied_column_is_reported_once(grants):
    # A column read in the projection and again in the WHERE clause is one
    # problem, not two.
    violations = authorize(
        resolved(
            tables=[EMPLOYEES],
            columns=[(EMPLOYEES, "salary"), (EMPLOYEES, "salary")],
        ),
        grants,
    )
    assert len(violations) == 1


def test_the_same_column_name_on_two_tables_is_two_permissions():
    # A flat column allow-list cannot express this difference.
    policy = Policy(
        tables={
            ORDERS: TablePolicy(table=ORDERS, allowed_columns=frozenset({"amount"})),
            EMPLOYEES: TablePolicy(table=EMPLOYEES, allowed_columns=frozenset({"id"})),
        }
    )
    violations = authorize(
        resolved(
            tables=[ORDERS, EMPLOYEES],
            columns=[(ORDERS, "amount"), (EMPLOYEES, "amount")],
        ),
        policy,
    )
    assert codes(violations) == [ViolationCode.COLUMN_ACCESS_DENIED]
    assert violations[0].table == "public.employees"


def test_a_denied_table_does_not_also_enumerate_its_columns(grants):
    # Listing the columns of a table the subject cannot see would confirm
    # which columns exist on it.
    violations = authorize(
        resolved(
            tables=[SECRET_ORDERS],
            columns=[(SECRET_ORDERS, "id"), (SECRET_ORDERS, "internal_note")],
        ),
        grants,
    )
    assert codes(violations) == [ViolationCode.TABLE_ACCESS_DENIED]


def test_a_denied_table_still_lets_other_tables_be_checked(grants):
    violations = authorize(
        resolved(
            tables=[SECRET_ORDERS, EMPLOYEES],
            columns=[(SECRET_ORDERS, "id"), (EMPLOYEES, "salary")],
        ),
        grants,
    )
    assert set(codes(violations)) == {
        ViolationCode.TABLE_ACCESS_DENIED,
        ViolationCode.COLUMN_ACCESS_DENIED,
    }


def test_a_column_whose_table_never_appeared_is_denied_not_allowed(grants):
    # Only reachable if resolution attributed a column to a table it did not
    # list as a base table. Deny rather than reason about it.
    violations = authorize(resolved(columns=[(CUSTOMERS, "name")]), grants)
    assert codes(violations) == [ViolationCode.TABLE_ACCESS_DENIED]
    assert violations[0].table == "public.customers"


def test_such_a_table_is_only_reported_once(grants):
    violations = authorize(
        resolved(columns=[(CUSTOMERS, "name"), (CUSTOMERS, "region")]), grants
    )
    assert len(violations) == 1


# -- functions ---------------------------------------------------------------


def test_a_function_outside_the_allow_list_is_denied(grants):
    # Without this a query needs no table at all to be dangerous.
    violations = authorize(resolved(functions=["PG_READ_FILE"]), grants)
    assert codes(violations) == [ViolationCode.FUNCTION_NOT_ALLOWED]
    assert violations[0].function == "PG_READ_FILE"
    assert violations[0].action == RepairAction.REMOVE_FUNCTION


def test_an_allow_listed_function_passes(grants):
    assert authorize(resolved(functions=["COUNT", "SUM"]), grants) == []


def test_any_matching_candidate_spelling_is_enough(grants):
    # sqlglot canonicalizes DATE_TRUNC to TimestampTrunc.
    query = ResolvedQuery(
        expression=None,  # type: ignore[arg-type]
        functions=[
            FunctionRef(
                display="TIMESTAMP_TRUNC",
                candidates=frozenset({"TIMESTAMP_TRUNC", "DATE_TRUNC"}),
            )
        ],
    )
    assert authorize(query, grants) == []


def test_the_same_denied_function_is_reported_once(grants):
    query = ResolvedQuery(
        expression=None,  # type: ignore[arg-type]
        functions=[
            FunctionRef(display="VERSION", candidates=frozenset({"VERSION"})),
            FunctionRef(display="VERSION", candidates=frozenset({"VERSION"})),
        ],
    )
    assert len(authorize(query, grants)) == 1


def test_functions_are_checked_even_with_no_tables(grants):
    # SELECT version() references nothing the table and column checks can see.
    violations = authorize(resolved(functions=["VERSION"]), grants)
    assert codes(violations) == [ViolationCode.FUNCTION_NOT_ALLOWED]


def test_a_denied_function_does_not_suppress_column_checks(grants):
    violations = authorize(
        resolved(
            tables=[EMPLOYEES],
            columns=[(EMPLOYEES, "salary")],
            functions=["VERSION"],
        ),
        grants,
    )
    assert set(codes(violations)) == {
        ViolationCode.COLUMN_ACCESS_DENIED,
        ViolationCode.FUNCTION_NOT_ALLOWED,
    }


# -- disclosure --------------------------------------------------------------


def test_violations_name_only_what_the_query_already_referenced(grants):
    # The message may name the denied object the model asked for, but must not
    # enumerate the rest of the schema.
    violations = authorize(
        resolved(tables=[EMPLOYEES], columns=[(EMPLOYEES, "salary")]), grants
    )
    blob = violations[0].message + str(violations[0].details)
    assert "ssn" not in blob
    assert "orders" not in blob
