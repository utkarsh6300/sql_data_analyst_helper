"""Pass 5: apply row-level filters recorded on the policy.

``TablePolicy.row_filter`` used to be recorded and never enforced (see
``docs/04-decisions.md#2``). These tests pin the derived-subquery shape that
closes the gap: every base-table *occurrence* -- not every mention of a name
-- gets its own filtered copy, so a self-join, a CTE, and a plain FROM all
end up correctly scoped rather than the filter landing on an unrelated outer
WHERE clause.
"""

from __future__ import annotations

import pytest
import sqlglot
from sqlglot import exp

from sql_compiler import Catalog, Policy, TablePolicy, TableRef
from sql_compiler.errors import ConfigurationError
from sql_compiler.passes.resolve import resolve
from sql_compiler.passes.rowsec import apply_row_filters

pytestmark = pytest.mark.unit


ORDERS = TableRef("public", "orders")
CUSTOMERS = TableRef("public", "customers")


def run(sql: str, catalog: Catalog):
    resolved, violations = resolve(sqlglot.parse_one(sql, dialect=catalog.dialect), catalog)
    assert violations == []
    return resolved


def render(resolved, catalog: Catalog) -> str:
    return resolved.expression.sql(dialect=catalog.dialect)


def policy_with_filter(row_filter: str, *, table: TableRef = ORDERS) -> Policy:
    return Policy(
        tables={
            table: TablePolicy(table=table, row_filter=row_filter),
            CUSTOMERS: TablePolicy(table=CUSTOMERS),
        }
    )


# -- no-op when there is nothing to filter -----------------------------------


def test_a_table_with_no_row_filter_is_left_untouched(catalog):
    resolved = run("SELECT id FROM orders", catalog)
    before = render(resolved, catalog)
    apply_row_filters(resolved, policy_with_filter(None), catalog)
    assert render(resolved, catalog) == before


def test_a_table_absent_from_the_policy_is_left_untouched(catalog):
    resolved = run("SELECT id FROM orders", catalog)
    before = render(resolved, catalog)
    # Policy only mentions customers -- orders has no TablePolicy at all.
    apply_row_filters(
        resolved, Policy(tables={CUSTOMERS: TablePolicy(table=CUSTOMERS)}), catalog
    )
    assert render(resolved, catalog) == before


# -- the filter is applied where the table is, not on the outer query -------


def test_a_filtered_table_becomes_a_derived_subquery(catalog):
    resolved = run("SELECT id FROM orders", catalog)
    apply_row_filters(resolved, policy_with_filter("tenant_id = 7"), catalog)
    sql = render(resolved, catalog)
    assert "WHERE" in sql
    assert "tenant_id" in sql
    # Reparses cleanly under the same dialect -- the filter is real SQL, not
    # a mangled fragment.
    assert sqlglot.parse_one(sql, dialect=catalog.dialect) is not None


def test_the_predicate_is_parsed_not_string_concatenated(catalog):
    """A filter containing a quote must not corrupt the surrounding query.

    If this were built with an f-string, a stray quote in the filter would
    either break parsing or -- worse -- let the filter's text splice into
    the outer query. Parsing it as an AST node and re-emitting it sidesteps
    that entirely.
    """
    resolved = run("SELECT id FROM orders", catalog)
    apply_row_filters(
        resolved, policy_with_filter("region = 'it''s-eu'"), catalog
    )
    sql = render(resolved, catalog)
    reparsed = sqlglot.parse_one(sql, dialect=catalog.dialect)
    literal = next(reparsed.find_all(exp.Literal))
    assert literal.this == "it's-eu"


def test_only_the_filtered_table_is_wrapped(catalog):
    resolved = run(
        "SELECT o.id, c.name FROM orders o JOIN customers c ON o.customer_id = c.id",
        catalog,
    )
    apply_row_filters(resolved, policy_with_filter("tenant_id = 7"), catalog)
    sql = render(resolved, catalog)
    assert sql.count("WHERE") == 1
    assert '"customers"' in sql


def test_a_self_join_filters_each_occurrence_independently(catalog):
    resolved = run(
        "SELECT a.id FROM orders a JOIN orders b ON a.customer_id = b.customer_id",
        catalog,
    )
    apply_row_filters(resolved, policy_with_filter("tenant_id = 7"), catalog)
    sql = render(resolved, catalog)
    # Both sides of the self-join are filtered -- not just one, which would
    # be the "binds to one relation, leaves the other unfiltered" failure
    # mode docs/04-decisions.md documents for the naive approach.
    assert sql.count("tenant_id") == 2


def test_a_filtered_table_inside_a_cte_is_filtered_there_not_outside(catalog):
    resolved = run(
        "WITH recent AS (SELECT id, amount FROM orders) SELECT amount FROM recent",
        catalog,
    )
    apply_row_filters(resolved, policy_with_filter("tenant_id = 7"), catalog)
    sql = render(resolved, catalog)
    parsed = sqlglot.parse_one(sql, dialect=catalog.dialect)
    # The filter lives inside the CTE's own definition...
    cte = next(parsed.find_all(exp.CTE))
    assert "tenant_id" in cte.sql()
    # ...and the outer query, which never selected tenant_id, is untouched --
    # exactly what the naive "append WHERE to the outer statement" approach
    # gets wrong (docs/04-decisions.md#2).
    outer_only = parsed.copy()
    outer_only.set("with", None)
    assert "tenant_id" not in outer_only.sql(dialect=catalog.dialect)


# -- a bad row_filter is the host's bug, not the query's ---------------------


def test_unparseable_row_filter_is_a_configuration_error(catalog):
    resolved = run("SELECT id FROM orders", catalog)
    with pytest.raises(ConfigurationError):
        apply_row_filters(resolved, policy_with_filter("not valid sql ((("), catalog)


def test_a_smuggled_second_statement_is_a_configuration_error(catalog):
    resolved = run("SELECT id FROM orders", catalog)
    with pytest.raises(ConfigurationError):
        apply_row_filters(
            resolved,
            policy_with_filter("tenant_id = 1; DROP TABLE orders"),
            catalog,
        )


def test_an_unmodeled_row_filter_construct_is_a_configuration_error(catalog):
    resolved = run("SELECT id FROM orders", catalog)
    with pytest.raises(ConfigurationError):
        apply_row_filters(resolved, policy_with_filter("VACUUM FULL"), catalog)
