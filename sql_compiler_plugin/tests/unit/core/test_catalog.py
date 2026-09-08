"""Catalog construction and identifier normalization."""

from __future__ import annotations

import pytest

from sql_compiler import Catalog, ConfigurationError, TableRef
from sql_compiler.catalog import UNKNOWN_TYPE

pytestmark = pytest.mark.unit


# -- from_dict ---------------------------------------------------------------


def test_nested_and_flat_forms_agree():
    nested = Catalog.from_dict({"public": {"orders": {"id": "INT", "amount": "NUMERIC"}}})
    flat = Catalog.from_dict({"public.orders": {"id": "INT", "amount": "NUMERIC"}})
    assert nested.to_mapping_schema() == flat.to_mapping_schema()


def test_unqualified_table_lands_in_default_schema():
    catalog = Catalog.from_dict({"orders": ["id"]})
    assert catalog.tables == [TableRef("public", "orders")]


def test_default_schema_is_configurable():
    catalog = Catalog.from_dict({"orders": ["id"]}, default_schema="analytics")
    assert catalog.tables == [TableRef("analytics", "orders")]


def test_column_sequence_without_types_is_accepted():
    catalog = Catalog.from_dict({"orders": ["id", "amount"]})
    assert catalog.columns(TableRef("public", "orders")) == ["id", "amount"]


def test_untyped_columns_get_the_placeholder_type():
    # qualify only needs column names, so an unknown type must not block
    # resolution -- but it must also not masquerade as a real type.
    catalog = Catalog.from_dict({"orders": ["id"]})
    assert catalog.to_mapping_schema()["public"]["orders"]["id"] == UNKNOWN_TYPE


def test_null_column_type_becomes_the_placeholder():
    catalog = Catalog.from_dict({"orders": {"id": None}})
    assert catalog.to_mapping_schema()["public"]["orders"]["id"] == UNKNOWN_TYPE


def test_same_table_name_in_two_schemas_stays_distinct():
    catalog = Catalog.from_dict(
        {
            "public.orders": ["id", "amount"],
            "secret.orders": ["id", "ssn"],
        }
    )
    assert catalog.columns(TableRef("public", "orders")) == ["id", "amount"]
    assert catalog.columns(TableRef("secret", "orders")) == ["id", "ssn"]


def test_table_with_no_columns_is_rejected():
    with pytest.raises(ConfigurationError, match="no columns"):
        Catalog.from_dict({"public.orders": []})


def test_an_empty_nested_schema_value_is_a_configuration_error_not_a_silent_no_op():
    # {"public": {}} is ambiguous -- "an empty schema" or "a table named
    # public with no columns" -- and _is_nested_schema treats an empty dict
    # as not-nested, so it resolves to the second reading. Either way it
    # must fail closed with ConfigurationError, never silently produce an
    # empty, table-less catalog.
    with pytest.raises(ConfigurationError, match="no columns"):
        Catalog.from_dict({"public": {}})


def test_three_part_name_is_rejected():
    with pytest.raises(ConfigurationError, match="three-part"):
        Catalog.from_dict({"db.public.orders": ["id"]})


def test_columns_of_an_unsupported_type_are_rejected():
    # A bare int or string would otherwise be iterated into nonsense columns.
    with pytest.raises(ConfigurationError, match="must be a mapping or a sequence"):
        Catalog.from_dict({"orders": 7})


# -- normalization -----------------------------------------------------------


def test_unquoted_identifiers_fold_to_postgres_case():
    catalog = Catalog.from_dict({"PUBLIC.Orders": {"ID": "INT"}})
    assert catalog.tables == [TableRef("public", "orders")]
    assert catalog.columns(TableRef("public", "orders")) == ["id"]


def test_quoted_identifiers_keep_their_case():
    # "Orders" and orders are genuinely different tables in Postgres; folding
    # them together would let a policy for one authorize the other.
    catalog = Catalog.from_dict({'public."Orders"': ["id"]})
    assert catalog.tables == [TableRef("public", "Orders")]
    assert TableRef("public", "orders") not in catalog


def test_snowflake_folds_upward():
    catalog = Catalog.from_dict(
        {"orders": ["id"]}, dialect="snowflake", default_schema="public"
    )
    assert catalog.tables == [TableRef("PUBLIC", "ORDERS")]


# -- lookup ------------------------------------------------------------------


def test_columns_of_an_unknown_table_is_empty_not_an_error():
    # Unknown tables are denied by the resolve pass; the catalog itself just
    # reports what it knows.
    catalog = Catalog.from_dict({"orders": ["id"]})
    assert catalog.columns(TableRef("public", "nonexistent")) == []


def test_has_column_is_schema_aware():
    catalog = Catalog.from_dict(
        {"public.orders": ["id", "amount"], "secret.orders": ["id", "note"]}
    )
    assert catalog.has_column(TableRef("public", "orders"), "amount")
    assert not catalog.has_column(TableRef("secret", "orders"), "amount")
    assert not catalog.has_column(TableRef("public", "nonexistent"), "id")


def test_ref_parses_against_the_catalogs_own_settings():
    catalog = Catalog.from_dict({"orders": ["id"]}, default_schema="analytics")
    assert catalog.ref("Orders") == TableRef("analytics", "orders")
    assert catalog.ref("public.orders") == TableRef("public", "orders")


def test_len_counts_tables():
    assert len(Catalog.from_dict({"a": ["id"], "b": ["id"]})) == 2
    assert len(Catalog.from_dict({})) == 0


def test_contains_requires_a_matching_schema():
    catalog = Catalog.from_dict({"public.orders": ["id"]})
    assert TableRef("public", "orders") in catalog
    assert TableRef("secret", "orders") not in catalog


