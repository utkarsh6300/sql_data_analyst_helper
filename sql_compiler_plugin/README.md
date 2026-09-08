# sql-compiler-plugin

A plug-and-play SQL security compiler for Text-to-SQL systems.

It takes SQL an LLM produced, resolves every name in it against a real schema,
checks what it reads against what the caller is allowed to read, and hands back
regenerated SQL that is safe to execute. It has no opinion about who your users
are, no database connection, and no framework dependency — a host attaches
identity and a datasource; this package attaches the access control.

```python
from sql_compiler import Catalog, Policy, SqlCompiler

catalog = Catalog.from_ddl(project_ddl_statements)      # or Catalog.from_dict(...)
policy  = Policy.from_dict({
    "subject": "analyst-1",
    "tables": {
        "public.orders":    ["id", "customer_id", "amount"],
        "public.employees": {"columns": "*", "denied_columns": ["salary", "ssn"]},
    },
})

result = SqlCompiler(catalog=catalog).compile(llm_generated_sql, policy=policy)

if result.ok:
    run(result.sql)          # never run the model's original string
else:
    retry_with(result.repair_prompt())
```

## Documentation

| Document | Answers |
|---|---|
| [Architecture](docs/01-architecture.md) | How does it work? What does each file do? |
| [Security model](docs/02-security-model.md) | What does it stop, and what does it not? |
| [Integration](docs/03-integration.md) | How do I attach this to my application? |
| [Design decisions](docs/04-decisions.md) | Why is it built this way, and how do I change it? |

## The one rule

**Execute only `result.sql`, never the string the model produced.**

Validating one string and executing another is how a validator ends up
enforcing nothing. `result.sql` is rendered from the validated tree, and is
`None` whenever the query was rejected — so a caller who forgets to check `ok`
gets a `None`, not an unvalidated query.

## Pipeline

```
LLM SQL
   │
   ├─ 1. parse ─────────── one statement, or reject
   ├─ 2. read-only ─────── whole tree, deny-by-default
   ├─ 3. resolve ───────── qualify against the catalog, expand stars, map scopes
   ├─ 4. authorize ─────── tables, columns, functions
   └─ 5. generate ─────── safe SQL, rendered from the tree
```

Passes 1–3 are fatal and short-circuit. Pass 4 collects *every* violation, so a
repair loop learns all the problems in one round trip.

### Why resolution comes before authorization

An unqualified parse tree tells you a node is named `amount`. It does not tell
you which relation it belongs to. Authorizing that tree authorizes the wrong
names — which is the root cause of four separate bypasses, all closed by the
same phase:

| Query | Naive checker | Here |
|---|---|---|
| `SELECT * FROM employees` | `*` is a `Star`, not a `Column` — zero column checks run | expanded, every column checked |
| `SELECT p.ssn FROM employees p` | sees a column of relation `p` | `p` resolved to `employees` |
| `SELECT id FROM secret.orders` | `table.name == "orders"` — allowed | schema-qualified, denied |
| `WITH t AS (…) SELECT * FROM t` | `t` looks like an unauthorized table | `t` known to be a CTE; its body checked |

## What is enforced

**Read-only.** The whole tree is walked, not just the root. Postgres allows
data-modifying CTEs, so `WITH x AS (INSERT … RETURNING id) SELECT * FROM x` has
a `Select` root and still writes. Also caught: `SELECT … INTO`, `FOR UPDATE`,
and stacked statements (`SELECT 1; DROP TABLE orders`).

Anything sqlglot cannot parse becomes an `exp.Command` node, which is denied.
That is what keeps unmodelled syntax *denied* rather than *ignored*.

**Tables and columns.** Permissions are `(table, column)` pairs, always
schema-qualified. A flat column allow-list cannot express "`amount` on
`transactions` but not on `payroll`"; this one can. Denies always beat grants.
A table absent from the policy is denied — there is deliberately no wildcard
that grants unlisted tables.

**Functions.** Deny-by-default against an allow-list of analytic functions,
because a query needs no table at all to leak: `SELECT version()` and
`SELECT pg_read_file('/etc/passwd')` reference nothing the table and column
checks can see.

**Unknown objects.** A table or column missing from the catalog is rejected,
never inferred. No catalog at all is a hard failure, not a free pass.

## Filtering the schema before generation

Guarding only the compiler's output means the prompt still contains tables the
subject cannot read — a metadata leak, and a source of avoidable rejections.

```python
from sql_compiler import render_schema_prompt

prompt_schema = render_schema_prompt(catalog, policy)   # CREATE TABLE text
```

A test asserts that everything this advertises actually compiles, so the filter
cannot drift from the enforcement.

## What is **not** enforced — read this before deploying

This is a validation and fast-fail layer. **It is not a security boundary.**
One bug in a traversal, one code path that reaches the database without going
through it, and enforcement evaporates. The database is the only place where
enforcement is unconditional.

Back it with, at minimum:

- a read-only database role, with `REVOKE` on base tables and `GRANT SELECT`
  on secured views
- `SET TRANSACTION READ ONLY` and a `statement_timeout`
- PostgreSQL RLS policies keyed on a session variable set with `SET LOCAL`
  inside the transaction

Specifically out of scope in this version:

