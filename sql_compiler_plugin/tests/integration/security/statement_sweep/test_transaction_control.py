"""Transaction control: ABORT, BEGIN, COMMIT, ROLLBACK, SAVEPOINT,
two-phase commit, LOCK.

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

TRANSACTION_CONTROL_STATEMENTS = {
    "ABORT": "ABORT",
    "BEGIN": "BEGIN",
    "START TRANSACTION": "START TRANSACTION",
    "COMMIT": "COMMIT",
    "END": "END",
    "ROLLBACK": "ROLLBACK",
    "SAVEPOINT": "SAVEPOINT sp1",
    "RELEASE SAVEPOINT": "RELEASE SAVEPOINT sp1",
    "ROLLBACK TO SAVEPOINT": "ROLLBACK TO SAVEPOINT sp1",
    "SET TRANSACTION": "SET TRANSACTION READ ONLY",
    "SET CONSTRAINTS": "SET CONSTRAINTS ALL DEFERRED",
    "PREPARE TRANSACTION": "PREPARE TRANSACTION 'txn1'",
    "COMMIT PREPARED": "COMMIT PREPARED 'txn1'",
    "ROLLBACK PREPARED": "ROLLBACK PREPARED 'txn1'",
    "LOCK": "LOCK TABLE t1",
}


@pytest.mark.parametrize(
    "sql", list(TRANSACTION_CONTROL_STATEMENTS.values()), ids=list(TRANSACTION_CONTROL_STATEMENTS.keys())
)
def test_transaction_control_statement_never_reaches_resolution_or_authorization(sql, compiler, policy):
    result = compiler.compile(sql, policy=policy)
    assert not result.ok, f"{sql!r} was accepted; it must be a pure read to pass"
    assert result.sql is None
    reached = codes(result) & POST_READONLY_CODES
    assert not reached, (
        f"{sql!r} was rejected for {reached}, which only resolve()/authorize() "
        "produce -- the read-only pass should have stopped it first"
    )
