"""The compiler's public contract, end to end through every pass."""

from __future__ import annotations

import pytest
import sqlglot

from sql_compiler import (
    Catalog,
    CompilationRejected,
    ConfigurationError,
    Policy,
    RepairAction,
    SqlCompiler,
    StaticPolicyProvider,
    ViolationCode,
    compile_sql,
)

pytestmark = pytest.mark.integration


# -- the execute-only-what-you-regenerated rule ------------------------------


def test_output_is_regenerated_from_the_tree_not_the_input(compiler, policy):
    result = compiler.compile("select o.amount from orders o", policy=policy)
    assert result.ok
    # Fully qualified, quoted, aliased -- structurally different from the
    # input, which proves it came from the AST rather than the string.
    assert result.sql != "select o.amount from orders o"
    assert '"public"."orders"' in result.sql


def test_output_is_stable_under_recompilation(compiler, policy):
    once = compiler.compile("SELECT amount FROM orders", policy=policy).sql
    twice = compiler.compile(once, policy=policy).sql
    assert once == twice


def test_output_reparses_cleanly(compiler, policy):
    result = compiler.compile("SELECT amount FROM orders", policy=policy)
    assert sqlglot.parse_one(result.sql, dialect="postgres") is not None


def test_rejected_queries_never_carry_sql(compiler, policy):
    result = compiler.compile("SELECT salary FROM employees", policy=policy)
    assert not result.ok
    assert result.sql is None


def test_result_is_falsey_when_rejected(compiler, policy):
    assert not compiler.compile("SELECT salary FROM employees", policy=policy)
    assert compiler.compile("SELECT amount FROM orders", policy=policy)


# -- error surfaces ----------------------------------------------------------


def test_compile_or_raise_returns_sql_on_success(compiler, policy):
    assert '"public"."orders"' in compiler.compile_or_raise(
        "SELECT amount FROM orders", policy=policy
    )


def test_compile_or_raise_raises_with_violations(compiler, policy):
    with pytest.raises(CompilationRejected) as excinfo:
        compiler.compile_or_raise("SELECT salary FROM employees", policy=policy)
    assert excinfo.value.violations[0].code == ViolationCode.COLUMN_ACCESS_DENIED


def test_missing_catalog_is_a_configuration_error(policy):
    with pytest.raises(ConfigurationError, match="no catalog"):
        SqlCompiler().compile("SELECT 1", policy=policy)


def test_missing_policy_is_a_configuration_error(catalog):
    with pytest.raises(ConfigurationError, match="no policy"):
        SqlCompiler(catalog=catalog).compile("SELECT 1")


def test_provider_without_subject_is_a_configuration_error(catalog, policy):
    compiler = SqlCompiler(
        catalog=catalog, policy_provider=StaticPolicyProvider({"u": policy})
    )
    with pytest.raises(ConfigurationError, match="subject is required"):
        compiler.compile("SELECT amount FROM orders")


def test_unknown_subject_is_a_configuration_error_not_a_denial(catalog, policy):
    # Reporting a wiring bug as "access denied" hides the bug.
    compiler = SqlCompiler(
        catalog=catalog, policy_provider=StaticPolicyProvider({"u": policy})
    )
    with pytest.raises(ConfigurationError):
        compiler.compile("SELECT amount FROM orders", subject="nobody")


def test_empty_catalog_is_reported_not_silently_permissive(policy):
    compiler = SqlCompiler(catalog=Catalog.from_dict({}))
    result = compiler.compile("SELECT amount FROM orders", policy=policy)
    assert not result.ok
    assert result.violations[0].code == ViolationCode.EMPTY_CATALOG


def test_an_unexpected_resolve_failure_fails_closed_not_crashed(compiler, policy, monkeypatch):
    # A bug in a pass must never reach the caller as a raw exception -- it
    # must come back as an ordinary rejected CompileResult, the same way a
    # malformed FROM-clause expression once escaped uncaught.
    def boom(*_args, **_kwargs):
        raise RuntimeError("SELECT ssn FROM secret_table -- simulated internal bug")

    monkeypatch.setattr("sql_compiler.compiler.resolve", boom)
    result = compiler.compile("SELECT amount FROM orders", policy=policy)
    assert not result.ok
    assert result.violations[0].code == ViolationCode.INTERNAL_ERROR
    assert result.violations[0].action == RepairAction.NOT_REPAIRABLE
    assert result.violations[0].details == {"error_type": "RuntimeError"}
    # The exception message must never reach the caller: it can carry a
    # fragment of the query, or worse.
    assert "ssn" not in str(result.to_dict())
    assert "secret_table" not in str(result.to_dict())


