"""Permission-filtered schema, used before generation rather than after.

The agreement between this filter and the compiler is checked end to end in
``tests/integration/test_schema_prompt_contract.py``.
"""

from __future__ import annotations

import pytest

from sql_compiler import Catalog, Policy, render_schema_prompt, visible_schema

pytestmark = pytest.mark.unit


# -- what is hidden ----------------------------------------------------------


def test_denied_table_is_absent(catalog, policy):
    visible = visible_schema(catalog, policy)
    assert "secret.orders" not in visible
    assert "public.orders" in visible


def test_denied_columns_are_absent(catalog, policy):
    visible = visible_schema(catalog, policy)
    assert set(visible["public.employees"]) == {"id", "name"}
    assert "salary" not in visible["public.employees"]


def test_ungranted_column_is_absent(catalog, policy):
    # tenant_id exists on orders but is not in the grant.
    assert "tenant_id" not in visible_schema(catalog, policy)["public.orders"]


def test_table_with_no_readable_columns_is_omitted_entirely(catalog):
    # An empty table entry would still disclose that the table exists.
    policy = Policy.from_dict(
        {"tables": {"public.employees": {"columns": "*", "denied_columns":
                                         ["id", "name", "salary", "ssn"]}}}
    )
    assert visible_schema(catalog, policy) == {}


def test_empty_policy_shows_nothing(catalog):
    assert visible_schema(catalog, Policy.from_dict({})) == {}


def test_a_grant_for_a_table_the_catalog_lacks_shows_nothing():
    # The catalog is the source of truth about what exists; a stale grant must
    # not invent a table in the prompt.
    catalog = Catalog.from_dict({"orders": ["id"]})
    policy = Policy.from_dict({"tables": {"orders": ["id"], "gone": ["id"]}})
    assert set(visible_schema(catalog, policy)) == {"public.orders"}


def test_same_table_name_in_two_schemas_is_filtered_independently(catalog, policy):
    visible = visible_schema(catalog, policy)
    assert "public.orders" in visible
    assert "secret.orders" not in visible


# -- what is kept ------------------------------------------------------------


def test_visible_columns_keep_their_types(catalog, policy):
    assert visible_schema(catalog, policy)["public.orders"]["amount"] == "NUMERIC"


def test_tables_are_emitted_in_catalog_order(catalog, policy):
    # Prompt stability matters for caching and for reproducible generations.
    assert list(visible_schema(catalog, policy)) == [
        "public.customers",
        "public.employees",
        "public.orders",
    ]


# -- rendering ---------------------------------------------------------------


def test_rendered_prompt_is_ddl_and_leaks_nothing(catalog, policy):
    prompt = render_schema_prompt(catalog, policy)
    assert "CREATE TABLE public.orders" in prompt
    for hidden in ("salary", "ssn", "tenant_id", "secret.orders", "internal_note"):
        assert hidden not in prompt


def test_rendered_prompt_keeps_column_types(catalog, policy):
    assert "amount NUMERIC" in render_schema_prompt(catalog, policy)


def test_rendered_prompt_is_empty_when_nothing_is_visible(catalog):
    assert render_schema_prompt(catalog, Policy.from_dict({})) == ""


def test_rendered_prompt_covers_every_visible_table(catalog, policy):
    prompt = render_schema_prompt(catalog, policy)
    for qualified in visible_schema(catalog, policy):
        assert f"CREATE TABLE {qualified} (" in prompt


def test_rendered_prompt_is_parseable_ddl(catalog, policy):
    # It is fed to a model as DDL, so it should be real DDL -- and it is the
    # same text Catalog.from_ddl consumes.
    rebuilt = Catalog.from_ddl([render_schema_prompt(catalog, policy)])
    assert [ref.qualified for ref in rebuilt.tables] == list(
        visible_schema(catalog, policy)
    )
