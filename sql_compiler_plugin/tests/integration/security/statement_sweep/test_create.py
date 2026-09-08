"""CREATE * statements.

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

CREATE_STATEMENTS = {
    "CREATE TABLE": "CREATE TABLE t2 (c1 INT)",
    "CREATE TABLE AS": "CREATE TABLE t2 AS SELECT * FROM t1",
    "CREATE VIEW": "CREATE VIEW v1 AS SELECT 1",
    "CREATE MATERIALIZED VIEW": "CREATE MATERIALIZED VIEW mv1 AS SELECT 1",
    "CREATE INDEX": "CREATE INDEX idx1 ON t1 (c1)",
    "CREATE FOREIGN TABLE": "CREATE FOREIGN TABLE ftab1 (c1 INT) SERVER srv1",
    "CREATE SCHEMA": "CREATE SCHEMA sch1",
    "CREATE DATABASE": "CREATE DATABASE db1",
    "CREATE TABLESPACE": "CREATE TABLESPACE ts1 LOCATION '/data'",
    "CREATE TYPE": "CREATE TYPE type1 AS (c1 INT)",
    "CREATE DOMAIN": "CREATE DOMAIN dom1 AS INT",
    "CREATE SEQUENCE": "CREATE SEQUENCE seq1",
    "CREATE FUNCTION": "CREATE FUNCTION fn1() RETURNS INT AS 'SELECT 1' LANGUAGE SQL",
    "CREATE PROCEDURE": "CREATE PROCEDURE proc1() AS 'BEGIN END' LANGUAGE plpgsql",
    "CREATE TRIGGER": "CREATE TRIGGER trig1 BEFORE INSERT ON t1 EXECUTE FUNCTION fn1()",
    "CREATE EVENT TRIGGER": "CREATE EVENT TRIGGER trig1 ON ddl_command_start EXECUTE FUNCTION fn1()",
    "CREATE RULE": "CREATE RULE rule1 AS ON INSERT TO t1 DO NOTHING",
    "CREATE OPERATOR": "CREATE OPERATOR === (LEFTARG = int, RIGHTARG = int, FUNCTION = fn1)",
    "CREATE OPERATOR CLASS": "CREATE OPERATOR CLASS opc1 FOR TYPE int USING btree AS STORAGE int",
    "CREATE OPERATOR FAMILY": "CREATE OPERATOR FAMILY opf1 USING btree",
    "CREATE CAST": "CREATE CAST (int AS text) WITH FUNCTION fn1(int)",
    "CREATE AGGREGATE": "CREATE AGGREGATE agg1(int) (SFUNC = sfunc1, STYPE = int)",
    "CREATE TRANSFORM": "CREATE TRANSFORM FOR int LANGUAGE lang1 (FROM SQL WITH FUNCTION fn1(internal), TO SQL WITH FUNCTION fn2(int))",
    "CREATE ACCESS METHOD": "CREATE ACCESS METHOD am1 TYPE INDEX HANDLER am_handler",
    "CREATE COLLATION": "CREATE COLLATION col1 (LOCALE = 'en_US')",
    "CREATE CONVERSION": "CREATE CONVERSION conv1 FOR 'UTF8' TO 'LATIN1' FROM fn1",
    "CREATE STATISTICS": "CREATE STATISTICS stat1 ON c1, id FROM t1",
    "CREATE LANGUAGE": "CREATE LANGUAGE lang1",
    "CREATE EXTENSION": "CREATE EXTENSION ext1",
    "CREATE TEXT SEARCH CONFIGURATION": "CREATE TEXT SEARCH CONFIGURATION cfg1 (PARSER = pg_catalog.default)",
    "CREATE TEXT SEARCH DICTIONARY": "CREATE TEXT SEARCH DICTIONARY dict1 (TEMPLATE = simple)",
    "CREATE TEXT SEARCH PARSER": "CREATE TEXT SEARCH PARSER parser1 (START = fn1, GETTOKEN = fn2, END = fn3, LEXTYPES = fn4)",
    "CREATE TEXT SEARCH TEMPLATE": "CREATE TEXT SEARCH TEMPLATE tmpl1 (LEXIZE = fn1)",
    "CREATE FOREIGN DATA WRAPPER": "CREATE FOREIGN DATA WRAPPER fdw1",
    "CREATE SERVER": "CREATE SERVER srv1 FOREIGN DATA WRAPPER fdw1",
    "CREATE USER MAPPING": "CREATE USER MAPPING FOR user1 SERVER srv1",
    "CREATE PUBLICATION": "CREATE PUBLICATION pub1 FOR ALL TABLES",
    "CREATE SUBSCRIPTION": "CREATE SUBSCRIPTION sub1 CONNECTION 'x' PUBLICATION pub1",
    "CREATE ROLE": "CREATE ROLE role1",
    "CREATE USER": "CREATE USER user1",
    "CREATE GROUP": "CREATE GROUP grp1",
    "CREATE POLICY": "CREATE POLICY pol1 ON t1 USING (true)",
}


@pytest.mark.parametrize(
    "sql", list(CREATE_STATEMENTS.values()), ids=list(CREATE_STATEMENTS.keys())
)
def test_create_statement_never_reaches_resolution_or_authorization(sql, compiler, policy):
    result = compiler.compile(sql, policy=policy)
    assert not result.ok, f"{sql!r} was accepted; it must be a pure read to pass"
    assert result.sql is None
    reached = codes(result) & POST_READONLY_CODES
    assert not reached, (
        f"{sql!r} was rejected for {reached}, which only resolve()/authorize() "
        "produce -- the read-only pass should have stopped it first"
    )
