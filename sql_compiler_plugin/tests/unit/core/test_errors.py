"""Diagnostics: violation codes, repair actions and exception types.

Codes are part of the public contract -- hosts and the LLM repair loop switch
on them -- and violation payloads travel back to callers, so both the shape and
what they refuse to carry are tested here.
"""

from __future__ import annotations

import json

import pytest

from sql_compiler import (
    CompilationRejected,
    ConfigurationError,
    RepairAction,
    SqlCompilerError,
    Violation,
    ViolationCode,
)

pytestmark = pytest.mark.unit


# -- the code and action enums -----------------------------------------------


def test_codes_are_plain_strings():
    # Hosts compare against literals and serialize without a custom encoder.
    assert ViolationCode.PARSE_ERROR == "PARSE_ERROR"
    assert json.dumps(ViolationCode.PARSE_ERROR.value) == '"PARSE_ERROR"'


def test_code_names_and_values_match():
    # A code whose value drifts from its name breaks every host switching on
    # the string form.
    for code in ViolationCode:
        assert code.value == code.name


def test_action_names_and_values_match():
    for action in RepairAction:
        assert action.value == action.name


def test_every_pass_has_at_least_one_code():
    # A pass with no way to report failure would have to fail silently.
    expected = {
        "PARSE_ERROR",
        "EMPTY_STATEMENT",
        "MULTIPLE_STATEMENTS",
        "NON_SELECT_STATEMENT",
        "FORBIDDEN_EXPRESSION",
        "EMPTY_CATALOG",
        "UNKNOWN_TABLE",
        "NAME_RESOLUTION_FAILED",
        "TABLE_ACCESS_DENIED",
        "COLUMN_ACCESS_DENIED",
        "FUNCTION_NOT_ALLOWED",
        "GENERATION_FAILED",
    }
    assert expected <= {code.value for code in ViolationCode}


# -- Violation ---------------------------------------------------------------


def test_defaults_to_rewrite_query():
    assert Violation(code=ViolationCode.PARSE_ERROR, message="x").action == (
        RepairAction.REWRITE_QUERY
    )


def test_to_dict_carries_code_message_and_action_as_strings():
    payload = Violation(
        code=ViolationCode.TABLE_ACCESS_DENIED,
        message="denied",
        action=RepairAction.REMOVE_TABLE,
    ).to_dict()
    assert payload == {
        "code": "TABLE_ACCESS_DENIED",
        "message": "denied",
        "action": "REMOVE_TABLE",
    }


def test_to_dict_omits_absent_targets():
    # An explicit null table/column would read as "no table" rather than "not
    # applicable" on the far side of an HTTP boundary.
    payload = Violation(code=ViolationCode.PARSE_ERROR, message="x").to_dict()
    assert "table" not in payload
    assert "column" not in payload
    assert "function" not in payload


def test_to_dict_includes_the_targets_that_are_set():
    payload = Violation(
        code=ViolationCode.COLUMN_ACCESS_DENIED,
        message="x",
        table="public.employees",
        column="salary",
        function="AVG",
    ).to_dict()
    assert payload["table"] == "public.employees"
    assert payload["column"] == "salary"
    assert payload["function"] == "AVG"


def test_to_dict_omits_empty_details_and_copies_the_rest():
    assert "details" not in Violation(code=ViolationCode.PARSE_ERROR, message="x").to_dict()

    details = {"parser_message": "line 1"}
    payload = Violation(
        code=ViolationCode.PARSE_ERROR, message="x", details=details
    ).to_dict()
    assert payload["details"] == details
    payload["details"]["parser_message"] = "mutated"
    assert details["parser_message"] == "line 1"


def test_to_dict_is_json_serializable():
    payload = Violation(
        code=ViolationCode.UNKNOWN_TABLE,
        message="x",
        action=RepairAction.REMOVE_TABLE,
        table="public.orders",
        details={"count": 2},
    ).to_dict()
    assert json.loads(json.dumps(payload))["code"] == "UNKNOWN_TABLE"


def test_violations_are_immutable():
    violation = Violation(code=ViolationCode.PARSE_ERROR, message="x")
    with pytest.raises(Exception):
        violation.message = "y"  # type: ignore[misc]


def test_str_names_the_code():
    text = str(Violation(code=ViolationCode.PARSE_ERROR, message="broken"))
    assert "PARSE_ERROR" in text
    assert "broken" in text


# -- exceptions --------------------------------------------------------------


def test_everything_shares_one_base_class():
    # Hosts wrap the compiler in a single except clause.
    assert issubclass(CompilationRejected, SqlCompilerError)
    assert issubclass(ConfigurationError, SqlCompilerError)
    assert issubclass(SqlCompilerError, Exception)


def test_configuration_error_is_not_a_rejection():
    # A wiring bug reported as "access denied" hides the bug.
    assert not issubclass(ConfigurationError, CompilationRejected)
    assert not issubclass(CompilationRejected, ConfigurationError)


def test_rejection_carries_its_violations():
    violations = [
        Violation(code=ViolationCode.COLUMN_ACCESS_DENIED, message="a"),
        Violation(code=ViolationCode.TABLE_ACCESS_DENIED, message="b"),
    ]
    error = CompilationRejected(violations)
    assert error.violations == violations


def test_rejection_copies_the_list_it_was_given():
    violations = [Violation(code=ViolationCode.PARSE_ERROR, message="a")]
    error = CompilationRejected(violations)
    violations.clear()
    assert len(error.violations) == 1


def test_rejection_message_summarizes_every_violation():
    error = CompilationRejected(
        [
            Violation(code=ViolationCode.COLUMN_ACCESS_DENIED, message="a"),
            Violation(code=ViolationCode.TABLE_ACCESS_DENIED, message="b"),
        ]
    )
    assert "COLUMN_ACCESS_DENIED" in str(error)
    assert "TABLE_ACCESS_DENIED" in str(error)


def test_rejection_with_no_violations_still_has_a_message():
    assert str(CompilationRejected([])) == "query rejected"


def test_rejection_to_dict_is_json_serializable():
    payload = CompilationRejected(
        [Violation(code=ViolationCode.PARSE_ERROR, message="a")]
    ).to_dict()
    assert json.loads(json.dumps(payload)) == {
        "violations": [
            {"code": "PARSE_ERROR", "message": "a", "action": "REWRITE_QUERY"}
        ]
    }


# -- first_line ---------------------------------------------------------


from sql_compiler.errors import first_line


def test_first_line_takes_only_the_first_line():
    assert first_line("first\nsecond\nthird") == "first"


def test_first_line_strips_surrounding_whitespace():
    assert first_line("  padded message  ") == "padded message"


def test_first_line_truncates_at_200_characters():
    assert first_line("x" * 300) == "x" * 200


def test_first_line_of_empty_string_is_empty_not_a_crash():
    assert first_line("") == ""


def test_first_line_of_whitespace_only_is_empty_not_a_crash():
    assert first_line("   \n\t  ") == ""
