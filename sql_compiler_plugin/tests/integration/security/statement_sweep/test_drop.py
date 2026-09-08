"""DROP * statements.

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

DROP_STATEMENTS = {
    "DROP TABLE": "DROP TABLE t1",
    "DROP VIEW": "DROP VIEW v1",
    "DROP MATERIALIZED VIEW": "DROP MATERIALIZED VIEW mv1",
    "DROP INDEX": "DROP INDEX idx1",
    "DROP FOREIGN TABLE": "DROP FOREIGN TABLE ftab1",
    "DROP SCHEMA": "DROP SCHEMA sch1",
    "DROP DATABASE": "DROP DATABASE db1",
    "DROP TABLESPACE": "DROP TABLESPACE ts1",
    "DROP TYPE": "DROP TYPE type1",
    "DROP DOMAIN": "DROP DOMAIN dom1",
    "DROP SEQUENCE": "DROP SEQUENCE seq1",
    "DROP FUNCTION": "DROP FUNCTION fn1()",
    "DROP PROCEDURE": "DROP PROCEDURE proc1()",
    "DROP ROUTINE": "DROP ROUTINE routine1()",
    "DROP TRIGGER": "DROP TRIGGER trig1 ON t1",
    "DROP EVENT TRIGGER": "DROP EVENT TRIGGER trig1",
    "DROP RULE": "DROP RULE rule1 ON t1",
    "DROP OPERATOR": "DROP OPERATOR === (int, int)",
    "DROP OPERATOR CLASS": "DROP OPERATOR CLASS opc1 USING btree",
    "DROP OPERATOR FAMILY": "DROP OPERATOR FAMILY opf1 USING btree",
    "DROP CAST": "DROP CAST (int AS text)",
    "DROP AGGREGATE": "DROP AGGREGATE agg1(int)",
    "DROP TRANSFORM": "DROP TRANSFORM FOR int LANGUAGE lang1",
    "DROP ACCESS METHOD": "DROP ACCESS METHOD am1",
    "DROP COLLATION": "DROP COLLATION col1",
    "DROP CONVERSION": "DROP CONVERSION conv1",
    "DROP STATISTICS": "DROP STATISTICS stat1",
    "DROP LANGUAGE": "DROP LANGUAGE lang1",
    "DROP EXTENSION": "DROP EXTENSION ext1",
    "DROP TEXT SEARCH CONFIGURATION": "DROP TEXT SEARCH CONFIGURATION cfg1",
    "DROP TEXT SEARCH DICTIONARY": "DROP TEXT SEARCH DICTIONARY dict1",
    "DROP TEXT SEARCH PARSER": "DROP TEXT SEARCH PARSER parser1",
    "DROP TEXT SEARCH TEMPLATE": "DROP TEXT SEARCH TEMPLATE tmpl1",
    "DROP FOREIGN DATA WRAPPER": "DROP FOREIGN DATA WRAPPER fdw1",
    "DROP SERVER": "DROP SERVER srv1",
    "DROP USER MAPPING": "DROP USER MAPPING FOR user1 SERVER srv1",
    "DROP PUBLICATION": "DROP PUBLICATION pub1",
    "DROP SUBSCRIPTION": "DROP SUBSCRIPTION sub1",
    "DROP ROLE": "DROP ROLE role1",
    "DROP USER": "DROP USER user1",
    "DROP GROUP": "DROP GROUP grp1",
    "DROP POLICY": "DROP POLICY pol1 ON t1",
    "DROP OWNED": "DROP OWNED BY role1",
}


@pytest.mark.parametrize(
    "sql", list(DROP_STATEMENTS.values()), ids=list(DROP_STATEMENTS.keys())
)
def test_drop_statement_never_reaches_resolution_or_authorization(sql, compiler, policy):
    result = compiler.compile(sql, policy=policy)
    assert not result.ok, f"{sql!r} was accepted; it must be a pure read to pass"
    assert result.sql is None
    reached = codes(result) & POST_READONLY_CODES
    assert not reached, (
        f"{sql!r} was rejected for {reached}, which only resolve()/authorize() "
        "produce -- the read-only pass should have stopped it first"
    )
