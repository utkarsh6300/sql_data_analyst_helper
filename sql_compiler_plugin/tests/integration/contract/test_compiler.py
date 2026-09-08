"""The compiler's public contract, end to end through every pass."""

from __future__ import annotations

import pytest
import sqlglot

from sql_compiler import (
    Catalog,
    CompilationRejected,
    ConfigurationError,
    Policy,
    PolicyProvider,
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


def test_pathologically_nested_input_is_rejected_not_crashed(compiler, policy):
    # A parenthesis bomb can blow sqlglot's recursion limit inside Pass 1
    # (parsing) before there is even a tree for Pass 2 to walk. This must
    # come back as an ordinary rejected CompileResult, the same way an
    # unanticipated failure in resolve()/authorize() already does -- not
    # propagate as a raw RecursionError.
    deeply_nested = "SELECT " + "(" * 3000 + "1" + ")" * 3000
    result = compiler.compile(deeply_nested, policy=policy)
    assert not result.ok
    assert result.sql is None
    assert result.violations[0].code == ViolationCode.INTERNAL_ERROR


def test_generation_failure_fails_closed_without_leaking_the_exception_text(
    compiler, policy, monkeypatch
):
    # Pass 5 (regenerating the validated tree back into SQL) is defensive
    # code and not expected to fail in practice, but if it ever does, the
    # exception text must be scrubbed exactly like _internal_error_violation
    # already scrubs it for Passes 3/4 -- not embedded raw the way
    # GENERATION_FAILED used to.
    from sql_compiler.ir import ResolvedQuery

    class ExplodingExpression:
        def sql(self, *_args, **_kwargs):
            raise RuntimeError(
                "SELECT ssn FROM secret_table -- simulated generator bug"
            )

    def fake_resolve(_statement, _catalog):
        return (
            ResolvedQuery(
                expression=ExplodingExpression(),
                base_tables=set(),
                column_refs=[],
                functions=[],
            ),
            [],
        )

    monkeypatch.setattr("sql_compiler.compiler.resolve", fake_resolve)
    result = compiler.compile("SELECT amount FROM orders", policy=policy)
    assert not result.ok
    assert result.violations[0].code == ViolationCode.GENERATION_FAILED
    assert result.violations[0].details == {"error_type": "RuntimeError"}
    assert "ssn" not in str(result.to_dict())
    assert "secret_table" not in str(result.to_dict())


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


class _ReturnsWrongType(PolicyProvider):
    """A deliberately buggy provider, for testing the type guard."""

    def resolve(self, subject):
        return {"not": "a Policy instance"}


def test_a_policy_provider_returning_the_wrong_type_fails_closed(catalog):
    # A buggy provider is the host's bug, not the query's -- it must raise
    # ConfigurationError, never silently proceed with a malformed object.
    compiler = SqlCompiler(catalog=catalog, policy_provider=_ReturnsWrongType())
    with pytest.raises(ConfigurationError, match="expected Policy"):
        compiler.compile("SELECT amount FROM orders", subject="analyst-1")


def test_subject_label_falls_back_to_the_compile_call_subject(catalog):
    # When the resolved Policy itself carries no subject, the label reported
    # on CompileResult falls back to whatever subject= the caller passed to
    # compile() -- every other fixture policy in this suite already sets
    # Policy.subject, so this path is otherwise never exercised.
    subjectless = Policy.from_dict(
        {"tables": {"public.orders": ["id", "amount"]}}
    )
    compiler = SqlCompiler(catalog=catalog)
    result = compiler.compile(
        "SELECT amount FROM orders", policy=subjectless, subject="caller-provided-id"
    )
    assert result.ok
    assert result.subject == "caller-provided-id"


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