def test_tables_are_returned_sorted():
    catalog = Catalog.from_dict({"public.orders": ["id"], "public.customers": ["id"]})
    assert catalog.tables == [
        TableRef("public", "customers"),
        TableRef("public", "orders"),
    ]


def test_catalog_does_not_alias_the_mapping_it_was_built_from():
    columns = {"id": "INT"}
    catalog = Catalog.from_dict({"orders": columns})
    columns["salary"] = "NUMERIC"
    assert catalog.columns(TableRef("public", "orders")) == ["id"]


# -- from_ddl ----------------------------------------------------------------


def test_from_ddl_extracts_tables_and_columns():
    catalog = Catalog.from_ddl(
        [
            """
            CREATE TABLE public.orders (
                id INT PRIMARY KEY,
                customer_id INT REFERENCES customers(id),
                amount NUMERIC(12, 2) NOT NULL
            );
            """
        ]
    )
    assert catalog.tables == [TableRef("public", "orders")]
    assert catalog.columns(TableRef("public", "orders")) == ["id", "customer_id", "amount"]


def test_from_ddl_handles_multi_statement_blobs():
    catalog = Catalog.from_ddl(
        [
            "CREATE TABLE orders (id INT, amount NUMERIC);"
            "CREATE TABLE customers (id INT, name TEXT);"
        ]
    )
    assert catalog.tables == [
        TableRef("public", "customers"),
        TableRef("public", "orders"),
    ]


def test_from_ddl_ignores_non_create_table_statements():
    # Real DDL dumps are full of indexes, comments and views.
    catalog = Catalog.from_ddl(
        [
            "CREATE TABLE orders (id INT);",
            "CREATE INDEX idx_orders ON orders (id);",
            "COMMENT ON TABLE orders IS 'hello';",
            "CREATE VIEW v AS SELECT id FROM orders;",
        ]
    )
    assert catalog.tables == [TableRef("public", "orders")]


def test_from_ddl_ignores_create_table_as_select():
    # There are no column definitions to harvest, and inventing them would
    # register a table whose real columns are unknown.
    catalog = Catalog.from_ddl(
        ["CREATE TABLE snapshot AS SELECT id FROM orders;"]
    )
    assert catalog.tables == []


def test_from_ddl_skips_blank_entries():
    catalog = Catalog.from_ddl(["", "   \n ", "CREATE TABLE orders (id INT);"])
    assert catalog.tables == [TableRef("public", "orders")]


def test_from_ddl_skips_table_level_constraints():
    catalog = Catalog.from_ddl(
        ["CREATE TABLE t (a INT, b INT, PRIMARY KEY (a, b), UNIQUE (b));"]
    )
    assert catalog.columns(TableRef("public", "t")) == ["a", "b"]


def test_from_ddl_drops_a_table_with_only_constraints_and_no_columns():
    # Distinct from test_from_ddl_skips_table_level_constraints (which mixes
    # constraints with real columns): a CREATE TABLE with *only* table-level
    # constraints has nothing to harvest, so the whole table is absent from
    # the catalog -- not registered with zero columns. Combined with
    # deny-by-default (an absent table is UNKNOWN_TABLE), this fails safe.
    catalog = Catalog.from_ddl(["CREATE TABLE t (PRIMARY KEY (a, b));"])
    assert catalog.tables == []


def test_from_ddl_keeps_column_types_with_their_precision():
    # sqlglot canonicalizes the type name (NUMERIC renders as DECIMAL), so the
    # spelling is not preserved -- but the precision must be, since this text
    # is what gets rendered back into a schema prompt.
    catalog = Catalog.from_ddl(["CREATE TABLE t (amount NUMERIC(12, 2));"])
    assert catalog.to_mapping_schema()["public"]["t"]["amount"] == "DECIMAL(12, 2)"


def test_from_ddl_normalizes_identifier_case():
    catalog = Catalog.from_ddl(["CREATE TABLE Public.Orders (Id INT);"])
    assert catalog.tables == [TableRef("public", "orders")]
    assert catalog.columns(TableRef("public", "orders")) == ["id"]


def test_from_ddl_honours_the_default_schema():
    catalog = Catalog.from_ddl(
        ["CREATE TABLE orders (id INT);"], default_schema="analytics"
    )
    assert catalog.tables == [TableRef("analytics", "orders")]


def test_from_ddl_is_strict_about_unparseable_input():
    with pytest.raises(ConfigurationError, match="could not parse DDL"):
        Catalog.from_ddl(["CREATE TABLE ((("])


def test_from_ddl_can_skip_unparseable_input_when_asked():
    catalog = Catalog.from_ddl(
        ["CREATE TABLE (((", "CREATE TABLE ok (id INT);"], strict=False
    )
    assert catalog.tables == [TableRef("public", "ok")]


def test_empty_catalog_is_falsey():
    assert not Catalog.from_dict({})
    assert Catalog.from_dict({"orders": ["id"]})


def test_to_mapping_schema_shape_matches_sqlglot_expectation():
    catalog = Catalog.from_dict({"public.orders": {"id": "INT"}})
    assert catalog.to_mapping_schema() == {"public": {"orders": {"id": "INT"}}}


def test_to_mapping_schema_groups_tables_by_schema():
    catalog = Catalog.from_dict(
        {"public.orders": {"id": "INT"}, "secret.orders": {"id": "INT"}}
    )
    mapping = catalog.to_mapping_schema()
    assert set(mapping) == {"public", "secret"}
    assert set(mapping["public"]) == {"orders"}