- **Row-level security.** `TablePolicy.row_filter` is recorded and *not acted
  on*. Row filtering belongs in the database. Appending `WHERE tenant_id = …`
  to every `SELECT` breaks on CTEs, derived tables and set operations, and
  fails open on joins where the column is ambiguous — the worst possible
  failure mode for a security predicate.
- **Inference attacks.** `SELECT AVG(salary) FROM employees WHERE id = 5` is
  blocked only because `salary` is denied. Where an aggregate *is* permitted, a
  narrow predicate turns it into row access. Defending that needs minimum-group
  -size rules, which no amount of node-type checking provides.
- **Query cost.** Nothing here stops an authorized cross join. Use `EXPLAIN`
  cost gating and an enforced `LIMIT`.
- **Result caching.** Caching by query hash across subjects with different
  permissions leaks across them. Key any cache by policy as well.
- **Error side channels.** Never return raw database errors to a user;
  `CASE WHEN (SELECT secret…) THEN 1/0 END` leaks through the message.

## API

| Object | Purpose |
|---|---|
| `Catalog.from_ddl(...)` / `.from_dict(...)` | the schema to resolve names against |
| `Policy.from_dict(...)` | what a subject may read; serializable both ways |
| `PolicyProvider` | implement in the host that owns identity |
| `SqlCompiler(catalog=, policy_provider=)` | stateless, shareable across requests |
| `.compile(sql, policy=|subject=)` | → `CompileResult` |
| `.compile_or_raise(...)` | → safe SQL, or raises `CompilationRejected` |
| `CompileResult` | `.ok` `.sql` `.violations` `.tables` `.columns` `.repair_prompt()` `.to_dict()` |
| `render_schema_prompt(catalog, policy)` | permission-filtered schema for the prompt |

`ConfigurationError` means the *host* is wired wrong (no catalog, unknown
subject). It is raised, never converted into a violation — reporting a
misconfiguration as "access denied" hides bugs.

### Notes on two design choices

**`SELECT *` is expanded and checked, not rejected.** Every expanded column is
authorized individually, and the query is rejected if any is denied. To refuse
`*` outright instead, reject on `exp.Star` before pass 3.

**`ALL_COLUMNS` is a standing grant.** A column added to the table later
becomes readable with no policy change to review. Prefer explicit column lists
on anything sensitive.

## Development

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest -q                  # everything
.venv/bin/python -m pytest -q -m unit          # one module or pass at a time
.venv/bin/python -m pytest -q -m integration   # end to end through every pass
.venv/bin/python -m pytest -q -m security      # the bypasses, on their own
.venv/bin/python -m pytest -q --cov            # with a coverage report
```

### Test layout

```
tests/
├── conftest.py                        shared catalog + policy fixtures
├── unit/                              no full pipeline; -m unit
│   ├── core/                          one file per top-level module
│   │   ├── test_names.py              identifier normalization, TableRef
│   │   ├── test_errors.py             violation codes and payload shape
│   │   ├── test_catalog.py            from_dict, from_ddl, lookup
│   │   ├── test_policy.py             grants, denies, serialization, providers
│   │   ├── test_schema_view.py        permission-filtered schema
│   │   └── test_compile_result.py     the result object and repair prompt
│   └── passes/                        one file per pass, in pipeline order
│       ├── test_parse.py              pass 1: exactly one statement
│       ├── test_readonly.py           pass 2: read-only enforcement
│       ├── test_resolve.py            pass 3: name resolution
│       └── test_authorize.py          pass 4: access checks
└── integration/                       drives SqlCompiler; -m integration
    ├── contract/                      the public contract, end to end
    │   ├── test_compiler.py           CompileResult, error surfaces, audit
    │   ├── test_accepted_queries.py   legitimate queries that must compile
    │   └── test_schema_prompt_contract.py  filter and compiler must agree
    └── security/                      also -m security
        ├── test_adversarial.py        the bypasses this package exists to close
        └── statement_sweep/           every non-SELECT PostgreSQL command,
            │                          grouped by leading keyword/verb
            ├── test_alter.py          all ALTER * variants
            ├── test_create.py         all CREATE * variants
            ├── test_drop.py           all DROP * variants
            ├── test_dml.py            INSERT/UPDATE/DELETE/MERGE/COPY/TRUNCATE/
            │                          SELECT INTO/VALUES; also the one positive
            │                          control proving a real SELECT still passes
            ├── test_transaction_control.py  ABORT/BEGIN/COMMIT/ROLLBACK/SAVEPOINT/...
            ├── test_dcl.py            GRANT/REVOKE/roles/SECURITY LABEL/COMMENT
            ├── test_session.py        SET/RESET/SHOW/DISCARD
            ├── test_cursors.py        PREPARE/EXECUTE/DECLARE/FETCH/MOVE/CLOSE
            └── test_misc_admin.py     everything else: LISTEN/NOTIFY, VACUUM/
                                       ANALYZE/REINDEX/CLUSTER, CALL/DO
```

`tests/integration/security/test_adversarial.py` holds the bypasses this
package exists to close. Add to it before adding features.

Two rules keep the split honest. A test in `unit/` must not construct a
`SqlCompiler` — if a case needs the whole pipeline to express, it belongs in
`integration/`. And `test_accepted_queries.py` exists because a compiler that
rejected everything would pass every other file in the suite.
