"""Identifier normalization and qualified table names.

Every authorization decision is ultimately a string comparison between an
identifier an LLM wrote and one a human wrote in a policy.  If the two sides
normalize differently the compiler compares the wrong strings and authorizes
the wrong thing, so this module is tested directly rather than only through
the catalog.
"""

from __future__ import annotations

import pytest
import sqlglot
from sqlglot import exp

from sql_compiler import ConfigurationError, TableRef
from sql_compiler.names import normalize_identifier

pytestmark = pytest.mark.unit


# -- normalize_identifier ----------------------------------------------------


def test_postgres_folds_unquoted_names_down():
    assert normalize_identifier("Orders", "postgres") == "orders"
    assert normalize_identifier("ORDERS", "postgres") == "orders"


def test_snowflake_folds_unquoted_names_up():
    assert normalize_identifier("orders", "snowflake") == "ORDERS"


def test_quoted_names_keep_their_case():
    # "Orders" and orders are genuinely different tables in Postgres; folding
    # them together would let a policy for one authorize the other.
    assert normalize_identifier("Orders", "postgres", quoted=True) == "Orders"
    assert normalize_identifier("orders", "snowflake", quoted=True) == "orders"


def test_already_normalized_names_are_stable():
    once = normalize_identifier("Orders", "postgres")
    assert normalize_identifier(once, "postgres") == once


def test_unusable_identifier_is_a_configuration_error():
    with pytest.raises(ConfigurationError, match="not a usable identifier"):
        normalize_identifier(None, "postgres")  # type: ignore[arg-type]


def test_an_empty_name_currently_normalizes_to_an_empty_string():
    # Documenting real behaviour rather than endorsing it: sqlglot turns "" into
    # a quoted empty identifier rather than nothing, so the ConfigurationError
    # guard above never fires for it. Harmless today because an empty column
    # name cannot match a grant, but it is the reason a blank entry in a
    # catalog column list passes construction instead of being rejected.
    assert normalize_identifier("", "postgres") == ""


def test_unknown_dialect_is_reported():
    # A typo in the dialect must not silently fall back to "no normalization".
    with pytest.raises(Exception):
        normalize_identifier("orders", "not_a_real_dialect")


# -- TableRef.parse ----------------------------------------------------------


def test_bare_name_takes_the_default_schema():
    ref = TableRef.parse("orders", dialect="postgres", default_schema="public")
    assert ref == TableRef("public", "orders")


def test_qualified_name_keeps_its_own_schema():
    ref = TableRef.parse("secret.orders", dialect="postgres", default_schema="public")
    assert ref == TableRef("secret", "orders")


def test_default_schema_is_not_applied_over_an_explicit_one():
    # The other_schema.orders bypass: an explicit schema must win.
    ref = TableRef.parse("secret.orders", dialect="postgres", default_schema="analytics")
    assert ref.schema == "secret"


def test_surrounding_whitespace_is_ignored():
    ref = TableRef.parse("  orders \n", dialect="postgres", default_schema="public")
    assert ref == TableRef("public", "orders")


def test_case_is_folded_by_the_dialect():
    assert TableRef.parse(
        "PUBLIC.Orders", dialect="postgres", default_schema="public"
    ) == TableRef("public", "orders")


def test_quoted_parts_keep_their_case():
    ref = TableRef.parse(
        '"Public"."Orders"', dialect="postgres", default_schema="public"
    )
    assert ref == TableRef("Public", "Orders")


def test_empty_name_is_a_configuration_error():
    with pytest.raises(ConfigurationError, match="cannot be empty"):
        TableRef.parse("   ", dialect="postgres", default_schema="public")


def test_three_part_name_is_a_configuration_error():
    # Cross-database references are out of scope; accepting one silently would
    # mean authorizing a name whose first part was never checked.
    with pytest.raises(ConfigurationError, match="three-part"):
        TableRef.parse("db.public.orders", dialect="postgres", default_schema="public")


# -- TableRef.from_table_node ------------------------------------------------


def test_from_table_node_reads_schema_and_name():
    node = sqlglot.parse_one("SELECT 1 FROM secret.orders").find(exp.Table)
    ref = TableRef.from_table_node(node, dialect="postgres", default_schema="public")
    assert ref == TableRef("secret", "orders")


def test_from_table_node_falls_back_to_the_default_schema():
    node = sqlglot.parse_one("SELECT 1 FROM orders").find(exp.Table)
    ref = TableRef.from_table_node(node, dialect="postgres", default_schema="analytics")
    assert ref == TableRef("analytics", "orders")


def test_from_table_node_ignores_the_alias():
    # `orders o` must resolve to orders, not to o.
    node = sqlglot.parse_one("SELECT 1 FROM orders o").find(exp.Table)
    ref = TableRef.from_table_node(node, dialect="postgres", default_schema="public")
    assert ref == TableRef("public", "orders")


def test_from_table_node_without_a_name_is_rejected():
    with pytest.raises(ConfigurationError, match="cannot read a table name"):
        TableRef.from_table_node(
            exp.Table(), dialect="postgres", default_schema="public"
        )


# -- value semantics ---------------------------------------------------------


def test_qualified_and_str_agree():
    ref = TableRef("public", "orders")
    assert ref.qualified == "public.orders"
    assert str(ref) == "public.orders"


def test_refs_are_hashable_and_compare_by_value():
    # Catalog and Policy both key dicts on TableRef.
    assert TableRef("public", "orders") == TableRef("public", "orders")
    assert len({TableRef("public", "orders"), TableRef("public", "orders")}) == 1
    assert TableRef("public", "orders") != TableRef("secret", "orders")


def test_refs_sort_by_schema_then_name():
    # Violation order is derived from sorted refs, so this ordering is part of
    # the compiler's observable output.
    refs = [
        TableRef("public", "orders"),
        TableRef("public", "customers"),
        TableRef("analytics", "orders"),
    ]
    assert sorted(refs) == [
        TableRef("analytics", "orders"),
        TableRef("public", "customers"),
        TableRef("public", "orders"),
    ]


def test_refs_are_immutable():
    ref = TableRef("public", "orders")
    with pytest.raises(Exception):
        ref.schema = "secret"  # type: ignore[misc]
