"""ALTER * statements.

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

ALTER_STATEMENTS = {
    "ALTER TABLE": "ALTER TABLE t1 ADD COLUMN c2 INT",
    "ALTER VIEW": "ALTER VIEW v1 RENAME TO v2",
    "ALTER MATERIALIZED VIEW": "ALTER MATERIALIZED VIEW mv1 RENAME TO mv2",
    "ALTER INDEX": "ALTER INDEX idx1 RENAME TO idx2",
    "ALTER FOREIGN TABLE": "ALTER FOREIGN TABLE ftab1 ADD COLUMN c1 INT",
    "ALTER SCHEMA": "ALTER SCHEMA sch1 OWNER TO role1",
    "ALTER DATABASE": "ALTER DATABASE db1 RENAME TO db2",
    "ALTER TABLESPACE": "ALTER TABLESPACE ts1 OWNER TO role1",
    "ALTER TYPE": "ALTER TYPE type1 OWNER TO role1",
    "ALTER DOMAIN": "ALTER DOMAIN dom1 SET NOT NULL",
    "ALTER SEQUENCE": "ALTER SEQUENCE seq1 RESTART WITH 100",
    "ALTER FUNCTION": "ALTER FUNCTION fn1() OWNER TO role1",
    "ALTER PROCEDURE": "ALTER PROCEDURE proc1() OWNER TO role1",
    "ALTER ROUTINE": "ALTER ROUTINE routine1() OWNER TO role1",
    "ALTER TRIGGER": "ALTER TRIGGER trig1 ON t1 RENAME TO trig2",
    "ALTER EVENT TRIGGER": "ALTER EVENT TRIGGER trig1 DISABLE",
    "ALTER RULE": "ALTER RULE rule1 ON t1 RENAME TO rule2",
    "ALTER OPERATOR": "ALTER OPERATOR === (int, int) OWNER TO role1",
    "ALTER OPERATOR CLASS": "ALTER OPERATOR CLASS opc1 USING btree OWNER TO role1",
    "ALTER OPERATOR FAMILY": "ALTER OPERATOR FAMILY opf1 USING btree OWNER TO role1",
    "ALTER AGGREGATE": "ALTER AGGREGATE agg1(int) OWNER TO role1",
    "ALTER COLLATION": "ALTER COLLATION col1 OWNER TO role1",
    "ALTER CONVERSION": "ALTER CONVERSION conv1 OWNER TO role1",
    "ALTER STATISTICS": "ALTER STATISTICS stat1 OWNER TO role1",
    "ALTER LANGUAGE": "ALTER LANGUAGE lang1 OWNER TO role1",
    "ALTER EXTENSION": "ALTER EXTENSION ext1 UPDATE",
    "ALTER TEXT SEARCH CONFIGURATION": "ALTER TEXT SEARCH CONFIGURATION cfg1 OWNER TO role1",
    "ALTER TEXT SEARCH DICTIONARY": "ALTER TEXT SEARCH DICTIONARY dict1 OWNER TO role1",
    "ALTER TEXT SEARCH PARSER": "ALTER TEXT SEARCH PARSER parser1 RENAME TO parser2",
    "ALTER TEXT SEARCH TEMPLATE": "ALTER TEXT SEARCH TEMPLATE tmpl1 RENAME TO tmpl2",
    "ALTER FOREIGN DATA WRAPPER": "ALTER FOREIGN DATA WRAPPER fdw1 OWNER TO role1",
    "ALTER SERVER": "ALTER SERVER srv1 OWNER TO role1",
    "ALTER USER MAPPING": "ALTER USER MAPPING FOR user1 SERVER srv1 OPTIONS (SET opt 'val')",
    "ALTER PUBLICATION": "ALTER PUBLICATION pub1 OWNER TO role1",
    "ALTER SUBSCRIPTION": "ALTER SUBSCRIPTION sub1 OWNER TO role1",
    "ALTER DEFAULT PRIVILEGES": "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO role1",
    "ALTER ROLE": "ALTER ROLE role1 WITH PASSWORD 'x'",
    "ALTER USER": "ALTER USER user1 WITH PASSWORD 'x'",
    "ALTER GROUP": "ALTER GROUP grp1 ADD USER user1",
    "ALTER POLICY": "ALTER POLICY pol1 ON t1 RENAME TO pol2",
    "ALTER LARGE OBJECT": "ALTER LARGE OBJECT 12345 OWNER TO role1",
    "ALTER SYSTEM": "ALTER SYSTEM SET work_mem = '64MB'",
}


@pytest.mark.parametrize(
    "sql", list(ALTER_STATEMENTS.values()), ids=list(ALTER_STATEMENTS.keys())
)
def test_alter_statement_never_reaches_resolution_or_authorization(sql, compiler, policy):
    result = compiler.compile(sql, policy=policy)
    assert not result.ok, f"{sql!r} was accepted; it must be a pure read to pass"
    assert result.sql is None
    reached = codes(result) & POST_READONLY_CODES
    assert not reached, (
        f"{sql!r} was rejected for {reached}, which only resolve()/authorize() "
        "produce -- the read-only pass should have stopped it first"
    )
