# Security model

## What is being defended against

The threat is not primarily a malicious user typing SQL. It is that **an LLM
generates SQL and no amount of prompting makes it trustworthy.** It will
hallucinate table names, reach for columns it was told not to touch, forget a
tenant filter, or faithfully translate a user's request into something that
happens to be a data breach. Prompt injection through the natural-language
input makes the "user is malicious" case real too, but the baseline problem is
that a probabilistic system is writing statements against your database.

So the model is: **treat generated SQL as untrusted input**, in the same way
you treat a form field.

## Where this sits — and where it does not

```
┌─────────────────────────────────────────────────────────────┐
│  Retrieval        filter the schema before it reaches the   │  ← reduces leaks
│                   prompt                    schema_view.py  │     AND rejections
├─────────────────────────────────────────────────────────────┤
│  Compiler         parse · read-only · resolve · authorize   │  ← THIS PACKAGE
│                   fast-fail + structured feedback           │     a filter, not a wall
├─────────────────────────────────────────────────────────────┤
│  Database         read-only role · REVOKE on base tables    │  ← the actual boundary
│                   GRANT on views · RLS · READ ONLY txn      │     NOT YET BUILT
│                   statement_timeout · read replica          │
└─────────────────────────────────────────────────────────────┘
```

**This package is the middle layer. The middle layer is not a security
boundary.**

An in-process AST rewriter is single-layer and bypassable: one bug in a
traversal, one unhandled node type, one code path that reaches the database
without going through here, and enforcement evaporates entirely. The database
is the only place where enforcement is unconditional, because it applies no
matter which code path arrived.

