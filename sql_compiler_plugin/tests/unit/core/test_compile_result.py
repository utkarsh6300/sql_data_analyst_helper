"""The result object, exercised without running a compilation.

``CompileResult`` is the whole interface between the compiler and the host: it
decides what a caller may execute, what an audit log records, and what the
repair loop is told.  Those are worth pinning down independently of the passes
that populate them.
"""

from __future__ import annotations

import json

import pytest

from sql_compiler import CompilationRejected, RepairAction, Violation, ViolationCode
from sql_compiler.compiler import CompileResult

pytestmark = pytest.mark.unit


DENIED = Violation(
    code=ViolationCode.COLUMN_ACCESS_DENIED,
    message="Access to column 'salary' of table 'public.employees' is not permitted.",
    action=RepairAction.REMOVE_COLUMN,
    table="public.employees",
    column="salary",
)


def accepted(**kwargs) -> CompileResult:
    return CompileResult(ok=True, sql='SELECT "id" FROM "public"."orders"', **kwargs)


def rejected(*violations) -> CompileResult:
    return CompileResult(ok=False, violations=list(violations) or [DENIED])


# -- ok and sql move together ------------------------------------------------


def test_truthiness_follows_ok():
    # `if result:` is the documented guard, so it must never disagree with ok.
    assert accepted()
    assert not rejected()


def test_a_fresh_rejection_carries_no_sql():
    assert rejected().sql is None


def test_raise_for_violations_raises_only_when_rejected():
    assert accepted().raise_for_violations() is not None
    with pytest.raises(CompilationRejected) as excinfo:
        rejected().raise_for_violations()
    assert excinfo.value.violations[0].code == ViolationCode.COLUMN_ACCESS_DENIED


def test_raise_for_violations_returns_the_same_result():
    result = accepted()
    assert result.raise_for_violations() is result


# -- to_dict -----------------------------------------------------------------


def test_to_dict_always_reports_ok_and_violations():
    payload = rejected().to_dict()
    assert payload["ok"] is False
    assert payload["violations"][0]["code"] == "COLUMN_ACCESS_DENIED"


def test_to_dict_omits_the_fields_that_are_unset():
    payload = CompileResult(ok=False).to_dict()
    assert set(payload) == {"ok", "violations"}


def test_to_dict_includes_audit_fields_when_present():
    payload = accepted(
        tables=["public.orders"],
        columns=["public.orders.id"],
        subject="analyst-1",
    ).to_dict()
    assert payload["sql"].startswith("SELECT")
    assert payload["tables"] == ["public.orders"]
    assert payload["columns"] == ["public.orders.id"]
    assert payload["subject"] == "analyst-1"


def test_to_dict_is_json_serializable():
    payload = rejected().to_dict()
    assert json.loads(json.dumps(payload))["ok"] is False


# -- repair_prompt -----------------------------------------------------------


def test_repair_prompt_is_empty_on_success():
    # A non-empty prompt on success would send a repair loop round again for
    # no reason.
    assert accepted().repair_prompt() == ""


def test_repair_prompt_names_the_code_and_the_target():
    prompt = rejected().repair_prompt()
    assert "COLUMN_ACCESS_DENIED" in prompt
    assert "(salary)" in prompt


def test_repair_prompt_lists_every_violation():
    prompt = rejected(
        DENIED,
        Violation(
            code=ViolationCode.TABLE_ACCESS_DENIED,
            message="Access to table 'secret.orders' is not permitted.",
            action=RepairAction.REMOVE_TABLE,
            table="secret.orders",
        ),
    ).repair_prompt()
    assert "COLUMN_ACCESS_DENIED" in prompt
    assert "TABLE_ACCESS_DENIED" in prompt
    # One header plus one line per violation.
    assert len(prompt.splitlines()) == 3


def test_repair_prompt_prefers_the_most_specific_target():
    prompt = rejected(
        Violation(
            code=ViolationCode.COLUMN_ACCESS_DENIED,
            message="denied",
            table="public.employees",
            column="salary",
            function="AVG",
        )
    ).repair_prompt()
    assert "(salary)" in prompt


def test_repair_prompt_handles_a_violation_with_no_target():
    prompt = rejected(
        Violation(code=ViolationCode.PARSE_ERROR, message="The query is not valid SQL.")
    ).repair_prompt()
    assert "PARSE_ERROR:" in prompt
    assert "()" not in prompt


def test_repair_prompt_does_not_echo_the_rejected_sql():
    # The prompt goes back to the model; the SQL it already sent adds nothing
    # and the violation messages are the deliberately non-disclosing part.
    result = rejected()
    result.sql = "SELECT salary FROM employees"
    assert "SELECT salary FROM employees" not in result.repair_prompt()