def test_an_unexpected_authorize_failure_fails_closed_not_crashed(compiler, policy, monkeypatch):
    def boom(*_args, **_kwargs):
        raise RuntimeError("SELECT ssn FROM secret_table -- simulated internal bug")

    monkeypatch.setattr("sql_compiler.compiler.authorize", boom)
    result = compiler.compile("SELECT amount FROM orders", policy=policy)
    assert not result.ok
    assert result.violations[0].code == ViolationCode.INTERNAL_ERROR
    assert "ssn" not in str(result.to_dict())


# -- policy resolution -------------------------------------------------------


def test_policy_provider_resolves_by_subject(catalog, policy):
    compiler = SqlCompiler(
        catalog=catalog, policy_provider=StaticPolicyProvider({"analyst-1": policy})
    )
    result = compiler.compile("SELECT amount FROM orders", subject="analyst-1")
    assert result.ok
    assert result.subject == "analyst-1"


def test_explicit_policy_wins_over_the_provider(catalog, policy):
    empty = Policy.from_dict({})
    compiler = SqlCompiler(
        catalog=catalog, policy_provider=StaticPolicyProvider({"analyst-1": policy})
    )
    result = compiler.compile(
        "SELECT amount FROM orders", policy=empty, subject="analyst-1"
    )
    assert not result.ok


def test_catalog_can_be_overridden_per_call(compiler, policy):
    other = Catalog.from_dict({"public.orders": ["id", "customer_id", "amount"]})
    assert compiler.compile("SELECT amount FROM orders", policy=policy, catalog=other).ok


# -- audit and repair --------------------------------------------------------


def test_accepted_query_reports_what_it_reads(compiler, policy):
    result = compiler.compile(
        "SELECT c.name, o.amount FROM orders o JOIN customers c ON c.id = o.customer_id",
        policy=policy,
    )
    assert result.tables == ["public.customers", "public.orders"]
    assert "public.orders.amount" in result.columns
    assert "public.customers.name" in result.columns


def test_rejected_query_still_reports_what_it_attempted(compiler, policy):
    # An access denial is exactly the event an audit log needs details for.
    result = compiler.compile("SELECT salary FROM employees", policy=policy)
    assert not result.ok
    assert result.tables == ["public.employees"]


def test_all_violations_are_collected_not_just_the_first(compiler, policy):
    # A repair loop that learns one problem per round trip converges slowly.
    result = compiler.compile(
        "SELECT salary, ssn FROM employees", policy=policy
    )
    assert {v.column for v in result.violations} == {"salary", "ssn"}


def test_repair_prompt_names_codes_and_is_empty_on_success(compiler, policy):
    assert compiler.compile("SELECT amount FROM orders", policy=policy).repair_prompt() == ""
    prompt = compiler.compile("SELECT salary FROM employees", policy=policy).repair_prompt()
    assert "COLUMN_ACCESS_DENIED" in prompt


def test_denied_table_does_not_also_enumerate_its_columns(compiler, policy):
    # Listing the columns of a table the subject cannot see would confirm
    # which columns exist on it.
    result = compiler.compile("SELECT internal_note FROM secret.orders", policy=policy)
    assert {v.code for v in result.violations} == {ViolationCode.TABLE_ACCESS_DENIED}


def test_result_serializes_to_json_safe_data(compiler, policy):
    import json

    payload = compiler.compile("SELECT salary FROM employees", policy=policy).to_dict()
    assert json.loads(json.dumps(payload))["ok"] is False


# -- convenience wrapper -----------------------------------------------------


def test_compile_sql_wrapper(catalog, policy):
    assert compile_sql("SELECT amount FROM orders", catalog=catalog, policy=policy).ok
