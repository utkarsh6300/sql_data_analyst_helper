"""The filtered schema and the compiler must agree.

Two components decide independently what a subject may read: the schema filter
that builds the prompt, and the authorization pass that judges the result.  If
they disagree in one direction the prompt advertises columns that will be
rejected -- avoidable rejections and a model that looks broken.  If they
disagree in the other, the compiler accepts something the prompt was trying to
hide, which is the direction that matters.
"""

from __future__ import annotations

import pytest

from sql_compiler import Catalog, Policy, render_schema_prompt, visible_schema

pytestmark = pytest.mark.integration


def test_everything_the_prompt_advertises_compiles(catalog, policy, compiler):
    for qualified, columns in visible_schema(catalog, policy).items():
        column_list = ", ".join(columns)
        result = compiler.compile(f"SELECT {column_list} FROM {qualified}", policy=policy)
        assert result.ok, (qualified, result.violations)


def test_a_star_over_an_advertised_table_compiles_only_if_all_of_it_is_visible(
    catalog, policy, compiler
):
    # The prompt shows a subset of employees' columns, so `SELECT *` on it must
    # still be rejected -- the filter narrows the prompt, it does not widen the
    # grant.
    visible = visible_schema(catalog, policy)
    assert set(visible["public.employees"]) != set(
        catalog.columns(catalog.ref("public.employees"))
    )
    assert not compiler.compile("SELECT * FROM employees", policy=policy).ok


def test_nothing_the_prompt_hides_can_be_compiled(catalog, policy, compiler):
    visible = visible_schema(catalog, policy)

    for ref in catalog.tables:
        advertised = visible.get(ref.qualified, {})
        for column in catalog.columns(ref):
            if column in advertised:
                continue
            result = compiler.compile(
                f"SELECT {column} FROM {ref.qualified}", policy=policy
            )
            assert not result.ok, (ref.qualified, column)


def test_a_prompt_rebuilt_into_a_catalog_grants_nothing_extra(catalog, policy):
    # A host may feed the rendered DDL back through Catalog.from_ddl. Doing so
    # must not turn the filtered view into a wider grant.
    from sql_compiler import SqlCompiler

    narrowed = Catalog.from_ddl([render_schema_prompt(catalog, policy)])
    compiler = SqlCompiler(catalog=narrowed)

    assert compiler.compile("SELECT amount FROM orders", policy=policy).ok
    assert not compiler.compile("SELECT salary FROM employees", policy=policy).ok
    assert not compiler.compile("SELECT id FROM secret.orders", policy=policy).ok


def test_an_empty_grant_advertises_nothing_and_compiles_nothing(catalog, compiler):
    empty = Policy.from_dict({})
    assert render_schema_prompt(catalog, empty) == ""
    assert not compiler.compile("SELECT id FROM orders", policy=empty).ok
