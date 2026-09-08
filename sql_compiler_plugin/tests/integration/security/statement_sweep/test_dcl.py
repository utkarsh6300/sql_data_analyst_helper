"""Access control: GRANT, REVOKE, SET ROLE, SECURITY LABEL, COMMENT,
REASSIGN OWNED. (DROP OWNED lives in test_drop.py with the other DROP *
statements.)

Split out of the full PostgreSQL statement sweep
(see tests/integration/security/ sibling files for the other command
families) so a failure in one family doesn't require scrolling past the
other ~170 parametrized cases to find it. See the module docstring in
git history of test_postgres_statement_sweep.py, or
docs/02-security-model.md, for why this sweep exists: it proves the
read-only pass rejects every PostgreSQL command that is not a pure read --
not by naming each command's AST node individually, but as a consequence of
`ALLOWED_ROOT_TYPES` in `passes/readonly.py` accepting only
Select/SetOperation/Subquery/Paren at the root.

Each statement is minimal, often-nonsensical SQL (placeholder object names
like `t1`, `role1`, `fn1`) -- the read-only pass runs before catalog
resolution and inspects AST node shape only, so nothing here needs to
reference a real object. Several of these statements don't even parse into
a dedicated sqlglot node (sqlglot falls back to a generic `Command`), which
is fine: `Command` is itself denied, and a `PARSE_ERROR` is just as much a
rejection as `NON_SELECT_STATEMENT` is. What matters, and what every case
below asserts, is that none of these commands ever reaches name resolution
or authorization -- reaching those passes would mean pass ordering was
violated, which is a correctness bug in this package regardless of what the
query does.
"""

from __future__ import annotations

import pytest

from sql_compiler import ViolationCode

pytestmark = [pytest.mark.integration, pytest.mark.security]


def codes(result):
    return {v.code for v in result.violations}


#: Codes that can only be produced by resolve() or authorize() (passes 3-4).
#: A non-SELECT statement reaching one of these means the read-only pass
#: (pass 2) failed to stop it first -- itself a bug, independent of whether
#: the specific statement here happens to be harmless.
POST_READONLY_CODES = {
    ViolationCode.UNKNOWN_TABLE,
    ViolationCode.NAME_RESOLUTION_FAILED,
    ViolationCode.NATURAL_JOIN_NOT_SUPPORTED,
    ViolationCode.TABLE_ACCESS_DENIED,
    ViolationCode.COLUMN_ACCESS_DENIED,
    ViolationCode.FUNCTION_NOT_ALLOWED,
}

DCL_STATEMENTS = {
    "GRANT": "GRANT SELECT ON t1 TO role1",
    "REVOKE": "REVOKE SELECT ON t1 FROM role1",
    "SET ROLE": "SET ROLE role1",
    "SET SESSION AUTHORIZATION": "SET SESSION AUTHORIZATION user1",
    "SECURITY LABEL": "SECURITY LABEL ON TABLE t1 IS 'label1'",
    "COMMENT": "COMMENT ON TABLE t1 IS 'hello'",
    "REASSIGN OWNED": "REASSIGN OWNED BY role1 TO role2",
}


@pytest.mark.parametrize(
    "sql", list(DCL_STATEMENTS.values()), ids=list(DCL_STATEMENTS.keys())
)
def test_dcl_statement_never_reaches_resolution_or_authorization(sql, compiler, policy):
    result = compiler.compile(sql, policy=policy)
    assert not result.ok, f"{sql!r} was accepted; it must be a pure read to pass"
    assert result.sql is None
    reached = codes(result) & POST_READONLY_CODES
    assert not reached, (
        f"{sql!r} was rejected for {reached}, which only resolve()/authorize() "
        "produce -- the read-only pass should have stopped it first"
    )