The right mental model is that a bug in this package should be a **correctness
incident, not a breach.** That is only true once the database layer exists.
Today it does not — see [What this does not defend
against](#what-this-does-not-defend-against).

## The bypass catalogue

These are the concrete attacks, each with a test in
[`tests/test_adversarial.py`](../tests/test_adversarial.py). The first five
defeated the naive implementation in [chat.txt](notes/chat.txt) — each passed
*all three* of its security checks.

### 1. Bare `SELECT *`

```sql
SELECT * FROM employees
```

A checker that iterates `exp.Column` nodes runs **zero** column checks here,
because `*` is an `exp.Star`. Every column, including `salary` and `ssn`,
arrives unexamined.

**Closed by:** resolution expands the star into explicit columns before
authorization, so each is checked individually.

### 2. Schema-qualified impersonation

```sql
SELECT id FROM secret.orders
```

`table.name` is `"orders"` for both `public.orders` and `secret.orders`. A
comparison against a bare name grants access to the wrong table.

**Closed by:** `TableRef` is always schema-qualified. There is no code path
that compares an unqualified name.

### 3. Non-`SELECT` statements

```sql
DROP TABLE orders
```

`exp.Table` nodes appear in DDL and DML too, so passing a table allow-list says
**nothing** about the statement being a read.

**Closed by:** the read-only pass, before authorization runs at all.

### 4. CTE names read as tables

```sql
WITH t AS (SELECT id FROM orders) SELECT * FROM t
```

`t` is an `exp.Table` node that is not on any allow-list — so a naive checker
**falsely rejects a safe query**, while a checker patched to ignore unknown
names now ignores real ones.

**Closed by:** `scope.sources` resolves `t` to a `Scope`, not a table. Its body
is authorized in its own scope.

### 5. Tableless queries

```sql
SELECT version()
SELECT pg_read_file('/etc/passwd')
```

No table, no column, no `FROM`. Invisible to both the table and column checks.

**Closed by:** deny-by-default function allow-list.

### 6. Writes hiding under a `SELECT` root

```sql
WITH x AS (INSERT INTO orders VALUES (1) RETURNING id) SELECT * FROM x
WITH d AS (DELETE FROM orders RETURNING id) SELECT * FROM d
SELECT id INTO new_table FROM orders
SELECT * FROM orders FOR UPDATE
```

Postgres data-modifying CTEs. Root node is `Select` in every case.

**Closed by:** walking the whole tree, not just the root.

### 7. Unmodelled syntax

```sql
VACUUM FULL
```

sqlglot does not fail here — it wraps unsupported syntax in an `exp.Command`
node. Allowing `Command` means **everything the parser does not understand is
permitted**.

**Closed by:** `Command` is denied. This is the entry that makes deny-by-default
real rather than aspirational.

### 8. Stacked statements

```sql
SELECT 1; DROP TABLE orders
```

Validate statement one, execute the original string.

**Closed by:** multi-statement input is rejected outright.

### 9. Reads that are not projections

```sql
SELECT id FROM employees WHERE salary > 100000     -- predicate
SELECT id FROM employees ORDER BY salary DESC      -- sort key
SELECT AVG(salary) FROM employees                  -- aggregate argument
SELECT salary AS not_a_salary FROM employees       -- renamed output
SELECT x.salary FROM (SELECT salary FROM employees) x   -- derived table
SELECT id FROM orders UNION ALL SELECT salary FROM employees  -- set branch
```

Reading a column in a predicate is still reading it — and supports
binary-search style extraction one comparison at a time. Renaming the output
does not change what was read.

**Closed by:** authorization runs over every resolved column reference in every
scope, not over the projection list.

### 10. Identifier case games

```sql
SELECT id FROM "Orders"
```

In Postgres `"Orders"` is a **different table** from `orders`. A validator that
lowercases everything would let a policy for one authorize the other.

**Closed by:** normalization is delegated to the dialect and preserves quoting.

### 11. Table-valued functions smuggling a relation into FROM

```sql
SELECT * FROM generate_series(1, 10)
SELECT * FROM jsonb_each('{}'::jsonb)
SELECT o.id FROM orders o JOIN generate_series(1, 10) AS g(n) ON o.id = g.n
```

sqlglot represents a set-returning function used directly as a relation the
same way it represents a real table (`exp.Table`), except `this` is a
function call rather than a plain identifier. Code that assumes every
`exp.Table` names a catalogued table therefore breaks on this shape.

**Closed by:** the scope-source loop in `resolve.py` catches the specific
failure this produces (`TableRef.from_table_node` raising
`ConfigurationError`) and reports it as `NAME_RESOLUTION_FAILED` rather than
letting the exception escape uncaught — which it previously did, with a
message that embedded a fragment of the query.

### 12. NATURAL JOIN's invisible column predicate

```sql
SELECT e.id FROM employees e NATURAL JOIN audit_log a
```

`NATURAL JOIN` implicitly joins on every column the two sides share by name.
sqlglot's `qualify()` does not expand that into a real `ON` condition — it
stays a bare `method='NATURAL'` marker with no `Column` nodes at all. If
`employees.salary` is denied but `audit_log` also has a column named
`salary`, Postgres executes `... ON e.salary = a.salary` at runtime — a read
of the denied column that never produces anything for this package's
column-authorization pass to see. Filtering the permitted side
(`WHERE a.salary = <guess>`) and observing which rows survive the natural
join is a full oracle for extracting the denied column's exact values,
one comparison at a time (the same class of attack as bypass #9, "Reads
that are not projections" — just through a join path instead of a
predicate).

**Closed by:** `NATURAL JOIN` is rejected unconditionally, wherever it
appears in the query (top level, inside a CTE, inside a derived table, inside
any branch of a set operation) — not reconstructed or verified, since there
is no way to do that safely from inside this package. The explicit
equivalents, `JOIN ... ON` and `JOIN ... USING (...)`, are unaffected and
already correctly authorize their columns.

## Parser differential

A validator whose parser disagrees with the database's parser is a known
vulnerability class — it is how WAF bypasses work. sqlglot's dialect coverage
is good, not exact.

The mitigation is structural: **only the regenerated SQL is executed.** The
database is handed sqlglot's own unambiguous interpretation — fully qualified,
explicitly quoted, stars expanded — rather than the model's original text. If
sqlglot misread the input, the database executes the misreading, which is a
correctness problem rather than a bypass.

Residual risk worth knowing about: Postgres `search_path` resolution of
unqualified names (mitigated by always emitting a schema), and dialect-specific
string escapes.

## Fail-closed by construction, not just by test coverage

Every pass is fallible against input nobody has specifically tested —
sqlglot adds syntax across releases, and dialects keep surprising shapes.
`compiler.py` wraps the resolve and authorize passes in a catch-all: any
exception neither pass was written to expect becomes an `INTERNAL_ERROR`
violation (action `NOT_REPAIRABLE`) instead of propagating out of
`SqlCompiler.compile()`. The exception's message is never included in the
violation — only its class name — because an internal error's message can
itself embed a fragment of the query, as the table-valued-function bug above
did before it was fixed.

This is a safety net, not a substitute for fixing root causes: an
`INTERNAL_ERROR` means a specific construct needs its own clean violation the
way table-valued functions now have one, and should be tracked as a bug when
it appears.

## Deny-by-default over-reach: structural syntax mistaken for functions

The bypass catalogue above is all under-restriction — things that were
wrongly *allowed*. This one runs the other way: things that were wrongly
*denied*, which matters just as much for a compiler meant to sit in front of
a real workload rather than a security demo.

`_collect_functions` in `resolve.py` walks every `exp.Func` node and denies
it unless allow-listed. sqlglot's class hierarchy models several pieces of
ordinary, unavoidable SQL syntax as `exp.Func` subclasses purely for parsing
convenience:

```sql
SELECT id FROM orders WHERE EXISTS (SELECT 1 FROM customers)   -- exp.Exists
SELECT id FROM orders WHERE amount > 1 AND amount < 100         -- exp.And
SELECT CASE WHEN amount > 1 THEN 1 ELSE 0 END FROM orders        -- exp.Case
```

`exp.Exists` is, structurally, both an `exp.Func` and an
`exp.SubqueryPredicate`; `exp.And`/`exp.Or`/`exp.Xor` subclass
`exp.Connector`; `exp.Case`/`exp.If` have no distinguishing base beyond
`Func` itself. None of them is a callable a policy should have to
allow-list — a query cannot avoid `AND`, and any correlated subquery or
semi-join needs `EXISTS`. Before this was caught, **every query using
`EXISTS`, `NOT EXISTS`, `CASE WHEN`, or a bare `AND`/`OR` in a predicate was
rejected outright** as an unauthorized function call, regardless of whether
anything it actually read was unauthorized. That is close to "rejects every
non-trivial query."

**Why it went undetected:** the one existing test exercising `EXISTS`
(`test_denied_column_in_a_correlated_subquery_is_caught`) asserted only
`violations[0].column`, never the full violation set — so a spurious
`FUNCTION_NOT_ALLOWED` riding alongside the expected `COLUMN_ACCESS_DENIED`
passed silently. Asserting the complete `codes(result)` set, not just the
first violation, is now the pattern to follow when a test's whole point is
that exactly one thing is wrong.

**Closed by:** nodes matching `_NON_FUNCTION_SYNTAX_TYPES`
(`Connector`, `SubqueryPredicate`, `Case`, `If`, resolved by name the same
version-safe way `readonly.py`'s deny list is) are excluded from function
collection entirely, so they are invisible to the allow-list rather than
failing it. A genuine function call — including a dangerous one like
`pg_read_file` — is unaffected; only structural syntax is excluded.

## Row-level security (defence in depth, not the boundary)

`TablePolicy.row_filter` is enforced by `passes/rowsec.py`, which runs after
authorization succeeds. Every *occurrence* of a base table (one per FROM/JOIN
item, tracked separately from any same-named CTE) is replaced with a secured
derived table:

```sql
-- policy: row_filter="tenant_id = current_setting('app.tenant_id')::int"
FROM orders o
-- becomes
FROM (SELECT * FROM orders WHERE tenant_id = current_setting('app.tenant_id')::int) AS o
```

This is the shape [chat.txt](notes/chat.txt) originally proposed, done the way
[chat2-1.txt](notes/chat2-1.txt) shows it has to be done to actually work:

- The filter travels with the table reference itself, so it lands inside a
  CTE's own definition rather than an outer `SELECT` that never chose the
  filtered column — the naive "append `WHERE` to the outer statement"
  approach produces `SELECT * FROM high_value_orders WHERE tenant_id = 123`
  for a CTE that never selected `tenant_id`, a **broken query**.
- A self-join (`FROM orders a JOIN orders_archive b`) gets one filtered copy
  per occurrence, so neither side is left unfiltered the way an unqualified
  `tenant_id` appended once would be — silently binding to one relation, or
  erroring as ambiguous.
- The predicate is parsed with `sqlglot.parse` into an AST node and
  re-emitted, never built as a string and re-parsed, so there is no channel
  for injection inside the anti-injection layer.

**It is still not the boundary.** An in-process rewriter is bypassed by any
code path that reaches the database without going through it; Postgres RLS is
unconditional regardless of caller. Treat `row_filter` as a second layer
behind RLS, not a replacement for it — see
[the minimum database layer to add next](#the-minimum-database-layer-to-add-next).
A table with no `row_filter` configured is exactly as exposed as it was
before this pass existed: nothing fills in a filter the policy did not ask
for.

## What this does **not** defend against

Take this section literally before putting the package in front of real data.

### Inference attacks

```sql
SELECT AVG(salary) FROM employees WHERE employee_id = 123
```

Blocked here only because `salary` itself is denied. Wherever an aggregate *is*
permitted, a sufficiently narrow predicate turns aggregate access into row
access. Defending this needs minimum-group-size / k-anonymity rules — a
semantic policy that no amount of node-type checking provides.

Related: `SELECT COUNT(*) FROM orders` is permitted on any granted table and
discloses the row count.

### Query cost

Nothing here stops an authorized `CROSS JOIN` across three large tables. Needs
`EXPLAIN` cost gating, an enforced `LIMIT`, and `statement_timeout`.

### Error and timing side channels

```sql
SELECT CASE WHEN (SELECT secret…) THEN 1/0 END
```

leaks through the exception message. **Never return raw database errors to a
user.** This package's own violations are structured and never echo query text,
but it cannot control what your driver surfaces.

### Result caching

SQL or results cached by query hash and reused across subjects with different
permissions leaks across them. Key any cache by policy identity as well as by
query.

### Prompt injection via returned data

Rows returned to the model may contain text that the model treats as
instructions. Out of scope entirely.

### Audit logging

`CompileResult` exposes `.tables`, `.columns` and `.subject` for exactly this,
including on rejection — but **writing the log is the host's job.** An access
denial is precisely the event an incident review needs a record of.

## The minimum database layer to add next

This is Phase 3 in [plan.txt](notes/plan.txt), and it is what turns this package
from "the security" into "one layer of the security":

```sql
-- a role that cannot write, regardless of what SQL reaches it
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM analyst_role;
GRANT SELECT ON secured_orders_view TO analyst_role;

-- row security enforced by the database, not the application
ALTER TABLE orders ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON orders
  USING (tenant_id = current_setting('app.tenant_id')::uuid);
```

```python
# per request, inside the transaction
SET LOCAL app.tenant_id = '…';
SET TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '30s';
```

With that in place, a bug in this package becomes a correctness incident. Until
then, it is a breach.
